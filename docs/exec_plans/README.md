# Exec Plans

这里存放 `ScienceMonitor` 的复杂任务计划。

- `GovernanceBoard.md`：统一治理总览，串联版本目标、阻塞项、计划、日志与评测状态
- `active/`：正在执行的计划
- `completed/`：完成后的归档
- `Todo.md`：已明确但暂未立项的近期待办
- `tech_debt_tracker.md`：未立项但应持续记录的工程债

具体格式见根目录的 [PLANS.md](../../PLANS.md)。
新计划请直接基于 [config/templates/exec_plan_template.md](../../config/templates/exec_plan_template.md) 起草。

额外要求：

- `active/` 里的计划必须有 `Progress` 勾选清单
- 计划移到 `completed/` 前，要把对应步骤改成已完成 `- [x]`
- `harness-check` 会校验 `config/templates/exec_plan_template.md` 与 `active/` 中计划的标题结构与勾选状态；`completed/` 当前按归档资料处理
- `harness-check` 会输出 `active/` 中计划的待办摘要，作为当前执行状态的一部分
