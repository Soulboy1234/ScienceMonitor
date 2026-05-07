# Harness 治理总览

这份文档解释 `ScienceMonitor` 当前的 harness 是什么、监测哪些内容、各个 gate 分别负责什么。

它的定位是：

- 面向人类阅读的总览
- 用来回答“现在 harness 在管什么”
- 作为 `README.md`、`AGENTS.md` 和各类 runbook 之间的总入口

它不是：

- source of truth 矩阵
- 具体配置说明
- 单个命令的替代帮助页

## 一句话定义

当前项目的 harness 是一套“审核 -> 测试 -> 回归 -> 维护”的治理链路，用来保证：

- 运行环境一致
- 计划和说明文件不漂移
- 标签输出会尽量收敛到 formal 体系
- UI 结构、功能和视觉不回退
- 报告模板和输出格式不悄悄变化
- 真实案例和 golden 基线仍可复现
- 代码熵不会持续恶化

## 当前 harness 都监测什么

### 1. `doctor`

命令：

```bash
./scripts/run_science_monitor.sh doctor
```

负责检查：

- Python 解释器和 `.venv`
- PDF 工具链
- provider 可用性
- 配置同步状态
- 输出路径解析

它回答的是：**当前环境和控制面是否可运行**。

### 2. `harness-check`

命令：

```bash
./scripts/run_science_monitor.sh harness-check --profile default
```

这是当前分层 harness gate。`--profile` 决定检查范围：

- `smoke`：doctor consistency、ExecPlan/docs 轻量检查和核心单元测试子集
- `default`：日常本地/CI gate，包含资源预检、pytest、harness 自审、ExecPlan/docs 和 golden eval，不扫描私人输出库
- `output`：输出库治理，检查当前有效 `output_root` 下的标签治理和标签输出漂移；扫描 0 个文件时会显示 `empty`
- `ui`：配置面板结构、功能和视觉检查，并运行相关 UI 单测子集
- `release`：发布前完整 gate，包含 default、output、ui 和可选真实案例 fixture 检查

常用命令：

```bash
./scripts/run_science_monitor.sh harness-check --profile smoke
./scripts/run_science_monitor.sh harness-check --profile default
./scripts/run_science_monitor.sh harness-check --profile output
./scripts/run_science_monitor.sh harness-check --profile ui
./scripts/run_science_monitor.sh harness-check --profile release
```

`tag_output_review` 只在 `output` / `release` profile 或显式 `--include-output-review` 时运行。它依赖当前有效 `output_root`，因此不作为默认 CI 硬 gate。

可选的 `real-eval fixture` 仍然只有显式带 `--include-real-eval` 时才检查，用于真实案例输出和 fixture 漂移治理。

它回答的是：**当前项目的治理链路是否整体健康**。
### 2.5 `harness-audit`

命令：

```bash
./scripts/run_science_monitor.sh harness-audit
```

负责：

- 检查当前 harness 是否仍覆盖了项目工作流的关键风险点
- 检查 README / AGENTS / CI / runbook / code map 是否与 harness 规则同步
- 输出结构化 finding 和优化建议

它回答的是：**当前 harness 自身是否还需要增强**。

### 2.6 `harness-optimize`

命令：

```bash
./scripts/run_science_monitor.sh harness-optimize
```

负责：

- 根据 `harness-audit` 的 finding 做低风险、确定性的治理修补
- 修补后重新执行一次 harness 审计
- 输出前后对比报告

它回答的是：**当前 harness 自身是否已经按建议完成基础收敛**。



### 3. `maintenance-check`

命令：

```bash
./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2
```

这是代码维护循环，不是单纯的 harness 汇总。它会执行：

1. `doctor`
2. `entropy-check`
3. `pytest`
4. `harness-check`
5. 低风险自动修补
6. 再审核

它回答的是：**当前代码库在功能、熵和治理层面是否可持续维护**。

### 4. `entropy-check`

命令：

```bash
./scripts/run_science_monitor.sh entropy-check
```

负责检查：

- 模块有效代码行数
- 超长函数
- import cycle
- unused import
- 包级预算

预算 source of truth 在：

- `config/maintenance_budget.json`

它回答的是：**代码熵是否失控**。

### 5. `golden-eval`

命令：

```bash
./scripts/run_science_monitor.sh golden-eval
```

负责：

- 对稳定样例输出做回归检查
- 防止模板、审核层、报告结构悄悄漂移

它回答的是：**固定输入的输出结构有没有回退**。

### 6. `real-eval`

命令：

```bash
./scripts/run_science_monitor.sh real-eval
```

负责：

- 真实案例评测
- 真实案例输出产物生成
- 可选的 fixture 对比或刷新

它回答的是：**真实论文链路是否仍然跑得通，且是否偏离了已接受基线**。

## 这些 gate 之间的关系

最实用的理解方式是：

- `doctor`：环境与配置是否可运行
- `harness-audit`：治理链路自身是否还有盲区
- `harness-check`：治理链路是否整体健康
- `entropy-check`：代码熵是否超预算
- `harness-optimize`：按审计建议做低风险治理修补，再重新审计
- `maintenance-check`：把以上内容收成“审核 -> 调整 -> 测试 -> 再审核”
- `golden-eval` / `real-eval`：输出和案例回归层

也就是说：

- `harness-audit` 是治理自监督
- `harness-check` 是治理 gate
- `harness-optimize` 是治理低风险修补
- `maintenance-check` 是维护循环
- `golden-eval` / `real-eval` 是评测层

## 日常使用建议

### 改代码后至少跑

```bash
./scripts/run_science_monitor.sh harness-check
./.venv/bin/python -m pytest -q
```

### 改结构、模板、UI 或治理规则后建议跑

```bash
./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2
```

### 改报告结构或审核逻辑后建议再跑

```bash
./scripts/run_science_monitor.sh golden-eval
```

### 改真实案例链路后建议再跑

```bash
./scripts/run_science_monitor.sh real-eval --check-fixtures
```

## 结果和日志去哪里看

- 维护报告：
  - `log/maintenance/latest.md`

- golden eval 产物：
  - `log/golden_eval/`

- real eval 产物：
  - `log/real_case_eval/`

- UI 视觉检查截图：
  - `log/ui_visual_review/`

## 建议阅读顺序

如果你要理解整个 harness，建议顺序是：

1. 本文
2. `docs/user_guides/eval_governance_runbook.md`
3. `docs/user_guides/maintenance_governance_runbook.md`
4. `docs/user_guides/release_checklist.md`
5. `docs/exec_plans/GovernanceBoard.md`

## 当前边界

当前 harness 已经覆盖：

- 运行环境
- 计划治理
- 文档放置治理
- UI 结构 / 功能 / 视觉治理
- golden 基线
- 可选真实案例 fixture
- 代码熵治理

当前还**没有**做成完整截图像素 diff，也没有做全量真实业务端到端 UI 自动化。这是有意的：目前的目标是用较轻的成本，先把最容易回退的治理面固定住。
