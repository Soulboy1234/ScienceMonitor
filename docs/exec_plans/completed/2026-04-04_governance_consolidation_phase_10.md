# Governance Consolidation Phase 10

## Purpose / Big Picture

第十阶段解决“治理记录分散、问题容易遗忘”的问题，不继续做功能增强。

目标：

- 建立一个统一的治理总览入口
- 明确计划、问题、日志、版本、评测各自该记在哪里
- 补一份发版清单，固定 `v1.0.0` 前后的 release gate
- 把这些入口接到现有 runbook 和 agent 入口里

## Progress

- [x] 建立统一治理总览入口
- [x] 补 `release_checklist.md`
- [x] 把治理入口接入现有文档
- [x] 核对 runbook 与当前事实一致

## Current Targets

- `docs/exec_plans/`
  - 需要从“计划目录”补成“项目治理入口”
- `docs/user_guides/`
  - 需要补发版清单，并说明与维护/评测 runbook 的关系
- `AGENTS.md`
  - 需要补“先看治理总览”的入口

## Plan Of Work

1. 新增统一治理总览文件，明确记录边界
2. 新增发版清单
3. 更新 `AGENTS.md`、`docs/README.md`、`docs/exec_plans/README.md`
4. 更新维护与评测 runbook 的“记录要求”部分

## Decision Log

- 统一治理入口放在 `docs/exec_plans/GovernanceBoard.md`，而不是继续把状态散落在 `Todo.md`、`tech_debt_tracker.md` 和口头上下文里
- `GovernanceBoard.md` 只记录“治理状态变化”，不记录每次运行细节；运行细节仍放 `log/`
- 发版流程单独写成 `docs/user_guides/release_checklist.md`，与维护 runbook、评测 runbook 并列
- `AGENTS.md` 和 `docs/README.md` 都新增了治理总览入口，确保后续接手时先看状态再开始改动
