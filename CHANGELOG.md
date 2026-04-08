# Changelog

这个文件用于保存 `ScienceMonitor` 的文件化版本记录。

版本记录目前采用两层：

- Git tag：记录版本号对应的精确代码快照
- `CHANGELOG.md`：记录该版本的范围、状态和主要变化

建议以后遵循下面的约定：

- 每个正式版本都创建 Git tag，例如 `v0.1.0`
- 每个正式版本都在本文件追加一个版本小节
- `Unreleased` 记录当前工作树中还未发布的变化

## [Unreleased]

暂无。

## [v1.2.0] - 2026-04-08

Tag: `v1.2.0`

Snapshot commit:

- 待 tag 创建后补充

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
