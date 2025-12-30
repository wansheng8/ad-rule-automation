#!/usr/bin/env python3
"""
智能广告规则处理系统 - 智能去重与优化版
生成 Adblock.txt, hosts.txt, Domains.txt 三种格式的规则，带智能去重和优化
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.settings import get_all_sources, Config
except ImportError as e:
    print(f"❌ 导入配置失败: {e}")
    print("⚠️  请确保 config/settings.py 存在且格式正确")
    sys.exit(1)

import re
import time
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("错误：请先安装依赖：pip install requests")
    sys.exit(1)

def get_shanghai_time() -> datetime:
    """获取当前上海时间 (UTC+8)"""
    try:
        shanghai_tz = timezone(timedelta(hours=8))
        utc_now = datetime.now(timezone.utc)
        return utc_now.astimezone(shanghai_tz)
    except Exception:
        return datetime.now()

def get_time_string() -> str:
    """获取格式化的上海时间字符串"""
    return get_shanghai_time().strftime('%Y-%m-%d %H:%M:%S')

class RuleFetcher:
    """规则获取器"""
    
    def __init__(self):
        self.session = self._create_session()
        self.stats = {
            'total_sources': 0,
            'successful': 0,
            'failed': 0,
            'source_details': {}
        }
        
    def _create_session(self):
        """创建HTTP会话"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            'User-Agent': 'AdRuleAutomation/4.0',
            'Accept': 'text/plain, */*',
        })
        
        return session
    
    def fetch_url(self, url: str) -> Tuple[bool, Optional[str], int]:
        """获取单个URL的内容"""
        try:
            start_time = time.time()
            timeout = getattr(Config, 'REQUEST_TIMEOUT', 30)
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            content = response.text
            lines = len(content.split('\n'))
            elapsed = time.time() - start_time
            
            self.stats['successful'] += 1
            self.stats['source_details'][url] = {
                'status': 'success',
                'lines': lines,
                'time_seconds': round(elapsed, 2),
                'size_bytes': len(content.encode('utf-8'))
            }
            
            return True, content, lines
        except Exception as e:
            self.stats['failed'] += 1
            self.stats['source_details'][url] = {
                'status': 'failed',
                'error': str(e)
            }
            return False, None, 0

