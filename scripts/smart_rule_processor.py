#!/usr/bin/env python3
"""
智能广告规则处理系统 - 上海时间版
生成 Adblock 和 Hosts 格式的广告规则
"""

import os
import sys
import re
import time
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_AVAILABLE = True
except ImportError:
    print("错误：请先安装依赖：pip install requests")
    sys.exit(1)

def get_shanghai_time() -> datetime:
    """获取当前上海时间 (UTC+8)"""
    try:
        # 创建上海时区 (UTC+8)
        shanghai_tz = timezone(timedelta(hours=8))
        # 获取当前UTC时间并转换为上海时间
        utc_now = datetime.now(timezone.utc)
        shanghai_time = utc_now.astimezone(shanghai_tz)
        return shanghai_time
    except Exception:
        # 如果失败，回退到本地时间
        return datetime.now()

def get_time_string() -> str:
    """获取格式化的上海时间字符串"""
    shanghai_time = get_shanghai_time()
    return shanghai_time.strftime('%Y-%m-%d %H:%M:%S')

class RuleFetcher:
    """规则获取器"""
    
    def __init__(self):
        self.session = self._create_session()
        self.success_count = 0
        self.failed_count = 0
        
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
    
    def fetch_url(self, url: str) -> Optional[str]:
        """获取单个URL的内容"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            self.success_count += 1
            return response.text
        except Exception as e:
            print(f"  获取失败 {url}: {e}")
            self.failed_count += 1
            return None

class RuleProcessor:
    """规则处理器"""
    
    def __init__(self):
        self.fetcher = RuleFetcher()
        self.adblock_rules = set()
        self.hosts_entries = set()
        
        # 默认规则源
        self.rule_sources = [
            "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
            "https://easylist.to/easylist/easylist.txt",
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            "https://someonewhocares.org/hosts/zero/hosts",
        ]
    
    def process_rules(self) -> bool:
        """处理所有规则"""
        print("=" * 60)
        print("🔄 开始处理广告规则")
        print(f"📅 当前上海时间: {get_time_string()}")
        print("=" * 60)
        
        start_time = time.time()
        
        # 获取规则内容
        print(f"📥 获取 {len(self.rule_sources)} 个规则源...")
        contents = {}
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(self.fetcher.fetch_url, url): url 
                           for url in self.rule_sources}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                content = future.result()
                if content:
                    contents[url] = content
                    print(f"  ✅ 获取成功: {url}")
        
        # 处理规则内容
        print(f"\n🔍 分析规则内容...")
        for url, content in contents.items():
            self._parse_content(content)
        
        # 保存结果
        print(f"\n💾 保存规则文件...")
        success = self._save_results()
        
        elapsed_time = time.time() - start_time
        
        print("=" * 60)
        if success:
            print(f"✅ 处理完成！")
            print(f"⏱️  总耗时: {elapsed_time:.2f}秒")
            print(f"📊 Adblock规则: {len(self.adblock_rules)} 条")
            print(f"📊 Hosts域名: {len(self.hosts_entries)} 个")
        else:
            print(f"❌ 处理失败")
        
        print("=" * 60)
        return success
    
    def _parse_content(self, content: str):
        """解析规则内容"""
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('!') or line.startswith('#'):
                continue
            
            # 识别Adblock规则
            if (line.startswith('||') and line.endswith('^')) or \
               line.startswith('|') or \
               '##' in line or \
               line.startswith('/'):
                self.adblock_rules.add(line)
            
            # 识别Hosts规则
            elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+', line):
                parts = line.split()
                if len(parts) >= 2 and parts[0] in ['0.0.0.0', '127.0.0.1']:
                    self.hosts_entries.add(f"{parts[0]} {parts[1]}")
    
    def _save_results(self) -> bool:
        """保存规则结果"""
        try:
            os.makedirs("dist", exist_ok=True)
            current_time = get_time_string()
            
            # 保存Adblock规则
            adblock_file = "dist/adblock_optimized.txt"
            with open(adblock_file, 'w', encoding='utf-8') as f:
                f.write(f"""! Adblock规则
! 最后更新: {current_time}
! 规则总数: {len(self.adblock_rules)}
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
            
            # 保存时间验证文件
            time_file = "dist/time_verification.json"
            with open(time_file, 'w', encoding='utf-8') as f:
                time_data = {
                    "generated_at": get_time_string(),
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "adblock_rules": len(self.adblock_rules),
                    "hosts_entries": len(self.hosts_entries),
                    "timezone": "Asia/Shanghai (UTC+8)"
                }
                json.dump(time_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"  ❌ 保存失败: {e}")
            return False

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
