# Changelog

这个文件用于保存 `ScienceMonitor` 的文件化版本记录。

版本记录目前采用两层：

- Git tag：记录版本号对应的精确代码快照
- `CHANGELOG.md`：记录该版本的范围、状态和主要变化

建议以后遵循下面的约定：

- 版本号格式固定为 `x.y.z`
- `x` 是大版本号：用户或发版计划明确说“大版本更新”时递增，并将 `y`、`z` 重置为 `0`
- `y` 是中版本号：用户或发版计划明确说“中版本更新”时递增，并将 `z` 重置为 `0`
- `z` 是小版本号：用于小范围修复、兼容性补丁或不改变版本主线定位的增量更新
- 每个正式版本都创建 Git tag，例如 `v0.1.0`
- 每个正式版本都在本文件追加一个版本小节
- `Unreleased` 记录当前工作树中还未发布的变化

## [Unreleased]

- 下一轮变更待规划。

## [v2.1.2] - 2026-05-13

Tag: `v2.1.2`

Snapshot commit:

- `TO_BE_FILLED_AFTER_TAG`

版本定位：

- `v2.1.1` 之后的正式小版本检查点
- 目标是把深度解读恢复、PDF 抽取、标签治理和当前候选改动收束为可同步 GitHub 的稳定备份点

主要变化：

- 强化深度解读和 Ollama 结构化恢复：
  - 改善本地模型返回非严格 JSON 时的结构化恢复能力
  - 深度解读生成链路补充兼容修复、元数据回填和测试覆盖
- 修复非空间 AI 深读和正文抽取边界：
  - 空间物理主线之外但与研究相关的 AI 论文深读标签可被正确保留
  - PDF / 网页正文抽取和索引解析相关边界补充回归测试
- 收束标签治理资产：
  - formal / pending 标签入口和机器标签资产已同步当前审计结果
  - 标签审核、自动输出标签转正和索引联动补充治理逻辑
- 更新发布治理记录：
  - 归档近期深读、ChatGPT 旧文重写迁移和标签全量审计 ExecPlan
  - golden deep-read fixture 已同步当前稳定输出
  - `maintenance_budget.json` 已重校准到 `v2.1.2` 源码基线
- `real-eval` 未作为本轮阻塞项，保留为后续真实案例验证。

发版时状态：

- `git diff --check`：通过
- `./scripts/run_science_monitor.sh doctor`：通过
- `./scripts/run_science_monitor.sh entropy-check`：通过
- `./scripts/run_science_monitor.sh harness-audit`：通过
- `./scripts/run_science_monitor.sh harness-check --profile release`：通过
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2`：通过
- `./.venv/bin/python -m pytest -q`：通过

## [v2.1.1] - 2026-05-08

Tag: `v2.1.1`

Snapshot commit:

- `9fb84292a297e11494977af302174ec7d7599ece`

版本定位：

- `v2.1.0` 之后的正式小版本检查点
- 目标是把当前稳定性、安全性、CI 和 harness gate 治理收束为可同步 GitHub 的发布基线

主要变化：

- 强化发布 gate 和 CI：
  - `harness-check` 支持 `smoke/default/output/ui/release` 分层 profile
  - default/release profile 内置资源预检与 pytest，CI 改为执行 `harness-check --profile default`
  - 维护循环加入资源预检，避免磁盘不足时产生级联误报
- 强化 config-ui 安全边界：
  - 默认只允许 loopback 绑定，非 loopback 访问需要显式开关
  - 页面、状态轮询、最新结果和关闭请求使用短期 token
  - 本地文件访问限制到受信任输出产物和人工中转请求文件，并限制文件类型和大小
  - 表单、人工响应和 PDF 上传增加大小上限
- 强化网络与路径边界：
  - HTTP 抓取加入响应体大小限制，避免异常大响应拖垮本地运行
  - article index 解析 wiki target 时拒绝绝对路径和目录穿越
  - doctor 新增输出删除保护检查
- 强化测试运行稳定性：
  - 新增统一 pytest runner 和 `SCIENCEMONITOR_TEST_TMPDIR` 资源隔离
  - 删除历史 `tag_candidates` 兼容入口与旧测试，标签治理测试改为直接覆盖当前入口
  - 文档、runbook、source of truth matrix 和 Python module map 已同步新 gate 边界
- 稳定性与安全性复核：
  - 未发现 `shell=True`、`eval()`、`exec()`、`os.system()` 高危执行点
  - 受控子进程调用均保留参数数组形式
  - `real-eval` 未作为本轮阻塞项，保留为后续非阻塞真实案例验证

发版时状态：

- `git diff --check`：通过
- `./scripts/run_science_monitor.sh doctor`：通过
- `./scripts/run_science_monitor.sh entropy-check`：通过
- `./scripts/run_science_monitor.sh harness-audit`：通过
- `./scripts/run_science_monitor.sh harness-check --profile smoke`：通过
- `./scripts/run_science_monitor.sh harness-check --profile default`：通过
- `./scripts/run_science_monitor.sh harness-check --profile output`：通过
- `./scripts/run_science_monitor.sh harness-check --profile ui`：通过
- `./scripts/run_science_monitor.sh harness-check --profile release`：通过
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2`：通过
- `./.venv/bin/python -m pytest -q`：通过