class RuleOptimizer:
    """规则优化器 - 提供智能去重和优化功能"""
    
    @staticmethod
    def deduplicate_adblock_rules(rules: Set[str]) -> Set[str]:
        """智能去重Adblock规则"""
        if not rules:
            return set()
        
        print(f"  正在对 {len(rules)} 条Adblock规则进行智能去重...")
        
        # 1. 基本去重（基于字符串完全匹配）
        unique_rules = set(rules)
        print(f"    基本去重后: {len(unique_rules)} 条")
        
        # 2. 域名级去重：提取规则中的域名，去除重复域名的不同变体
        domain_to_rules = defaultdict(set)
        optimized_rules = set()
        removed_count = 0
        
        for rule in unique_rules:
            domain = RuleOptimizer._extract_domain_from_adblock_rule(rule)
            if domain:
                # 如果这个域名已经有规则了，检查是否有更通用的规则
                existing_rules = domain_to_rules.get(domain, set())
                if existing_rules:
                    # 检查新规则是否比现有规则更具体或更通用
                    should_add = True
                    for existing_rule in existing_rules:
                        # 如果新规则更通用，替换旧规则
                        if RuleOptimizer._is_more_general_rule(rule, existing_rule):
                            optimized_rules.remove(existing_rule)
                            domain_to_rules[domain].remove(existing_rule)
                            removed_count += 1
                            break
                        # 如果新规则更具体，跳过
                        elif RuleOptimizer._is_more_specific_rule(rule, existing_rule):
                            should_add = False
                            removed_count += 1
                            break
                    
                    if should_add:
                        optimized_rules.add(rule)
                        domain_to_rules[domain].add(rule)
                else:
                    optimized_rules.add(rule)
                    domain_to_rules[domain].add(rule)
            else:
                optimized_rules.add(rule)
        
        print(f"    智能去重后: {len(optimized_rules)} 条 (移除了 {removed_count} 条冗余规则)")
        return optimized_rules
    
    @staticmethod
    def _extract_domain_from_adblock_rule(rule: str) -> Optional[str]:
        """从Adblock规则中提取域名"""
        # 处理常见的Adblock语法
        if rule.startswith('||'):
            # ||example.com^
            match = re.match(r'^\|\|([a-zA-Z0-9.*-]+)\^', rule)
            if match:
                return match.group(1)
        elif rule.startswith('|'):
            # |https://example.com/
            match = re.match(r'^\|(?:https?://)?([a-zA-Z0-9.*-]+)', rule)
            if match:
                return match.group(1)
        elif '##' in rule:
            # example.com##selector
            parts = rule.split('##')
            if len(parts) == 2:
                return parts[0].strip()
        return None
    
    @staticmethod
    def _is_more_general_rule(rule1: str, rule2: str) -> bool:
        """检查rule1是否比rule2更通用"""
        # 简单的启发式规则：通配符更多或更短通常更通用
        if '*' in rule1 and '*' not in rule2:
            return True
        if rule1.startswith('||') and not rule2.startswith('||'):
            return True
        return False
    
    @staticmethod
    def _is_more_specific_rule(rule1: str, rule2: str) -> bool:
        """检查rule1是否比rule2更具体"""
        # 相反的启发式
        if '*' not in rule1 and '*' in rule2:
            return True
        if not rule1.startswith('||') and rule2.startswith('||'):
            return True
        return False
    
    @staticmethod
    def deduplicate_hosts_entries(entries: Set[str]) -> Set[str]:
        """去重Hosts条目"""
        if not entries:
            return set()
        
        print(f"  正在对 {len(entries)} 个Hosts条目进行去重...")
        
        # 基于域名的去重：每个域名只保留一个条目（优先0.0.0.0）
        domain_to_entry = {}
        duplicates_removed = 0
        
        for entry in entries:
            parts = entry.split()
            if len(parts) >= 2:
                ip, domain = parts[0], parts[1]
                if domain in domain_to_entry:
                    duplicates_removed += 1
                    # 优先保留0.0.0.0而不是127.0.0.1
                    existing_ip = domain_to_entry[domain].split()[0]
                    if existing_ip == '127.0.0.1' and ip == '0.0.0.0':
                        domain_to_entry[domain] = entry
                else:
                    domain_to_entry[domain] = entry
        
        result = set(domain_to_entry.values())
        print(f"    Hosts去重后: {len(result)} 个 (移除了 {duplicates_removed} 个重复域名)")
        return result
    
    @staticmethod
    def deduplicate_domains(domains: Set[str]) -> Set[str]:
        """去重域名"""
        if not domains:
            return set()
        
        print(f"  正在对 {len(domains)} 个域名进行去重...")
        
        # 基本去重
        unique_domains = set(domains)
        
        # 移除子域名如果父域名已存在（可选）
        optimized_domains = set()
        removed_subdomains = 0
        
        for domain in sorted(unique_domains, key=len, reverse=True):
            # 检查是否是其他域名的子域名
            is_subdomain = False
            for other_domain in optimized_domains:
                if domain.endswith('.' + other_domain):
                    is_subdomain = True
                    removed_subdomains += 1
                    break
            
            if not is_subdomain:
                optimized_domains.add(domain)
        
        print(f"    域名去重后: {len(optimized_domains)} 个 (移除了 {removed_subdomains} 个子域名)")
        return optimized_domains

