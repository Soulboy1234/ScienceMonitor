# Maintenance Governance Phase 6

## Purpose / Big Picture

第六阶段把 harness engineering 从“运行与评测治理”推进到“代码维护治理”。

目标是补齐两个代码级角色：

- `Reliability Reviewer`：审核代码功能是否正常，驱动修复后再测试
- `Entropy Steward`：审核代码熵是否失控，阻止文件、函数和依赖关系继续恶化

最终形成一个统一维护流程：

- 审核
- 调整
- 测试
- 再次审核

直到代码处于“功能正常且熵可控”的状态。

## Progress

- [x] 定义代码熵预算文件和可量化指标
- [x] 新增 `entropy-check`
- [x] 新增 `maintenance-check`
- [x] 新增安全范围内的自动调整步骤
- [x] 补维护 runbook、CLI 文档和测试
- [x] 决定 Phase 6 可以归档

## Surprises & Discoveries

- 当前 harness 已经覆盖运行一致性、稳定样例回归和真实案例回归，但没有代码级“维护角色”
- 当前已存在一个 import cycle：`article_summaries -> llm -> article_summaries`
- 当前若直接对文件长度和函数长度做硬阈值判死，会把现状全部判失败，因此需要先冻结预算，再阻止继续恶化

## Decision Log

- 先做“预算冻结 + 防继续恶化”，不在 Phase 6 一开始就强推大拆分
- 自动调整只做低风险、确定性的动作，不做大规模自动重构
- 维护循环先实现为本地命令和报告，不直接接入 CI

## Outcomes & Retrospective

- 已新增 `config/maintenance_budget.json`，把代码熵预算文件化
- 已新增 `entropy-check`，可以检查包总行数、模块行数、函数长度和 import cycle
- 已新增 `maintenance-check`，执行“审核 -> 调整 -> 测试 -> 再审核”
- 维护循环已经可以输出 `log/maintenance/latest.md`
- 当前大文件和一个历史 import cycle 仍然存在，但已经被预算和 allowlist 显式冻结，不再允许继续无约束恶化

## Context and Orientation

- 当前统一运行 gate：`harness-check`
- 当前维护 gate：`maintenance-check`
- 当前主要评测治理：`golden-eval`、`real-eval`
- 当前长期工程债记录：`docs/exec_plans/tech_debt_tracker.md`

## Plan of Work

1. 定义熵预算与代码审计器
2. 实现维护循环入口
3. 补测试与文档
4. 跑维护检查并确认收尾

## Concrete Steps

1. 新增 `config/maintenance_budget.json`
2. 新增 `src/sciencemonitor/entropy.py`
3. 新增 `src/sciencemonitor/maintenance.py`
4. 给 CLI 增加 `entropy-check` 与 `maintenance-check`
5. 补 `tests/test_entropy.py` 与 `tests/test_maintenance.py`
6. 补维护 runbook 和 README / AGENTS 导航

## Completion Note

这一阶段已经完成。

完成标志：

- `entropy-check` 已可运行，且当前预算通过
- `maintenance-check --auto-repair` 已可运行，当前项目通过
- `Reliability Reviewer` / `Entropy Steward` 的职责已经写入 runbook
- 维护治理已进入项目入口文档和代码地图
