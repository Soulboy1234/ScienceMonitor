# ScienceMonitor

Space Physics 文献监测、单篇总结、深度解读与周报生成工具。

项目默认采用“本地代码仓库 + 独立输出仓库”的结构：
- 当前仓库 `ScienceMonitor`：代码、配置、测试、虚拟环境、数据库、日志
- 输出目录：Obsidian 使用的周报、单篇总结、深读、索引、个人工作区
- 当前默认输出位置：`out/`。如需接入 Obsidian vault，请在 [PROJECT_CONFIG.md](PROJECT_CONFIG.md) 中修改 `config/paths.json` 同步块。

## 功能概览

- 监控多个 Space Physics 相关期刊与高影响力观察哨期刊
- 抓取标题、摘要、DOI、发表日期等元数据
- 生成单篇文献总结、深度解读和周报
- 支持 `codex_local`、`openai_api`、`chatgpt_web_manual` 三种分析后端
- 支持 Obsidian wiki link、article index 和双向链接
- 支持 PDF 工具链自检与项目环境自检

## 目录结构

```text
ScienceMonitor/
├── evals/                    # golden eval 与真实论文集成评测
├── PROJECT_CONFIG.md         # 根目录配置面板，推荐的日常配置入口
├── README.md
├── config/                   # 机器可读配置与运行时模板
│   └── templates/            # 程序运行时直接消费的模板资产
├── data/                     # SQLite、LLM cache 等运行态数据
├── docs/                     # 规则、说明文档与执行计划
├── log/                      # 审计日志、LLM 临时文件
├── scripts/                  # 环境初始化、运行脚本
├── src/                      # 主代码
├── tests/                    # 自动化测试
├── science_monitor.py        # 主入口
└── scripts/requirements/requirements-local.txt
```

## 运行环境

推荐环境：
- macOS 或 Linux
- Python `3.10+`
- 可联网
- 可写本地磁盘

可选环境：
- 本地 `codex` CLI：只有使用 `codex_local` 时才需要
- OpenAI 兼容 API：如果使用 `openai_api`
- ChatGPT 网页：如果使用 `chatgpt_web_manual`
- `poppler`：如果系统已安装，项目会优先复用；如果没有，项目会回退到本地 PDF 包装器

当前项目不是打包发布形态，没有 `pyproject.toml`。默认通过虚拟环境 + `scripts/requirements/requirements-local.txt` 运行。

项目不依赖 Codex desktop 或 Codex app 本身。

- 如果选择 `openai_api`，只要提供可用模型和 API key，就可以脱离 Codex 环境运行
- 只有 `codex_local` provider 才依赖本地 `codex` CLI
- 如果选择 `chatgpt_web_manual`，程序本身不调用外部 API，但需要人工把请求包交给 ChatGPT 网页并导回响应

## 依赖包

Python 依赖在 [scripts/requirements/requirements-local.txt](scripts/requirements/requirements-local.txt)：
- `pypdf`
- `pdfplumber`
- `pymupdf`
- `reportlab`

PDF 命令行工具优先使用：
- `pdftotext`
- `pdfinfo`
- `pdftoppm`

如果系统没有这些命令，[scripts/bootstrap_local_env.sh](scripts/bootstrap_local_env.sh) 会尝试：
1. 通过 `brew install poppler` 安装
2. 如果失败，则在 `.venv/bin/` 下安装本地 Python 包装器

## 部署步骤

### 1. 获取项目

如果你是从 GitHub 部署到新电脑，常见方式如下：

```bash
git clone <your-repo-url> ScienceMonitor
cd ScienceMonitor
```

如果是直接复制当前目录到新电脑，也可以，只要保留完整目录结构即可。

### 2. 初始化项目环境

推荐直接运行：

```bash
./scripts/bootstrap_local_env.sh
```

