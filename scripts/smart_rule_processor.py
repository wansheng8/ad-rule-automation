#!/usr/bin/env python3
"""
智能广告规则处理系统 - 修复版
"""

import os
import sys
import re
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 先导入requests，确保全局可用
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_AVAILABLE = True
except ImportError:
    print("错误：请先安装依赖：pip install requests")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class RuleFetcher:
    """规则获取器 - 支持重试和并发"""
    
    def __init__(self):
        self.session = self._create_session()
        self.success_count = 0
        self.failed_count = 0
        
    def _create_session(self):
        """创建HTTP会话，配置重试策略"""
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
            'User-Agent': 'AdRuleAutomation/1.0',
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
            logger.error(f"获取URL失败 {url}: {e}")
            self.failed_count += 1
            return None
    
    def fetch_batch(self, urls: List[str]) -> Dict[str, str]:
        """批量获取URL内容"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(self.fetch_url, url): url for url in urls}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                content = future.result()
                if content:
                    results[url] = content
        
        logger.info(f"获取完成: 成功 {self.success_count}, 失败 {self.failed_count}")
        return results

class RuleProcessor:
    """规则处理器 - 简化的核心逻辑"""
    
    def __init__(self, sources=None):
        self.fetcher = RuleFetcher()
        self.sources = sources or [
            "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
            "https://easylist.to/easylist/easylist.txt",
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
        ]
        
    def process(self):
        """主处理流程"""
        logger.info("开始处理广告规则")
        start_time = time.time()
        
        # 获取规则
        contents = self.fetcher.fetch_batch(self.sources)
        
        # 处理规则
        adblock_rules = set()
        hosts_entries = set()
        
        for content in contents.values():
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('!') or line.startswith('#'):
                    continue
                
                # 简单分类
                if line.startswith('||') or '##' in line or line.startswith('/'):
                    adblock_rules.add(line)
                elif re.match(r'^\d+\.\d+\.\d+\.\d+\s+', line):
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] in ['0.0.0.0', '127.0.0.1']:
                        hosts_entries.add(f"{parts[0]} {parts[1]}")
        
        # 保存结果
        self._save_results(sorted(adblock_rules), sorted(hosts_entries))
        
        elapsed_time = time.time() - start_time
        logger.info(f"处理完成，耗时: {elapsed_time:.2f}秒")
        logger.info(f"生成规则: Adblock {len(adblock_rules)}条, Hosts {len(hosts_entries)}条")
        
        return True
    
    def _save_results(self, adblock_rules, hosts_entries):
        """保存优化后的规则"""
        os.makedirs("dist", exist_ok=True)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 保存Adblock规则
        with open("dist/adblock_optimized.txt", 'w', encoding='utf-8') as f:
            f.write(f"""! Adblock规则
! 最后更新: {current_time}
! 规则总数: {len(adblock_rules)}
! 
! 由智能广告规则处理系统生成
! GitHub: https://github.com/wansheng8/ad-rule-automation
!

""")
            f.write('\n'.join(adblock_rules))
        
        # 保存Hosts规则
        with open("dist/hosts_optimized.txt", 'w', encoding='utf-8') as f:
            f.write(f"""# Hosts规则
# 最后更新: {current_time}
# 域名总数: {len(hosts_entries)}
# 
! 由智能广告规则处理系统生成
! GitHub: https://github.com/wansheng8/ad-rule-automation
#

""")
            f.write('\n'.join(hosts_entries))

def main():
    """主函数"""
    processor = RuleProcessor()
    try:
        success = processor.process()
        if success:
            print("\n" + "="*60)
            print("✅ 处理成功！")
            print("="*60)
            print(f"文件已保存到 dist/ 目录")
            return 0
        else:
            return 1
    except Exception as e:
        logger.error(f"处理失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
