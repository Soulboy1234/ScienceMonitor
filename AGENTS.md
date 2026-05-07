# AGENTS.md

## 项目定位

`ScienceMonitor` 是一个面向空间物理文献监测的本地工程，主线流程是：

- 从期刊源抓取论文元数据
- 基于当前 LLM provider 生成单篇总结、深度解读和周报
- 维护适配 Obsidian 的输出目录、文章索引和回链
- 用 doctor、harness、eval、entropy 和 maintenance gate 约束长期演化

默认范围：

- 监测、单篇总结和周报默认围绕空间物理文献
- 深度解读通常也是空间物理论文，但可以覆盖与主线研究相关的其他学科论文
- 当前特别允许并鼓励把与空间物理研究相关的人工智能论文作为深度解读对象

## Agent 启动阅读顺序

新任务先按这个顺序建立上下文：

1. [README.md](README.md)：项目是什么、怎么运行、输出目录边界
2. [ARCHITECTURE.md](ARCHITECTURE.md)：主数据流和子系统边界
3. [PROJECT_CONFIG.md](PROJECT_CONFIG.md)：当前运行配置、provider、路径和研究偏好同步段
4. [docs/exec_plans/GovernanceBoard.md](docs/exec_plans/GovernanceBoard.md)：当前版本、gate 状态、活跃计划和阻塞项
5. [PLANS.md](PLANS.md)：什么时候必须写 ExecPlan
6. [docs/README.md](docs/README.md)：docs 目录分层

按任务追加阅读：

- 输出结构、提示词、模板、标签或研究偏好：读 [docs/workflow_specs/source_of_truth_matrix.md](docs/workflow_specs/source_of_truth_matrix.md)，再读相关 workflow spec
- 全量代码地图：读 [docs/user_guides/python_module_map.md](docs/user_guides/python_module_map.md)
- harness 和发版：读 [docs/user_guides/harness_governance_overview.md](docs/user_guides/harness_governance_overview.md) 与 [docs/user_guides/release_checklist.md](docs/user_guides/release_checklist.md)
- 网页正文抽取、Obsidian vault 或 Obsidian Markdown：读 [docs/user_guides/agent_skill_usage.md](docs/user_guides/agent_skill_usage.md)
- 近期排队事项和长期工程债：读 [docs/exec_plans/Todo.md](docs/exec_plans/Todo.md) 与 [docs/exec_plans/tech_debt_tracker.md](docs/exec_plans/tech_debt_tracker.md)

## 任务分流导航

- 配置、路径、provider、研究偏好：先看 `PROJECT_CONFIG.md`、`config/*.json`、`src/sciencemonitor/config.py`
- CLI 命令或参数：先看 `src/sciencemonitor/cli.py`、`src/sciencemonitor/cli_support.py`
- 抓取、主题过滤、入库：先看 `src/sciencemonitor/pipeline.py`、`src/sciencemonitor/crossref.py`、`src/sciencemonitor/topics.py`、`src/sciencemonitor/storage.py`
- 网页全文、摘要、PDF 文本来源：先看 `src/sciencemonitor/article_fetch.py`、`src/sciencemonitor/article_source_text.py`、`src/sciencemonitor/html_extract.py`
- 单篇总结：先看 `src/sciencemonitor/article_summaries.py` 和 `config/templates/article_summary_template.md`
- 周报：先看 `src/sciencemonitor/reporting.py`、`src/sciencemonitor/reporting_template.py` 和 `config/templates/daily_report_template.md`
- 深度解读：先看 `src/sciencemonitor/deep_reads.py`、`src/sciencemonitor/deep_read_markdown.py` 和 `config/templates/deep_reading_report_template.md`
- LLM provider、prompt、schema、缓存和 token：先看 `src/sciencemonitor/llm.py`、`src/sciencemonitor/llm_contracts.py`、`src/sciencemonitor/analysis_providers.py`、`src/sciencemonitor/token_monitor.py`
- ChatGPT 网页人工中转：先看 `src/sciencemonitor/chatgpt_web_manual.py` 和 [docs/user_guides/chatgpt_web_manual_workflow.md](docs/user_guides/chatgpt_web_manual_workflow.md)
- 标签归一化、审核、转正：先看 `config/tag/formal_tags.md`、`config/tag/pending_tags.md`、`config/focus_tags.json`、`src/sciencemonitor/tags.py`、`src/sciencemonitor/tag_review.py`、`src/sciencemonitor/tag_governance.py`
- Obsidian 输出索引和链接修复：先看 `src/sciencemonitor/article_index.py`、`src/sciencemonitor/article_index_rules.py`、`src/sciencemonitor/article_index_paths.py`
- 本地配置面板：先看 `src/sciencemonitor/config_ui.py`、`src/sciencemonitor/config_ui_page.py`、`src/sciencemonitor/config_ui_actions.py`、`src/sciencemonitor/ui_assets/`
- gate、审计、维护和评测：先看 `src/sciencemonitor/doctor.py`、`src/sciencemonitor/harness.py`、`src/sciencemonitor/harness_audit.py`、`src/sciencemonitor/entropy.py`、`src/sciencemonitor/maintenance.py`、`src/sciencemonitor/golden_eval.py`、`src/sciencemonitor/real_case_eval.py`

