#!/usr/bin/env python3
"""
广告规则自动化处理系统 - 超强优化版
专为GitHub Actions环境优化，解决超时问题
"""

import os
import sys
import re
import time
import json
import signal
import pickle
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.settings import get_all_sources, Config
except ImportError as e:
    print(f"❌ 导入配置失败: {e}")
    sys.exit(1)

# 编译正则表达式（性能优化）
DOMAIN_PATTERN = re.compile(r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$')
HOSTS_PATTERN = re.compile(r'^(0\.0\.0\.0|127\.0\.0\.1)\s+(\S+)')
ADBLOCK_PATTERN = re.compile(r'^\|\|([a-zA-Z0-9.*-]+)\^')

# === 全局超时控制 ===
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("处理超时，已强制停止")

signal.signal(signal.SIGALRM, timeout_handler)

def get_shanghai_time() -> datetime:
    """获取当前上海时间"""
    try:
        shanghai_tz = timezone(timedelta(hours=8))
        return datetime.now(shanghai_tz)
    except:
        return datetime.now()

def get_time_string() -> str:
    return get_shanghai_time().strftime('%Y-%m-%d %H:%M:%S')

class UltraFastRuleFetcher:
    """极速规则获取器"""
    
    def __init__(self):
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            self.requests = requests
            self.HTTPAdapter = HTTPAdapter
            self.Retry = Retry
        except ImportError as e:
            print(f"❌ 导入requests失败: {e}")
            print("💡 请运行: pip install requests")
            sys.exit(1)
            
        self.session = self._create_session()
        self.stats = {
            'total': 0,
            'success': 0,
            'cached': 0,
            'failed': 0,
            'timeout': 0
        }
        self.cache_dir = Path(Config.CACHE_DIR)
        self.cache_dir.mkdir(exist_ok=True)
        
    def _create_session(self):
        """创建超快速会话"""
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
    
    def _get_cache_key(self, url: str) -> Path:
        return self.cache_dir / f"cache_{hashlib.md5(url.encode()).hexdigest()}.txt"
    
    def fetch_with_cache(self, url: str) -> Tuple[bool, Optional[str], int]:
        """带缓存的获取（极速版）"""
        cache_file = self._get_cache_key(url)
        
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
        
        # 网络获取（带严格超时）
        try:
            signal.alarm(Config.REQUEST_TIMEOUT + 5)  # 设置系统级超时
            response = self.session.get(
                url, 
                timeout=Config.REQUEST_TIMEOUT,
                stream=False  # 禁用流式，加快小文件
            )
            signal.alarm(0)  # 取消超时
            
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
            
        except TimeoutError:
            self.stats['timeout'] += 1
            return False, None, 0
        except Exception as e:
            self.stats['failed'] += 1
            return False, None, 0
        finally:
            signal.alarm(0)

class FastRuleOptimizer:
    """极速规则优化器"""
    
    @staticmethod
    def simple_deduplicate(rules: List[str]) -> List[str]:
        """极简去重（性能优先）"""
        if not rules:
            return []
        
        # 第一步：快速去重
        seen = set()
        unique_rules = []
        
        for rule in rules:
            if rule not in seen:
                seen.add(rule)
                unique_rules.append(rule)
        
        # 第二步：简单域名去重（仅对Adblock规则）
        if len(unique_rules) > 10000:  # 只有规则多时才启用
            domain_map = {}
            final_rules = []
            
            for rule in unique_rules:
                # 快速提取域名
                domain = None
                if rule.startswith('||') and '^' in rule:
                    domain = rule[2:].split('^')[0]
                elif rule.startswith('0.0.0.0 ') or rule.startswith('127.0.0.1 '):
                    parts = rule.split()
                    if len(parts) >= 2:
                        domain = parts[1]
                
                if domain:
                    if domain not in domain_map:
                        domain_map[domain] = rule
                        final_rules.append(rule)
                else:
                    final_rules.append(rule)
            
            return final_rules
        
        return unique_rules
    
    @staticmethod
    def filter_and_sort_rules(rules: List[str]) -> List[str]:
        """过滤和排序规则"""
        if not rules:
            return []
        
        # 按规则类型分组
        adblock_rules = []
        hosts_rules = []
        domain_rules = []
        
        for rule in rules:
            rule_lower = rule.lower()
            
            # 跳过明显无效的规则
            if len(rule) > 500:  # 过长的规则
                continue
            if ' ' in rule and not rule.startswith(('0.0.0.0', '127.0.0.1')):
                continue
            
            # 分类
            if rule.startswith('||') or '##' in rule or rule.startswith('|'):
                adblock_rules.append(rule)
            elif rule.startswith('0.0.0.0') or rule.startswith('127.0.0.1'):
                hosts_rules.append(rule)
            elif DOMAIN_PATTERN.match(rule):
                domain_rules.append(rule)
        
        # 合并并限制数量
        all_rules = []
        all_rules.extend(sorted(adblock_rules)[:Config.MAX_RULES_PER_TYPE])
        all_rules.extend(sorted(hosts_rules)[:Config.MAX_RULES_PER_TYPE//2])
        all_rules.extend(sorted(domain_rules)[:Config.MAX_RULES_PER_TYPE//2])
        
        return all_rules[:Config.MAX_TOTAL_RULES]

class SmartRuleProcessor:
    """智能规则处理器（解决超时问题）"""
    
    def __init__(self):
        self.fetcher = UltraFastRuleFetcher()
        self.optimizer = FastRuleOptimizer()
        self.all_rules = []
        
        # 加载规则源（自动过滤）
        try:
            sources = get_all_sources()
            self.rule_sources = sources[:80] if len(sources) > 80 else sources  # 最多80个
        except:
            self.rule_sources = [
                "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
                "https://easylist.to/easylist/easylist.txt",
                "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            ]
        
        self.start_time = time.time()
        self.stats = {
            'total_sources': len(self.rule_sources),
            'processed_sources': 0,
            'total_rules': 0,
            'final_rules': 0,
            'duration': 0,
            'status': 'unknown'
        }
    
    def check_timeout(self):
        """检查是否超时"""
        elapsed = time.time() - self.start_time
        if elapsed > Config.TIMEOUT_FORCE_STOP:
            print(f"⏰ 超时保护触发：已运行 {elapsed:.0f} 秒，强制停止")
            return True
        return False
    
    def process(self) -> bool:
        """主处理流程"""
        print("=" * 70)
        print("🚀 广告规则处理系统 - 超强优化版")
        print(f"📅 开始时间: {get_time_string()}")
        print(f"📊 规则源: {self.stats['total_sources']} 个")
        print(f"⚙️  配置: 并发={Config.MAX_WORKERS}, 超时={Config.REQUEST_TIMEOUT}s")
        print("=" * 70)
        
        # 设置总超时
        signal.alarm(Config.TIMEOUT_FORCE_STOP + 60)
        
        try:
            # 阶段1：并行下载（严格控制）
            print(f"\n📥 阶段1: 下载规则源")
            contents = self._fetch_all_sources()
            
            if self.check_timeout():
                return False
            
            # 阶段2：快速解析
            print(f"\n🔍 阶段2: 解析规则")
            self._parse_contents(contents)
            
            if self.check_timeout():
                return False
            
            # 阶段3：极速优化
            print(f"\n⚡ 阶段3: 优化规则")
            final_rules = self._optimize_rules()
            
            if self.check_timeout():
                return False
            
            # 阶段4：保存结果
            print(f"\n💾 阶段4: 保存结果")
            success = self._save_results(final_rules)
            
            # 生成报告
            self._generate_report(success)
            
            signal.alarm(0)  # 取消超时
            return success
            
        except TimeoutException:
            print("\n⏰ 处理超时，保存已处理的数据...")
            self._save_partial_results()
            self.stats['status'] = 'timeout'
            return False
        except Exception as e:
            print(f"\n❌ 处理异常: {e}")
            self.stats['status'] = 'error'
            return False
    
    def _fetch_all_sources(self) -> Dict[str, str]:
        """并行获取所有源"""
        contents = {}
        max_workers = min(Config.MAX_WORKERS, 4)  # 最大4个并发
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetcher.fetch_with_cache, url): url 
                      for url in self.rule_sources}
            
            completed = 0
            batch_size = 10
            
            for future in as_completed(futures):
                url = futures[future]
                success, content, lines = future.result()
                
                completed += 1
                
                if success and content:
                    contents[url] = content
                    status = "缓存" if self.fetcher.stats['cached'] > 0 and \
                        completed <= self.fetcher.stats['cached'] else "下载"
                    
                    if completed % batch_size == 0 or completed == len(self.rule_sources):
                        print(f"  [{completed}/{len(self.rule_sources)}] {status} {lines:6d} 行")
                else:
                    if completed % batch_size == 0 or completed == len(self.rule_sources):
                        print(f"  [{completed}/{len(self.rule_sources)}] 失败")
                
                # 定期检查超时
                if completed % 20 == 0 and self.check_timeout():
                    break
        
        print(f"✅ 下载完成: {len(contents)}成功, {self.fetcher.stats['failed']}失败, "
              f"{self.fetcher.stats['cached']}缓存")
        return contents
    
    def _parse_contents(self, contents: Dict[str, str]):
        """解析所有内容"""
        rule_count = 0
        batch_size = 50000
        
        for url, content in contents.items():
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if not line or line[0] in '!#':
                    continue
                
                # 快速分类
                if len(line) < 500:  # 跳过过长的行
                    self.all_rules.append(line)
                    rule_count += 1
                
                # 定期检查超时和数量限制
                if rule_count % batch_size == 0:
                    print(f"  已解析 {rule_count:,} 条规则")
                    if self.check_timeout():
                        return
                    if rule_count > Config.MAX_TOTAL_RULES * 2:
                        print(f"⚠️  规则数量过多，提前停止解析")
                        return
        
        self.stats['total_rules'] = rule_count
        print(f"✅ 解析完成: {rule_count:,} 条原始规则")
    
    def _optimize_rules(self) -> List[str]:
        """优化规则"""
        print(f"  开始优化 {len(self.all_rules):,} 条规则...")
        
        # 第一步：快速去重
        unique_start = time.time()
        unique_rules = self.optimizer.simple_deduplicate(self.all_rules)
        unique_time = time.time() - unique_start
        print(f"  去重完成: {len(unique_rules):,} 条 (耗时: {unique_time:.1f}s)")
        
        if self.check_timeout():
            return unique_rules[:10000]  # 返回部分结果
        
        # 第二步：过滤和排序
        filter_start = time.time()
        final_rules = self.optimizer.filter_and_sort_rules(unique_rules)
        filter_time = time.time() - filter_start
        
        self.stats['final_rules'] = len(final_rules)
        print(f"  过滤完成: {len(final_rules):,} 条 (耗时: {filter_time:.1f}s)")
        
        return final_rules
    
    def _save_results(self, rules: List[str]) -> bool:
        """保存结果"""
        try:
            os.makedirs("dist", exist_ok=True)
            os.makedirs("stats", exist_ok=True)
            
            current_time = get_time_string()
            total_rules = len(rules)
            
            # 智能分割规则
            adblock_rules = []
            hosts_rules = []
            domain_rules = []
            
            for rule in rules:
                if rule.startswith('||') or '##' in rule or rule.startswith('|'):
                    adblock_rules.append(rule)
                elif rule.startswith('0.0.0.0') or rule.startswith('127.0.0.1'):
                    hosts_rules.append(rule)
                else:
                    domain_rules.append(rule)
            
            # 保存Adblock规则
            if adblock_rules:
                with open("dist/Adblock.txt", 'w', encoding='utf-8') as f:
                    f.write(f"""! Adblock规则 - 超强优化版
! 生成时间: {current_time}
! 规则数量: {len(adblock_rules):,}
! 项目地址: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
!

""")
                    # 批量写入
                    for i in range(0, len(adblock_rules), 10000):
                        batch = adblock_rules[i:i+10000]
                        f.write('\n'.join(batch) + '\n')
                
                print(f"  ✅ Adblock规则: {len(adblock_rules):,} 条")
            
            # 保存Hosts规则
            if hosts_rules:
                with open("dist/hosts.txt", 'w', encoding='utf-8') as f:
                    f.write(f"""# Hosts规则 - 超强优化版
# 生成时间: {current_time}
# 规则数量: {len(hosts_rules):,}
# 项目地址: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
#

""")
                    for i in range(0, len(hosts_rules), 10000):
                        batch = hosts_rules[i:i+10000]
                        f.write('\n'.join(batch) + '\n')
                
                print(f"  ✅ Hosts规则: {len(hosts_rules):,} 条")
            
            # 保存域名规则
            if domain_rules:
                with open("dist/Domains.txt", 'w', encoding='utf-8') as f:
                    f.write(f"""# 域名规则 - 超强优化版
# 生成时间: {current_time}
# 域名数量: {len(domain_rules):,}
# 项目地址: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
#

""")
                    for i in range(0, len(domain_rules), 10000):
                        batch = domain_rules[i:i+10000]
                        f.write('\n'.join(batch) + '\n')
                
                print(f"  ✅ 域名规则: {len(domain_rules):,} 条")
            
            print(f"  💾 总计保存: {total_rules:,} 条规则")
            return True
            
        except Exception as e:
            print(f"  ❌ 保存失败: {e}")
            return False
    
    def _save_partial_results(self):
        """保存部分结果（超时情况下）"""
        try:
            if self.all_rules:
                # 只保存前5万条规则
                sample_rules = self.all_rules[:50000]
                optimized = self.optimizer.simple_deduplicate(sample_rules)
                
                os.makedirs("dist", exist_ok=True)
                with open("dist/Adblock_partial.txt", 'w', encoding='utf-8') as f:
                    f.write(f"! 部分规则 (超时保护触发)\n")
                    f.write(f"! 生成时间: {get_time_string()}\n")
                    f.write(f"! 规则数量: {len(optimized):,}\n!\n\n")
                    f.write('\n'.join(optimized[:20000]))
                
                print(f"  ⚠️  已保存部分规则 ({len(optimized):,} 条)")
        except:
            pass
    
    def _generate_report(self, success: bool):
        """生成报告"""
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
                    'cache_enabled': Config.CACHE_ENABLED,
                    'max_rules': Config.MAX_TOTAL_RULES
                }
            }
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            with open(f"stats/report_{timestamp}.json", 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            # 简版控制台报告
            print(f"\n{'='*70}")
            print(f"{'✅ 处理成功' if success else '⚠️  部分完成'}")
            print(f"{'='*70}")
            print(f"⏱️  总耗时: {elapsed:.1f} 秒")
            print(f"📊 原始规则: {self.stats['total_rules']:,} 条")
            print(f"📊 最终规则: {self.stats['final_rules']:,} 条")
            print(f"📥 下载统计: {self.fetcher.stats['success']}成功 "
                  f"({self.fetcher.stats['cached']}缓存) / "
                  f"{self.fetcher.stats['failed']}失败 / "
                  f"{self.fetcher.stats['timeout']}超时")
            
        except Exception as e:
            print(f"  ⚠️  报告生成失败: {e}")

def main():
    """主函数"""
    print("🔄 启动广告规则处理系统")
    
    # 设置Ctrl+C处理
    def interrupt_handler(sig, frame):
        print("\n\n🛑 用户中断，保存当前进度...")
        sys.exit(130)
    
    signal.signal(signal.SIGINT, interrupt_handler)
    
    try:
        processor = SmartRuleProcessor()
        success = processor.process()
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ 系统错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        signal.alarm(0)  # 确保取消所有超时

if __name__ == "__main__":
    sys.exit(main())
