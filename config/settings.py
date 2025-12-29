"""
配置文件 - 广告规则自动化处理系统
"""

# ==================== 基础配置 ====================
class Config:
    # GitHub仓库配置
    REPO_OWNER = "wansheng8"  # 更改为您的用户名
    REPO_NAME = "ad-rule-automation"
    
    # 处理配置
    MAX_WORKERS = 15           # 并发处理数
    REQUEST_TIMEOUT = 30       # 请求超时(秒)
    MAX_RULES_PER_TYPE = 50000 # 每种规则最大数量
    
    # 输出配置
    OUTPUT_DIR = "dist"        # 输出目录
    STATS_DIR = "stats"        # 统计目录
    BACKUP_DIR = "backups"     # 备份目录
    
    # 规则优先级关键词
    HIGH_PRIORITY_KEYWORDS = [
        'ad', 'ads', 'advert', 'track', 'tracker', 'analytics',
        'click', 'banner', 'popup', 'sponsor', 'affiliate'
    ]
    
    MEDIUM_PRIORITY_KEYWORDS = [
        'doubleclick', 'googlead', 'facebook.com/tr',
        'metrics', 'pixel', 'beacon', 'cookie'
    ]
    
    # 文件命名格式
    FILE_FORMATS = {
        'adblock': 'adblock_optimized_{date}.txt',
        'hosts': 'hosts_optimized_{date}.txt',
        'domains': 'domains_{date}.txt',
        'stats': 'stats_{date}.json'
    }
    
    # 支持的规则类型
    RULE_TYPES = ['adblock', 'hosts', 'domain', 'regex', 'element_hiding']
    
    # 更新频率（Cron表达式）
    UPDATE_SCHEDULE = '0 2 * * *'  # 每天UTC 2点（北京时间10点）
    
    @staticmethod
    def get_user_agent():
        """获取User-Agent"""
        return f"AdRuleAutomation/1.0 (+https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME})"

# ==================== 默认规则源 ====================
DEFAULT_RULE_SOURCES = {
    'adblock': [
        "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
        "https://easylist.to/easylist/easylist.txt",
        "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/filters.txt",
        "https://raw.githubusercontent.com/vokins/yhosts/master/data/tvbox.txt"
    ],
    
    'hosts': [
        "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
        "https://someonewhocares.org/hosts/zero/hosts",
        "https://raw.githubusercontent.com/notracking/hosts-blocklists/master/hostnames.txt"
    ],
    
    'domain': [
        "https://raw.githubusercontent.com/anudeepND/blacklist/master/adservers.txt",
        "https://s3.amazonaws.com/lists.disconnect.me/simple_ad.txt"
    ],
    
    'regex': [
        "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/resource-abuse.txt"
    ]
}

# ==================== 分类规则源 ====================
CATEGORIZED_SOURCES = {
    'ads': {
        'name': '广告拦截',
        'sources': DEFAULT_RULE_SOURCES['adblock'][:3]
    },
    'privacy': {
        'name': '隐私保护',
        'sources': [
            "https://easylist.to/easylist/easyprivacy.txt",
            "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/privacy.txt"
        ]
    },
    'malware': {
        'name': '恶意软件',
        'sources': [
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/data/add.Spam/hosts",
            "https://raw.githubusercontent.com/notracking/hosts-blocklists/master/hostnames.txt"
        ]
    },
    'annoyances': {
        'name': '烦人元素',
        'sources': [
            "https://easylist.to/easylist/easyprivacy.txt",
            "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/annoyances.txt"
        ]
    }
}