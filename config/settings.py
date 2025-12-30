"""
配置文件 - 广告规则自动化处理系统 (多阶段优化版)
"""
import os
from datetime import datetime

class Config:
    # GitHub仓库配置
    REPO_OWNER = "wansheng8"
    REPO_NAME = "ad-rule-automation"
    
    # ===【第一阶段：下载配置】===
    MAX_WORKERS = 8
    REQUEST_TIMEOUT = 15
    CACHE_ENABLED = True
    CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '.cache')
    CACHE_EXPIRE_HOURS = 72
    
    # ===【第二阶段：解析配置】===
    PARSE_MAX_LINE_LENGTH = 1000  # 最大行长度限制
    SKIP_COMMENT_LINES = True     # 跳过注释行
    MIN_DOMAIN_LENGTH = 3         # 最小域名长度
    MAX_DOMAIN_LENGTH = 255       # 最大域名长度
    
    # ===【第三阶段：去重配置】===
    ENABLE_MULTI_STAGE_DEDUP = True  # 启用多阶段去重
    # 第一阶段：快速哈希去重
    HASH_DEDUP_ENABLED = True
    # 第二阶段：域名级去重
    DOMAIN_DEDUP_ENABLED = True
    # 第三阶段：子域名优化
    SUBDOMAIN_OPTIMIZATION = True
    
    # ===【第四阶段：优化配置】===
    # 1. 数量限制（大幅提高）
    MAX_ADBLOCK_RULES = 3500000     # Adblock规则上限：100万条
    MAX_HOSTS_RULES = 5000000        # Hosts规则上限：50万条
    MAX_DOMAIN_RULES = 5000000       # 域名规则上限：50万条
    MAX_TOTAL_RULES = 20000000       # 总规则数上限：200万条
    
    # 2. 规则质量过滤
    MIN_RULE_PRIORITY = 0          # 最低优先级（0-100）
    ENABLE_RULE_VALIDATION = True  # 启用规则验证
    
    # 3. 性能优化
    BATCH_PROCESS_SIZE = 100000    # 批处理大小
    TIMEOUT_FORCE_STOP = 1800      # 30分钟超时保护
    
    # ===【第五阶段：二次优化配置】===
    ENABLE_SECONDARY_OPTIMIZATION = True
    # 1. 移除过期/失效规则
    REMOVE_EXPIRED_DOMAINS = True
    # 2. 合并相似规则
    MERGE_SIMILAR_RULES = True
    SIMILARITY_THRESHOLD = 0.8     # 相似度阈值（0-1）
    # 3. 规则排序优化
    SORT_BY_PRIORITY = True
    SORT_BY_LENGTH = True
    
    # ===【文件输出配置】===
    OUTPUT_DIR = "dist"
    STATS_DIR = "stats"
    BACKUP_DIR = "backups"
    CHECK_DIR = "checks"
    
    # ===【规则优先级关键词】===
    HIGH_PRIORITY_KEYWORDS = [
        'ad', 'ads', 'advert', 'track', 'tracker', 'analytics',
        'click', 'banner', 'popup', 'sponsor', 'affiliate',
        'doubleclick', 'googlead', 'facebook.com/tr',
        'metrics', 'pixel', 'beacon', 'cookie',
        'adsystem', 'adserver', 'adservice', 'advertise',
        'marketing', 'monetize', 'promo', 'affiliate',
        'spam', 'malware', 'phishing', 'scam'
    ]
    
    MEDIUM_PRIORITY_KEYWORDS = [
        'analytic', 'statistic', 'measure',
        'count', 'log', 'record',
        'widget', 'plugin', 'extension',
        'script', 'code', 'js', 'javascript'
    ]
    
    LOW_PRIORITY_KEYWORDS = [
        'cdn', 'cloud', 'service',
        'api', 'gateway', 'endpoint',
        'static', 'asset', 'resource'
    ]
    
    # ===【文件命名格式】===
    FILE_FORMATS = {
        'adblock': 'Adblock.txt',
        'hosts': 'hosts.txt',
        'domains': 'Domains.txt',
        'stats': 'stats_{date}.json',
        'check': 'rule_check_{date}.json',
        'backup': 'backup_{date}.tar.gz'
    }
    
    # ===【性能监控】===
    ENABLE_PERFORMANCE_MONITORING = True
    LOG_MEMORY_USAGE = True
    LOG_PROCESSING_TIME = True
    
    @staticmethod
    def get_user_agent():
        return f"AdRuleAutomation/4.0 (+https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME})"
    
    @staticmethod
    def get_current_date():
        return datetime.now().strftime("%Y%m%d")
    
    @staticmethod
    def get_priority_score(rule: str) -> int:
        """计算规则优先级分数"""
        score = 0
        rule_lower = rule.lower()
        
        for keyword in Config.HIGH_PRIORITY_KEYWORDS:
            if keyword in rule_lower:
                score += 3
                break
                
        for keyword in Config.MEDIUM_PRIORITY_KEYWORDS:
            if keyword in rule_lower:
                score += 2
                break
                
        for keyword in Config.LOW_PRIORITY_KEYWORDS:
            if keyword in rule_lower:
                score += 1
                break
        
        # 基于规则类型加分
        if rule.startswith('||') and rule.endswith('^'):
            score += 2  # 域名级规则
        elif '##' in rule:
            score += 1  # 元素隐藏规则
        
        return score

