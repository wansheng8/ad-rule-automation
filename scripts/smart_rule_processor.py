#!/usr/bin/env python3
"""
智能广告规则处理系统 - 优化统计版
生成 Adblock 和 Hosts 格式的广告规则
"""

import os
import sys
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
            'User-Agent': 'AdRuleAutomation/2.0',
            'Accept': 'text/plain, */*',
        })
        
        return session
    
    def fetch_url(self, url: str) -> Tuple[bool, Optional[str], int]:
        """获取单个URL的内容，返回(是否成功, 内容, 行数)"""
        try:
            start_time = time.time()
            response = self.session.get(url, timeout=30)
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
    """规则处理器"""
    
    def __init__(self):
        self.fetcher = RuleFetcher()
        self.adblock_rules = set()
        self.hosts_entries = set()
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
        print("=" * 60)
        
        self.stats['start_time'] = get_time_string()
        start_timestamp = time.time()
        
        # 获取规则内容
        print(f"📥 获取 {len(self.rule_sources)} 个规则源...")
        self.fetcher.stats['total_sources'] = len(self.rule_sources)
        
        contents = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(self.fetcher.fetch_url, url): url 
                           for url in self.rule_sources}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                success, content, lines = future.result()
                if success and content:
                    contents[url] = content
                    print(f"  ✅ 获取成功: {url} ({lines} 行)")
                    self.stats['rules_by_source'][url] = lines
                else:
                    print(f"  ❌ 获取失败: {url}")
        
        # 处理规则内容
        print(f"\n🔍 分析规则内容...")
        previous_adblock_count = len(self.adblock_rules)
        previous_hosts_count = len(self.hosts_entries)
        
        for url, content in contents.items():
            self._parse_content(content, url)
        
        # 计算统计
        self.stats['rules_processed'] = len(self.adblock_rules) + len(self.hosts_entries)
        
        # 判断是否需要更新
        current_adblock_count = len(self.adblock_rules)
        current_hosts_count = len(self.hosts_entries)
        
        if current_adblock_count > 0 and current_hosts_count > 0:
            if (current_adblock_count != previous_adblock_count or 
                current_hosts_count != previous_hosts_count):
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
            print(f"📊 Hosts域名: {current_hosts_count} 个")
            print(f"📈 规则源: {self.fetcher.stats['successful']}成功/{self.fetcher.stats['failed']}失败")
        else:
            print(f"❌ 处理失败")
        
        print("=" * 60)
        return success and self.stats['update_status'] != 'failed'
    
    def _parse_content(self, content: str, source_url: str):
        """解析规则内容"""
        lines = content.split('\n')
        source_adblock = 0
        source_hosts = 0
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('!') or line.startswith('#'):
                continue
            
            # 识别Adblock规则
            if (line.startswith('||') and line.endswith('^')) or \
               line.startswith('|') or \
               '##' in line or \
               line.startswith('/'):
                if line not in self.adblock_rules:
                    self.adblock_rules.add(line)
                    source_adblock += 1
            
            # 识别Hosts规则
            elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+', line):
                parts = line.split()
                if len(parts) >= 2 and parts[0] in ['0.0.0.0', '127.0.0.1']:
                    rule = f"{parts[0]} {parts[1]}"
                    if rule not in self.hosts_entries:
                        self.hosts_entries.add(rule)
                        source_hosts += 1
        
        # 记录该源的贡献
        if source_adblock > 0 or source_hosts > 0:
            self.stats['rules_by_source'][source_url] = {
                'adblock': source_adblock,
                'hosts': source_hosts,
                'total': source_adblock + source_hosts
            }
    
    def _save_results(self) -> bool:
        """保存规则结果"""
        try:
            os.makedirs("dist", exist_ok=True)
            os.makedirs("stats", exist_ok=True)
            
            current_time = get_time_string()
            
            # 保存Adblock规则
            adblock_file = "dist/adblock_optimized.txt"
            with open(adblock_file, 'w', encoding='utf-8') as f:
                f.write(f"""! Adblock规则
! 最后更新: {current_time}
! 规则总数: {len(self.adblock_rules)}
! 更新状态: {self.stats['update_status']}
! 
! 由智能广告规则处理系统生成
! 时区: 上海 (UTC+8)
! GitHub: https://github.com/wansheng8/ad-rule-automation
!

""")
                f.write('\n'.join(sorted(self.adblock_rules)))
            
            print(f"  ✅ 保存Adblock规则: {len(self.adblock_rules)} 条")
            
            # 保存Hosts规则
            hosts_file = "dist/hosts_optimized.txt"
            with open(hosts_file, 'w', encoding='utf-8') as f:
                f.write(f"""# Hosts规则
# 最后更新: {current_time}
# 域名总数: {len(self.hosts_entries)}
# 更新状态: {self.stats['update_status']}
# 
# 由智能广告规则处理系统生成
# 时区: 上海 (UTC+8)
# GitHub: https://github.com/wansheng8/ad-rule-automation
# 
# 使用方法: 复制到系统hosts文件
# 格式: 0.0.0.0 example.com
#

""")
                f.write('\n'.join(sorted(self.hosts_entries)))
            
            print(f"  ✅ 保存Hosts规则: {len(self.hosts_entries)} 个域名")
            
            return True
            
        except Exception as e:
            print(f"  ❌ 保存失败: {e}")
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
                "message": "规则已更新，建议使用新生成的规则文件",
                "priority": "high"
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
                "message": "处理完成，请检查规则文件",
                "priority": "medium"
            }
    
    def _generate_markdown_report(self, stats_data):
        """生成Markdown格式的简明报告"""
        try:
            timestamp = get_shanghai_time().strftime('%Y%m%d_%H%M%S')
            md_file = f"stats/report_{timestamp}.md"
            
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(f"# 广告规则处理报告\n\n")
                f.write(f"**生成时间**: {stats_data['processing_info']['end_time']}\n")
                f.write(f"**状态**: {stats_data['processing_info']['update_status']}\n\n")
                
                f.write(f"## 📊 处理概览\n\n")
                f.write(f"- **开始时间**: {stats_data['processing_info']['start_time']}\n")
                f.write(f"- **结束时间**: {stats_data['processing_info']['end_time']}\n")
                f.write(f"- **总耗时**: {stats_data['processing_info']['total_duration_seconds']} 秒\n\n")
                
                f.write(f"## 📈 规则统计\n\n")
                f.write(f"- **Adblock规则**: {stats_data['rules_summary']['adblock_rules']} 条\n")
                f.write(f"- **Hosts规则**: {stats_data['rules_summary']['hosts_entries']} 个\n")
                f.write(f"- **总计**: {stats_data['rules_summary']['total_processed']} 条规则\n\n")
                
                f.write(f"## 🌐 规则源状态\n\n")
                f.write(f"- **规则源总数**: {stats_data['sources_summary']['total_sources']}\n")
                f.write(f"- **成功获取**: {stats_data['sources_summary']['successful']}\n")
                f.write(f"- **失败获取**: {stats_data['sources_summary']['failed']}\n")
                f.write(f"- **成功率**: {stats_data['sources_summary']['success_rate']}%\n\n")
                
                f.write(f"## 💡 建议\n\n")
                f.write(f"{stats_data['recommendation']['message']}\n")
                f.write(f"\n**优先级**: {stats_data['recommendation']['priority']}\n")
                f.write(f"\n**建议操作**: {stats_data['recommendation']['action']}\n")
            
            print(f"  📋 Markdown报告已保存: {md_file}")
            
        except Exception as e:
            print(f"  ⚠️  生成Markdown报告时出错: {e}")

def main():
    """主函数"""
    processor = RuleProcessor()
    
    try:
        success = processor.process_rules()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断处理")
        return 130
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
