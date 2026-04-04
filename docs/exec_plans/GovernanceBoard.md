# Governance Board

这个文件是 `ScienceMonitor` 的统一治理总览。

作用只有一个：防止“计划、问题、日志、版本、评测”分散后被遗忘。

## 当前状态

- 当前目标版本：`v1.0.0`
- 当前备份版本：`v0.1.0`
- 当前结构治理状态：Phase 1 到 Phase 10 已完成
- 当前 `docs/exec_plans/active/`：无进行中的计划
- 当前发布阻塞项：无

## 当前 Gate 状态

- 代码维护 gate：
  - 命令：`./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2`
  - 最新报告：`log/maintenance/latest.md`
- Harness gate：
  - 命令：`./scripts/run_science_monitor.sh harness-check`
- 熵检查：
  - 命令：`./scripts/run_science_monitor.sh entropy-check`
- 全量测试：
  - 命令：`./.venv/bin/python -m pytest -q`

注意：

- `latest.md` 只代表最近一次维护运行结果，不等于正式发版状态
- 正式发版时仍需按 `release_checklist.md` 再跑一轮完整 gate

## 当前评测状态

- Golden 基线：
  - 定义：`evals/golden/`
  - 运行产物：`log/golden_eval/`
- 真实案例基线：
  - 案例清单：`evals/real_cases/cases.json`
  - 已认可 fixture：`evals/real_cases/fixtures/`
  - 运行产物：`log/real_case_eval/`

## 当前问题分层

### 发布阻塞项

- 这里仅记录“会阻止当前目标版本发布”的问题
- 当前：无

### 近期待办

- 位置：`docs/exec_plans/Todo.md`
- 适用：已经明确、但暂不立项的短中期事项

### 长期工程债

- 位置：`docs/exec_plans/tech_debt_tracker.md`
- 适用：结构性问题、长期方向、非当前版本阻塞项

### 已完成治理记录

- 位置：`docs/exec_plans/completed/`
- 适用：已经做完的阶段计划、关键决策与迁移记录

## 记录边界

### 计划记在哪里

- 正在做的复杂事项：`docs/exec_plans/active/`
- 完成后的计划：`docs/exec_plans/completed/`

### 问题记在哪里

- 会阻止当前目标版本发布的问题：本文件 `发布阻塞项`
- 已排队、近期想做但未开工的问题：`Todo.md`
- 长期工程债：`tech_debt_tracker.md`

### 日志记在哪里

- 维护循环报告：`log/maintenance/`
- Golden eval 运行结果：`log/golden_eval/`
- 真实案例运行结果：`log/real_case_eval/`
- LLM 临时工件：`log/llm_tmp/`

### 版本与发版记在哪里

- 版本历史：`CHANGELOG.md`
- 发版流程：`docs/user_guides/release_checklist.md`

## 更新规则

出现以下情况时，必须更新这个文件：

- 当前目标版本发生变化
- 发布阻塞项新增、关闭或优先级变化
- `active/` 从空变非空，或从非空变空
- 评测治理策略发生变化
- 维护 gate 的标准发生变化

出现以下情况时，不需要更新这个文件：

- 单次 maintenance 运行成功
- 单次 golden/real eval 运行成功
- 普通代码修改但未改变治理状态

## 推荐使用顺序

1. 先看本文件，确认当前项目所处状态
2. 再看 `AGENTS.md`
3. 如果有进行中的计划，再看 `docs/exec_plans/active/`
4. 如果要发版，再看 `docs/user_guides/release_checklist.md`