class RuleProcessor:
    """规则处理器 - 增强版，包含智能去重"""
    
    def __init__(self):
        self.fetcher = RuleFetcher()
        self.optimizer = RuleOptimizer()
        self.adblock_rules = set()
        self.hosts_entries = set()
        self.domains_set = set()
        
        # 从配置文件加载规则源
        try:
            all_sources = get_all_sources()
            if all_sources:
                self.rule_sources = all_sources
            else:
                self.rule_sources = [
                    "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
                    "https://easylist.to/easylist/easylist.txt",
                    "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
                    "https://someonewhocares.org/hosts/zero/hosts",
                ]
                print("⚠️  配置文件为空，使用默认规则源")
        except Exception as e:
            print(f"❌ 加载规则源配置失败: {e}")
            self.rule_sources = [
                "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
                "https://easylist.to/easylist/easylist.txt",
                "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
                "https://someonewhocares.org/hosts/zero/hosts",
            ]
        
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_duration': 0,
            'rules_processed': 0,
            'rules_by_source': {},
            'duplicates_removed': {
                'adblock': 0,
                'hosts': 0,
                'domains': 0
            },
            'update_status': 'no_change'
        }
    
    def process_rules(self) -> bool:
        """处理所有规则"""
        print("=" * 60)
        print("🔄 开始处理广告规则（智能去重版）")
        print(f"📅 当前上海时间: {get_time_string()}")
        print(f"📊 规则源总数: {len(self.rule_sources)} 个")
        print("=" * 60)
        
        self.stats['start_time'] = get_time_string()
        start_timestamp = time.time()
        
        print(f"📥 获取 {len(self.rule_sources)} 个规则源...")
        self.fetcher.stats['total_sources'] = len(self.rule_sources)
        
        contents = {}
        max_workers = getattr(Config, 'MAX_WORKERS', 15)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.fetcher.fetch_url, url): url 
                           for url in self.rule_sources}
            
            processed = 0
            total = len(self.rule_sources)
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                success, content, lines = future.result()
                processed += 1
                
                if success and content:
                    contents[url] = content
                    print(f"  [{processed}/{total}] ✅ 获取成功: {url} ({lines} 行)")
                    self.stats['rules_by_source'][url] = lines
                else:
                    print(f"  [{processed}/{total}] ❌ 获取失败: {url}")
        
        print(f"\n🔍 分析规则内容...")
        previous_counts = {
            'adblock': len(self.adblock_rules),
            'hosts': len(self.hosts_entries),
            'domains': len(self.domains_set)
        }
        
        for url, content in contents.items():
            self._parse_content(content, url)
        
        print(f"\n🧹 开始智能去重和优化...")
        
        # 记录去重前的数量
        before_dedup = {
            'adblock': len(self.adblock_rules),
            'hosts': len(self.hosts_entries),
            'domains': len(self.domains_set)
        }
        
        # 应用智能去重
        self.adblock_rules = self.optimizer.deduplicate_adblock_rules(self.adblock_rules)
        self.hosts_entries = self.optimizer.deduplicate_hosts_entries(self.hosts_entries)
        self.domains_set = self.optimizer.deduplicate_domains(self.domains_set)
        
        # 记录去重效果
        self.stats['duplicates_removed'] = {
            'adblock': before_dedup['adblock'] - len(self.adblock_rules),
            'hosts': before_dedup['hosts'] - len(self.hosts_entries),
            'domains': before_dedup['domains'] - len(self.domains_set)
        }
        
        self.stats['rules_processed'] = len(self.adblock_rules) + len(self.hosts_entries) + len(self.domains_set)
        
        current_counts = {
            'adblock': len(self.adblock_rules),
            'hosts': len(self.hosts_entries),
            'domains': len(self.domains_set)
        }
        
        if all(count > 0 for count in current_counts.values()):
            if any(current_counts[k] != previous_counts[k] for k in current_counts):
                self.stats['update_status'] = 'updated'
            else:
                self.stats['update_status'] = 'no_change'
        else:
            self.stats['update_status'] = 'failed'
        
        print(f"\n💾 保存优化后的规则文件...")
        success = self._save_results()
        
        elapsed_time = time.time() - start_timestamp
        self.stats['end_time'] = get_time_string()
        self.stats['total_duration'] = round(elapsed_time, 2)
        
        self._generate_detailed_stats()
        
        print("=" * 60)
        if success:
            status_emoji = "🔄" if self.stats['update_status'] == 'updated' else "⏸️"
            print(f"{status_emoji} 处理完成！状态: {self.stats['update_status']}")
            print(f"⏱️  总耗时: {elapsed_time:.2f}秒")
            print(f"📊 Adblock规则: {current_counts['adblock']} 条")
            print(f"📊 Hosts规则: {current_counts['hosts']} 个")
            print(f"📊 纯域名: {current_counts['domains']} 个")
            print(f"📈 去重统计: {self.stats['duplicates_removed']['adblock']}条Adblock, "
                  f"{self.stats['duplicates_removed']['hosts']}个Hosts, "
                  f"{self.stats['duplicates_removed']['domains']}个域名")
            print(f"📈 规则源: {self.fetcher.stats['successful']}成功/{self.fetcher.stats['failed']}失败")
        else:
            print(f"❌ 处理失败")
        
        print("=" * 60)
        return success and self.stats['update_status'] != 'failed'
    
    def _parse_content(self, content: str, source_url: str):
        """解析规则内容，分离三种格式"""
        lines = content.split('\n')
        counts = {'adblock': 0, 'hosts': 0, 'domains': 0}
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('!') or line.startswith('#'):
                continue
            
            # 1. 识别Adblock-style规则
            if (line.startswith('||') and line.endswith('^')) or \
               line.startswith('|') or \
               '##' in line or \
               (line.startswith('/') and line.endswith('/')):
                self.adblock_rules.add(line)
                counts['adblock'] += 1
            
            # 2. 识别Hosts规则
            elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+', line):
                parts = line.split()
                if len(parts) >= 2 and parts[0] in ['0.0.0.0', '127.0.0.1']:
                    rule = f"{parts[0]} {parts[1]}"
                    self.hosts_entries.add(rule)
                    counts['hosts'] += 1
                    
                    domain = parts[1]
                    if self._is_valid_domain(domain):
                        self.domains_set.add(domain)
                        counts['domains'] += 1
            
            # 3. 识别纯域名
            elif self._is_valid_domain(line):
                self.domains_set.add(line)
                counts['domains'] += 1
        
        if any(counts.values()):
            self.stats['rules_by_source'][source_url] = counts
    
    def _is_valid_domain(self, text: str) -> bool:
        """检查是否为有效的域名格式"""
        if not text or ' ' in text or '#' in text or '!' in text:
            return False
        domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        return bool(re.match(domain_pattern, text))
    
    def _save_results(self) -> bool:
        """保存三种格式的规则结果"""
        try:
            os.makedirs("dist", exist_ok=True)
            os.makedirs("stats", exist_ok=True)
            
            current_time = get_time_string()
            
            # 1. 保存Adblock规则
            adblock_path = "dist/Adblock.txt"
            with open(adblock_path, 'w', encoding='utf-8') as f:
                f.write(f"""! Adblock-style 规则（智能去重优化版）
! 适用于 uBlock Origin, AdGuard, Adblock Plus 等浏览器插件
! 最后更新: {current_time}
! 规则总数: {len(self.adblock_rules)} 条
! 去重移除: {self.stats['duplicates_removed']['adblock']} 条重复规则
! 更新状态: {self.stats['update_status']}
! GitHub: https://github.com/wansheng8/ad-rule-automation
!

""")
                for rule in sorted(self.adblock_rules):
                    f.write(f"{rule}\n")
            
            # 检查文件大小
            file_size = os.path.getsize(adblock_path)
            file_size_mb = file_size / (1024 * 1024)
            print(f"  ✅ 保存Adblock规则: {len(self.adblock_rules)} 条 -> dist/Adblock.txt ({file_size_mb:.2f} MB)")
            
            if file_size_mb > 90:
                print(f"  ⚠️  警告: Adblock.txt 文件较大 ({file_size_mb:.2f} MB)")
                print(f"  💡 建议: 如需进一步减小文件大小，可考虑:")
                print(f"     1. 减少规则源数量")
                print(f"     2. 启用规则压缩（可联系开发者启用）")
            
            # 2. 保存Hosts规则
            hosts_path = "dist/hosts.txt"
            with open(hosts_path, 'w', encoding='utf-8') as f:
                f.write(f"""# /etc/hosts 语法规则（智能去重优化版）
# 适用于系统hosts文件、Pi-hole、AdGuard Home等
# 最后更新: {current_time}
# 规则总数: {len(self.hosts_entries)} 个
# 去重移除: {self.stats['duplicates_removed']['hosts']} 个重复域名
# 更新状态: {self.stats['update_status']}
# GitHub: https://github.com/wansheng8/ad-rule-automation
#

""")
                sorted_hosts = sorted(self.hosts_entries)
                zero_hosts = [h for h in sorted_hosts if h.startswith('0.0.0.0')]
                local_hosts = [h for h in sorted_hosts if h.startswith('127.0.0.1')]
                for rule in zero_hosts + local_hosts:
                    f.write(f"{rule}\n")
            
            print(f"  ✅ 保存Hosts规则: {len(self.hosts_entries)} 个 -> dist/hosts.txt")
            
            # 3. 保存纯域名列表
            domains_path = "dist/Domains.txt"
            with open(domains_path, 'w', encoding='utf-8') as f:
                f.write(f"""# 纯域名列表（智能去重优化版）
# 适用于DNS过滤、防火墙规则等
# 最后更新: {current_time}
# 域名总数: {len(self.domains_set)} 个
# 去重移除: {self.stats['duplicates_removed']['domains']} 个重复域名
# 更新状态: {self.stats['update_status']}
# GitHub: https://github.com/wansheng8/ad-rule-automation
#

""")
                for domain in sorted(self.domains_set):
                    f.write(f"{domain}\n")
            
            print(f"  ✅ 保存纯域名列表: {len(self.domains_set)} 个 -> dist/Domains.txt")
            
            return True
            
        except Exception as e:
            print(f"  ❌ 保存失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _generate_detailed_stats(self):
        """生成详细统计报告"""
        try:
            timestamp = get_shanghai_time().strftime('%Y%m%d_%H%M%S')
            stats_file = f"stats/processing_stats_{timestamp}.json"
            
            detailed_stats = {
                "processing_info": {
                    "start_time": self.stats['start_time'],
                    "end_time": self.stats['end_time'],
                    "total_duration_seconds": self.stats['total_duration'],
                    "update_status": self.stats['update_status'],
                    "shanghai_timezone": True
                },
                "rules_summary": {
                    "adblock_rules": len(self.adblock_rules),
                    "hosts_entries": len(self.hosts_entries),
                    "domains": len(self.domains_set),
                    "total_processed": self.stats['rules_processed']
                },
                "duplicates_removed": self.stats['duplicates_removed'],
                "sources_summary": self.fetcher.stats,
                "rules_by_source": self.stats['rules_by_source'],
                "output_files": {
                    "adblock": "dist/Adblock.txt",
                    "hosts": "dist/hosts.txt",
                    "domains": "dist/Domains.txt"
                }
            }
            
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(detailed_stats, f, indent=2, ensure_ascii=False)
            
            print(f"  📊 统计报告已保存: {stats_file}")
            
            # 生成Markdown报告
            self._generate_markdown_report(detailed_stats, timestamp)
            
        except Exception as e:
            print(f"  ⚠️  生成统计报告时出错: {e}")
    
    def _generate_markdown_report(self, stats_data, timestamp):
        """生成Markdown报告"""
        try:
            md_file = f"stats/report_{timestamp}.md"
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(f"# 广告规则处理报告（智能去重版）\n\n")
                f.write(f"**生成时间**: {stats_data['processing_info']['end_time']}\n")
                f.write(f"**状态**: {stats_data['processing_info']['update_status']}\n")
                f.write(f"**输出文件**: [Adblock.txt](dist/Adblock.txt), [hosts.txt](dist/hosts.txt), [Domains.txt](dist/Domains.txt)\n\n")
                
                f.write(f"## 处理概览\n\n")
                f.write(f"- **总耗时**: {stats_data['processing_info']['total_duration_seconds']}秒\n")
                f.write(f"- **规则源**: {stats_data['sources_summary']['successful']}成功/{stats_data['sources_summary']['failed']}失败\n\n")
                
                f.write(f"## 规则统计（去重后）\n\n")
                f.write(f"- **Adblock规则**: {stats_data['rules_summary']['adblock_rules']}条\n")
                f.write(f"- **Hosts规则**: {stats_data['rules_summary']['hosts_entries']}个\n")
                f.write(f"- **纯域名**: {stats_data['rules_summary']['domains']}个\n")
                f.write(f"- **总计**: {stats_data['rules_summary']['total_processed']}条规则\n\n")
                
                f.write(f"## 去重效果\n\n")
                f.write(f"- **移除的Adblock重复规则**: {stats_data['duplicates_removed']['adblock']}条\n")
                f.write(f"- **移除的Hosts重复域名**: {stats_data['duplicates_removed']['hosts']}个\n")
                f.write(f"- **移除的域名重复**: {stats_data['duplicates_removed']['domains']}个\n")
            
            print(f"  📋 Markdown报告已保存: {md_file}")
        except Exception as e:
            print(f"  ⚠️  生成Markdown报告时出错: {e}")

def verify_configuration():
    """验证配置是否正确加载"""
    try:
        print("🔧 验证配置...")
        all_sources = get_all_sources()
        
        if not all_sources:
            print("❌ 配置文件错误: 未找到任何有效的规则源URL")
            print("💡 请检查 config/rule_sources.txt 文件（每行一个URL）")
            return False
        
        print(f"✅ 配置验证通过: 从TXT文件加载了 {len(all_sources)} 个规则源")
        
        print("📋 规则源示例:")
        for i, url in enumerate(all_sources[:3], 1):
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            print(f"  {i}. [{domain}]")
        if len(all_sources) > 3:
            print(f"  ... 还有 {len(all_sources) - 3} 个规则源")
        
        return True
        
    except Exception as e:
        print(f"❌ 配置验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("🤖 智能广告规则自动化处理系统 (智能去重版)")
    print("=" * 60)
    
    if not verify_configuration():
        print("❌ 配置验证失败，无法继续运行")
        return 1
    
    processor = RuleProcessor()
    
    try:
        success = processor.process_rules()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断处理")
        return 130
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
