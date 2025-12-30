"""
配置文件 - 广告规则自动化处理系统 (实战优化版)
"""
import os
from datetime import datetime

class Config:
    # GitHub仓库配置
    REPO_OWNER = "wansheng8"
    REPO_NAME = "ad-rule-automation"
    
    # ===【实战优化】关键配置 ===
    MAX_WORKERS = 3
    REQUEST_TIMEOUT = 10
    MAX_RULES_PER_TYPE = 150000
    MAX_TOTAL_RULES = 500000
    
    # ===【缓存配置】===
    CACHE_ENABLED = True
    CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '.cache')
    CACHE_EXPIRE_HOURS = 72
    
    # ===【性能安全配置】===
    SKIP_SLOW_SOURCES = True
    TIMEOUT_FORCE_STOP = 1200
    
    # ===【规则自查】===
    RULE_CHECK_ENABLED = False
    RULE_CHECK_SAMPLE_PERCENT = 1
    RULE_CHECK_TIMEOUT = 3
    RULE_CHECK_CONCURRENCY = 3
    RULE_CHECK_MIN_SAMPLE = 20
    RULE_CHECK_MAX_SAMPLE = 100
    
    # 输出目录
    OUTPUT_DIR = "dist"
    STATS_DIR = "stats"
    BACKUP_DIR = "backups"
    CHECK_DIR = "checks"
    
    # 规则关键词
    HIGH_PRIORITY_KEYWORDS = [
        'ad', 'ads', 'advert', 'track', 'tracker', 'analytics',
        'click', 'banner', 'popup', 'sponsor', 'affiliate'
    ]
    
    MEDIUM_PRIORITY_KEYWORDS = [
        'doubleclick', 'googlead', 'facebook.com/tr',
        'metrics', 'pixel', 'beacon', 'cookie'
    ]
    
    # 文件格式
    FILE_FORMATS = {
        'adblock': 'Adblock.txt',
        'hosts': 'hosts.txt',
        'domains': 'Domains.txt',
        'stats': 'stats_{date}.json',
        'check': 'rule_check_{date}.json'
    }
    
    # 规则类型
    RULE_TYPES = ['adblock', 'hosts', 'domain']
    
    # 慢速源黑名单
    SLOW_SOURCES_BLACKLIST = [
        'someonewhocares.org',
        'pgl.yoyo.org',
        'hosts-file.net',
        'winhelp2002.mvps.org',
    ]
    
    @staticmethod
    def get_user_agent():
        return f"AdRuleAutomation/2.0 (+https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME})"
    
    @staticmethod
    def get_current_date():
        return datetime.now().strftime("%Y%m%d")

def load_rule_sources_from_txt():
    """从 rule_sources.txt 加载规则源"""
    txt_path = os.path.join(os.path.dirname(__file__), 'rule_sources.txt')
    yaml_path = os.path.join(os.path.dirname(__file__), 'rule_sources.yaml')
    
    file_to_load = txt_path if os.path.exists(txt_path) else yaml_path if os.path.exists(yaml_path) else None
    
    if not file_to_load:
        print("⚠️  警告：未找到配置文件")
        return []
    
    urls = []
    loaded = 0
    filtered = 0
    
    try:
        with open(file_to_load, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                line = line.strip('"').strip("'")
                if '#' in line:
                    line = line.split('#')[0].strip()
                
                # 过滤慢速源
                if Config.SKIP_SLOW_SOURCES:
                    skip = False
                    for blacklist in Config.SLOW_SOURCES_BLACKLIST:
                        if blacklist in line:
                            filtered += 1
                            skip = True
                            break
                    if skip:
                        continue
                
                if line and '.' in line:
                    urls.append(line)
                    loaded += 1
        
        print(f"✅ 已加载 {loaded} 个规则源，过滤 {filtered} 个慢速源")
        return urls[:100] if len(urls) > 100 else urls
        
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return []

SOURCE_URLS = load_rule_sources_from_txt()

if SOURCE_URLS:
    DEFAULT_RULE_SOURCES = {
        'adblock': SOURCE_URLS,
        'hosts': [],
        'domain': []
    }
    print(f"✅ 配置完成: {len(SOURCE_URLS)} 个规则源")
else:
    DEFAULT_RULE_SOURCES = {
        'adblock': [
            "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
            "https://easylist.to/easylist/easylist.txt",
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
        ],
        'hosts': [],
        'domain': []
    }

def get_rule_sources():
    return DEFAULT_RULE_SOURCES

def get_sources_by_type(source_type):
    return DEFAULT_RULE_SOURCES.get(source_type, [])

def get_all_sources():
    return SOURCE_URLS

if __name__ == "__main__":
    print("配置自检:")
    urls = get_all_sources()
    print(f"- 规则源: {len(urls)} 个")
    if urls:
        print("- 示例:")
        for i, url in enumerate(urls[:3], 1):
            print(f"  {i}. {url}")
