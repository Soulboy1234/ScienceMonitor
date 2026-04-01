# ScienceMonitor

Space Physics 文献监测、单篇总结、深度解读与周报生成工具。

项目默认采用“本地代码仓库 + 独立输出仓库”的结构：
- 当前仓库 `ScienceMonitor`：代码、配置、测试、虚拟环境、数据库、日志
- 输出仓库 `ScienceMonitorOut`：Obsidian 使用的周报、单篇总结、深读、索引、个人工作区
- 当前默认输出位置：`/Users/liwenbo/Library/Mobile Documents/iCloud~md~obsidian/Documents/AI/ScienceMonitorOut`

## 功能概览

- 监控多个 Space Physics 相关期刊与高影响力观察哨期刊
- 抓取标题、摘要、DOI、发表日期等元数据
- 生成单篇文献总结、深度解读和周报
- 支持 `rules`、`codex_local`、`openai_api` 三种分析后端
- 支持 Obsidian wiki link、article index 和双向链接
- 支持 PDF 工具链自检与项目环境自检

## 目录结构

```text
ScienceMonitor/
├── PROJECT_CONFIG.md         # 根目录配置面板，推荐的日常配置入口
├── README.md
├── config/                   # 机器可读配置
├── data/                     # SQLite、LLM cache 等运行态数据
├── doc/                      # 规则、模板、说明文档
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
- 本地 `codex` CLI：如果使用 `codex_local`
- OpenAI 兼容 API：如果使用 `openai_api`
- `poppler`：如果系统已安装，项目会优先复用；如果没有，项目会回退到本地 PDF 包装器

当前项目不是打包发布形态，没有 `pyproject.toml`。默认通过虚拟环境 + `scripts/requirements/requirements-local.txt` 运行。

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
- [doc/runtime_control/master plan.md](doc/runtime_control/master%20plan.md)

### 4. 配置 LLM 后端

当前默认配置是 `codex_local`，见 [config/analysis.json](config/analysis.json)。

可选模式：
- `rules`：只用规则与模板
- `codex_local`：调用本地 Codex
- `openai_api`：调用外部 API

如果使用 `codex_local`：
- 确保本机已安装并可调用 `codex`
- 如有需要，在 `PROJECT_CONFIG.md` 中填写 `codex_local.executable`

如果使用 `openai_api`，推荐通过环境变量设置 key：

```bash
export SCIENCEMONITOR_OPENAI_API_KEY="YOUR_API_KEY"
```

详细说明见 [doc/user_guides/llm_analysis_readme.md](doc/user_guides/llm_analysis_readme.md)。

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
./scripts/run_science_monitor.sh config-ui
./scripts/run_science_monitor.sh update --date 2026-03-31 --days-back 7 --max-per-source 100
./scripts/run_science_monitor.sh summaries --date 2026-03-31 --window-days 7
./scripts/run_science_monitor.sh report --date 2026-03-31 --window-days 7
./scripts/run_science_monitor.sh daily --date 2026-03-31 --days-back 7 --max-per-source 100
./scripts/run_science_monitor.sh audit --date 2026-03-31 --window-days 7 --max-per-source 100
./scripts/run_science_monitor.sh deep-read --doi 10.xxxx/xxxxx --pdf /path/to/paper.pdf
./scripts/run_science_monitor.sh index
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
- `codex_local / openai_api / rules`
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
2. 如果没有提供 PDF，且配置允许，则按 DOI/题目尝试获取全文
3. 如果拿到了 PDF 或可判定的全文页面，则调用当前 LLM provider 生成深度解读
4. 如果没拿到全文，则明确返回失败并提示提供 PDF

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
./.venv/bin/python -m unittest discover -s tests -v
```

## 相关文档

- [doc/README.md](doc/README.md)
- [doc/user_guides/llm_analysis_readme.md](doc/user_guides/llm_analysis_readme.md)
- [doc/runtime_control/master plan.md](doc/runtime_control/master%20plan.md)
- [doc/user_guides/tasks.md](doc/user_guides/tasks.md)

## 迁移到其他电脑时建议优先检查

1. `./scripts/bootstrap_local_env.sh` 是否成功创建 `.venv`
2. `./scripts/run_science_monitor.sh doctor` 是否无告警
3. [PROJECT_CONFIG.md](PROJECT_CONFIG.md) 里的 `output_root` 是否指向正确的输出仓库
4. LLM provider 是否符合新电脑环境
5. PDF 工具是否能正常用
