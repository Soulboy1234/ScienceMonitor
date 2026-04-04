# V1 Release Phase 11

## Purpose / Big Picture

这一阶段不再继续做功能增强，而是把当前 `Unreleased` 的结构治理、维护治理和文档治理正式收口成 `v1.0.0`。

目标：

- 跑完发版前 gate
- 写出 `v1.0.0` 的版本记录
- 创建正式提交和 `v1.0.0` tag
- 在发版后把治理总览切到下一阶段

## Progress

- [ ] 跑发版 gate
- [ ] 更新 `CHANGELOG.md`
- [ ] 更新 `GovernanceBoard.md`
- [ ] 创建 release commit
- [ ] 创建 `v1.0.0` tag

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