这个脚本会：
- 创建 `.venv`
- 升级 `pip`
- 安装 [scripts/requirements/requirements-local.txt](scripts/requirements/requirements-local.txt)
- 补齐或包装 PDF 工具

如果你要手动安装，也可以：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r scripts/requirements/requirements-local.txt
```

### 3. 配置项目

日常推荐只改根目录的 [PROJECT_CONFIG.md](PROJECT_CONFIG.md)。

程序启动时会读取其中标记为 `## Sync:` 的 JSON 配置块，并同步到：
- [config/runtime.json](config/runtime.json)
- [config/analysis.json](config/analysis.json)
- [config/paths.json](config/paths.json)

常见需要改的项目：
- 默认调研时间范围
- 每个期刊的抓取上限
- 是否启用 LLM
- LLM provider 和模型
- 输出目录 `output_root`

高级配置仍然直接编辑这些文件：
- [config/sources.json](config/sources.json)
- [config/topics.json](config/topics.json)
- [config/focus_tags.json](config/focus_tags.json)
- [config/templates/article_summary_template.md](config/templates/article_summary_template.md)
- [config/templates/daily_report_template.md](config/templates/daily_report_template.md)
- [config/templates/deep_reading_report_template.md](config/templates/deep_reading_report_template.md)

研究偏好和重点提醒不要直接改 JSON，改 [PROJECT_CONFIG.md](PROJECT_CONFIG.md) 里的 `## Sync: config/research_preferences.json` 段。

### 4. 配置 LLM 后端

当前默认配置是 `codex_local`，见 [config/analysis.json](config/analysis.json)。

可选模式：
- `codex_local`：调用本地 Codex
- `openai_api`：调用外部 API
- `chatgpt_web_manual`：生成人工中转请求包，由你在 ChatGPT 网页完成分析后再导回结果

说明：
- 单篇总结、周报和深度解读已不再支持规则法文本生成
- 规则逻辑仍保留在抓取、过滤、标签归一化、模板校验和一致性检查等护栏层

如果使用 `codex_local`：
- 确保本机已安装并可调用 `codex`
- 如有需要，在 `PROJECT_CONFIG.md` 中填写 `codex_local.executable`

如果使用 `openai_api`，推荐通过环境变量设置 key：

```bash
export SCIENCEMONITOR_OPENAI_API_KEY="YOUR_API_KEY"
```

详细说明见 [docs/user_guides/llm_analysis_readme.md](docs/user_guides/llm_analysis_readme.md)。
如果使用 `chatgpt_web_manual`，工作流说明见 [docs/user_guides/chatgpt_web_manual_workflow.md](docs/user_guides/chatgpt_web_manual_workflow.md)。

如果你的目标是“脱离 Codex 环境独立运行”，推荐直接用：

- `provider=openai_api`
- 正确的 `SCIENCEMONITOR_OPENAI_API_KEY`
- 可访问的 `openai_api.base_url`
- 已安装好的 Python 依赖和 PDF 工具链

如果你的目标是“尽量减少 Codex 与 API 消耗”，可以改用：

- `provider=chatgpt_web_manual`
- 运行现有命令后处理 `data/chatgpt_web_manual/requests/` 下的请求包
- 用 `manual-llm-import` 导入响应，再重新执行原命令

### 5. 运行自检

首次部署或迁移到新电脑后，先跑：

```bash
./scripts/run_science_monitor.sh doctor
```

它会检查：
- 当前解释器是不是项目 `.venv`
- `PATH` 是否优先命中 `.venv/bin`
- `pdftotext`、`pdfinfo`、`pdftoppm` 是否可用
- 当前 LLM provider 是什么
- `codex` 是否可用
- `openai_api` 的 key 是否就绪
- 输出目录是否存在

### 6. 开始运行

推荐统一使用：

```bash
./scripts/run_science_monitor.sh <command> ...
```

常用命令：

