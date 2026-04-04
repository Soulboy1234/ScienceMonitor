# Maintenance Governance Runbook

这个 runbook 解释代码级维护治理，不解释业务生成逻辑。

目标是把两个角色固定下来：

- `Reliability Reviewer`
- `Entropy Steward`

并明确自动维护流程：

- 审核
- 调整
- 测试
- 再次审核

## 1. 两个角色的分工

### Reliability Reviewer

负责回答：

- 代码现在还能不能正常运行
- 关键 gate 有没有失败
- 当前失败是环境问题、测试问题，还是输出回归

它当前审的内容：

- `doctor`
- `pytest`
- `harness-check`

### Entropy Steward

负责回答：

- 代码体量有没有继续恶化
- 超长函数有没有继续增长
- 有没有出现新的 import cycle

它当前审的内容：

- 模块行数预算
- 函数长度预算
- 包总行数预算
- import cycle allowlist

预算文件：

- `config/maintenance_budget.json`

## 2. 命令入口

### 只看代码熵

```bash
./scripts/run_science_monitor.sh entropy-check
```

### 跑完整维护循环

```bash
./scripts/run_science_monitor.sh maintenance-check
```

### 带安全自动调整的维护循环

```bash
./scripts/run_science_monitor.sh maintenance-check --auto-repair
```

如需把真实案例也纳入维护检查：

```bash
./scripts/run_science_monitor.sh maintenance-check --include-real-eval --real-case-ids 2023_sw_resnet_tmd
```

## 3. 当前自动调整范围

Phase 6 只允许低风险、确定性的自动调整。

当前已启用：

- `PROJECT_CONFIG.md` 同步段回写到运行时 JSON

当前明确不自动做：

- 自动更新 golden fixture
- 自动更新真实案例 fixture
- 自动重构超长文件
- 自动拆分函数
- 自动消除 import cycle

这些动作都可能改语义，不适合默认自动执行。

## 4. 维护循环实际步骤

`maintenance-check --auto-repair` 当前执行顺序：

1. 初始审核
   - `doctor`
   - `entropy-check`
2. 安全自动调整
   - 同步 `PROJECT_CONFIG.md`
3. 测试
   - `pytest`
   - `harness-check`
4. 再次审核
   - `doctor`
   - `entropy-check`

输出报告位置：

- `log/maintenance/latest.md`
- `log/maintenance/<timestamp>_maintenance_report.md`

## 5. 什么时候算通过

维护循环通过的条件：

- 最终 `doctor` 无告警
- `pytest` 通过
- `harness-check` 通过
- `entropy-check` 通过

只要其中一项失败，维护循环就失败。

## 6. 什么时候改预算，什么时候改代码

允许改 `maintenance_budget.json` 的情况：

- 你明确接受某个模块暂时保留当前规模，并希望先冻结它、阻止继续恶化
- 你做了结构性迁移，预算需要重新按新边界定义

不应该只靠改预算解决的情况：

- 新增超长函数只是图省事
- 新增 import cycle
- 新逻辑把大文件继续堆大

这类问题应优先改代码，不是放宽预算。

## 7. 推荐工作流

### 普通改动后

```bash
./scripts/run_science_monitor.sh maintenance-check
```

### 配置漂移或轻微维护后

```bash
./scripts/run_science_monitor.sh maintenance-check --auto-repair
```

### 涉及真实案例链路时

```bash
./scripts/run_science_monitor.sh maintenance-check --include-real-eval --real-case-ids 2023_sw_resnet_tmd,2026_jgr_polar_convection_mohe
```

## 8. 记录要求

维护流程相关信息按下面方式记录：

- 单次运行结果：`log/maintenance/latest.md`
- 长期维护规则：本 runbook
- 当前项目治理状态：`docs/exec_plans/GovernanceBoard.md`
- 长期工程债：`docs/exec_plans/tech_debt_tracker.md`

只有在“治理状态发生变化”时才更新 `GovernanceBoard.md`，不要把每次成功运行都写进去。

## 9. 当前约束

- 维护循环不是自动重构器，它只负责发现问题、做低风险修补并验证
- 当前 `allowed_import_cycles` 为空；新增 import cycle 会直接被 `entropy-check` 拦下
- 当前仍有若干预算内热点模块，但都已进入 `maintenance_budget.json` 控制；后续重点是防止反弹和重复绕路，不是为了拆分而拆分