## 常用命令速查

统一入口：

- 本地运行：`./scripts/run_science_monitor.sh <command>`
- 全量测试：`./.venv/bin/python -m pytest -q`
- 列出期刊：`./scripts/run_science_monitor.sh sources`
- 环境自检：`./scripts/run_science_monitor.sh doctor`
- 配置一致性自检：`./scripts/run_science_monitor.sh doctor --consistency-only`
- 本地配置面板：`./scripts/run_science_monitor.sh config-ui`

主流程命令：

- 抓取入库：`./scripts/run_science_monitor.sh update --date <YYYY-MM-DD> --days-back 7 --max-per-source 20`
- 单篇总结：`./scripts/run_science_monitor.sh summaries --date <YYYY-MM-DD> --window-days 7`
- 周报：`./scripts/run_science_monitor.sh report --date <YYYY-MM-DD> --window-days 7`
- 抓取加周报：`./scripts/run_science_monitor.sh daily --date <YYYY-MM-DD> --days-back 7 --max-per-source 20`
- 来源审计：`./scripts/run_science_monitor.sh audit --date <YYYY-MM-DD> --window-days 7 --max-per-source 100`
- 输出索引修复：`./scripts/run_science_monitor.sh index`

深度解读与人工中转：

- 单篇深读：`./scripts/run_science_monitor.sh deep-read --doi <doi> --pdf /absolute/path/to/paper.pdf`
- 文件夹批量深读：`./scripts/run_science_monitor.sh deep-read-folder --folder /absolute/path/to/pdf_folder`
- 人工中转状态：`./scripts/run_science_monitor.sh manual-llm-status`
- 只看待导入请求：`./scripts/run_science_monitor.sh manual-llm-status --pending-only`
- 导入人工响应：`./scripts/run_science_monitor.sh manual-llm-import --request-id <id>`
- 从指定文件导入：`./scripts/run_science_monitor.sh manual-llm-import --request-id <id> --response-file /path/to/response.txt`

标签与治理：

- 刷新预选标签报告：`./scripts/run_science_monitor.sh tag-candidates --min-count 2 --limit 50`
- 重审自动输出标签并同步索引：`./scripts/run_science_monitor.sh tag-candidates --reconcile-output --limit 0`
- Golden eval：`./scripts/run_science_monitor.sh golden-eval`
- 真实案例评测：`./scripts/run_science_monitor.sh real-eval`
- 真实案例 fixture 检查：`./scripts/run_science_monitor.sh real-eval --check-fixtures`
- 代码熵检查：`./scripts/run_science_monitor.sh entropy-check`
- Harness 审计：`./scripts/run_science_monitor.sh harness-audit`
- Harness 优化：`./scripts/run_science_monitor.sh harness-optimize`
- 默认 harness gate：`./scripts/run_science_monitor.sh harness-check --profile default`
- 输出库 harness gate：`./scripts/run_science_monitor.sh harness-check --profile output`
- UI harness gate：`./scripts/run_science_monitor.sh harness-check --profile ui`
- 维护循环：`./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2`

