🚀 智能广告规则自动化处理系统
一个全自动的广告规则处理系统，支持数百条规则源的智能识别、优化与合并，每日自动更新，生成纯净的 Adblock 和 Hosts 规则。

✨ 核心特性
海量规则源：支持从数百个公开规则源（如 Easylist, AdGuard, uBlock Origin 等）自动抓取。

智能处理：自动去重、分类，并优化规则优先级。

多格式输出：一键生成适用于浏览器插件（如 uBlock Origin）和系统 hosts 文件的规则。

完全自动化：通过 GitHub Actions 实现每日定时更新，无需手动干预。

透明报告：每次处理均生成详细的统计报告（JSON 和 Markdown 格式）。

📦 获取与使用规则
系统每日自动运行，生成的规则文件可在 dist 目录获取：

🧱 Adblock 规则：适用于 uBlock Origin、AdGuard 等浏览器扩展。

直接订阅链接：https://raw.githubusercontent.com/wansheng8/ad-rule-automation/main/dist/adblock_optimized.txt

🖥️ Hosts 规则：适用于系统 hosts 文件，屏蔽广告与跟踪域名。

直接订阅链接：https://raw.githubusercontent.com/wansheng8/ad-rule-automation/main/dist/hosts_optimized.txt

直接使用：点击上方链接，然后在你的广告拦截器或 hosts 管理工具中添加这些订阅链接即可。

🔧 本地开发与手动运行
如果你想自行修改规则源或手动运行脚本，请按以下步骤操作：

1. 克隆项目
bash
git clone https://github.com/wansheng8/ad-rule-automation.git
cd ad-rule-automation
2. 安装依赖
bash
pip install -r requirements.txt
3. 添加或修改规则源
编辑 config/rule_sources.yaml 文件，按 - "URL" 格式添加或删除规则源链接。

4. 运行处理脚本
bash
python scripts/smart_rule_processor.py
处理完成后，优化后的规则文件将生成在 dist/ 目录，统计报告将生成在 stats/ 目录。

⚙️ 项目配置
主要配置文件位于 config/ 目录：

rule_sources.yaml: 核心配置文件，管理所有规则源 URL 列表。

settings.py: 系统参数设置，如并发数(MAX_WORKERS)、超时时间(REQUEST_TIMEOUT)等。

🤖 自动化流程
本项目通过 GitHub Actions 实现全自动化。工作流文件为 .github/workflows/smart-rules.yml，默认设置为每日（UTC 时间 2:00）自动运行处理脚本并提交更新。

你也可以在 GitHub 仓库的 “Actions” 标签页手动触发工作流。

📊 文件结构
text
ad-rule-automation/
├── .github/workflows/  # GitHub Actions 自动化脚本
├── scripts/            # 核心处理脚本 (smart_rule_processor.py)
├── config/             # 配置文件 (rule_sources.yaml, settings.py)
├── dist/               # 【输出】生成的规则文件 (adblock_optimized.txt, hosts_optimized.txt)
├── stats/              # 【输出】每次运行的详细统计报告
├── rules/              # （可选）原始规则备份
└── README.md           # 本文件
📄 许可证
本项目基于 MIT 许可证开源，详见 LICENSE 文件。

🤝 贡献
欢迎贡献代码、提交新的可靠规则源或提出改进建议！

让广告拦截更智能，让网络浏览更纯净！ 🛡️
