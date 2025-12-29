#!/usr/bin/env python3
"""
智能广告规则处理系统 v3.0
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
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("错误：请先安装依赖：pip install requests pyyaml")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rule_processor.log'),
        logging.StreamHandler()
    ]
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
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 设置请求头
        session.headers.update({
            'User-Agent': 'AdRuleAutomation/1.0',
            'Accept': 'text/plain, application/octet-stream, */*',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        
        return session
    
    def fetch_url(self, url: str) -> Optional[str]:
        """获取单个URL的内容"""
        try:
            response = self.session.get(
                url, 
                timeout=30,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # 检查内容类型
            content_type = response.headers.get('content-type', '').lower()
            if 'text' not in content_type and 'octet-stream' not in content_type:
                logger.warning(f"URL {url} 返回非文本内容: {content_type}")
                return None
            
            self.success_count += 1
            return response.text
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取URL失败 {url}: {e}")
            self.failed_count += 1
            return None
    
    def fetch_batch(self, urls: List[str], max_workers: int = 15) -> Dict[str, str]:
        """批量获取URL内容"""
        results = {}
        
        logger.info(f"开始批量获取 {len(urls)} 个URL，并发数: {max_workers}")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.fetch_url, url): url for url in urls}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    content = future.result()
                    if content:
                        results[url] = content
                except Exception as e:
                    logger.error(f"处理URL时出错 {url}: {e}")
        
        logger.info(f"获取完成: 成功 {self.success_count}, 失败 {self.failed_count}")
        return results

class RuleAnalyzer:
    """规则分析器 - 智能识别和分类"""
    
    # 规则类型特征
    PATTERNS = {
        'adblock': [
            (r'^\|\|.*\^$', 0.9),           # ||example.com^
            (r'^@@\|\|.*\^$', 0.8),         # @@||example.com^ (白名单)
            (r'^\|https?://.*\|$', 0.7),    # |http://example.com|
            (r'^/.*/\$.*', 0.6),            # /ads/*$domain=example.com
            (r'^##.*', 0.5),                # ##div[ad] (元素隐藏)
            (r'^#@#.*', 0.5),               # #@#div[ad] (白名单)
            (r'.*\$(script|image|stylesheet|object)', 0.8),  # 资源类型
            (r'.*\.(gif|jpg|png|js|swf)\^.*', 0.7),  # 文件扩展名
        ],
        'hosts': [
            (r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+\S+', 1.0),  # IP 域名
            (r'^127\.0\.0\.1\s+', 0.9),     # 127.0.0.1
            (r'^::1\s+', 0.8),              # IPv6
            (r'^#\s*Hosts\s*file', 0.7),    # Hosts文件注释
        ],
        'domain': [
            (r'^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', 0.9),  # 纯域名
            (r'^\*?\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', 0.8),        # *.example.com
        ],
        'regex': [
            (r'^/.*/$', 0.9),               # 正则表达式
            (r'.*\$.*', 0.6),               # 带选项的规则
        ]
    }
    
    @staticmethod
    def detect_type(line: str) -> Tuple[str, float]:
        """检测单行规则类型及置信度"""
        line = line.strip()
        
        if not line or line.startswith('!') or line.startswith('#'):
            return 'comment', 1.0
        
        best_type = 'unknown'
        best_score = 0.0
        
        for rule_type, patterns in RuleAnalyzer.PATTERNS.items():
            for pattern, score in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    if score > best_score:
                        best_score = score
                        best_type = rule_type
        
        # 如果没有匹配到已知模式，尝试启发式判断
        if best_type == 'unknown':
            if '.' in line and len(line) > 4 and ' ' not in line:
                return 'domain', 0.5
        
        return best_type, best_score
    
    @staticmethod
    def extract_domain(rule: str) -> Optional[str]:
        """从规则中提取域名"""
        # 移除常见前缀
        prefixes = ['||', '|', '://', 'http://', 'https://', 'www.']
        for prefix in prefixes:
            if rule.startswith(prefix):
                rule = rule[len(prefix):]
        
        # 移除常见后缀
        suffixes = ['^', '^$', '/', '/*', '^$third-party']
        for suffix in suffixes:
            if rule.endswith(suffix):
                rule = rule[:-len(suffix)]
        
        # 提取域名
        domain_pattern = r'([a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        match = re.search(domain_pattern, rule)
        
        if match:
            domain = match.group(1).lower()
            # 验证域名
            if RuleAnalyzer.is_valid_domain(domain):
                return domain
        
        return None
    
    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        """验证域名有效性"""
        if not domain or len(domain) < 4:
            return False
        
        # 检查IP地址
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', domain):
            return False
        
        # 域名格式
        pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, domain))

class RuleOptimizer:
    """规则优化器 - 去重和排序"""
    
    def __init__(self):
        self.rules = {
            'adblock': set(),
            'hosts': set(),
            'domains': set(),
            'regex': set(),
        }
        self.stats = {
            'total_processed': 0,
            'by_type': defaultdict(int),
            'duplicates_removed': 0,
        }
    
    def add_rule(self, rule: str, rule_type: str):
        """添加规则到对应集合"""
        if rule_type in self.rules:
            if rule in self.rules[rule_type]:
                self.stats['duplicates_removed'] += 1
            else:
                self.rules[rule_type].add(rule)
                self.stats['by_type'][rule_type] += 1
        
        self.stats['total_processed'] += 1
    
    def optimize_adblock(self) -> List[str]:
        """优化Adblock规则"""
        optimized = []
        seen_domains = set()
        
        # 按优先级排序
        def get_priority(rule):
            priority = 50
            
            # 关键词优先级
            rule_lower = rule.lower()
            for keyword in ['ad', 'ads', 'track', 'analytics']:
                if keyword in rule_lower:
                    priority += 30
                    break
            
            # 规则类型优先级
            if rule.startswith('||') and rule.endswith('^'):
                priority += 20
            elif rule.startswith('@@'):
                priority -= 10
            elif '##' in rule:
                priority += 10
            
            # 长度优先级（短的规则更通用）
            if len(rule) < 20:
                priority += 10
            
            return priority
        
        # 排序并去重
        sorted_rules = sorted(
            self.rules['adblock'],
            key=lambda x: (-get_priority(x), len(x), x)
        )
        
        for rule in sorted_rules:
            domain = RuleAnalyzer.extract_domain(rule)
            if domain and domain in seen_domains:
                # 如果已经有更通用的规则，跳过特定规则
                if rule.startswith('||') and rule.endswith('^'):
                    continue
            
            if domain:
                seen_domains.add(domain)
            
            optimized.append(rule)
            
            # 限制数量
            if len(optimized) >= 50000:
                break
        
        return optimized
    
    def optimize_hosts(self) -> Dict[str, List[str]]:
        """优化Hosts规则，按IP分组"""
        hosts_dict = defaultdict(set)
        
        for entry in self.rules['hosts']:
            # 解析Hosts条目
            parts = entry.strip().split()
            if len(parts) >= 2:
                ip = parts[0]
                domain = parts[1]
                
                if ip in ['0.0.0.0', '127.0.0.1']:
                    if RuleAnalyzer.is_valid_domain(domain):
                        hosts_dict[ip].add(domain)
        
        # 转换为排序列表
        return {
            ip: sorted(domains)
            for ip, domains in hosts_dict.items()
        }

class SmartRuleProcessor:
    """智能规则处理器 - 主类"""
    
    def __init__(self, config_file: str = None):
        self.config_file = config_file
        self.fetcher = RuleFetcher()
        self.analyzer = RuleAnalyzer()
        self.optimizer = RuleOptimizer()
        
        # 加载规则源
        self.rule_sources = self._load_rule_sources()
        
    def _load_rule_sources(self) -> List[str]:
        """加载规则源列表"""
        sources = []
        
        # 1. 从YAML文件加载
        if self.config_file and os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if isinstance(data, list):
                    sources.extend(data)
        
        # 2. 从TXT文件加载
        txt_file = os.path.join('config', 'rule_sources.txt')
        if os.path.exists(txt_file):
            with open(txt_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        sources.append(line)
        
        # 3. 使用默认规则源
        if not sources:
            logger.warning("未找到规则源文件，使用默认规则源")
            sources = [
                "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
                "https://easylist.to/easylist/easylist.txt",
                "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            ]
        
        # 去重
        return list(set(sources))
    
    def process(self):
        """主处理流程"""
        logger.info("开始智能规则处理")
        start_time = time.time()
        
        # 1. 获取规则源内容
        logger.info(f"获取 {len(self.rule_sources)} 个规则源")
        source_contents = self.fetcher.fetch_batch(self.rule_sources)
        
        # 2. 分析处理每个规则源
        logger.info("分析规则内容")
        for url, content in source_contents.items():
            self._process_content(content, url)
        
        # 3. 优化规则
        logger.info("优化规则")
        adblock_rules = self.optimizer.optimize_adblock()
        hosts_rules = self.optimizer.optimize_hosts()
        
        # 4. 保存结果 - 只保存两个核心文件
        logger.info("保存结果")
        results = self._save_results(adblock_rules, hosts_rules)
        
        # 5. 生成统计报告
        elapsed_time = time.time() - start_time
        logger.info(f"处理完成，总耗时: {elapsed_time:.2f}秒")
        
        return results
    
    def _process_content(self, content: str, source_url: str):
        """处理单个规则源内容"""
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            rule_type, confidence = self.analyzer.detect_type(line)
            
            if rule_type != 'comment' and confidence > 0.3:
                self.optimizer.add_rule(line.strip(), rule_type)
    
    def _save_results(self, adblock_rules, hosts_rules):
        """保存优化后的规则 - 只生成两个固定文件"""
        # 确保输出目录存在
        os.makedirs("dist", exist_ok=True)
        os.makedirs("stats", exist_ok=True)
        
        results = {}
        
        # 1. 保存Adblock规则 - 固定文件名（每次覆盖）
        adblock_file = os.path.join("dist", "adblock_optimized.txt")
        
        with open(adblock_file, 'w', encoding='utf-8') as f:
            # 使用datetime.now()获取当前时间
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"""! Adblock规则
! 最后更新: {current_time}
! 规则总数: {len(adblock_rules)}
! 
! 由智能广告规则处理系统生成
! GitHub: https://github.com/wansheng8/ad-rule-automation
! 
! 统计信息:
! - 处理规则源: {len(self.rule_sources)} 个
! - Adblock规则: {len(self.optimizer.rules['adblock'])} 条
! - Hosts条目: {len(self.optimizer.rules['hosts'])} 条
! - 重复移除: {self.optimizer.stats['duplicates_removed']} 条
!