```bash
./scripts/run_science_monitor.sh sources
./scripts/run_science_monitor.sh doctor
./scripts/run_science_monitor.sh entropy-check
./scripts/run_science_monitor.sh maintenance-check --auto-repair
./scripts/run_science_monitor.sh manual-llm-status
./scripts/run_science_monitor.sh config-ui
./scripts/run_science_monitor.sh update --date 2026-03-31 --days-back 7 --max-per-source 100
./scripts/run_science_monitor.sh summaries --date 2026-03-31 --window-days 7
./scripts/run_science_monitor.sh report --date 2026-03-31 --window-days 7
./scripts/run_science_monitor.sh daily --date 2026-03-31 --days-back 7 --max-per-source 100
./scripts/run_science_monitor.sh audit --date 2026-03-31 --window-days 7 --max-per-source 100
./scripts/run_science_monitor.sh deep-read --doi 10.xxxx/xxxxx --pdf /path/to/paper.pdf
./scripts/run_science_monitor.sh tag-candidates --min-count 2 --limit 50
./scripts/run_science_monitor.sh real-eval --case-ids 2024_epp_superstorm_it_diff
./scripts/run_science_monitor.sh index
```

人工中转常用命令：

```bash
./scripts/run_science_monitor.sh manual-llm-status --pending-only
./scripts/run_science_monitor.sh manual-llm-import --request-id <request_id>
```

## 输出与路径

输出根目录由 [config/paths.json](config/paths.json) 中的 `output_root` 决定。

默认输出结构：
- `research_reports/`：周报与 `latest.md`
- `auto/article_summaries/`：单篇总结
- `auto/deep_reads/`：深度解读
- `auto/deep_reads_pdf/`：深读关联 PDF
- `article_index/`：Obsidian 文章索引
- `my_work/`：个人工作知识库

运行态数据默认仍保留在当前仓库：
- [data](data)
- [log](log)

如果你想把运行态也迁走，可以用环境变量：

```bash
export SCIENCEMONITOR_STATE_ROOT="$HOME/Library/Application Support/ScienceMonitor"
export SCIENCEMONITOR_DATA_ROOT="$HOME/Library/Application Support/ScienceMonitor/data"
export SCIENCEMONITOR_LOG_ROOT="$HOME/Library/Application Support/ScienceMonitor/log"
```

## 根目录配置面板

[PROJECT_CONFIG.md](PROJECT_CONFIG.md) 是推荐的配置入口。

它的定位是：
- 人类可读
- 适合日常改默认参数
- 适合在不同电脑上迁移时快速核对环境与路径

它当前会同步三类配置：
- `config/runtime.json`
- `config/analysis.json`
- `config/paths.json`

你也可以直接打开本地配置界面：

```bash
./scripts/run_science_monitor.sh config-ui
```

或者直接双击根目录里的：
- `启动操作面板.app`
- `关闭操作面板.app`

这个界面适合调整：
- 默认时间窗口
- 每个来源抓取上限
- 周报功能开关
- 深度解读功能开关
- 缺少 PDF 时是否自动搜索全文
- `codex_local / openai_api`
- `codex_local.model`、超时、输出路径等

注意：
- 这个文件里的 `## Sync:` JSON 代码块必须保持合法 JSON
- 程序启动时会把其中内容写回对应的 `config/*.json`
- 关闭浏览器页签不会自动关闭后台控制面板服务；可以用页面里的“关闭面板服务”按钮，或双击 `关闭操作面板.app`
- 如果你直接改了 `config/*.json`，而没有同步更新这个文件，后续启动时会被这里覆盖

## 程序运行逻辑

当前主流程是：
1. 抓取窗口期内文献
2. 生成单篇总结
3. 修复 Obsidian 链接并同步 `article_index`
4. 基于单篇总结生成周报

因此周报不应该早于单篇总结完成。

新增的深度解读流程是：
1. 优先读取你提供的 PDF
2. 如果没有提供 PDF，且配置允许，则按 DOI/题目做简单网页搜索
3. 如果拿到了 PDF 或可判定的全文页面，则调用当前 LLM provider 生成深度解读
4. 如果没拿到可用全文，则明确返回失败并提示提供 PDF

