#!/usr/bin/env python3
"""
智能广告规则处理器 - 修改版
"""

import sys
import os
import asyncio
import aiohttp
from datetime import datetime
from typing import List, Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.settings import get_all_sources, Config
    RULE_SOURCES = get_all_sources()  # 获取所有规则源
    print(f"✅ 从配置文件加载了 {len(RULE_SOURCES)} 个规则源")
except ImportError as e:
    print(f"❌ 导入配置失败: {e}")
    # 使用默认规则源作为后备
    RULE_SOURCES = [
        "https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/BaseFilter/sections/adservers.txt",
        "https://easylist.to/easylist/easylist.txt",
        "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
        "https://someonewhocares.org/hosts/zero/hosts"
    ]
    print(f"⚠️  使用默认规则源 ({len(RULE_SOURCES)} 个)")

# 原有的函数定义...
async def fetch_rules():
    """获取规则"""
    print(f"📥 获取 {len(RULE_SOURCES)} 个规则源...")
    
    # 使用 Config.MAX_WORKERS 设置并发数
    # ... 原有的处理逻辑 ...

# 主函数
def main():
    print("=== 开始运行脚本 ===")
    print(datetime.now().strftime("%a %b %d %H:%M:%S %Y"))
    print("=" * 60)
    
    # 显示实际加载的规则源数量
    print(f"🔄 开始处理广告规则")
    print(f"📅 当前上海时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 配置规则源数量: {len(RULE_SOURCES)}")
    print("=" * 60)
    
    # 运行主处理逻辑
    asyncio.run(fetch_rules())
    
if __name__ == "__main__":
    main()
