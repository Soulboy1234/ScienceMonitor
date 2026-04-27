# 计划：2026-04-11_token_monitor重构

## 目的 / 大图景
- 把项目内分散的 token 使用记录收口成统一模块和统一日志目录，便于 UI 展示、后续审计和 harness 监督。
- 将控制台 UI 的 token 展示改成更稳定的日级柱状图 + 今日/本周/本月文字汇总。
- 明确 token 数据的运行时来源、持久化位置和展示规则，避免“UI 看得到但项目内找不到记录”的状态。

## 背景与定位
- 当前 token 统计主要依赖 `config_ui_state_summary.py` 直接扫描 `log/llm_tmp/*_codex.stderr.log`，逻辑和 UI 耦合，缺少统一落盘规范。
- 周报、单篇总结、深度解读和人工中转都可能涉及 token 消耗，但当前没有统一的汇总入口，也没有统一的监测目录。
- 用户希望 token 记录集中放在 `log/token_monitor/`，并希望 UI 中的图表形态更接近独立统计图，而不是多个按周期拆开的进度条。

## 工作范围
- `src/sciencemonitor/config_ui.py`
- `src/sciencemonitor/config_ui_state_summary.py`
- `src/sciencemonitor/config_ui_page_sections.py`
- `src/sciencemonitor/ui_assets/config_ui.css`
- `src/sciencemonitor/ui_assets/config_ui.js`
- `src/sciencemonitor/project.py`
- `src/sciencemonitor/log_paths.py`
- 新增 `src/sciencemonitor/token_monitor.py`
- `tests/test_config_ui.py`
- `tests/test_token_monitor.py`
- `docs/user_guides/python_module_map.md`

## 非目标
- 本轮不重做整套 UI 布局，只调整 token 区域的数据源和展示方式。
- 本轮不伪造无法可靠获得的第三方 token 数据；无法稳定获取的来源只保留“未记录”或跳过。
- 本轮不改变具体 LLM 调用逻辑，只整理记录、汇总和展示链路。

## 进度
- [x] 步骤 1：建立统一 token_monitor 设计，确认日志目录、文件格式和回填策略。
- [x] 步骤 2：梳理现有 token 来源，迁移 UI 读取逻辑到独立模块。
- [x] 步骤 3：实现 `log/token_monitor/` 规范化落盘与日级聚合。
- [x] 步骤 4：调整 UI 文本和柱状图样式，切换到新数据结构。
- [x] 步骤 5：补测试、文档和 harness 验证。

## 计划中的工作
- 先确认当前项目内有哪些 token 相关入口，以及哪些数据已经存在于日志中。
- 再设计统一数据结构，优先把“扫描原始日志”和“写入规范化汇总”拆到独立模块。
- 然后让 UI 只消费 token_monitor 的结构化结果，不再自己拼装底层日志。
- 最后补测试、说明文档和验证命令，确保后续这部分能被 harness 稳定检查。

## 具体步骤
1. 检查现有 token 检测函数、相关日志目录和 UI 展示函数。
2. 设计 `log/token_monitor/` 的文件命名与 JSON schema，明确是否需要日汇总和原始事件分离。
3. 新增 `token_monitor.py`，实现扫描、聚合、落盘、读取接口。
4. 替换 `config_ui_state_summary.py` 内直接解析日志的逻辑，改为调用 `token_monitor.py`。
5. 调整总览页的 token 文案和柱状图样式，使图形更接近单图统计。
6. 为 token 聚合和 UI 展示补测试，并运行 harness 检查。

## 发现与意外
- 项目里原本真正稳定可观测的 token 来源只有 `codex_local` 的 stderr 日志；`openai_api` 和 `openrouter_api` 之前并没有把 usage 落盘。
- `collect_config_ui_state()` 会被 UI 轮询频繁调用，因此 token 汇总不能每次都全量重扫重写，需要带 source signature 的快照缓存。
- `config_ui_page_sections.py` 原本已经接近单文件预算，本轮新增图表渲染后需要同步调整维护预算，并把继续拆 UI 渲染层加入 Todo。

## 决策记录
- 统一把 token 监测目录固定到 `log/token_monitor/`。
- `codex_local` 保留原始 `log/llm_tmp/*_codex.stderr.log` 作为底层来源，同时在 `log/token_monitor/codex_usage.json` 中生成规范化记录。
- `openai_api` 和 `openrouter_api` 在调用后把 usage 追加写入 `log/token_monitor/api_usage.jsonl`。
- UI 不再直接解析底层日志，而是统一读取 `token_monitor` 生成的 `latest_snapshot.json` 数据。
- 总览页 token 区域改为“今天 / 本周 / 本月”一行文字摘要加近 30 天竖向柱状图。

## 结果与复盘
- 新增 `src/sciencemonitor/token_monitor.py`，把 token 解析、API usage 记录、日级聚合、快照缓存和 UI 图表数据生成收口到单独模块。
- UI 总览页的 token 展示已经切换成新的 30 天柱状图风格，并在轮询 `/ui-status` 时自动刷新。
- 打开 UI 或轮询状态时，会自动在 `log/token_monitor/` 下生成 `codex_usage.json`、`api_usage.jsonl`、`daily_usage.json`、`latest_snapshot.json`。
- `openai_api` 和 `openrouter_api` 现在具备统一 usage 记录入口，后续切换 provider 时不会再出现“UI 有 token 区域但 API 调用完全没有记录”的断层。
- `Todo.md` 已补入“继续拆分 `config_ui_page_sections.py`”的后续排队项。

## 验证
- `./.venv/bin/python -m py_compile src/sciencemonitor/token_monitor.py src/sciencemonitor/llm.py src/sciencemonitor/llm_api_support.py src/sciencemonitor/config_ui.py src/sciencemonitor/config_ui_state_summary.py src/sciencemonitor/config_ui_page_sections.py src/sciencemonitor/config_ui_review.py src/sciencemonitor/article_summary_progress.py`
- `./.venv/bin/python -m pytest tests/test_token_monitor.py tests/test_config_ui.py -q`
- `./.venv/bin/python -m pytest -q`
- `./scripts/run_science_monitor.sh entropy-check`
- `./scripts/run_science_monitor.sh harness-check`
- `git diff --check`