## [v2.1.0] - 2026-05-06

Tag: `v2.1.0`

Snapshot commit:

- `938f17099e73f91b635ec2545fd33a1c4f310e3e`

版本定位：

- `v2.0.0` 之后的正式中版本检查点
- 目标是把 Ollama 长任务稳定性、深度解读批处理与质量模式、周报摘要兜底、标签治理强化和 config-ui 运行反馈修复收束为新的稳定基线

主要变化：

- 强化 Ollama / API 分析链路稳定性：
  - 增加长任务 keep-alive、超时跳过续跑、空响应处理和结构化 JSON 失败跳过逻辑
  - 深度解读支持质量模式，并改善标签、PDF 链接、元数据和批处理反馈
  - 单篇总结、周报和深度解读的 LLM 合同与兼容修复已补齐测试覆盖
- 改进网页正文、摘要和周报兜底：
  - 网页全文抽取失败时更稳健地回落到摘要证据边界
  - 周报生成可处理未完成总结、当前来源显示、期刊显示名和标签词云相关边界
  - golden 输出已同步新的周报和深读格式预期
- 强化标签治理：
  - formal / pending 标签资产扩充并同步人工入口
  - 修正流光、行星环境等标签归一化规则
  - 自动输出标签审核与转正路径补充治理逻辑和测试
- 优化 config-ui 运行反馈：
  - 深度解读任务面板拆出独立模块，批量任务、状态卡片和结果卡片反馈更清晰
  - 周报、深度解读、运行时状态和前端样式脚本同步修复
  - UI 功能审查、视觉审查和页面结构测试已更新
- 补齐完成态计划记录：
  - 归档 Ollama、深度解读、周报、UI 和标签治理相关 ExecPlan
  - `docs/exec_plans/active/` 保持为空
- 重校准维护预算：
  - 清理 entropy 检查发现的未使用导入
  - `maintenance_budget.json` 已更新到 `v2.1.0` 源码基线，后续增量继续受预算约束

发版时状态：

- `git diff --check`：通过
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2`：通过
- `./scripts/run_science_monitor.sh harness-audit`：通过
- `./scripts/run_science_monitor.sh harness-check`：通过
- `./.venv/bin/python -m pytest -q`：通过

## [v2.0.0] - 2026-04-28

Tag: `v2.0.0`

Snapshot commit:

- `36d8b6bf45144c024bf1bfc163836d1ffd65018f`

版本定位：

- `v1.4.0` 之后的正式大版本检查点
- 目标是把 Ollama 本地模型接入、周报输出与推荐链路优化、维护预算重校准、entropy 检查修复和完整 gate 复核收束为稳定基线

主要变化：

- 新增 `ollama_api` 自动分析后端：
  - 默认模型为 `gemma4:26b`
  - 默认请求 `http://127.0.0.1:11434/api/chat`
  - 单篇总结、周报、深度解读复用现有结构化 JSON、缓存、审核和 token 记录链路
