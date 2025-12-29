"""
配置文件 - 广告规则自动化处理系统
"""

import os
import yaml
from datetime import datetime

# ==================== 基础配置 ====================
class Config:
    # GitHub仓库配置
    REPO_OWNER = "wansheng8"
    REPO_NAME = "ad-rule-automation"
    
    # 处理配置
    MAX_WORKERS = 30           # 并发处理数（根据规则源数量调高）
    REQUEST_TIMEOUT = 60       # 请求超时(秒)（根据规则源数量调高）
    MAX_RULES_PER_TYPE = 200000  # 每种规则最大数量
    
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
    
    @staticmethod
    def get_current_date():
        """获取当前日期字符串"""
        return datetime.now().strftime("%Y%m%d")

# ==================== 配置加载函数 ====================
def load_rule_sources_from_yaml():
    """
    从 rule_sources.yaml 文件加载规则源列表
    如果文件不存在或读取失败，则返回空字典
    """
    yaml_path = os.path.join(os.path.dirname(__file__), 'rule_sources.yaml')
    
    if not os.path.exists(yaml_path):
        print(f"⚠️  警告：配置文件未找到 - {yaml_path}")
        return {}
    
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            yaml_content = yaml.safe_load(f)
        
        # 支持两种格式：纯URL列表或包含sources键的字典
        if isinstance(yaml_content, list):
            # 纯URL列表格式，将所有URL归到'adblock'类别
            return {'adblock': yaml_content}
        elif isinstance(yaml_content, dict):
            # 结构化格式，直接使用
            return yaml_content
        else:
            print(f"⚠️  警告：YAML文件格式不支持 - {yaml_path}")
            return {}
            
    except yaml.YAMLError as e:
        print(f"❌  YAML解析错误 - {yaml_path}: {e}")
        return {}
    except Exception as e:
        print(f"❌ 读取配置文件失败 - {yaml_path}: {e}")
        return {}

# ==================== 动态生成默认规则源 ====================
# 优先从 YAML 文件加载
YAML_SOURCES = load_rule_sources_from_yaml()

# 如果 YAML 文件加载成功，则使用它；否则回退到硬编码的默认值
if YAML_SOURCES:
    DEFAULT_RULE_SOURCES = YAML_SOURCES
    # 计算总规则源数量
    total_sources = sum(len(urls) for urls in YAML_SOURCES.values() if isinstance(urls, list))
    print(f"✅ 已从 rule_sources.yaml 加载 {total_sources} 个规则源")
else:
    # 原有的硬编码默认值（保底，防止出错）
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
    print("ℹ️  使用内置默认规则源（未找到或未使用YAML配置）")

# ==================== 分类规则源（可选） ====================
# 如果你不需要分类，可以删除或清空这部分
CATEGORIZED_SOURCES = {}

# ==================== 辅助函数 ====================
def get_rule_sources():
    """获取规则源（兼容旧代码）"""
    return DEFAULT_RULE_SOURCES

def get_sources_by_type(source_type):
    """按类型获取规则源"""
    return DEFAULT_RULE_SOURCES.get(source_type, [])

def get_all_sources():
    """获取所有规则源URL的扁平列表"""
    all_sources = []
    for source_list in DEFAULT_RULE_SOURCES.values():
        if isinstance(source_list, list):
            all_sources.extend(source_list)
    return all_sources

# ==================== 初始化检查 ====================
if __name__ == "__main__":
    # 模块导入时进行简单测试
    print(f"配置加载检查:")
    print(f"- MAX_WORKERS: {Config.MAX_WORKERS}")
    print(f"- REQUEST_TIMEOUT: {Config.REQUEST_TIMEOUT}")
    print(f"- 规则源总数: {len(get_all_sources())}")
    
    # 显示各类型规则源数量
    for source_type, urls in DEFAULT_RULE_SOURCES.items():
        if isinstance(urls, list):
            print(f"- {source_type}: {len(urls)} 个")
