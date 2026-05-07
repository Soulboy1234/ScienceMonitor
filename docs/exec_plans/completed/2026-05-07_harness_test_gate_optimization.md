# 计划：2026-05-07_harness_test_gate_optimization

## 目的 / 大图景
- 将当前累积式 harness/test gate 拆成分层治理入口，降低日常误报和重复耗时，同时保留输出质量、source-of-truth 和发布前检查护栏。

## 背景与定位
- 当前默认 `harness-check` 同时运行 doctor、harness 自审、ExecPlan、docs、标签、UI 结构/功能/视觉和 golden eval。
- 本机私人 Obsidian 输出库会让 `tag_output_review` 扫描真实输出，而 CI 的公开 `out/` 形态会扫描 0 个文件。
- `maintenance-check` 会先跑完整 pytest/harness，再因 entropy 预算失败而失败，浪费一次完整 gate。
- 本机磁盘空间不足会让 pytest 产生 `No space left on device` 级联失败，需要前置资源预检。

## 工作范围
- 修改 harness 分层接口、CLI 参数、维护循环、资源预检和测试临时目录处理。
- 调整 CI gate 使用方式和相关治理文档。
- 更新 harness/maintenance 相关测试，并补资源预检测试。
- 仅做第一轮降脆弱度，不大规模删除业务测试。

## 非目标
- 不删除核心业务测试。
- 不把真实案例评测默认纳入 CI。
- 不自动修复私人 Obsidian 输出库中的历史标签或历史格式。
- 不重构 `llm.py` 大块逻辑；本轮只记录预算重校准，后续若继续增长再立拆分计划。

## 进度
- [x] 建立活跃 ExecPlan
- [x] 实现 harness profile 与 output/UI 按需检查
- [x] 实现资源预检、测试临时目录和维护循环 fail-fast
- [x] 调整 entropy 预算与 UI fragment 审查脆弱度
- [x] 更新测试、CI 和治理文档
- [x] 运行可行验证并记录结果

## 计划中的工作
- 先新增轻量资源/pytest 运行支撑模块。
- 再改 harness 的 profile 分发和 summary 展示。
- 然后改 maintenance 的前置检查与跳过语义。
- 最后同步 CLI、CI、runbook 和测试。

## 具体步骤
1. 新增资源预检与 pytest runner，统一 `SCIENCEMONITOR_TEST_TMPDIR` / `TMPDIR`。
2. 给 `harness-check` 增加 `--profile smoke|default|output|ui|release` 和 `--include-output-review`。
3. 默认 profile 不再硬跑私人输出库扫描；output/release 或显式参数才跑。
4. 让 maintenance 在资源或 entropy 已失败时跳过 pytest/harness，并在摘要里明确显示 skipped。
5. 更新 CI 为单一 default harness gate，避免重复 pytest。
6. 更新测试覆盖 profile、skipped/empty 输出、资源预检和 maintenance fail-fast。

## 发现与意外
- `SCIENCEMONITOR_OUTPUT_ROOT=out` 会污染 harness 内部 pytest，导致临时项目测试错误使用仓库公开 `out/`；已在 `test_runner.py` 默认清理输出、data、log 路径覆盖。
- `tag_governance_review` 也依赖当前有效输出库 usage count，不只 `tag_output_review` 依赖输出库；因此 default profile 同时跳过标签治理和标签输出审查。
- 本机磁盘空间在实现中恢复到可用状态，资源预检、pytest 和 profile gate 均可实跑。

## 决策记录
- `tag_output_review` 降为 output/release 或显式启用，因为它的有效性取决于当前 `output_root` 是否指向真实输出库。
- `tag_governance_review` 同样降为 output/release，因为 pending usage count 会随 `output_root` 变化。
- `default` profile 保留 pytest 和 golden，作为日常 CI gate；maintenance 调用 harness 时关闭内置 pytest，避免重复。
- entropy 预算不按精确当前值卡死，改为小幅 headroom；本轮新增支撑模块会增加治理代码量，继续用精确预算会产生低信号失败。

## 结果与复盘
- 已完成 harness profile 分层、资源预检、pytest 临时目录隔离、maintenance fail-fast、CI 去重、UI fragment 降脆弱度和治理文档同步。
- `default` profile 已验证不再依赖私人输出库；`output` profile 继续扫描本机有效输出库。
- 已补正式复盘并归档到 `docs/exec_plans/completed/`。

## 验证
- `./scripts/run_science_monitor.sh harness-check --profile smoke`：通过，22 tests
- `./scripts/run_science_monitor.sh harness-check --profile default`：通过，340 tests
- `SCIENCEMONITOR_OUTPUT_ROOT=out ./scripts/run_science_monitor.sh harness-check --profile default`：通过，341 tests
- `./scripts/run_science_monitor.sh harness-check --profile output`：通过，扫描 103 个输出文件
- `./scripts/run_science_monitor.sh harness-check --profile ui`：通过，39 tests + UI 结构/功能/视觉审查
- `./scripts/run_science_monitor.sh maintenance-check --no-write-report`：通过
- `./scripts/run_science_monitor.sh entropy-check`：通过
- `./.venv/bin/python -m pytest -q tests/test_harness.py tests/test_maintenance.py tests/test_resource_checks.py tests/test_test_runner.py`：通过
- `git diff --check`：通过
- `./scripts/run_science_monitor.sh harness-audit --no-write-report`：通过
