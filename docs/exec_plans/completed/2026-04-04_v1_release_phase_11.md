# V1 Release Phase 11

## Purpose / Big Picture

这一阶段不再继续做功能增强，而是把当前 `Unreleased` 的结构治理、维护治理和文档治理正式收口成 `v1.0.0`。

目标：

- 跑完发版前 gate
- 写出 `v1.0.0` 的版本记录
- 创建正式提交和 `v1.0.0` tag
- 在发版后把治理总览切到下一阶段

## Progress

- [x] 跑发版 gate
- [x] 更新 `CHANGELOG.md`
- [x] 更新 `GovernanceBoard.md`
- [x] 创建 release commit
- [x] 创建 `v1.0.0` tag

## Current Targets

- `CHANGELOG.md`
- `docs/exec_plans/GovernanceBoard.md`
- `docs/user_guides/release_checklist.md`
- Git tag `v1.0.0`

## Plan Of Work

1. 按 `release_checklist.md` 跑维护 gate、harness gate、全量测试
2. 将 `Unreleased` 收口到 `v1.0.0`
3. 提交 release commit
4. 创建 `v1.0.0` tag
5. 把治理总览切换到发布后状态

## Decision Log

- 发版 gate 已通过：
  - `maintenance-check --auto-repair --max-passes 2`
  - `harness-check --include-real-eval --real-case-ids 2023_sw_resnet_tmd,2026_jgr_polar_convection_mohe`
  - `pytest -q`
- `v1.0.0` release commit 为 `1b16b4a3ebd2e1b310a5d8622b542d9fc1008c02`
- `v1.0.0` tag 已创建并指向上述 release commit
- 发版后把治理总览切换到下一阶段：`v1.1.0（待规划）`
