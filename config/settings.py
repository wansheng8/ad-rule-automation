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
    MAX_WORKERS = 3                     # 进一步降低到3，避免GitHub Actions限制
    REQUEST_TIMEOUT = 10                # 大幅降低到10秒，快速失败
    MAX_RULES_PER_TYPE = 150000         # 限制最大规则数，防止内存爆炸
    
    # ===【实战优化】缓存配置 ===
    CACHE_ENABLED = True
    CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '.cache')
    CACHE_EXPIRE_HOURS = 72             # 缓存延长到72小时
    
    # ===【新增】性能安全配置 ===
    ENABLE_PERFORMANCE_LIMITS = True    # 启用性能限制
    MAX_TOTAL_RULES = 500000            # 总规则数上限
    SKIP_SLOW_SOURCES = True            # 跳过慢速源
    TIMEOUT_FORCE_STOP = 1200           # 20分钟后强制停止（秒）
    
    # ===【实战优化】规则自查配置 ===
    RULE_CHECK_ENABLED = False          # 先关闭自查，专注解决超时
    RULE_CHECK_SAMPLE_PERCENT = 1       # 如果启用，只抽样1%
    
    # 输出配置
    OUTPUT_DIR = "dist"
    STATS_DIR = "stats"
    BACKUP_DIR = "backups"
    CHECK_DIR = "checks"
    
    # 规则优先级关键词（保持不变）
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
        'adblock': 'Adblock.txt',
        'hosts': 'hosts.txt',
        'domains': 'Domains.txt',
        'stats': 'stats_{date}.json'
    }
    
    # 支持的规则类型
    RULE_TYPES = ['adblock', 'hosts', 'domain']
    
    # 更新频率（Cron表达式）
    UPDATE_SCHEDULE = '0 2 * * *'
    
    # ===【新增】已知问题源黑名单 ===
    SLOW_SOURCES_BLACKLIST = [
        'someonewhocares.org',          # 已知慢速源
        'pgl.yoyo.org',                 # 已知慢速源
        'hosts-file.net',               # 已知慢速源
        'winhelp2002.mvps.org',         # 已知慢速源
    ]
    
    @staticmethod
    def get_user_agent():
        return f"AdRuleAutomation/2.0 (+https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME})"
    
    @staticmethod
    def get_current_date():
        return datetime.now().strftime("%Y%m%d")

# ==================== 配置加载函数 ====================
def load_rule_sources_from_txt():
    """
    从 rule_sources.txt 文件加载规则源列表，自动过滤问题源
    """
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
    skipped_count = 0
    filtered_count = 0
    
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
                
                # 检查是否是已知慢速源
                skip_source = False
                if Config.SKIP_SLOW_SOURCES:
                    for blacklist_domain in Config.SLOW_SOURCES_BLACKLIST:
                        if blacklist_domain in line:
                            print(f"  ⚡ 跳过已知慢速源: {line}")
                            filtered_count += 1
                            skip_source = True
                            break
                
                if skip_source:
                    continue
                
                # 最终检查：行不能为空，且应包含点号（简易URL检查）
                if line and '.' in line:
                    urls.append(line)
                    loaded_count += 1
                else:
                    print(f"  ⚠️ 第 {line_num} 行内容无效，已跳过: {original_line[:60]}")
                    skipped_count += 1
        
        print(f"✅ 已从 {os.path.basename(file_to_load)} 加载 {loaded_count} 个规则源")
        if skipped_count > 0:
            print(f"⚠️  跳过了 {skipped_count} 个无效行")
        if filtered_count > 0:
            print(f"⚡ 过滤了 {filtered_count} 个已知慢速源")
        
        # 如果源太多，自动截取前100个（防止超时）
        if Config.ENABLE_PERFORMANCE_LIMITS and len(urls) > 100:
            print(f"⚠️  规则源过多 ({len(urls)}个)，自动截取前100个")
            urls = urls[:100]
        
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