- UI 设置页补充 Ollama 本地模型入口：
  - 可配置模型名、base_url 和超时时间
  - provider 显示、功能审查、视觉审查和 token 图例已同步
- 完成周报链路与输出优化：
  - 周报推荐理由重新接入 LLM 分析与本地审核，避免只靠规则拼接
  - 今日概览、重点方向分布、推荐论文和标签词云的展示逻辑已按新风格收束
  - 非研究型文献、获取不到摘要的文献和缓存复用策略已纳入周报主链路治理
- 完成维护稳定性检查：
  - `doctor` 无告警
  - `maintenance-check --auto-repair` 通过
  - `harness-check` 通过
  - 全量 pytest 通过
- 修复代码熵检查问题：
  - 删除未使用导入
  - entropy import-cycle 检查不再把函数内懒加载 import 误报为模块级循环
  - `maintenance_budget.json` 已重校准到当前稳定基线，后续增量仍受预算约束
- 安全边界复核：
  - 未发现 `shell=True`、`eval()`、`os.system()` 这类高风险执行点
  - 输出目录删除仍由 `safety.allow_output_deletions` 控制
  - UI 本地文件访问错误提示已明确为“项目目录或输出目录”
- 修复深度解读标签继承边界：
  - 深度解读继承相关单篇总结标签时，已有 `#事件/磁暴` 不会被全文片段误删
  - 普通文章总结仍保留“磁暴必须是主研究对象才打标签”的收紧规则

发版时状态：