# ==================== 配置加载函数 ====================
def load_rule_sources_from_txt():
    """从 rule_sources.txt 文件加载规则源列表（不自动过滤）"""
    txt_path = os.path.join(os.path.dirname(__file__), 'rule_sources.txt')
    yaml_path = os.path.join(os.path.dirname(__file__), 'rule_sources.yaml')
    
    file_to_load = None
    
    # 确定加载哪个文件
    if os.path.exists(txt_path):
        file_to_load = txt_path
    elif os.path.exists(yaml_path):
        file_to_load = yaml_path
        print(f"⚠️  发现旧版 rule_sources.yaml 文件，建议重命名为 rule_sources.txt")
    else:
        print(f"⚠️  警告：未找到配置文件 rule_sources.txt 或 rule_sources.yaml")
        return []
    
    urls = []
    loaded_count = 0
    
    try:
        with open(file_to_load, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                original_line = line.rstrip('\n\r')
                line = original_line.strip()
                
                # 跳过空行
                if not line:
                    continue
                    
                # 跳过以#开头的注释行
                if line.startswith('#'):
                    continue
                
                # 去除字符串首尾的双引号或单引号
                line = line.strip('"').strip("'")
                
                # 去除行尾的注释（#之后的内容）
                if '#' in line:
                    line = line.split('#')[0].strip()
                
                # 最终检查：行不能为空，且应包含点号（简易URL检查）
                if line and '.' in line:
                    urls.append(line)
                    loaded_count += 1
                else:
                    print(f"  警告：第 {line_num} 行内容无效，已跳过: {original_line[:60]}")
        
        print(f"✅ 已从 {os.path.basename(file_to_load)} 加载 {loaded_count} 个规则源")
        return urls
        
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        import traceback
        traceback.print_exc()
        return []

# ==================== 动态生成默认规则源 ====================
# 加载规则源列表
SOURCE_URLS = load_rule_sources_from_txt()

if SOURCE_URLS:
    DEFAULT_RULE_SOURCES = {
        'adblock': SOURCE_URLS,
        'hosts': [],
        'domain': []
    }
    print(f"✅ 配置解析完成，共 {len(SOURCE_URLS)} 个规则源。")
else:
    print("⚠️  配置文件为空或读取失败，使用内置默认规则源")
    DEFAULT_RULE_SOURCES = {
        'adblock': [
            "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
            "https://easylist.to/easylist/easylist.txt",
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            "https://someonewhocares.org/hosts/hosts",
        ],
        'hosts': [],
        'domain': []
    }

# ==================== 辅助函数 ====================
def get_rule_sources():
    """获取规则源字典（兼容旧代码）"""
    return DEFAULT_RULE_SOURCES

def get_sources_by_type(source_type):
    """按类型获取规则源"""
    return DEFAULT_RULE_SOURCES.get(source_type, [])

def get_all_sources():
    """
    获取所有规则源URL的扁平列表。
    这是主脚本 smart_rule_processor.py 调用的核心函数。
    """
    return SOURCE_URLS

# ==================== 初始化检查 ====================
if __name__ == "__main__":
    print("配置模块自检:")
    urls = get_all_sources()
    print(f"- 加载的规则源数量: {len(urls)}")
    if urls:
        print("- 前5个规则源:")
        for i, url in enumerate(urls[:5], 1):
            print(f"  {i}. {url}")
    
    print(f"\n- Adblock规则上限: {Config.MAX_ADBLOCK_RULES:,} 条")
    print(f"- Hosts规则上限: {Config.MAX_HOSTS_RULES:,} 条")
    print(f"- 域名规则上限: {Config.MAX_DOMAIN_RULES:,} 条")
    print(f"- 总规则数上限: {Config.MAX_TOTAL_RULES:,} 条")
