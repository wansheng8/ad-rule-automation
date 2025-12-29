#!/usr/bin/env python3
"""
智能广告规则处理系统 v3.0 - 时间修正版
支持数百条规则源的自动识别、优化和合并
"""

import os
import sys
import re
import yaml
import json
import time
import logging
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_current_time():
    """获取当前时间（确保使用正确的时间）"""
    # 方法1：使用UTC时间
    utc_now = datetime.now(timezone.utc)
    # 方法2：使用系统本地时间（备用）
    local_now = datetime.now()
    
    # 记录两种时间用于调试
    logger.debug(f"UTC时间: {utc_now}")
    logger.debug(f"本地时间: {local_now}")
    
    # 默认返回格式化的本地时间（与之前一致）
    return local_now.strftime('%Y-%m-%d %H:%M:%S')

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

class RuleAnalyzer:
    """规则分析器 - 智能识别和分类"""
    
    @staticmethod
    def detect_type(line: str) -> Tuple[str, float]:
        """检测单行规则类型及置信度"""
        line = line.strip()
        
        if not line or line.startswith('!') or line.startswith('#'):
            return 'comment', 1.0
        
        # 简化检测逻辑
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+\S+', line):
            return 'hosts', 0.9
        elif line.startswith('||') and line.endswith('^'):
            return 'adblock', 0.9
        elif line.startswith('##') or line.startswith('#@#'):
            return 'adblock', 0.8
        elif re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', line):
            return 'domain', 0.7
        
        return 'unknown', 0.0

class RuleOptimizer:
    """规则优化器 - 去重和排序"""
    
    def __init__(self):
        self.rules = {'adblock': set(), 'hosts': set()}
        self.stats = defaultdict(int)
    
    def add_rule(self, rule: str, rule_type: str):
        """添加规则到对应集合"""
        if rule_type in self.rules:
            if rule not in self.rules[rule_type]:
                self.rules[rule_type].add(rule)
                self.stats[rule_type] += 1
            else:
                self.stats['duplicates'] += 1
    
    def optimize_adblock(self) -> List[str]:
        """优化Adblock规则"""
        return sorted(self.rules['adblock'])
    
    def optimize_hosts(self) -> Dict[str, List[str]]:
        """优化Hosts规则"""
        hosts_dict = defaultdict(set)
        
        for entry in self.rules['hosts']:
            parts = entry.strip().split()
            if len(parts) >= 2 and parts[0] in ['0.0.0.0', '127.0.0.1']:
                hosts_dict[parts[0]].add(parts[1])
        
        return {ip: sorted(domains) for ip, domains in hosts_dict.items()}

class SmartRuleProcessor:
    """智能规则处理器 - 主类"""
    
    def __init__(self, config_file: str = None):
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            self.requests = requests
        except ImportError:
            logger.error("缺少requests库，请运行: pip install requests")
            sys.exit(1)
            
        self.fetcher = RuleFetcher()
        self.analyzer = RuleAnalyzer()
        self.optimizer = RuleOptimizer()
        self.rule_sources = self._load_rule_sources(config_file)
    
    def _load_rule_sources(self, config_file: str) -> List[str]:
        """加载规则源列表"""
        sources = []
        
        if config_file and os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if isinstance(data, list):
                    sources.extend(data)
        
        # 默认源
        if not sources:
            sources = [
                "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
                "https://easylist.to/easylist/easylist.txt",
                "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            ]
        
        return list(set(sources))
    
    def process(self):
        """主处理流程"""
        logger.info("开始智能规则处理")
        
        # 记录开始时间（用于调试）
        start_time = time.time()
        current_time_str = get_current_time()
        logger.info(f"处理开始时间: {current_time_str}")
        
        # 获取并处理规则
        source_contents = self.fetcher.fetch_batch(self.rule_sources)
        for content in source_contents.values():
            self._process_content(content)
        
        # 优化规则
        adblock_rules = self.optimizer.optimize_adblock()
        hosts_rules = self.optimizer.optimize_hosts()
        
        # 保存结果
        self._save_results(adblock_rules, hosts_rules, current_time_str)
        
        elapsed_time = time.time() - start_time
        logger.info(f"处理完成，总耗时: {elapsed_time:.2f}秒")
        
        return {
            'adblock': len(adblock_rules),
            'hosts': sum(len(d) for d in hosts_rules.values())
        }
    
    def _process_content(self, content: str):
        """处理单个规则源内容"""
        for line in content.split('\n'):
            rule_type, confidence = self.analyzer.detect_type(line)
            if rule_type not in ['comment', 'unknown'] and confidence > 0.3:
                self.optimizer.add_rule(line.strip(), rule_type)
    
    def _save_results(self, adblock_rules, hosts_rules, timestamp_str):
        """保存优化后的规则"""
        os.makedirs("dist", exist_ok=True)
        
        # 使用传入的时间戳（或获取新时间）
        file_time = timestamp_str
        
        # 保存Adblock规则
        adblock_file = "dist/adblock_optimized.txt"
        with open(adblock_file, 'w', encoding='utf-8') as f:
            f.write(f"""! Adblock规则
! 最后更新: {file_time}
! 规则总数: {len(adblock_rules)}
! 
! 由智能广告规则处理系统生成
! GitHub: https://github.com/wansheng8/ad-rule-automation
!

""")
            f.write('\n'.join(adblock_rules))
        
        logger.info(f"保存Adblock规则: {len(adblock_rules)} 条")
        
        # 保存Hosts规则
        hosts_file = "dist/hosts_optimized.txt"
        total_hosts = sum(len(d) for d in hosts_rules.values())
        with open(hosts_file, 'w', encoding='utf-8') as f:
            f.write(f"""# Hosts规则
# 最后更新: {file_time}
# 域名总数: {total_hosts}
# 
# 由智能广告规则处理系统生成
# GitHub: https://github.com/wansheng8/ad-rule-automation
#

""")
            for ip, domains in hosts_rules.items():
                for domain in domains:
                    f.write(f"{ip} {domain}\n")
        
        logger.info(f"保存Hosts规则: {total_hosts} 条")

def main():
    parser = argparse.ArgumentParser(description='智能广告规则处理系统')
    parser.add_argument('--config', default='config/rule_sources.yaml', help='规则源配置文件路径')
    parser.add_argument('--verbose', action='store_true', help='详细输出模式')
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    try:
        processor = SmartRuleProcessor(args.config)
        results = processor.process()
        
        print("\n" + "="*60)
        print("处理完成！")
        print("="*60)
        print(f"生成时间: {get_current_time()}")
        print(f"✓ Adblock规则: {results['adblock']} 条")
        print(f"✓ Hosts规则: {results['hosts']} 个域名")
        
        return 0
        
    except Exception as e:
        logger.error(f"处理失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
