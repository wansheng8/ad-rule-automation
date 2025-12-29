# ad-rule-automation
智能广告规则自动化处理系统

# 🚀 广告规则智能处理系统

![GitHub Actions](https://github.com/wansheng8/ad-rule-automation/actions/workflows/smart-rules.yml/badge.svg)
![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

一个全自动的广告规则处理系统，支持数百条规则源的智能识别、优化和合并。

## ✨ 特性

- **智能识别**：自动识别Adblock、Hosts、域名列表等多种规则格式
- **批量处理**：支持并发获取数百个规则源
- **智能优化**：去重、排序、优先级优化
- **多格式输出**：生成Adblock、Hosts、域名列表等多种格式
- **完全自动化**：GitHub Actions自动定时更新
- **详细统计**：生成完整的处理报告和统计信息

## 📁 项目结构
ad-rule-automation/
├── .github/workflows/ # GitHub Actions工作流
│ └── smart-rules.yml # 自动更新工作流
├── scripts/ # 处理脚本
│ └── smart_rule_processor.py # 核心处理脚本
├── config/ # 配置文件
│ ├── settings.py # 系统配置
│ └── rule_sources.yaml # 规则源配置
├── dist/ # 输出文件（自动生成）
├── stats/ # 统计报告（自动生成）
├── rules/ # 原始规则备份
├── docs/ # 文档
├── requirements.txt # Python依赖
└── README.md # 本文件

## 🚀 快速开始

### 1. 克隆仓库


git clone https://github.com/wansheng8/ad-rule-automation.git
cd ad-rule-automation

### 2. 安装依赖

pip install -r requirements.txt

### 3. 添加规则源

编辑 config/rule_sources.yaml，添加您的规则源URL（每行一个）。

### 4. 运行处理

python scripts/smart_rule_processor.py

⚙️ 配置说明
规则源配置
规则源支持多种格式：

# YAML格式（推荐）
- https://example.com/rules.txt
- https://another.com/list.txt

# 或TXT格式
# 每行一个URL，以#开头的为注释

系统配置

编辑 config/settings.py 调整系统参数：

MAX_WORKERS = 15           # 并发数
REQUEST_TIMEOUT = 30       # 请求超时(秒)
MAX_RULES_PER_TYPE = 50000 # 每种规则最大数量

🔄 自动化流程
系统配置了GitHub Actions自动化工作流：

定时执行：每天UTC时间2点（北京时间10点）自动运行

手动触发：在GitHub仓库的Actions页面手动运行

推送触发：当配置文件更新时自动运行

📊 输出文件
处理完成后，会在 dist/ 目录生成以下文件：

Adblock规则 (adblock_optimized_*.txt)

适用于uBlock Origin、AdGuard等浏览器扩展

包含智能去重和优先级排序

Hosts规则 (hosts_optimized_*.txt)

适用于系统hosts文件

包含0.0.0.0和127.0.0.1两种格式

域名列表 (domains_*.txt)

纯域名列表

适用于DNS过滤或防火墙规则

📈 统计报告
系统自动生成详细的统计报告：

JSON统计 (stats/stats_*.json)：详细的处理统计数据

Markdown报告 (stats/report_*.md)：可读性强的处理报告

GitHub Actions总结：每次运行的摘要信息

🤝 贡献
欢迎贡献代码、规则源或提出建议！

Fork本仓库

创建功能分支 (git checkout -b feature/AmazingFeature)

提交更改 (git commit -m 'Add some AmazingFeature')

推送分支 (git push origin feature/AmazingFeature)

创建Pull Request

📄 许可证
本项目基于MIT许可证开源。详见 LICENSE 文件。

让广告拦截更智能，让网络浏览更纯净！ 🛡️


**创建 `.gitignore`** (已自动生成，可添加):
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual Environment
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Output
dist/*.txt
!dist/README.md
stats/*.json
stats/*.md
backups/

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db

# Temporary files
tmp/
temp/
