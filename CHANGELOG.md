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

- 暂无

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
