"""
配置文件 - 广告规则自动化处理系统 (TXT配置版)
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
    MAX_WORKERS = 30
    REQUEST_TIMEOUT = 60
    MAX_RULES_PER_TYPE = 200000
    
    # 输出配置
    OUTPUT_DIR = "dist"
    STATS_DIR = "stats"
    BACKUP_DIR = "backups"
    
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
        'adblock': 'Adblock.txt',
        'hosts': 'hosts.txt',
        'domains': 'Domains.txt',
        'stats': 'stats_{date}.json'
    }
    
    # 支持的规则类型
    RULE_TYPES = ['adblock', 'hosts', 'domain', 'regex', 'element_hiding']
    
    # 更新频率（Cron表达式）
    UPDATE_SCHEDULE = '0 2 * * *'
    
    @staticmethod
    def get_user_agent():
        return f"AdRuleAutomation/1.0 (+https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME})"
    
    @staticmethod
    def get_current_date():
        return datetime.now().strftime("%Y%m%d")

# ==================== 配置加载函数 ====================
def load_rule_sources_from_txt():
    """
    从 rule_sources.txt 文件加载规则源列表。
    格式：每行一个URL，以#开头的为注释行。
    """
    # 尝试 .txt 文件（新格式）
    txt_path = os.path.join(os.path.dirname(__file__), 'rule_sources.txt')
    # 尝试 .yaml 文件（旧格式，兼容过渡）
    yaml_path = os.path.join(os.path.dirname(__file__), 'rule_sources.yaml')
    
    file_to_load = None
    file_type = ''
    
    # 确定要加载哪个文件
    if os.path.exists(txt_path):
        file_to_load = txt_path
        file_type = 'TXT'
    elif os.path.exists(yaml_path):
        file_to_load = yaml_path
        file_type = 'YAML'
        print(f"⚠️  发现旧版 rule_sources.yaml 文件，建议重命名为 rule_sources.txt")
    else:
        print(f"⚠️  警告：未找到配置文件 rule_sources.txt 或 rule_sources.yaml")
        return []
    
    urls = []
    try:
        with open(file_to_load, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                original_line = line.rstrip('\n')
                line = original_line.strip()
                
                # 跳过空行
                if not line:
                    continue
                    
                # 跳过注释行（以#开头）
                if line.startswith('#'):
                    continue
                
                # 去除行内注释（#之后的内容）
                if '#' in line:
                    line = line.split('#')[0].strip()
                    if not line:  # 如果整行都是注释
                        continue
                
                # 验证是否是URL（简单检查）
                if line.startswith(('http://', 'https://')):
                    urls.append(line)
                else:
                    print(f"  警告：第 {line_num} 行格式可能不正确，已跳过: {original_line[:50]}...")
        
        print(f"✅ 已从 {file_type} 文件加载 {len(urls)} 个规则源")
        return urls
        
    except UnicodeDecodeError:
        print(f"❌ 文件编码错误，请确保 {file_to_load} 是 UTF-8 编码")
        return []
    except Exception as e:
        print(f"❌ 读取配置文件失败 {file_to_load}: {e}")
        return []

# ==================== 动态生成默认规则源 ====================
# 加载规则源列表
SOURCE_URLS = load_rule_sources_from_txt()

if SOURCE_URLS:
    DEFAULT_RULE_SOURCES = {
        'adblock': SOURCE_URLS,
        'hosts': [],
        'domain': [],
        'regex': []
    }
    print(f"✅ 配置解析完成，共 {len(SOURCE_URLS)} 个规则源。")
else:
    print("⚠️  配置文件为空或读取失败，使用内置默认规则源")
    DEFAULT_RULE_SOURCES = {
        'adblock': [
            "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
            "https://easylist.to/easylist/easylist.txt",
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            "https://someonewhocares.org/hosts/zero/hosts",
        ],
        'hosts': [],
        'domain': [],
        'regex': []
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
    return SOURCE_URLS  # 直接返回从TXT文件加载的列表

# ==================== 初始化检查 ====================
if __name__ == "__main__":
    print("配置模块自检:")
    urls = get_all_sources()
    print(f"- 加载的规则源数量: {len(urls)}")
    if urls:
        print("- 前3个规则源:")
        for i, url in enumerate(urls[:3], 1):
            print(f"  {i}. {url}")
