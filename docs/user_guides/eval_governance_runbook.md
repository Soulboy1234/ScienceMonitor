# Eval Governance Runbook

这个 runbook 只解释评测治理，不解释业务功能。

目标是回答 4 个问题：

- `golden eval` 是干什么的
- `real eval` 是干什么的
- 什么情况下应该更新 fixture
- 什么情况下应该修代码而不是更新 fixture

适用边界：

- `golden-eval` 始终可以作为稳定回归 gate 使用
- `real-eval` 适合自动 provider（`codex_local`、`openai_api`）或人工校准
- 如果当前 `provider=chatgpt_web_manual`，`real-eval` 会生成请求包并等待人工导入，不是无人值守 gate
- 因此，CI 和默认 `harness-check` 不应依赖 `chatgpt_web_manual` 自动跑完真实案例

## 1. 两类评测的分工

### Golden Eval

入口：

```bash
./scripts/run_science_monitor.sh golden-eval
```

作用：

- 检查单篇总结、周报、深度解读这三类输出的稳定渲染结果
- 重点覆盖模板、后处理、标题层级、链接格式、审核闭环
- 输入是固定样例，不依赖真实网络和真实论文

基线位置：

- `evals/golden/*.md`

运行产物与 diff：

- `log/golden_eval/actual/`
- `log/golden_eval/diffs/`

### Real Eval

入口：

```bash
./scripts/run_science_monitor.sh real-eval
```

作用：

- 跑真实论文案例，验证真实来源获取、真实 PDF/摘要回退、真实 LLM 链路是否仍可运行
- 默认属于人工校准和集成评测，不进入 CI

案例清单：

- `evals/real_cases/cases.json`

运行产物：

- `log/real_case_eval/<case_id>/...`

## 2. 真实案例 fixture 治理

### 检查真实案例基线

```bash
./scripts/run_science_monitor.sh real-eval --check-fixtures
```

作用：

- 重新跑真实案例
- 把本次输出和已认可的 fixture 对比
- 如果 fixture 缺失或内容漂移，命令失败

fixture 位置：

- `evals/real_cases/fixtures/<case_id>/`

### 更新真实案例基线

```bash
./scripts/run_science_monitor.sh real-eval --update-fixtures
```

作用：

- 用当前输出刷新真实案例 fixture
- 只有在你已经人工确认“这是新的正确结果”时才应该执行

## 3. 统一 gate

入口：

```bash
./scripts/run_science_monitor.sh harness-check
```

默认检查：

- `doctor` 的控制面一致性
- `golden eval`

如需把真实案例也纳入当前 gate：

```bash
./scripts/run_science_monitor.sh harness-check --include-real-eval
```

常见变体：

```bash
./scripts/run_science_monitor.sh harness-check --include-real-eval --real-case-ids 2023_sw_resnet_tmd
./scripts/run_science_monitor.sh harness-check --update-golden
./scripts/run_science_monitor.sh harness-check --include-real-eval --update-real-fixtures
```

## 4. 什么时候更新 fixture

允许更新 fixture 的情况：

- 你主动修改了模板、审核规则或输出规范，并且人工确认新输出更正确
- 你主动调整了真实案例的 canonical 标签、标题风格或链接形式，并希望把新结果定为基线
- 真实案例之前没有 fixture，现在要正式纳入基线

不应该直接更新 fixture 的情况：

- 只是代码改动后出现意外漂移
- 输出格式退化
- 标签回退到旧命名
- 审核闭环失效
- 真实案例内容质量变差

这类情况应该先修代码，再重新跑评测。

## 5. 推荐工作流

### 改模板 / 改后处理 / 改审核

1. 先跑：

```bash
./scripts/run_science_monitor.sh harness-check
```

2. 如果只有 `golden eval` 漂移，先确认是否为预期改动
3. 预期改动才执行：

```bash
./scripts/run_science_monitor.sh golden-eval --update
```

### 改真实案例链路 / 改 prompt / 改标签

1. 先跑：

```bash
./scripts/run_science_monitor.sh real-eval --check-fixtures
```

2. 人工审阅真实案例输出
3. 只有确认“这是更好的结果”后，才执行：

```bash
./scripts/run_science_monitor.sh real-eval --update-fixtures
```

## 6. 当前约束

- `golden eval` 适合进 CI，因为它稳定、便宜、无外部依赖
- `real eval` 默认不进 CI，因为它依赖真实来源和真实 LLM，成本更高
- 深度解读真实基线是否纳入 fixture，应按额度和样例成熟度逐步推进

## 7. 记录要求

评测治理相关信息按下面方式记录：

- 基线定义：`evals/golden/`、`evals/real_cases/fixtures/`
- 单次运行产物：`log/golden_eval/`、`log/real_case_eval/`
- 当前项目治理状态：`docs/exec_plans/GovernanceBoard.md`
- 长期评测方向问题：`docs/exec_plans/tech_debt_tracker.md`

只有在“基线策略、真实案例范围、发布阻塞项”发生变化时，才更新 `GovernanceBoard.md`。
