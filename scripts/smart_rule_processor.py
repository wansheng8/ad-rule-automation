#!/usr/bin/env python3
"""
智能广告规则处理系统 - 支持三格式输出版
生成 Adblock、Hosts 和 纯域名 三种格式的广告规则
"""

import os
import sys

# 添加项目根目录到Python路径，确保可以导入config模块
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
            'User-Agent': 'AdRuleAutomation/3.0',
            'Accept': 'text/plain, */*',
        })
        
        return session
    
    def fetch_url(self, url: str) -> Tuple[bool, Optional[str], int]:
        """获取单个URL的内容，返回(是否成功, 内容, 行数)"""
        try:
            start_time = time.time()
            # 使用配置中的超时时间
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

class RuleProcessor:
    """规则处理器 - 支持三格式输出"""
    
    def __init__(self):
        self.fetcher = RuleFetcher()
        self.adblock_rules = set()      # Adblock-style 规则
        self.hosts_entries = set()      # /etc/hosts 格式规则
        self.domains_set = set()        # 纯域名列表
        
        # 从配置文件加载规则源
        try:
            all_sources = get_all_sources()
            if all_sources:
                self.rule_sources = all_sources
            else:
                # 如果配置文件没有规则源，使用默认的4个
                self.rule_sources = [
                    "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
                    "https://easylist.to/easylist/easylist.txt",
                    "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
                    "https://someonewhocares.org/hosts/zero/hosts",
                ]
        except Exception as e:
            print(f"❌ 加载规则源配置失败: {e}")
            # 出错时使用默认规则源
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
            'update_status': 'no_change'
        }
    
    def process_rules(self) -> bool:
        """处理所有规则"""
        print("=" * 60)
        print("🔄 开始处理广告规则")
        print(f"📅 当前上海时间: {get_time_string()}")
        print(f"📊 规则源总数: {len(self.rule_sources)} 个")
        print("=" * 60)
        
        self.stats['start_time'] = get_time_string()
        start_timestamp = time.time()
        
        # 获取规则内容
        print(f"📥 获取 {len(self.rule_sources)} 个规则源...")
        self.fetcher.stats['total_sources'] = len(self.rule_sources)
        
        contents = {}
        
        # 使用配置中的MAX_WORKERS作为并发数
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
        
        # 处理规则内容
        print(f"\n🔍 分析规则内容...")
        previous_adblock_count = len(self.adblock_rules)
        previous_hosts_count = len(self.hosts_entries)
        previous_domains_count = len(self.domains_set)
        
        for url, content in contents.items():
            self._parse_content(content, url)
        
        # 计算统计
        self.stats['rules_processed'] = len(self.adblock_rules) + len(self.hosts_entries) + len(self.domains_set)
        
        # 判断是否需要更新
        current_adblock_count = len(self.adblock_rules)
        current_hosts_count = len(self.hosts_entries)
        current_domains_count = len(self.domains_set)
        
        if current_adblock_count > 0 and current_hosts_count > 0 and current_domains_count > 0:
            if (current_adblock_count != previous_adblock_count or 
                current_hosts_count != previous_hosts_count or
                current_domains_count != previous_domains_count):
                self.stats['update_status'] = 'updated'
            else:
                self.stats['update_status'] = 'no_change'
        else:
            self.stats['update_status'] = 'failed'
        
        # 保存结果
        print(f"\n💾 保存规则文件...")
        success = self._save_results()
        
        elapsed_time = time.time() - start_timestamp
        self.stats['end_time'] = get_time_string()
        self.stats['total_duration'] = round(elapsed_time, 2)
        
        # 生成详细统计报告
        self._generate_detailed_stats()
        
        print("=" * 60)
        if success:
            status_emoji = "🔄" if self.stats['update_status'] == 'updated' else "⏸️"
            print(f"{status_emoji} 处理完成！状态: {self.stats['update_status']}")
            print(f"⏱️  总耗时: {elapsed_time:.2f}秒")
            print(f"📊 Adblock规则: {current_adblock_count} 条")
            print(f"📊 Hosts规则: {current_hosts_count} 个")
            print(f"📊 纯域名: {current_domains_count} 个")
            print(f"📈 规则源: {self.fetcher.stats['successful']}成功/{self.fetcher.stats['failed']}失败")
        else:
            print(f"❌ 处理失败")
        
        print("=" * 60)
        return success and self.stats['update_status'] != 'failed'
    
    def _parse_content(self, content: str, source_url: str):
        """解析规则内容，分离三种格式"""
        lines = content.split('\n')
        source_adblock = 0
        source_hosts = 0
        source_domains = 0
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('!') or line.startswith('#'):
                continue
            
            # 1. 识别Adblock-style规则 (现代浏览器广告拦截器兼容)
            # 包括：||domain.com^, |https://..., ##selector, /regex/
            if (line.startswith('||') and line.endswith('^')) or \
               line.startswith('|') or \
               '##' in line or \
               line.startswith('/') and line.endswith('/'):
                if line not in self.adblock_rules:
                    self.adblock_rules.add(line)
                    source_adblock += 1
            
            # 2. 识别Hosts规则 (/etc/hosts 语法)
            # 格式: 0.0.0.0 domain.com 或 127.0.0.1 domain.com
            elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+', line):
                parts = line.split()
                if len(parts) >= 2 and parts[0] in ['0.0.0.0', '127.0.0.1']:
                    # 保留完整hosts格式
                    rule = f"{parts[0]} {parts[1]}"
                    if rule not in self.hosts_entries:
                        self.hosts_entries.add(rule)
                        source_hosts += 1
                    
                    # 同时提取域名用于纯域名列表
                    domain = parts[1]
                    if self._is_valid_domain(domain) and domain not in self.domains_set:
                        self.domains_set.add(domain)
                        source_domains += 1
            
            # 3. 识别纯域名规则
            # 简单域名列表: domain.com, sub.domain.com
            elif self._is_valid_domain(line):
                if line not in self.domains_set:
                    self.domains_set.add(line)
                    source_domains += 1
        
        # 记录该源的贡献
        if source_adblock > 0 or source_hosts > 0 or source_domains > 0:
            self.stats['rules_by_source'][source_url] = {
                'adblock': source_adblock,
                'hosts': source_hosts,
                'domains': source_domains,
                'total': source_adblock + source_hosts + source_domains
            }
    
    def _is_valid_domain(self, text: str) -> bool:
        """检查是否为有效的域名格式"""
        # 简单域名验证：包含点号，只包含字母、数字、点号和连字符
        if not text or ' ' in text or '#' in text or '!' in text:
            return False
        
        # 匹配常见域名模式
        domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        return bool(re.match(domain_pattern, text))
    
    def _save_results(self) -> bool:
        """保存三种格式的规则结果到 dist/ 目录"""
        try:
            os.makedirs("dist", exist_ok=True)
            os.makedirs("stats", exist_ok=True)
            
            current_time = get_time_string()
            timestamp = get_shanghai_time().strftime('%Y%m%d_%H%M%S')
            
            # 1. 保存Adblock规则 (Adblock.txt)
            adblock_file = "dist/Adblock.txt"
            with open(adblock_file, 'w', encoding='utf-8') as f:
                f.write(f"""! Adblock-style 规则
! 现代浏览器广告拦截器兼容格式 (uBlock Origin, AdGuard, Adblock Plus)
! 最后更新: {current_time}
! 规则总数: {len(self.adblock_rules)}
! 更新状态: {self.stats['update_status']}
! 
! 由智能广告规则处理系统生成
! 时区: 上海 (UTC+8)
! GitHub: https://github.com/wansheng8/ad-rule-automation
!

""")
                # 排序并写入规则
                for rule in sorted(self.adblock_rules):
                    f.write(f"{rule}\n")
            
            print(f"  ✅ 保存Adblock规则: {len(self.adblock_rules)} 条 -> dist/Adblock.txt")
            
            # 2. 保存Hosts规则 (hosts.txt)
            hosts_file = "dist/hosts.txt"
            with open(hosts_file, 'w', encoding='utf-8') as f:
                f.write(f"""# /etc/hosts 语法规则
# 与操作系统hosts文件兼容的格式
# 最后更新: {current_time}
# 规则总数: {len(self.hosts_entries)}
# 更新状态: {self.stats['update_status']}
# 
# 由智能广告规则处理系统生成
# 时区: 上海 (UTC+8)
# GitHub: https://github.com/wansheng8/ad-rule-automation
# 
# 使用方法: 复制到系统hosts文件 (Windows: C:\Windows\System32\drivers\etc\hosts)
# 格式: 0.0.0.0 example.com 或 127.0.0.1 example.com
#

""")
                # 排序并写入规则，优先0.0.0.0格式
                sorted_hosts = sorted(self.hosts_entries)
                # 将0.0.0.0格式的规则放在前面
                zero_hosts = [h for h in sorted_hosts if h.startswith('0.0.0.0')]
                local_hosts = [h for h in sorted_hosts if h.startswith('127.0.0.1')]
                
                for rule in zero_hosts + local_hosts:
                    f.write(f"{rule}\n")
            
            print(f"  ✅ 保存Hosts规则: {len(self.hosts_entries)} 个 -> dist/hosts.txt")
            
            # 3. 保存纯域名列表 (Domains.txt)
            domains_file = "dist/Domains.txt"
            with open(domains_file, 'w', encoding='utf-8') as f:
                f.write(f"""# 纯域名列表
# 简单的域名列表，适用于DNS过滤、防火墙规则等
# 最后更新: {current_time}
# 域名总数: {len(self.domains_set)}
# 更新状态: {self.stats['update_status']}
# 
# 由智能广告规则处理系统生成
# 时区: 上海 (UTC+8)
# GitHub: https://github.com/wansheng8/ad-rule-automation
# 
# 使用方法: 每行一个域名，适用于DNS级过滤
#

""")
                # 按域名排序
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
                "sources_summary": {
                    "total_sources": self.fetcher.stats['total_sources'],
                    "successful": self.fetcher.stats['successful'],
                    "failed": self.fetcher.stats['failed'],
                    "success_rate": round(self.fetcher.stats['successful'] / self.fetcher.stats['total_sources'] * 100, 1) 
                    if self.fetcher.stats['total_sources'] > 0 else 0
                },
                "source_details": self.fetcher.stats['source_details'],
                "rules_by_source": self.stats['rules_by_source'],
                "output_files": {
                    "adblock": "dist/Adblock.txt",
                    "hosts": "dist/hosts.txt", 
                    "domains": "dist/Domains.txt"
                },
                "recommendation": self._get_recommendation()
            }
            
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(detailed_stats, f, indent=2, ensure_ascii=False)
            
            print(f"  📊 统计报告已保存: {stats_file}")
            
            # 同时生成简明的Markdown报告
            self._generate_markdown_report(detailed_stats)
            
        except Exception as e:
            print(f"  ⚠️  生成统计报告时出错: {e}")
    
    def _get_recommendation(self):
        """根据统计生成建议"""
        if self.stats['update_status'] == 'updated':
            return {
                "action": "use_new_rules",
                "message": "规则已更新，建议使用新生成的三格式规则文件",
                "priority": "high",
                "file_recommendation": {
                    "browser_use": "使用 dist/Adblock.txt 订阅到浏览器广告拦截器",
                    "system_use": "使用 dist/hosts.txt 添加到系统hosts文件",
                    "dns_use": "使用 dist/Domains.txt 配置到DNS过滤工具"
                }
            }
        elif self.stats['update_status'] == 'no_change':
            return {
                "action": "keep_current",
                "message": "规则未变化，可继续使用现有规则文件",
                "priority": "low"
            }
        elif self.fetcher.stats['failed'] > self.fetcher.stats['successful']:
            return {
                "action": "check_sources",
                "message": "多数规则源获取失败，请检查网络或源地址",
                "priority": "high"
            }
        else:
            return {
                "action": "review",
                "message": "处理完成，请检查三种格式的规则文件",
                "priority": "medium"
            }
    
    def _generate_markdown_report(self, stats_data):
        """生成Markdown格式的简明报告"""
        try:
            timestamp = get_shanghai_time().strftime('%Y%m%d_%H%M%S')
            md_file = f"stats/report_{timestamp}.md"
            
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(f"# 广告规则处理报告 (三格式输出)\n\n")
                f.write(f"**生成时间**: {stats_data['processing_info']['end_time']}\n")
                f.write(f"**状态**: {stats_data['processing_info']['update_status']}\n")
                f.write(f"**输出文件**: [Adblock.txt](dist/Adblock.txt), [hosts.txt](dist/hosts.txt), [Domains.txt](dist/Domains.txt)\n\n")
                
                f.write(f"## 📊 处理概览\n\n")
                f.write(f"- **开始时间**: {stats_data['processing_info']['start_time']}\n")
                f.write(f"- **结束时间**: {stats_data['processing_info']['end_time']}\n")
                f.write(f"- **总耗时**: {stats_data['processing_info']['total_duration_seconds']} 秒\n\n")
                
                f.write(f"## 📈 规则统计 (三格式)\n\n")
                f.write(f"- **Adblock规则**: {stats_data['rules_summary']['adblock_rules']} 条 (浏览器广告拦截器兼容)\n")
                f.write(f"- **Hosts规则**: {stats_data['rules_summary']['hosts_entries']} 个 (系统hosts文件兼容)\n")
                f.write(f"- **纯域名**: {stats_data['rules_summary']['domains']} 个 (DNS/防火墙规则兼容)\n")
                f.write(f"- **总计**: {stats_data['rules_summary']['total_processed']} 条规则\n\n")
                
                f.write(f"## 🌐 规则源状态\n\n")
                f.write(f"- **规则源总数**: {stats_data['sources_summary']['total_sources']}\n")
                f.write(f"- **成功获取**: {stats_data['sources_summary']['successful']}\n")
                f.write(f"- **失败获取**: {stats_data['sources_summary']['failed']}\n")
                f.write(f"- **成功率**: {stats_data['sources_summary']['success_rate']}%\n\n")
                
                f.write(f"## 📁 输出文件\n\n")
                f.write(f"1. **Adblock.txt** - Adblock-style语法，适用于uBlock Origin等浏览器插件\n")
                f.write(f"2. **hosts.txt** - /etc/hosts语法，适用于系统hosts文件\n")
                f.write(f"3. **Domains.txt** - 纯域名列表，适用于DNS过滤\n\n")
                
                f.write(f"## 💡 建议\n\n")
                f.write(f"{stats_data['recommendation']['message']}\n")
                
                if 'file_recommendation' in stats_data['recommendation']:
                    f.write(f"\n**使用建议**:\n")
                    for key, suggestion in stats_data['recommendation']['file_recommendation'].items():
                        f.write(f"- {suggestion}\n")
                
                f.write(f"\n**优先级**: {stats_data['recommendation']['priority']}\n")
                f.write(f"\n**建议操作**: {stats_data['recommendation']['action']}\n")
            
            print(f"  📋 Markdown报告已保存: {md_file}")
            
        except Exception as e:
            print(f"  ⚠️  生成Markdown报告时出错: {e}")

def verify_configuration():
    """验证配置是否正确加载"""
    try:
        print("🔧 验证配置...")
        all_sources = get_all_sources()
        
        if not all_sources:
            print("❌ 配置文件错误: 规则源列表为空")
            print("💡 请检查 config/rule_sources.yaml 文件格式")
            return False
        
        print(f"✅ 配置验证通过: 找到 {len(all_sources)} 个规则源")
        
        # 检查前几个URL格式
        print("📋 规则源示例:")
        for i, url in enumerate(all_sources[:3], 1):
            # 简单美化显示，截取域名部分
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
    print("🤖 智能广告规则自动化处理系统 (三格式输出版)")
    print("=" * 60)
    
    # 验证配置
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
