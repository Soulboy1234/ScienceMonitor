# Eval Governance Phase 5

## Purpose / Big Picture

第五阶段把 harness engineering 从“有评测命令”推进到“有评测治理”。

目标是把 `doctor`、`golden-eval`、`real-eval` 收成一套可执行、可审阅、可更新基线的治理流程。

## Scope

- `src/sciencemonitor/cli.py`
- `src/sciencemonitor/harness.py`
- `src/sciencemonitor/golden_eval.py`
- `src/sciencemonitor/real_case_eval.py`
- `tests/test_golden_eval.py`
- `tests/test_real_case_eval.py`
- `tests/test_harness.py`
- `.github/workflows/ci.yml`
- `evals/real_cases/`
- 相关说明文档与 runbook

## Progress

- [x] 新增真实案例 fixture 治理，明确“检查基线”和“更新基线”是两件事
- [x] 为 `real-eval` 增加 fixture compare / update 入口
- [x] 新增统一 `harness-check` 命令
- [x] 为 golden / real eval 补 runbook
- [x] 清理 CI 中对 golden eval 的重复执行
- [x] 提升当前认可的真实案例输出为 fixture

## Success Criteria

- `golden-eval` 仍然负责稳定模板/渲染回归
- `real-eval` 可以把人工认可的真实案例结果提升为 fixture，并在后续自动比较漂移
- 有统一的 `harness-check` 入口，便于本地和 CI 使用
- 仓库内有清晰的评测治理说明，不再依赖对话记忆

## Completion Note

这一阶段已经完成。

完成标志：

- `harness-check` 已成为统一 gate，默认执行控制面一致性检查和 `golden eval`
- `real-eval` 已支持 `--check-fixtures` 和 `--update-fixtures`
- `evals/real_cases/fixtures/` 已建立，并已收录当前认可的两篇真实案例单篇总结基线
- CI 已改为调用 `harness-check`，不再单独重复跑 golden eval
- 仓库内已补充 `docs/user_guides/eval_governance_runbook.md`
