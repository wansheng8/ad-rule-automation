#!/usr/bin/env python3
"""
广告规则自动化处理系统 - 最终优化版
GitHub Actions专用，解决超时和推送问题
"""

import os
import sys
import re
import time
import json
import signal
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.settings import get_all_sources, Config
except ImportError as e:
    print(f"❌ 导入配置失败: {e}")
    sys.exit(1)

# 编译正则表达式
DOMAIN_PATTERN = re.compile(r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$')

# 超时控制
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("处理超时")

signal.signal(signal.SIGALRM, timeout_handler)

def get_shanghai_time():
    try:
        return datetime.now(timezone(timedelta(hours=8)))
    except:
        return datetime.now()

def get_time_string():
    return get_shanghai_time().strftime('%Y-%m-%d %H:%M:%S')

class FastRuleFetcher:
    def __init__(self):
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            self.requests = requests
            self.HTTPAdapter = HTTPAdapter
            self.Retry = Retry
        except ImportError:
            print("❌ 请安装: pip install requests")
            sys.exit(1)
        
        self.session = self._create_session()
        self.cache_dir = Path(Config.CACHE_DIR)
        self.cache_dir.mkdir(exist_ok=True)
        
        self.stats = {
            'total': 0, 'success': 0, 'cached': 0,
            'failed': 0, 'timeout': 0
        }
    
    def _create_session(self):
        session = self.requests.Session()
        retry = self.Retry(total=1, backoff_factor=0.5)
        adapter = self.HTTPAdapter(
            max_retries=retry,
            pool_connections=5,
            pool_maxsize=5
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        session.headers.update({
            'User-Agent': Config.get_user_agent(),
            'Accept': 'text/plain',
            'Accept-Encoding': 'gzip',
            'Connection': 'close'
        })
        
        return session
    
    def _get_cache_path(self, url: str) -> Path:
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"cache_{url_hash}.txt"
    
    def fetch_url(self, url: str) -> Tuple[bool, Optional[str], int]:
        cache_file = self._get_cache_path(url)
        
        # 检查缓存
        if Config.CACHE_ENABLED and cache_file.exists():
            cache_age = time.time() - cache_file.stat().st_mtime
            if cache_age < Config.CACHE_EXPIRE_HOURS * 3600:
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        lines = content.count('\n')
                        self.stats['cached'] += 1
                        self.stats['success'] += 1
                        return True, content, lines
                except:
                    pass
        
        # 网络请求
        try:
            response = self.session.get(url, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            content = response.text
            lines = content.count('\n') + 1
            
            # 保存缓存
            if Config.CACHE_ENABLED:
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                except:
                    pass
            
            self.stats['success'] += 1
            return True, content, lines
            
        except Exception as e:
            self.stats['failed'] += 1
            return False, None, 0

class SimpleOptimizer:
    @staticmethod
    def deduplicate(rules: List[str]) -> List[str]:
        if not rules:
            return []
        
        # 快速去重
        seen = set()
        unique = []
        for rule in rules:
            if rule not in seen:
                seen.add(rule)
                unique.append(rule)
        
        # 域名去重（仅对大量数据）
        if len(unique) > 10000:
            domain_map = {}
            final = []
            for rule in unique:
                domain = None
                if rule.startswith('||') and '^' in rule:
                    domain = rule[2:].split('^')[0]
                elif rule.startswith(('0.0.0.0 ', '127.0.0.1 ')):
                    parts = rule.split()
                    if len(parts) >= 2:
                        domain = parts[1]
                
                if domain:
                    if domain not in domain_map:
                        domain_map[domain] = rule
                        final.append(rule)
                else:
                    final.append(rule)
            return final
        
        return unique
    
    @staticmethod
    def filter_rules(rules: List[str]) -> List[str]:
        if not rules:
            return []
        
        adblock = []
        hosts = []
        domains = []
        
        for rule in rules:
            if len(rule) > 500:
                continue
            
            if rule.startswith('||') or '##' in rule or rule.startswith('|'):
                adblock.append(rule)
            elif rule.startswith('0.0.0.0') or rule.startswith('127.0.0.1'):
                hosts.append(rule)
            elif DOMAIN_PATTERN.match(rule):
                domains.append(rule)
        
        result = []
        result.extend(sorted(adblock)[:Config.MAX_RULES_PER_TYPE])
        result.extend(sorted(hosts)[:Config.MAX_RULES_PER_TYPE//2])
        result.extend(sorted(domains)[:Config.MAX_RULES_PER_TYPE//2])
        
        return result[:Config.MAX_TOTAL_RULES]

class RuleProcessor:
    def __init__(self):
        self.fetcher = FastRuleFetcher()
        self.optimizer = SimpleOptimizer()
        self.all_rules = []
        
        try:
            sources = get_all_sources()
            self.sources = sources[:80] if len(sources) > 80 else sources
        except:
            self.sources = [
                "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
                "https://easylist.to/easylist/easylist.txt",
                "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            ]
        
        self.start_time = time.time()
        self.stats = {
            'total_sources': len(self.sources),
            'total_rules': 0,
            'final_rules': 0,
            'duration': 0,
            'status': 'unknown'
        }
    
    def check_timeout(self):
        elapsed = time.time() - self.start_time
        if elapsed > Config.TIMEOUT_FORCE_STOP:
            print(f"⏰ 超时保护: {elapsed:.0f}秒")
            return True
        return False
    
    def process(self) -> bool:
        print("=" * 60)
        print("🚀 广告规则处理系统")
        print(f"📅 时间: {get_time_string()}")
        print(f"📊 规则源: {self.stats['total_sources']} 个")
        print("=" * 60)
        
        signal.alarm(Config.TIMEOUT_FORCE_STOP + 60)
        
        try:
            # 1. 下载
            print(f"\n📥 下载规则源")
            contents = self._download_sources()
            if self.check_timeout():
                return False
            
            # 2. 解析
            print(f"\n🔍 解析规则")
            self._parse_rules(contents)
            if self.check_timeout():
                return False
            
            # 3. 优化
            print(f"\n⚡ 优化规则")
            final_rules = self._optimize_rules()
            if self.check_timeout():
                return False
            
            # 4. 保存
            print(f"\n💾 保存结果")
            success = self._save_results(final_rules)
            
            self._generate_report(success)
            signal.alarm(0)
            return success
            
        except TimeoutException:
            print("\n⏰ 超时，保存部分结果")
            self._save_partial()
            self.stats['status'] = 'timeout'
            return False
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            self.stats['status'] = 'error'
            return False
    
    def _download_sources(self) -> Dict[str, str]:
        contents = {}
        max_workers = min(Config.MAX_WORKERS, 4)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetcher.fetch_url, url): url 
                      for url in self.sources}
            
            completed = 0
            for future in as_completed(futures):
                url = futures[future]
                success, content, lines = future.result()
                completed += 1
                
                if success and content:
                    contents[url] = content
                    if completed % 10 == 0:
                        print(f"  [{completed}/{len(self.sources)}] {lines} 行")
        
        print(f"✅ 下载: {len(contents)}成功, {self.fetcher.stats['failed']}失败")
        return contents
    
    def _parse_rules(self, contents: Dict[str, str]):
        count = 0
        for content in contents.values():
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if not line or line[0] in '!#':
                    continue
                
                if len(line) < 500:
                    self.all_rules.append(line)
                    count += 1
                
                if count % 50000 == 0 and self.check_timeout():
                    return
        
        self.stats['total_rules'] = count
        print(f"✅ 解析: {count:,} 条规则")
    
    def _optimize_rules(self) -> List[str]:
        print(f"  优化 {len(self.all_rules):,} 条规则...")
        
        # 去重
        unique = self.optimizer.deduplicate(self.all_rules)
        print(f"  去重: {len(unique):,} 条")
        
        # 过滤
        final = self.optimizer.filter_rules(unique)
        self.stats['final_rules'] = len(final)
        print(f"  过滤: {len(final):,} 条")
        
        return final
    
    def _save_results(self, rules: List[str]) -> bool:
        try:
            os.makedirs("dist", exist_ok=True)
            os.makedirs("stats", exist_ok=True)
            
            current_time = get_time_string()
            
            # 分类
            adblock = [r for r in rules if r.startswith('||') or '##' in r or r.startswith('|')]
            hosts = [r for r in rules if r.startswith('0.0.0.0') or r.startswith('127.0.0.1')]
            domains = [r for r in rules if DOMAIN_PATTERN.match(r)]
            
            # 保存Adblock
            if adblock:
                with open("dist/Adblock.txt", 'w', encoding='utf-8') as f:
                    f.write(f"""! Adblock规则
! 时间: {current_time}
! 数量: {len(adblock):,}
! 项目: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
!

""")
                    for i in range(0, len(adblock), 10000):
                        f.write('\n'.join(adblock[i:i+10000]) + '\n')
                print(f"  ✅ Adblock: {len(adblock):,} 条")
            
            # 保存Hosts
            if hosts:
                with open("dist/hosts.txt", 'w', encoding='utf-8') as f:
                    f.write(f"""# Hosts规则
# 时间: {current_time}
# 数量: {len(hosts):,}
# 项目: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
#

""")
                    for i in range(0, len(hosts), 10000):
                        f.write('\n'.join(hosts[i:i+10000]) + '\n')
                print(f"  ✅ Hosts: {len(hosts):,} 条")
            
            # 保存域名
            if domains:
                with open("dist/Domains.txt", 'w', encoding='utf-8') as f:
                    f.write(f"""# 域名列表
# 时间: {current_time}
# 数量: {len(domains):,}
# 项目: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
#

""")
                    for domain in sorted(domains):
                        f.write(f"{domain}\n")
                print(f"  ✅ 域名: {len(domains):,} 个")
            
            return True
            
        except Exception as e:
            print(f"  ❌ 保存失败: {e}")
            return False
    
    def _save_partial(self):
        try:
            if self.all_rules:
                sample = self.all_rules[:50000]
                optimized = self.optimizer.deduplicate(sample)
                
                os.makedirs("dist", exist_ok=True)
                with open("dist/Adblock_partial.txt", 'w', encoding='utf-8') as f:
                    f.write(f"! 部分规则 (超时)\n")
                    f.write(f"! 时间: {get_time_string()}\n")
                    f.write(f"! 数量: {len(optimized):,}\n!\n\n")
                    f.write('\n'.join(optimized[:20000]))
                
                print(f"  ⚠️  保存部分规则")
        except:
            pass
    
    def _generate_report(self, success: bool):
        try:
            elapsed = time.time() - self.start_time
            self.stats['duration'] = round(elapsed, 2)
            self.stats['status'] = 'success' if success else 'partial'
            
            report = {
                'timestamp': get_time_string(),
                'stats': self.stats,
                'fetcher_stats': self.fetcher.stats,
                'config': {
                    'max_workers': Config.MAX_WORKERS,
                    'timeout': Config.REQUEST_TIMEOUT,
                    'cache_enabled': Config.CACHE_ENABLED
                }
            }
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            with open(f"stats/report_{timestamp}.json", 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            print(f"\n{'='*60}")
            print(f"{'✅ 成功' if success else '⚠️  部分完成'}")
            print(f"{'='*60}")
            print(f"⏱️  耗时: {elapsed:.1f}秒")
            print(f"📊 原始: {self.stats['total_rules']:,} 条")
            print(f"📊 最终: {self.stats['final_rules']:,} 条")
            print(f"📥 下载: {self.fetcher.stats['success']}成功 "
                  f"({self.fetcher.stats['cached']}缓存)")
            
        except Exception as e:
            print(f"  ⚠️  报告失败: {e}")

def main():
    print("🔄 启动规则处理")
    
    def interrupt_handler(sig, frame):
        print("\n🛑 用户中断")
        sys.exit(130)
    
    signal.signal(signal.SIGINT, interrupt_handler)
    
    try:
        processor = RuleProcessor()
        success = processor.process()
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ 系统错误: {e}")
        return 1
    finally:
        signal.alarm(0)

if __name__ == "__main__":
    sys.exit(main())