""")
            f.write('\n'.join(adblock_rules))
        
        results['adblock'] = adblock_file
        logger.info(f"✅ 保存Adblock规则: {len(adblock_rules)} 条")
        
        # 2. 保存Hosts规则 - 固定文件名（每次覆盖）
        hosts_file = os.path.join("dist", "hosts_optimized.txt")
        
        total_hosts = sum(len(d) for d in hosts_rules.values())
        with open(hosts_file, 'w', encoding='utf-8') as f:
            # 使用datetime.now()获取当前时间
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"""# Hosts规则
# 最后更新: {current_time}
# 域名总数: {total_hosts}
# 
# 由智能广告规则处理系统生成
# GitHub: https://github.com/wansheng8/ad-rule-automation
# 
# 使用方法: 将此文件内容复制到系统的hosts文件中
# 注意: 修改hosts文件可能需要管理员权限
#

""")
            
            for ip, domains in hosts_rules.items():
                for domain in domains:
                    f.write(f"{ip} {domain}\n")
        
        results['hosts'] = hosts_file
        logger.info(f"✅ 保存Hosts规则: {total_hosts} 条")
        
        return results

def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='智能广告规则处理系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s                            # 使用默认配置
  %(prog)s --config rule_sources.yaml # 使用自定义配置
  %(prog)s --test                     # 测试模式（仅处理少量规则源）
        """
    )
    
    parser.add_argument(
        '--config', 
        type=str, 
        default='config/rule_sources.yaml',
        help='规则源配置文件路径'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='测试模式（仅处理前5个规则源）'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='详细输出模式'
    )
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    try:
        processor = SmartRuleProcessor(args.config)
        
        # 测试模式：仅处理前5个规则源
        if args.test:
            logger.info("运行测试模式")
            processor.rule_sources = processor.rule_sources[:5]
        
        # 运行处理
        results = processor.process()
        
        # 输出结果路径
        print("\n" + "="*60)
        print("处理完成！")
        print("="*60)
        print(f"✓ Adblock规则: dist/adblock_optimized.txt")
        print(f"✓ Hosts规则: dist/hosts_optimized.txt")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("用户中断处理")
        return 130
    except Exception as e:
        logger.error(f"处理失败: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