Harness 自监督规则：

- `harness-audit` 用来评估当前治理覆盖面
- `harness-optimize` 用来做低风险、确定性的治理修补
- `harness-check` 是当前分层治理 gate；默认用 `--profile default`，输出库和 UI 分别用 `--profile output` / `--profile ui`
- Harness 总览见 `docs/user_guides/harness_governance_overview.md`

## Source of Truth 与文件边界

运行时配置和路径：

- 日常配置入口：`PROJECT_CONFIG.md`
- 运行时机器配置：`config/runtime.json`、`config/analysis.json`、`config/paths.json`
- 本机私人路径覆盖：`config/local.paths.json`，该文件不应提交；公开示例是 `config/local.paths.example.json`
- 输出根目录解析优先级：环境变量 `SCIENCEMONITOR_OUTPUT_ROOT` > `config/local.paths.json` > `config/paths.json` > `out`
- `output_root` 可能指向私人 Obsidian vault，修改输出文件前必须确认任务确实要求操作输出库
- `data/`、`log/`、`tmp/`、`.venv/` 和输出目录通常是运行态，不默认作为源码修改对象

治理与维护：

- 代码熵预算以 `config/maintenance_budget.json` 和 `src/sciencemonitor/entropy.py` 为准
- 维护循环以 `src/sciencemonitor/maintenance.py`、`tests/` 和当前 harness gate 结果为准

Provider 语义：

- 自动分析 provider：`codex_local`、`openai_api`、`openrouter_api`、`ollama_api`
- `chatgpt_web_manual` 是人工中转工作流，不当作常规无人值守自动 provider 使用
- 当前 provider 和模型以 `PROJECT_CONFIG.md` 的 `config/analysis.json` 同步块及落地后的 `config/analysis.json` 为准

研究偏好、模板和标签：

- 用户研究偏好优先改 `PROJECT_CONFIG.md` 的 `## Sync: config/research_preferences.json` 段；运行时落地到 `config/research_preferences.json`
- 期刊源和主题分类分别以 `config/sources.json`、`config/topics.json` 为准
- 正式 canonical 标签人工入口是 `config/tag/formal_tags.md`
- 预选标签人工入口是 `config/tag/pending_tags.md`
- 机器标签资产是 `config/focus_tags.json` 和 `config/pending_tags.json`
- 单篇总结展示层模板：`config/templates/article_summary_template.md`
- 周报展示层模板：`config/templates/daily_report_template.md`
- 深度解读展示层模板：`config/templates/deep_reading_report_template.md`
- 模板、提示词、规则文档和 Python 实现的优先级，以 `docs/workflow_specs/source_of_truth_matrix.md` 为准

真实输出判断：

- 当前真实输出由“运行时模板 + Python 逻辑”共同决定
- 模板控制展示结构，Python 负责字段内容、schema、归一化、兼容修复和校验
- 不要默认认为说明文档已经被代码消费；改输出行为前先核实渲染链路和测试
- 报告生成后的格式审核规则以 `docs/workflow_specs/report_review_rules.md` 和对应 Python 审核层共同约束

## Skill 使用规则

如果当前 agent 环境提供以下 skill，应主动使用：

- `defuddle`：用户给网页 URL 并要求读取或分析网页正文时使用，优先于直接抓取杂乱网页正文
- `obsidian-cli`：用户要求直接搜索、读取、创建或管理 Obsidian vault 内容时使用
- `obsidian-bases`：创建或修改 `.base` 文件、表格/卡片视图、过滤器、公式和 summary 时使用
- `obsidian-markdown`：创建或修改 Obsidian 特有 Markdown 语法时使用，包括 wikilinks、embeds、callouts、frontmatter 和 tags

