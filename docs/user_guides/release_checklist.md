# Release Checklist

这个清单用于正式版本发布前的最后核对。

默认适用于 `v1.0.0` 及后续正式版本。

## 1. 先确认版本状态

- 当前目标版本是否已经写入 `GovernanceBoard.md`
- `CHANGELOG.md` 是否已补齐本次版本内容
- 版本号是否符合 `x.y.z` 语义：
  - `x` 是大版本号，明确说“大版本更新”时递增，并将 `y`、`z` 重置为 `0`
  - `y` 是中版本号，明确说“中版本更新”时递增，并将 `z` 重置为 `0`
  - `z` 是小版本号，用于小范围修复和兼容性补丁
- 如果要打 tag，是否已确认 snapshot commit

## 2. 先确认治理状态

- `docs/exec_plans/active/` 应为空，或只保留明确接受的非阻塞计划
- `GovernanceBoard.md` 中的“发布阻塞项”应为空
- `Todo.md` 和 `tech_debt_tracker.md` 中的项目应确认“不是本次发布阻塞项”

## 3. 必跑命令

### 维护 gate

```bash
./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2
```

### Harness 自监督

```bash
./scripts/run_science_monitor.sh harness-audit
```

### Harness gate

```bash
./scripts/run_science_monitor.sh harness-check
```

如本次改动涉及真实案例链路，再跑：

```bash
./scripts/run_science_monitor.sh harness-check --include-real-eval --real-case-ids 2023_sw_resnet_tmd,2026_jgr_polar_convection_mohe
```

注意：

- 如果当前 `provider=chatgpt_web_manual`，真实案例链路会进入人工中转，不适合作为无人值守发版 gate
- 这种情况下，发版前如需跑真实案例，应临时切回 `codex_local` 或 `openai_api`

### 全量测试

```bash
./.venv/bin/python -m pytest -q
```

## 4. 结果核对

- `log/maintenance/latest.md` 应显示 `overall=ok`
- `harness-check` 不应出现 doctor / golden / real fixture 失败
- `pytest` 应全绿
- 如涉及真实案例，确认 `real-eval --check-fixtures` 通过，或已明确决定更新 fixture

## 5. 文档核对

- `CHANGELOG.md` 已更新
- 如治理流程有变化，相关 runbook 已更新：
  - `eval_governance_runbook.md`
  - `maintenance_governance_runbook.md`
  - `harness_governance_overview.md`
- 如项目状态有变化，`GovernanceBoard.md` 已更新

## 6. 发布动作

- 创建版本提交
- 打 tag
- 在 `CHANGELOG.md` 中写入 tag 和 snapshot commit

## 7. 发布后动作

- 将版本目标切换到下一个阶段
- 如有新增长期工程债，写入 `tech_debt_tracker.md`
- 如有近期排队项，写入 `Todo.md`
