#!/usr/bin/env python3
"""
广告规则自动化处理系统 - 多阶段优化版
包含：下载 → 解析 → 去重 → 优化 → 二次优化 → 输出
"""

import os
import sys
import re
import time
import json
import signal
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
ADBLOCK_DOMAIN_PATTERN = re.compile(r'^\|\|([a-zA-Z0-9.*-]+)\^')
ADBLOCK_ELEMENT_PATTERN = re.compile(r'^([^#]+)##(.+)$')

# 超时控制
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("处理超时")

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

class AdvancedRuleFetcher:
    """高级规则获取器"""
    
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
            sys.exit(1)
        
        self.session = self._create_session()
        self.cache_dir = Path(Config.CACHE_DIR)
        self.cache_dir.mkdir(exist_ok=True)
        
        self.stats = {
            'total': 0, 'success': 0, 'cached': 0,
            'failed': 0, 'timeout': 0
        }
    
    def _create_session(self):
        """创建优化的HTTP会话"""
        session = self.requests.Session()
        retry = self.Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = self.HTTPAdapter(
            max_retries=retry,
            pool_connections=Config.MAX_WORKERS,
            pool_maxsize=Config.MAX_WORKERS
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        session.headers.update({
            'User-Agent': Config.get_user_agent(),
            'Accept': 'text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        
        return session
    
    def _get_cache_path(self, url: str) -> Path:
        """生成缓存文件路径"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"cache_{url_hash}.txt"
    
    def fetch_url(self, url: str) -> Tuple[bool, Optional[str], int]:
        """获取URL内容（带智能缓存）"""
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
                    pass  # 缓存读取失败，重新下载
        
        # 网络请求
        try:
            start_time = time.time()
            response = self.session.get(
                url, 
                timeout=Config.REQUEST_TIMEOUT,
                stream=False
            )
            response.raise_for_status()
            
            content = response.text
            lines = content.count('\n') + 1
            elapsed = time.time() - start_time
            
            # 保存缓存
            if Config.CACHE_ENABLED:
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                except:
                    pass
            
            self.stats['success'] += 1
            return True, content, lines
            
        except self.requests.exceptions.Timeout:
            self.stats['timeout'] += 1
            return False, None, 0
        except Exception as e:
            self.stats['failed'] += 1
            return False, None, 0

class MultiStageProcessor:
    """多阶段处理器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.stats = {
            'stage1_download': {'time': 0, 'rules': 0},
            'stage2_parse': {'time': 0, 'rules': 0},
            'stage3_dedup': {'time': 0, 'before': 0, 'after': 0},
            'stage4_optimize': {'time': 0, 'before': 0, 'after': 0},
            'stage5_secondary': {'time': 0, 'before': 0, 'after': 0},
            'stage6_output': {'time': 0, 'rules': 0},
            'total_time': 0,
            'final_rules': 0
        }
    
    def log_stage_start(self, stage_name: str):
        """记录阶段开始"""
        print(f"\n{'='*60}")
        print(f"📊 {stage_name}")
        print(f"{'='*60}")
        return time.time()
    
    def log_stage_end(self, stage_name: str, start_time: float, **kwargs):
        """记录阶段结束"""
        elapsed = time.time() - start_time
        self.stats[stage_name]['time'] = elapsed
        print(f"✅ 完成，耗时: {elapsed:.2f}秒")
        for key, value in kwargs.items():
            if key in self.stats[stage_name]:
                self.stats[stage_name][key] = value
            print(f"   {key}: {value:,}")

class SmartRuleParser:
    """智能规则解析器"""
    
    @staticmethod
    def parse_line(line: str) -> Optional[str]:
        """解析单行规则"""
        line = line.strip()
        
        # 跳过空行和注释
        if not line or (Config.SKIP_COMMENT_LINES and line[0] in '!#'):
            return None
        
        # 长度检查
        if len(line) > Config.PARSE_MAX_LINE_LENGTH:
            return None
        
        # 规则验证
        if not SmartRuleParser.is_valid_rule(line):
            return None
        
        return line
    
    @staticmethod
    def is_valid_rule(rule: str) -> bool:
        """验证规则有效性"""
        # 检查基本格式
        if ' ' in rule and not rule.startswith(('0.0.0.0', '127.0.0.1')):
            return False
        
        # 检查域名规则
        if rule.startswith('||') and '^' in rule:
            domain = rule[2:].split('^')[0]
            return SmartRuleParser.is_valid_domain(domain)
        
        # 检查hosts规则
        if rule.startswith(('0.0.0.0 ', '127.0.0.1 ')):
            parts = rule.split()
            if len(parts) >= 2:
                return SmartRuleParser.is_valid_domain(parts[1])
        
        # 检查纯域名
        if DOMAIN_PATTERN.match(rule):
            return SmartRuleParser.is_valid_domain(rule)
        
        return True
    
    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        """验证域名有效性"""
        if not domain:
            return False
        
        length = len(domain)
        if length < Config.MIN_DOMAIN_LENGTH or length > Config.MAX_DOMAIN_LENGTH:
            return False
        
        # 检查特殊字符
        if '..' in domain or domain.startswith('.') or domain.endswith('.'):
            return False
        
        # 检查非法字符
        invalid_chars = [' ', '@', '!', '#', '$', '%', '^', '&', '*', '(', ')', '=', '+', '[', ']', '{', '}', '|', '\\', ';', ':', "'", '"', '<', '>', ',', '?', '/']
        for char in invalid_chars:
            if char in domain:
                return False
        
        return True

class MultiStageDeduplicator:
    """多阶段去重器"""
    
    def __init__(self):
        self.stats = {
            'stage1_hash': {'before': 0, 'after': 0},
            'stage2_domain': {'before': 0, 'after': 0},
            'stage3_subdomain': {'before': 0, 'after': 0},
            'total_removed': 0
        }
    
    def deduplicate(self, rules: List[str]) -> List[str]:
        """多阶段去重"""
        if not rules:
            return []
        
        print(f"  开始多阶段去重 {len(rules):,} 条规则...")
        
        current_rules = rules.copy()
        
        # 第一阶段：哈希去重（快速）
        if Config.HASH_DEDUP_ENABLED:
            current_rules = self._hash_deduplicate(current_rules)
        
        # 第二阶段：域名级去重
        if Config.DOMAIN_DEDUP_ENABLED:
            current_rules = self._domain_deduplicate(current_rules)
        
        # 第三阶段：子域名优化
        if Config.SUBDOMAIN_OPTIMIZATION:
            current_rules = self._subdomain_optimize(current_rules)
        
        total_removed = len(rules) - len(current_rules)
        self.stats['total_removed'] = total_removed
        
        print(f"  去重完成: {len(current_rules):,} 条 (移除 {total_removed:,} 条)")
        
        return current_rules
    
    def _hash_deduplicate(self, rules: List[str]) -> List[str]:
        """哈希去重（第一阶段）"""
        start_time = time.time()
        before = len(rules)
        
        seen = set()
        unique_rules = []
        
        for rule in rules:
            rule_hash = hashlib.md5(rule.encode()).hexdigest()
            if rule_hash not in seen:
                seen.add(rule_hash)
                unique_rules.append(rule)
        
        after = len(unique_rules)
        elapsed = time.time() - start_time
        
        self.stats['stage1_hash']['before'] = before
        self.stats['stage1_hash']['after'] = after
        
        print(f"    🎯 哈希去重: {before:,} → {after:,} 条 (-{before-after:,}), 耗时: {elapsed:.2f}s")
        
        return unique_rules
    
    def _domain_deduplicate(self, rules: List[str]) -> List[str]:
        """域名级去重（第二阶段）"""
        start_time = time.time()
        before = len(rules)
        
        # 分离不同类型规则
        domain_rules = {}
        other_rules = []
        
        for rule in rules:
            domain = self._extract_domain(rule)
            if domain:
                # 每个域名只保留一条规则（优先保留更通用的）
                if domain not in domain_rules:
                    domain_rules[domain] = rule
                else:
                    # 如果新规则更通用（更短或包含通配符），则替换
                    existing = domain_rules[domain]
                    if self._is_more_general(rule, existing):
                        domain_rules[domain] = rule
            else:
                other_rules.append(rule)
        
        # 合并结果
        result = list(domain_rules.values()) + other_rules
        after = len(result)
        elapsed = time.time() - start_time
        
        self.stats['stage2_domain']['before'] = before
        self.stats['stage2_domain']['after'] = after
        
        print(f"    🎯 域名去重: {before:,} → {after:,} 条 (-{before-after:,}), 耗时: {elapsed:.2f}s")
        
        return result
    
    def _subdomain_optimize(self, rules: List[str]) -> List[str]:
        """子域名优化（第三阶段）"""
        if len(rules) < 10000:  # 规则较少时跳过
            return rules
        
        start_time = time.time()
        before = len(rules)
        
        # 提取域名规则
        domain_to_rule = {}
        other_rules = []
        
        for rule in rules:
            domain = self._extract_domain(rule)
            if domain:
                domain_to_rule[domain] = rule
            else:
                other_rules.append(rule)
        
        # 构建域名树
        domain_tree = {}
        for domain in domain_to_rule.keys():
            parts = domain.split('.')
            current = domain_tree
            for part in reversed(parts):
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        # 优化：移除不必要的子域名
        optimized_domains = set()
        for domain in domain_to_rule.keys():
            parts = domain.split('.')
            current = domain_tree
            
            # 检查是否是其他域名的子域名
            is_subdomain = False
            for i in range(1, len(parts)):
                parent = '.'.join(parts[i:])
                if parent in domain_to_rule:
                    is_subdomain = True
                    break
            
            if not is_subdomain:
                optimized_domains.add(domain)
        
        # 构建结果
        result = [domain_to_rule[d] for d in optimized_domains] + other_rules
        after = len(result)
        elapsed = time.time() - start_time
        
        self.stats['stage3_subdomain']['before'] = before
        self.stats['stage3_subdomain']['after'] = after
        
        print(f"    🎯 子域名优化: {before:,} → {after:,} 条 (-{before-after:,}), 耗时: {elapsed:.2f}s")
        
        return result
    
    def _extract_domain(self, rule: str) -> Optional[str]:
        """从规则中提取域名"""
        if rule.startswith('||') and '^' in rule:
            return rule[2:].split('^')[0]
        elif rule.startswith(('0.0.0.0 ', '127.0.0.1 ')):
            parts = rule.split()
            if len(parts) >= 2:
                return parts[1]
        elif DOMAIN_PATTERN.match(rule):
            return rule
        return None
    
    def _is_more_general(self, rule1: str, rule2: str) -> bool:
        """判断rule1是否比rule2更通用"""
        # 规则1包含通配符而规则2不包含
        if '*' in rule1 and '*' not in rule2:
            return True
        
        # 规则1是域名规则（||domain^）而规则2是更具体的规则
        if rule1.startswith('||') and not rule2.startswith('||'):
            return True
        
        # 规则1比规则2短（通常更通用）
        if len(rule1) < len(rule2):
            return True
        
        return False

class AdvancedRuleOptimizer:
    """高级规则优化器"""
    
    def __init__(self):
        self.stats = {
            'by_priority': 0,
            'by_validation': 0,
            'by_quality': 0,
            'total_removed': 0
        }
    
    def optimize(self, rules: List[str]) -> List[str]:
        """优化规则"""
        if not rules:
            return []
        
        print(f"  开始优化 {len(rules):,} 条规则...")
        
        current_rules = rules.copy()
        
        # 1. 按优先级过滤
        if Config.MIN_RULE_PRIORITY > 0:
            current_rules = self._filter_by_priority(current_rules)
        
        # 2. 规则验证
        if Config.ENABLE_RULE_VALIDATION:
            current_rules = self._validate_rules(current_rules)
        
        # 3. 质量过滤
        current_rules = self._filter_by_quality(current_rules)
        
        # 4. 分类和限制
        current_rules = self._classify_and_limit(current_rules)
        
        total_removed = len(rules) - len(current_rules)
        self.stats['total_removed'] = total_removed
        
        print(f"  优化完成: {len(current_rules):,} 条 (移除 {total_removed:,} 条)")
        
        return current_rules
    
    def _filter_by_priority(self, rules: List[str]) -> List[str]:
        """按优先级过滤"""
        start_time = time.time()
        before = len(rules)
        
        filtered_rules = []
        for rule in rules:
            score = Config.get_priority_score(rule)
            if score >= Config.MIN_RULE_PRIORITY:
                filtered_rules.append(rule)
        
        after = len(filtered_rules)
        elapsed = time.time() - start_time
        
        self.stats['by_priority'] = before - after
        print(f"    🎯 优先级过滤: {before:,} → {after:,} 条 (-{before-after:,}), 耗时: {elapsed:.2f}s")
        
        return filtered_rules
    
    def _validate_rules(self, rules: List[str]) -> List[str]:
        """验证规则有效性"""
        start_time = time.time()
        before = len(rules)
        
        valid_rules = []
        for rule in rules:
            if SmartRuleParser.is_valid_rule(rule):
                valid_rules.append(rule)
        
        after = len(valid_rules)
        elapsed = time.time() - start_time
        
        self.stats['by_validation'] = before - after
        print(f"    🎯 规则验证: {before:,} → {after:,} 条 (-{before-after:,}), 耗时: {elapsed:.2f}s")
        
        return valid_rules
    
    def _filter_by_quality(self, rules: List[str]) -> List[str]:
        """按质量过滤"""
        start_time = time.time()
        before = len(rules)
        
        quality_rules = []
        for rule in rules:
            # 跳过明显低质量的规则
            if self._is_low_quality(rule):
                continue
            quality_rules.append(rule)
        
        after = len(quality_rules)
        elapsed = time.time() - start_time
        
        self.stats['by_quality'] = before - after
        print(f"    🎯 质量过滤: {before:,} → {after:,} 条 (-{before-after:,}), 耗时: {elapsed:.2f}s")
        
        return quality_rules
    
    def _is_low_quality(self, rule: str) -> bool:
        """判断是否为低质量规则"""
        # 规则过长或过短
        if len(rule) < 3 or len(rule) > 500:
            return True
        
        # 包含过多特殊字符
        special_chars = ['*', '^', '|', '#', '!']
        char_count = sum(1 for char in rule if char in special_chars)
        if char_count > 5:
            return True
        
        # 疑似无效的域名
        if rule.startswith('||') and '^' in rule:
            domain = rule[2:].split('^')[0]
            if len(domain.split('.')) > 5:  # 过多子域名
                return True
        
        return False
    
    def _classify_and_limit(self, rules: List[str]) -> List[str]:
        """分类并应用数量限制"""
        start_time = time.time()
        
        # 分类
        adblock_rules = []
        hosts_rules = []
        domain_rules = []
        
        for rule in rules:
            if rule.startswith('||') or '##' in rule or rule.startswith('|'):
                adblock_rules.append(rule)
            elif rule.startswith('0.0.0.0') or rule.startswith('127.0.0.1'):
                hosts_rules.append(rule)
            elif DOMAIN_PATTERN.match(rule):
                domain_rules.append(rule)
        
        # 应用限制
        adblock_rules = adblock_rules[:Config.MAX_ADBLOCK_RULES]
        hosts_rules = hosts_rules[:Config.MAX_HOSTS_RULES]
        domain_rules = domain_rules[:Config.MAX_DOMAIN_RULES]
        
        # 合并
        result = adblock_rules + hosts_rules + domain_rules
        result = result[:Config.MAX_TOTAL_RULES]
        
        # 按优先级排序
        if Config.SORT_BY_PRIORITY:
            result.sort(key=lambda x: Config.get_priority_score(x), reverse=True)
        
        # 按长度排序
        if Config.SORT_BY_LENGTH:
            result.sort(key=lambda x: len(x))
        
        elapsed = time.time() - start_time
        
        print(f"    🎯 分类限制:")
        print(f"      Adblock: {len(adblock_rules):,}/{Config.MAX_ADBLOCK_RULES:,}")
        print(f"      Hosts: {len(hosts_rules):,}/{Config.MAX_HOSTS_RULES:,}")
        print(f"      域名: {len(domain_rules):,}/{Config.MAX_DOMAIN_RULES:,}")
        print(f"      总计: {len(result):,}/{Config.MAX_TOTAL_RULES:,}")
        print(f"      耗时: {elapsed:.2f}s")
        
        return result

class SecondaryOptimizer:
    """二次优化器"""
    
    def __init__(self):
        self.stats = {
            'expired_removed': 0,
            'similar_merged': 0,
            'total_removed': 0
        }
    
    def optimize(self, rules: List[str]) -> List[str]:
        """二次优化"""
        if not Config.ENABLE_SECONDARY_OPTIMIZATION or len(rules) < 1000:
            return rules
        
        print(f"  开始二次优化 {len(rules):,} 条规则...")
        
        current_rules = rules.copy()
        
        # 1. 移除过期/失效规则
        if Config.REMOVE_EXPIRED_DOMAINS:
            current_rules = self._remove_expired_domains(current_rules)
        
        # 2. 合并相似规则
        if Config.MERGE_SIMILAR_RULES:
            current_rules = self._merge_similar_rules(current_rules)
        
        total_removed = len(rules) - len(current_rules)
        self.stats['total_removed'] = total_removed
        
        print(f"  二次优化完成: {len(current_rules):,} 条 (移除 {total_removed:,} 条)")
        
        return current_rules
    
    def _remove_expired_domains(self, rules: List[str]) -> List[str]:
        """移除过期域名"""
        start_time = time.time()
        before = len(rules)
        
        # 常见过期域名模式
        expired_patterns = [
            r'\d{8,}',  # 包含8位以上数字（可能是日期）
            r'20\d{2}[01]\d[0-3]\d',  # 日期格式
            r'expired', r'old', r'dead', r'invalid',
            r'test', r'example', r'dummy'
        ]
        
        filtered_rules = []
        for rule in rules:
            skip = False
            for pattern in expired_patterns:
                if re.search(pattern, rule, re.IGNORECASE):
                    skip = True
                    break
            if not skip:
                filtered_rules.append(rule)
        
        after = len(filtered_rules)
        elapsed = time.time() - start_time
        
        self.stats['expired_removed'] = before - after
        print(f"    🎯 移除过期域名: {before:,} → {after:,} 条 (-{before-after:,}), 耗时: {elapsed:.2f}s")
        
        return filtered_rules
    
    def _merge_similar_rules(self, rules: List[str]) -> List[str]:
        """合并相似规则"""
        if len(rules) < 5000:  # 规则较少时跳过
            return rules
        
        start_time = time.time()
        before = len(rules)
        
        # 按规则类型分组
        adblock_groups = defaultdict(list)
        hosts_groups = defaultdict(list)
        domain_groups = defaultdict(list)
        other_rules = []
        
        for rule in rules:
            if rule.startswith('||') and '^' in rule:
                domain = rule[2:].split('^')[0]
                base_domain = '.'.join(domain.split('.')[-2:])  # 取主域名
                adblock_groups[base_domain].append(rule)
            elif rule.startswith(('0.0.0.0 ', '127.0.0.1 ')):
                parts = rule.split()
                if len(parts) >= 2:
                    domain = parts[1]
                    base_domain = '.'.join(domain.split('.')[-2:])
                    hosts_groups[base_domain].append(rule)
            elif DOMAIN_PATTERN.match(rule):
                base_domain = '.'.join(rule.split('.')[-2:])
                domain_groups[base_domain].append(rule)
            else:
                other_rules.append(rule)
        
        # 合并每组中的规则（选择最优的一条）
        merged_rules = []
        
        for group in [adblock_groups, hosts_groups, domain_groups]:
            for base_domain, group_rules in group.items():
                if len(group_rules) == 1:
                    merged_rules.append(group_rules[0])
                else:
                    # 选择最优的规则（最短的或包含通配符的）
                    best_rule = min(group_rules, key=lambda x: (
                        len(x),
                        0 if '*' in x else 1  # 优先选择包含通配符的
                    ))
                    merged_rules.append(best_rule)
        
        merged_rules.extend(other_rules)
        after = len(merged_rules)
        elapsed = time.time() - start_time
        
        self.stats['similar_merged'] = before - after
        print(f"    🎯 合并相似规则: {before:,} → {after:,} 条 (-{before-after:,}), 耗时: {elapsed:.2f}s")
        
        return merged_rules

class RuleOutputManager:
    """规则输出管理器"""
    
    @staticmethod
    def save_results(rules: List[str]) -> bool:
        """保存优化后的规则"""
        try:
            os.makedirs("dist", exist_ok=True)
            os.makedirs("stats", exist_ok=True)
            
            current_time = get_time_string()
            
            # 分类规则
            adblock_rules = []
            hosts_rules = []
            domain_rules = []
            
            for rule in rules:
                if rule.startswith('||') or '##' in rule or rule.startswith('|'):
                    adblock_rules.append(rule)
                elif rule.startswith('0.0.0.0') or rule.startswith('127.0.0.1'):
                    hosts_rules.append(rule)
                elif DOMAIN_PATTERN.match(rule):
                    domain_rules.append(rule)
            
            # 保存Adblock规则
            if adblock_rules:
                RuleOutputManager._save_adblock_rules(adblock_rules, current_time)
            
            # 保存Hosts规则
            if hosts_rules:
                RuleOutputManager._save_hosts_rules(hosts_rules, current_time)
            
            # 保存域名规则
            if domain_rules:
                RuleOutputManager._save_domain_rules(domain_rules, current_time)
            
            print(f"  💾 总计保存: {len(rules):,} 条规则")
            return True
            
        except Exception as e:
            print(f"  ❌ 保存失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def _save_adblock_rules(rules: List[str], current_time: str):
        """保存Adblock规则"""
        file_path = "dist/Adblock.txt"
        batch_size = Config.BATCH_PROCESS_SIZE
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"""! Adblock规则 - 多阶段优化版
! 生成时间: {current_time}
! 规则数量: {len(rules):,}
! 项目地址: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
! 优化流程: 下载 → 解析 → 去重 → 优化 → 二次优化 → 输出
!

""")
            # 批量写入
            for i in range(0, len(rules), batch_size):
                batch = rules[i:i+batch_size]
                f.write('\n'.join(batch) + '\n')
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        print(f"  ✅ Adblock规则: {len(rules):,} 条 ({file_size:.2f} MB)")
    
    @staticmethod
    def _save_hosts_rules(rules: List[str], current_time: str):
        """保存Hosts规则"""
        file_path = "dist/hosts.txt"
        batch_size = Config.BATCH_PROCESS_SIZE
        
        # 分离0.0.0.0和127.0.0.1
        zero_rules = [r for r in rules if r.startswith('0.0.0.0')]
        local_rules = [r for r in rules if r.startswith('127.0.0.1')]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"""# Hosts规则 - 多阶段优化版
# 生成时间: {current_time}
# 规则数量: {len(rules):,} (0.0.0.0: {len(zero_rules):,}, 127.0.0.1: {len(local_rules):,})
# 项目地址: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
#

""")
            # 写入0.0.0.0规则
            if zero_rules:
                for i in range(0, len(zero_rules), batch_size):
                    batch = zero_rules[i:i+batch_size]
                    f.write('\n'.join(batch) + '\n')
            
            # 写入127.0.0.1规则
            if local_rules:
                f.write('\n')
                for i in range(0, len(local_rules), batch_size):
                    batch = local_rules[i:i+batch_size]
                    f.write('\n'.join(batch) + '\n')
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        print(f"  ✅ Hosts规则: {len(rules):,} 条 ({file_size:.2f} MB)")
    
    @staticmethod
    def _save_domain_rules(rules: List[str], current_time: str):
        """保存域名规则"""
        file_path = "dist/Domains.txt"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"""# 域名规则 - 多阶段优化版
# 生成时间: {current_time}
# 域名数量: {len(rules):,}
# 项目地址: https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}
#

""")
            # 按字母顺序排序
            sorted_rules = sorted(rules)
            for rule in sorted_rules:
                f.write(f"{rule}\n")
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        print(f"  ✅ 域名规则: {len(rules):,} 条 ({file_size:.2f} MB)")

class SmartRuleProcessor:
    """智能规则处理器（多阶段优化版）"""
    
    def __init__(self):
        self.fetcher = AdvancedRuleFetcher()
        self.multi_stage = MultiStageProcessor()
        self.parser = SmartRuleParser()
        self.deduplicator = MultiStageDeduplicator()
        self.optimizer = AdvancedRuleOptimizer()
        self.secondary_optimizer = SecondaryOptimizer()
        self.output_manager = RuleOutputManager()
        
        # 加载规则源
        try:
            sources = get_all_sources()
            self.rule_sources = sources
        except:
            self.rule_sources = [
                "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
                "https://easylist.to/easylist/easylist.txt",
                "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
                "https://someonewhocares.org/hosts/hosts",
            ]
        
        self.all_rules = []
        self.final_rules = []
        
    def process(self) -> bool:
        """主处理流程"""
        print("=" * 70)
        print("🚀 广告规则自动化处理系统 - 多阶段优化版")
        print(f"📅 开始时间: {get_time_string()}")
        print(f"📊 规则源: {len(self.rule_sources)} 个")
        print(f"⚙️  配置: 并发={Config.MAX_WORKERS}, 超时={Config.REQUEST_TIMEOUT}s")
        print("=" * 70)
        
        # 设置总超时
        signal.alarm(Config.TIMEOUT_FORCE_STOP + 60)
        
        try:
            # 阶段1：下载
            stage_start = self.multi_stage.log_stage_start("阶段1: 下载规则源")
            contents = self._download_sources()
            self.multi_stage.log_stage_end('stage1_download', stage_start, rules=len(contents))
            
            if self._check_timeout():
                return False
            
            # 阶段2：解析
            stage_start = self.multi_stage.log_stage_start("阶段2: 解析规则")
            self._parse_contents(contents)
            self.multi_stage.log_stage_end('stage2_parse', stage_start, rules=len(self.all_rules))
            
            if self._check_timeout():
                return False
            
            # 阶段3：多阶段去重
            stage_start = self.multi_stage.log_stage_start("阶段3: 多阶段去重")
            deduplicated_rules = self.deduplicator.deduplicate(self.all_rules)
            self.multi_stage.log_stage_end('stage3_dedup', stage_start, 
                                          before=len(self.all_rules), 
                                          after=len(deduplicated_rules))
            
            if self._check_timeout():
                return False
            
            # 阶段4：优化
            stage_start = self.multi_stage.log_stage_start("阶段4: 规则优化")
            optimized_rules = self.optimizer.optimize(deduplicated_rules)
            self.multi_stage.log_stage_end('stage4_optimize', stage_start,
                                          before=len(deduplicated_rules),
                                          after=len(optimized_rules))
            
            if self._check_timeout():
                return False
            
            # 阶段5：二次优化
            stage_start = self.multi_stage.log_stage_start("阶段5: 二次优化")
            final_rules = self.secondary_optimizer.optimize(optimized_rules)
            self.multi_stage.log_stage_end('stage5_secondary', stage_start,
                                          before=len(optimized_rules),
                                          after=len(final_rules))
            
            self.final_rules = final_rules
            
            if self._check_timeout():
                return False
            
            # 阶段6：输出
            stage_start = self.multi_stage.log_stage_start("阶段6: 保存结果")
            success = self.output_manager.save_results(final_rules)
            self.multi_stage.log_stage_end('stage6_output', stage_start, rules=len(final_rules))
            
            # 生成报告
            self._generate_final_report(success)
            
            signal.alarm(0)  # 取消超时
            return success
            
        except TimeoutException:
            print("\n⏰ 处理超时，保存已处理的数据...")
            self._save_partial_results()
            return False
        except Exception as e:
            print(f"\n❌ 处理异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _check_timeout(self):
        """检查是否超时"""
        elapsed = time.time() - self.multi_stage.start_time
        if elapsed > Config.TIMEOUT_FORCE_STOP:
            print(f"⏰ 超时保护触发：已运行 {elapsed:.0f} 秒")
            return True
        return False
    
    def _download_sources(self) -> Dict[str, str]:
        """下载所有规则源"""
        contents = {}
        max_workers = min(Config.MAX_WORKERS, len(self.rule_sources))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetcher.fetch_url, url): url 
                      for url in self.rule_sources}
            
            completed = 0
            total = len(self.rule_sources)
            
            for future in as_completed(futures):
                url = futures[future]
                success, content, lines = future.result()
                completed += 1
                
                if success and content:
                    contents[url] = content
                    if completed % 5 == 0:
                        print(f"  [{completed}/{total}] {lines:6d} 行")
                else:
                    if completed % 5 == 0:
                        print(f"  [{completed}/{total}] 失败")
        
        print(f"✅ 下载统计: {len(contents)}成功, {self.fetcher.stats['failed']}失败, "
              f"{self.fetcher.stats['cached']}缓存")
        return contents
    
    def _parse_contents(self, contents: Dict[str, str]):
        """解析所有内容"""
        rule_count = 0
        
        for url, content in contents.items():
            lines = content.split('\n')
            for line in lines:
                parsed = self.parser.parse_line(line)
                if parsed:
                    self.all_rules.append(parsed)
                    rule_count += 1
                
                # 定期检查超时
                if rule_count % 500000 == 0:
                    print(f"  已解析 {rule_count:,} 条规则")
                    if self._check_timeout():
                        return
        
        print(f"✅ 解析完成: {rule_count:,} 条原始规则")
    
    def _save_partial_results(self):
        """保存部分结果（超时情况下）"""
        try:
            if self.final_rules:
                # 保存最终规则
                self.output_manager.save_results(self.final_rules)
            elif self.all_rules:
                # 保存解析后的规则
                os.makedirs("dist", exist_ok=True)
                with open("dist/partial_rules.txt", 'w', encoding='utf-8') as f:
                    f.write(f"! 部分规则 (超时保护)\n")
                    f.write(f"! 生成时间: {get_time_string()}\n")
                    f.write(f"! 规则数量: {len(self.all_rules):,}\n!\n\n")
                    f.write('\n'.join(self.all_rules[:100000]))
                
                print(f"  ⚠️  已保存部分规则 ({len(self.all_rules):,} 条)")
        except:
            pass
    
    def _generate_final_report(self, success: bool):
        """生成最终报告"""
        try:
            elapsed = time.time() - self.multi_stage.start_time
            self.multi_stage.stats['total_time'] = elapsed
            self.multi_stage.stats['final_rules'] = len(self.final_rules)
            
            # 合并所有统计
            full_stats = {
                'processing_info': {
                    'start_time': get_time_string(),
                    'total_duration_seconds': round(elapsed, 2),
                    'status': 'success' if success else 'partial',
                    'timestamp': datetime.now().isoformat()
                },
                'stage_statistics': self.multi_stage.stats,
                'deduplication_stats': self.deduplicator.stats,
                'optimization_stats': self.optimizer.stats,
                'secondary_optimization_stats': self.secondary_optimizer.stats,
                'download_stats': self.fetcher.stats,
                'final_counts': {
                    'adblock_rules': len([r for r in self.final_rules if r.startswith('||') or '##' in r or r.startswith('|')]),
                    'hosts_rules': len([r for r in self.final_rules if r.startswith('0.0.0.0') or r.startswith('127.0.0.1')]),
                    'domain_rules': len([r for r in self.final_rules if DOMAIN_PATTERN.match(r)]),
                    'total_rules': len(self.final_rules)
                },
                'configuration': {
                    'max_workers': Config.MAX_WORKERS,
                    'request_timeout': Config.REQUEST_TIMEOUT,
                    'cache_enabled': Config.CACHE_ENABLED,
                    'max_adblock_rules': Config.MAX_ADBLOCK_RULES,
                    'max_hosts_rules': Config.MAX_HOSTS_RULES,
                    'max_domain_rules': Config.MAX_DOMAIN_RULES,
                    'max_total_rules': Config.MAX_TOTAL_RULES
                }
            }
            
            # 保存JSON报告
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            stats_file = f"stats/processing_stats_{timestamp}.json"
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(full_stats, f, indent=2, ensure_ascii=False)
            
            # 生成Markdown报告
            self._generate_markdown_report(full_stats, timestamp)
            
            # 打印最终总结
            print(f"\n{'='*70}")
            print(f"{'✅ 处理成功' if success else '⚠️  部分完成'}")
            print(f"{'='*70}")
            print(f"⏱️  总耗时: {elapsed:.2f} 秒")
            print(f"📊 最终规则: {len(self.final_rules):,} 条")
            print(f"📥 下载统计: {self.fetcher.stats['success']}成功 "
                  f"({self.fetcher.stats['cached']}缓存)")
            print(f"📈 去重效果: {self.deduplicator.stats['total_removed']:,} 条已移除")
            print(f"📈 优化效果: {self.optimizer.stats['total_removed']:,} 条已移除")
            print(f"📁 报告文件: {stats_file}")
            
        except Exception as e:
            print(f"  ⚠️  报告生成失败: {e}")
    
    def _generate_markdown_report(self, stats_data, timestamp):
        """生成Markdown报告"""
        try:
            md_file = f"stats/report_{timestamp}.md"
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(f"# 广告规则处理报告 - 多阶段优化版\n\n")
                f.write(f"**生成时间**: {stats_data['processing_info']['start_time']}\n")
                f.write(f"**处理状态**: {stats_data['processing_info']['status']}\n")
                f.write(f"**总耗时**: {stats_data['processing_info']['total_duration_seconds']}秒\n\n")
                
                f.write(f"## 📊 最终统计\n\n")
                f.write(f"- **总规则数**: {stats_data['final_counts']['total_rules']:,} 条\n")
                f.write(f"- **Adblock规则**: {stats_data['final_counts']['adblock_rules']:,} 条\n")
                f.write(f"- **Hosts规则**: {stats_data['final_counts']['hosts_rules']:,} 条\n")
                f.write(f"- **域名规则**: {stats_data['final_counts']['domain_rules']:,} 条\n\n")
                
                f.write(f"## 📈 处理效果\n\n")
                f.write(f"- **去重移除**: {stats_data['deduplication_stats']['total_removed']:,} 条\n")
                f.write(f"- **优化移除**: {stats_data['optimization_stats']['total_removed']:,} 条\n")
                f.write(f"- **二次优化移除**: {stats_data['secondary_optimization_stats']['total_removed']:,} 条\n\n")
                
                f.write(f"## ⚙️ 处理配置\n\n")
                f.write(f"- **最大并发数**: {stats_data['configuration']['max_workers']}\n")
                f.write(f"- **请求超时**: {stats_data['configuration']['request_timeout']}秒\n")
                f.write(f"- **缓存启用**: {stats_data['configuration']['cache_enabled']}\n")
                f.write(f"- **Adblock上限**: {stats_data['configuration']['max_adblock_rules']:,} 条\n")
                f.write(f"- **Hosts上限**: {stats_data['configuration']['max_hosts_rules']:,} 条\n")
                f.write(f"- **域名上限**: {stats_data['configuration']['max_domain_rules']:,} 条\n")
                f.write(f"- **总规则上限**: {stats_data['configuration']['max_total_rules']:,} 条\n\n")
                
                f.write(f"## 📁 生成文件\n\n")
                f.write(f"- [Adblock.txt](dist/Adblock.txt)\n")
                f.write(f"- [hosts.txt](dist/hosts.txt)\n")
                f.write(f"- [Domains.txt](dist/Domains.txt)\n")
                f.write(f"- [完整统计报告]({md_file})\n\n")
                
                f.write(f"---\n")
                f.write(f"*报告由智能广告规则自动化系统生成*\n")
            
            print(f"  📋 Markdown报告已保存: {md_file}")
        except Exception as e:
            print(f"  ⚠️  Markdown报告生成失败: {e}")

def main():
    """主函数"""
    print("🔄 启动广告规则自动化处理系统")
    
    def interrupt_handler(sig, frame):
        print("\n\n🛑 用户中断，正在保存当前进度...")
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