边界：

- skill 是工具，不是项目 source of truth
- skill 不覆盖 `PROJECT_CONFIG.md`、`config/*.json`、运行时模板和 `docs/workflow_specs/source_of_truth_matrix.md`
- skill 不可用时，说明缺口并使用本地命令或项目内逻辑兜底
- 使用 skill 后如果改了代码、模板、配置或输出格式，仍然按本项目 harness 规则运行对应检查
- 更细规则见 `docs/user_guides/agent_skill_usage.md`

## ExecPlan 触发规则

出现以下任一情况时，先在 `docs/exec_plans/active/` 新建或更新计划：

- 预计会改 3 个以上文件
- 预计会工作 30 分钟以上
- 会改变架构、source of truth 或目录结构
- 会引入迁移步骤或分阶段治理

执行要求：

- 新计划基于 `config/templates/exec_plan_template.md`
- 进行中的计划放 `docs/exec_plans/active/`
- 完成后补结果与验证，再移到 `docs/exec_plans/completed/`
- `harness-check` 会校验 active 计划结构，并读取勾选项摘要
- 仅修改单个说明性文档、且不改变 source of truth、架构、目录结构或运行行为时，通常不需要新建 ExecPlan

## 修改与验证矩阵

默认原则：

- 不要把运行态数据、缓存、日志、临时文件当作源码修改对象
- 不要提交 `config/local.paths.json`
- 涉及输出格式时，优先补测试，再改行为
- 涉及研究偏好时，优先更新 `PROJECT_CONFIG.md` 的研究偏好同步段
- 涉及长期工程规则时，优先同步 `AGENTS.md`、`ARCHITECTURE.md`、`PLANS.md` 和相关治理文档
- 如果某项 source of truth 发生变化，必须同步更新 `docs/workflow_specs/source_of_truth_matrix.md`

按改动类型选择验证：

- 仅改 `AGENTS.md`：`git diff --check`、`./scripts/run_science_monitor.sh harness-audit --no-write-report`、`./scripts/run_science_monitor.sh harness-check --profile default`
- 改 Python 代码：相关定向测试 + `./.venv/bin/python -m pytest -q`
- 改模板或输出格式：相关测试 + `./scripts/run_science_monitor.sh golden-eval` + `./scripts/run_science_monitor.sh harness-check --profile default`
- 改配置控制面：`./scripts/run_science_monitor.sh doctor --consistency-only` + `./scripts/run_science_monitor.sh harness-check --profile default`
- 改 UI：相关 `config_ui` 测试 + `./scripts/run_science_monitor.sh harness-check --profile ui`
- 改标签规则或标签资产：相关标签测试，必要时 `./scripts/run_science_monitor.sh tag-candidates --reconcile-output --limit 0`，再跑 `./scripts/run_science_monitor.sh harness-check --profile output`
- 改真实案例链路：`./scripts/run_science_monitor.sh real-eval --check-fixtures`，必要时再跑 `harness-check --profile release --include-real-eval`
- 发版前：按 `docs/user_guides/release_checklist.md` 跑维护 gate、harness 审计、harness gate 和全量测试

## Review 规则

执行 `/review` 或代码审核任务时：

- 默认只审核，不修改文件，除非用户明确要求修复
- 优先报告 correctness、silent failure、data loss、security、source of truth 不一致、配置污染、测试缺失和兼容性问题
- 不把纯格式、命名或个人风格偏好作为主要 finding，除非违反本项目明确规则或影响可维护性
- 每个 finding 应尽量包含：
	- 严重程度：High / Medium / Low
	- 文件路径与具体位置
	- 问题说明
	- 为什么这是问题
	- 建议修复方式
	- 是否需要补测试
- 如果没有发现实质问题，应明确说明未发现阻塞性问题，不要为了输出而强行挑刺
- 审核涉及输出格式、模板、标签、研究偏好或 source of truth 时，必须核对对应的 source of truth、模板和 Python 渲染/校验逻辑