- `./.venv/bin/python -m pytest -q`：通过
- `git diff --check`：通过
- `./scripts/run_science_monitor.sh harness-check`：通过
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair`：通过

## [v1.4.0] - 2026-04-17

Tag: `v1.4.0`

Snapshot commit:

- `ff5d558bc73e921aa692f75c5115d964b657bcb2`

版本定位：

- `v1.3.0` 之后的次版本整理记录
- 目标是把 UI 重构、标签治理重构、token 监测、人工中转治理和输出文件保护收口为一个新的中版本基线

主要变化：

- 完成 `config-ui` 重构与治理接入：
  - 左侧导航 + 右侧工作区布局稳定
  - 周报、深度解读、人工中转、设置页已统一纳入结构审查、功能审查和视觉审查
  - 总览页已接入运行状态、环境检查、LLM 状态和 token 使用图
- 完成 token 使用监测模块化：
  - 新增 `token_monitor` 统一记录和汇总本地 Codex/API token 使用
  - UI 可展示今天 / 本周 / 本月统计和 30 天柱状图
  - token 记录集中到 `log/token_monitor/`
- 完成标签治理重构：
  - 正式标签与预选标签分离为 `formal_tags.md / pending_tags.md`
  - 新增标签审核层和标签治理审查，优先用 formal 标签吸收模型标签
  - `auto` 输出已按当前 formal 体系重审并与 pending 对齐
- 完成人工中转工作流稳定化：
  - 请求包、响应导入、结果审核和最新结果展示已收口
  - 人工中转结果与自动周报/深读结果在 UI 中分流展示
- 完成输出文件保护治理：
  - 根文档已补充文件操作边界说明
  - 默认不删除 `output_root` 下文件
  - 新增 `safety.allow_output_deletions`，作为用户显式审核开关
- 完成非研究型文献过滤补强：
  - `审稿人致谢 / reviewer thanks / editorial / issue information` 等标题已被过滤出周报主链路

发版时状态：

- `harness-check` 通过
- `pytest -q` 已在本轮多次通过；最近一次定向验证包括：
  - `tests/test_article_summaries.py`
  - `tests/test_article_index.py`
- `git diff --check` 通过
- 当前记录为文档化版本基线；是否打正式 Git tag 取决于后续是否执行提交/发版动作

## [v1.3.0] - 2026-04-09

Tag: `v1.3.0`

Snapshot commit:

- `0f3b2bc4f2d664581e6ab51a5076d1888a46031d`

版本定位：

- `v1.2.1` 之后的大检查与低风险优化版本
- 目标是把当前累计的 UI、harness、文档治理和 provider 语义收束成一次系统性校验后的稳定版本

主要变化：

- 完成一次系统性大检查并通过完整 gate：
  - `doctor --consistency-only`
  - `entropy-check`
  - `harness-check`
  - `maintenance-check --auto-repair --max-passes 2`
  - `pytest -q`
  - `real-eval --check-fixtures`
- 修复 provider 语义与文档口径漂移：
  - `README.md` 已明确区分三种自动分析后端 `codex_local / openai_api / openrouter_api`
  - `chatgpt_web_manual` 统一表述为人工中转工作流，而不是常规自动 provider
  - `PROJECT_CONFIG.md`、`project_config_markdown.py`、`llm_analysis_readme.md` 已同步这套口径
  - `doctor.py` 对不支持 provider 的警告已补齐 `openrouter_api`
- 提升可读性与稳定性：
  - 新增 `src/sciencemonitor/analysis_providers.py`，统一 provider 常量和显示标签，减少 UI、LLM 和文档层复制漂移
  - `tests/test_config_ui.py` 不再把品牌版本号写死为 `v1.2.0`，避免版本升级时误报
  - `tests/test_pipeline.py` 已补齐周报分析 mock，保证维护链路能完整覆盖周报路径
- 加强 harness 对文档准确性的监管：
  - `docs_review` 现在不仅检查说明文件是否放对目录
  - 还会检查 `README.md` / `PROJECT_CONFIG.md` 是否缺少关键 provider 说明，或回退到旧表述
  - 新增对应测试，防止根文档再次静默漂移
- 完成本轮大检查计划并归档：
  - `docs/exec_plans/active/` 已清空
  - `2026-04-09_v1_2_1备份与v1_3_0大检查计划.md` 已转入 `completed/`

发版时状态：

- `doctor --consistency-only` 通过
- `entropy-check` 通过
- `harness-check` 通过
- `maintenance-check --auto-repair --max-passes 2` 通过
- `pytest -q` 通过，`149 passed`
- `real-eval --check-fixtures` 通过

## [v1.2.1] - 2026-04-09

Tag: `v1.2.1`

Snapshot commit:

- `f03c3cd51b73ac336e187235d917749d6580c3f4`

版本定位：

- `v1.2.0` 之后的大检查前备份版本
- 目标是把当前累计的 UI、harness、文档治理与标签参考统一改动固定成一个可回退版本点

主要变化：

- `workflow_specs` 文档治理更新：
  - `docs/workflow_specs/常用分级标签参考.md` 已统一重命名为 `docs/workflow_specs/hierarchical_tag_reference.md`
  - 该文档已补齐“目的 / 当前定位 / 数量与顺序建议 / 使用原则”等结构，和其他 workflow spec 文档保持一致
  - `docs_review` 现在除了检查缺失文件，也会检查已知说明文件是否放错目录，并会阻止旧中文文件名重新进入仓库
- 新增 harness 自监督闭环：
  - 新增 `harness-audit`，用于评估当前 harness 是否仍覆盖了项目工作流的关键风险点
  - 新增 `harness-optimize`，用于按审计结果执行低风险、确定性的治理修补并重新审计
  - `harness-check` 现在会纳入 `harness_audit` 结果，不再只检查业务侧 gate
  - `maintenance-check` 已恢复全绿，说明新增治理模块与现有维护链路兼容
  - `harness_governance_overview.md`、`README.md`、`AGENTS.md`、`release_checklist.md`、`python_module_map.md` 已同步新的治理入口
  - 新增 Playwright 驱动的 UI 结构 / 功能 / 视觉审查后，按新增治理范围重定包级总预算到 `14500`，未放宽单模块和单函数预算
- `ExecPlan` 治理收紧：
  - `ExecPlan` 的机器模板 source of truth 已迁到 `config/templates/exec_plan_template.md`
  - `harness-check` 现在会输出 `active/` 中计划的勾选摘要，明确当前执行状态
  - 新增 `config_ui_review` 审查模块，把关键 UI 结构和说明稳定性接入 harness gate
  - 新增 `config_ui_functional_review` 审查模块，把导航切换、滚动复位和 provider 切换等 UI 核心交互接入 harness gate
  - 删除 `docs/exec_plans/TEMPLATE.md`，不再保留导航页
  - 新增 `docs_review` 审查模块，把说明文件的放置规则接入 harness gate
- `config-ui` 界面重做：
  - 改为左侧导航 + 右侧交互日志 / 操作区的控制台布局
  - 周报、深度解读、人工中转、设置分区明确
  - 把样式和导航脚本从 Python 页面层拆到独立静态资源，降低页面代码熵
  - 固定左右分栏，窄窗口下不再把导航压到页面上方
  - 支持拖拽调整左侧导航宽度
  - 统一修复文字溢出背景框的问题
  - 总览页重排为：运行环境、LLM 状态、输出路径
  - 去掉顶部重复状态展示和交互日志里的冗余说明
  - 右侧主内容取消固定最大宽度，随浏览器窗口自适应
  - 品牌区显示当前版本号，左侧状态区补充面板地址
  - 人工中转最近活动改为显示 `【状态】作者（年份）- 期刊缩写 - 题目`
  - `config-ui` 页面读取 `doctor` 时不再误报运行 PATH 假阳性
  - 右侧主内容区恢复纵向滚动，页面整体保持左右固定分栏
  - 总览页改为运行统计 + 运行状态检查 + 运行环境 / LLM 状态
  - 导航项的小字说明已去掉，左侧只保留主模块名称和底部状态区
  - 表单字段已统一增加 hover 说明，周报、深度解读、人工中转和设置页都有解释浮窗
  - 表单布局已收紧为更稳定的设置行样式，面板间距统一
  - 周报页改为周报生成参数、监测期刊缩写列表和周报最新结果
  - 深度解读页改为任务面板、可调 PDF 页数、数量统计和最新深读结果
  - 人工中转页改为最近活动、请求生成、响应文件解读和最新生成结果
  - 支持在 UI 中直接预览和打开新生成的 `prompt.md`
  - UI 文件链接现在同时支持项目目录和实际输出目录
  - 深度解读页支持单次任务级 PDF 页数覆盖，`0` 表示读取全部页
  - 设置页已收口成“分析后端与服务 + 路径与输出”两块，移除了无效开关和重复设置
  - 新增 `openrouter_api` 作为可运行的分析后端，支持单独配置模型、base_url、API key 和可选请求头
- `config-ui` 控制面重审：
  - provider 切换入口前置并明确保存目标
  - 显示公开默认输出路径、本机私有输出路径和实际输出路径
  - 增加 `chatgpt_web_manual` 请求状态展示与推荐响应文件导入入口
- `ExecPlan` 格式治理：
  - 重新要求 `active/` 计划使用 `Progress` 勾选清单
  - 最近几份 UI 计划已补回完成态勾选
- 修复 `chatgpt_web_manual` 的响应文件名稳定性：
  - 同一 `request_id` 会复用既有 `request_label` 和 `response_filename`
  - 避免 Linux 大小写敏感文件系统下二次调用找不到已导入响应

发版时状态：

- 作为大检查前备份点记录
- `doctor --consistency-only` 通过
- `entropy-check` 通过
- `harness-check` 通过
- `pytest -q` 通过，`148 passed`

## [v1.2.0] - 2026-04-08

Tag: `v1.2.0`

Snapshot commit:

- `154053d11f2bb31450896464291f3b5e0a4e5223`

版本定位：

- `v1.1.0` 之后的 harness 维护版本
- 目标是固定 agent skill 使用规范、本机私有路径覆盖和报告格式审核治理，同时把不满意的 UI 改动延后，不纳入本版本

主要变化：

- 新增 agent skill 使用规范：
  - 固定 `defuddle`、`obsidian-cli`、`obsidian-bases`、`obsidian-markdown` 的触发条件和边界
  - 在 `AGENTS.md` 中增加 skill 使用入口
  - 新增 `docs/user_guides/agent_skill_usage.md` 作为 harness 化 skill runbook
- 新增本机私有路径覆盖：
  - `config/local.paths.json` 可保存私人 Obsidian 输出目录，且不会上传 GitHub
  - `config/local.paths.example.json` 提供公开示例
  - 路径解析优先级为环境变量、`config/local.paths.json`、`config/paths.json`、默认 `out`
- 新增报告格式审核治理规范：
  - `docs/workflow_specs/report_review_rules.md` 统一记录单篇总结、周报和深度解读的生成后审核规则
  - 明确模板只控制静态展示骨架，编号换行、否定转折清理、摘要级来源说明和 eval 链接语义等动态规则由 Python 审核层强制执行
  - 模板 guide、source-of-truth 矩阵和 agent 入口已同步引用这份规则
- 增强本机运行鲁棒性：
  - `codex_local` 解析会在 `PATH` 不完整时回退到 macOS `Codex.app` 内置可执行文件，避免后台服务误报找不到 `codex`
- 版本边界：
  - 新的 `config-ui` 改动未纳入本版本
  - UI 重新设计与同步已记录到 `docs/exec_plans/Todo.md`

发版时状态：

- `pytest -q` 通过，`130 passed`
- `harness-check` 通过
- `entropy-check` 通过
- `maintenance-check --auto-repair --max-passes 2` 通过

## [v1.1.0] - 2026-04-08

Tag: `v1.1.0`

Snapshot commit:

- `70407b1efee5ff630fb90c80eae24bb721f8b19a`

版本定位：

- `v1.0.0` 之后的首个功能版本
- 目标是新增并固定 `chatgpt_web_manual` 人工网页中转模式，分流 `codex_local` 与 API 的 LLM 分析消耗

主要变化：

- 新增 `chatgpt_web_manual` 人工中转 provider：
  - 程序会在 `data/chatgpt_web_manual/requests/` 下生成请求包
  - 用户可通过 `manual-llm-status` 查看状态，通过 `manual-llm-import` 导入 ChatGPT 网页响应
  - 单篇总结、周报、深度解读都已接入同一套 bundle + import + validation 机制
  - 请求包已收敛为轻量结构，默认只保留 `prompt.md`、`request.md`、`metadata.json`
  - prompt 已改为最小定位信息 + 严格 JSON-only 输出要求，不再默认复制全文整理稿、摘要整理稿或 PDF
  - 响应文件名已改为稳定可识别格式，并支持把标准 JSON 直接放入 `responses/`
  - 人工中转固定工作流已确定为“上传 `prompt.md`，深度解读按需上传原始 PDF，导入网页 JSON 后继续走本地审核”
  - 深度解读导入后会继续走本地报告审核闭环，已稳定 `关键结果` 四级标题、编号换行、补充信息分行，并清理否定转折式贡献表述
  - 深度解读不再继承单篇总结的 `信息来源/*` 状态标签，避免把单篇总结的摘要级证据边界误写到深读报告上
  - 标签推断已收紧 `亚暴` 的触发范围，避免背景或参考文献提及造成无关标签
- 配置和治理已同步更新：
  - `PROJECT_CONFIG.md`、`config-ui`、`doctor`
  - README、AGENTS、LLM 说明和专门工作流文档
  - maintenance / eval / release runbook 已注明 manual provider 的适用边界
- 维护 gate 已同步纳入这轮新边界：
  - `pytest -q` -> `127 passed`
  - `doctor --consistency-only`、`entropy-check`、`maintenance-check --auto-repair --max-passes 2` 通过

发版时状态：

- `pytest -q` 通过，`128 passed`
- `harness-check` 通过
- `entropy-check` 通过
- `maintenance-check --auto-repair --max-passes 2` 通过

## [v1.0.0] - 2026-04-04

Tag: `v1.0.0`

Snapshot commit:

- `1b16b4a3ebd2e1b310a5d8622b542d9fc1008c02`

版本定位：

- 以 harness engineering 理念完成重构后的首个正式版本
- 目标是让项目在稳定性、输出治理、评测治理、维护治理和代码熵控制上进入可持续状态

主要变化：

- 完成 `v1.0.0` 前的结构清扫与归档：
  - 新建根目录归档区 `no_need_for_v1.0.0/`
  - 迁出旧 `docs/archive/` 历史材料和无引用配置 `config/codex_test_schema.json`
  - 删除旧回退逻辑和一批死代码、旧引用、历史兼容转发
- 完成面向维护的结构降熵：
  - `cli.py` 收缩为薄入口，引入 `cli_support.py`
  - 研究偏好逻辑拆入 `research_preferences.py`
  - 全文科学文本清洗与证据抽取拆入 `article_source_text.py`
  - 单篇总结、深度解读、真实案例输出、LLM prompt/schema 合同都拆出专门子模块
- 完成代码级治理闭环：
  - `entropy-check` 已覆盖模块行数、函数长度、包总行数、import cycle、unused import
  - `maintenance-check` 已形成“审核-调整-测试-再审核”闭环
  - `harness-check`、`golden-eval`、`real-eval` 已成为统一评测 gate
- 完成项目治理入口收束：
  - 新增 `docs/exec_plans/GovernanceBoard.md`
  - 新增 `docs/user_guides/release_checklist.md`
  - 明确计划、工程债、待办、维护日志、评测日志和版本记录的分层

发版时状态：

- `maintenance-check --auto-repair --max-passes 2` 通过
- `harness-check --include-real-eval --real-case-ids 2023_sw_resnet_tmd,2026_jgr_polar_convection_mohe` 通过
- `pytest -q` 通过

## [v0.1.0] - 2026-04-03

Tag: `v0.1.0`

Snapshot commit:

- `8cf17236dab4e90ef51d58988fd6d9a1470a2a29`

版本定位：

- 大清扫前的备份版本
- 记录从 `v0.0.0` 到当前为止的 harness 建设、输出治理、评测治理和维护治理

主要变化：

- 已完成 harness Phase 1 到 Phase 6：
  - 工程骨架、Git 与版本记录
  - source-of-truth 治理
  - 运行加固与 `doctor`
  - `golden-eval` / `real-eval`
  - 真实案例 fixture 治理与 `harness-check`
  - `entropy-check` / `maintenance-check`
- 已将原 `doc/` 体系迁移为 `docs/`，并重建文档分层
- 已把单篇总结、周报、深度解读统一到“模板主控展示层 + 代码主控契约/校验”的结构
- 已建立真实案例集成评测，并把当前认可的两篇单篇总结提升为 fixture
- 已建立代码熵预算文件和维护循环，为后续持续降熵提供 gate

说明：

- 这个版本是清扫前的备份点，不等于项目已经完成最终整理
- `v1.0.0` 前仍计划继续做冗余归档、逻辑收束和代码降熵

## [v0.0.0] - 2026-04-02

Tag: `v0.0.0`

Snapshot commit:

- `d0b58396334d5c0d8a20d8eac289a95fe66ff16d`

版本定位：

- `ScienceMonitor` 的第一个 Git 快照版本
- 记录的是“补 Git 仓库之后、补 harness 骨架之前”的项目基线

包含内容：

- 当前主程序代码与测试
- `config/` 配置文件
- `doc/` 下原有文档体系
- `scripts/`、`src/`、`tests/` 等项目本体文件

未纳入快照的运行态目录：

- `data/`
- `log/`
- `tmp/`
- `.venv/`
- `.obsidian/`
- 本地 `.app` 启动器产物