单篇总结与周报在无 PDF 场景下的策略是：
1. 优先尝试网页全文
2. 如果拿不到全文，则退回摘要继续生成
3. 仅基于摘要生成的单篇总结会显式打上 `#信息来源/仅摘要`

常用命令示例：

```bash
./scripts/run_science_monitor.sh deep-read --doi 10.1029/2025JA034650
./scripts/run_science_monitor.sh deep-read --doi 10.1029/2025JA034650 --pdf /absolute/path/to/paper.pdf
./scripts/run_science_monitor.sh deep-read --title "Example Paper Title" --pdf /absolute/path/to/paper.pdf
```

说明：
- `weekly_report_enabled` 是“是否生成周报文件”的功能开关
- `report.enabled` 是“周报是否使用 LLM 分析”的开关，两者不是一回事
- `deep_reads.enabled` 是“是否允许深度解读”的功能开关

## 测试

运行全部测试：

```bash
./.venv/bin/python -m pytest -q
```

运行 golden eval：

```bash
./scripts/run_science_monitor.sh golden-eval
```

运行统一 harness gate：

```bash
./scripts/run_science_monitor.sh harness-check
./scripts/run_science_monitor.sh harness-check --include-real-eval --real-case-ids 2023_sw_resnet_tmd
```

运行代码维护治理：

```bash
./scripts/run_science_monitor.sh entropy-check
./scripts/run_science_monitor.sh maintenance-check
./scripts/run_science_monitor.sh maintenance-check --auto-repair
```

运行真实论文集成评测：

```bash
./scripts/run_science_monitor.sh real-eval
./scripts/run_science_monitor.sh real-eval --case-ids 2023_sw_resnet_tmd,2026_jgr_polar_convection_mohe
./scripts/run_science_monitor.sh real-eval --case-ids 2026_jgr_polar_convection_mohe --include-deep-read
./scripts/run_science_monitor.sh real-eval --check-fixtures
./scripts/run_science_monitor.sh real-eval --update-fixtures
```

说明：

- `golden-eval` 负责固定样例回归
- `real-eval` 负责真实论文集成评测
- `real-eval --check-fixtures` 会把当前真实案例输出和已认可基线比较
- `real-eval --update-fixtures` 只在你确认“新输出更正确”时使用
- `harness-check` 是本地和 CI 的统一 gate，默认只跑 `doctor` 一致性检查和 `golden eval`
- `maintenance-check` 是代码维护 gate，负责“审核 -> 调整 -> 测试 -> 再审核”
- `entropy-check` 负责代码熵预算，不检查业务输出正确性

## 相关文档

- [PROJECT_CONFIG.md](PROJECT_CONFIG.md)
- [docs/README.md](docs/README.md)
- [docs/user_guides/llm_analysis_readme.md](docs/user_guides/llm_analysis_readme.md)
- [docs/user_guides/eval_governance_runbook.md](docs/user_guides/eval_governance_runbook.md)
- [docs/user_guides/maintenance_governance_runbook.md](docs/user_guides/maintenance_governance_runbook.md)
- [config/research_preferences.json](config/research_preferences.json)
- [config/maintenance_budget.json](config/maintenance_budget.json)
- [docs/workflow_specs/source_of_truth_matrix.md](docs/workflow_specs/source_of_truth_matrix.md)

## 迁移到其他电脑时建议优先检查

1. `./scripts/bootstrap_local_env.sh` 是否成功创建 `.venv`
2. `./scripts/run_science_monitor.sh doctor` 是否无告警
3. [PROJECT_CONFIG.md](PROJECT_CONFIG.md) 里的 `output_root` 是否指向正确的输出仓库
4. LLM provider 是否符合新电脑环境
5. PDF 工具是否能正常用
