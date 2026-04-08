# ChatGPT Web Manual Plan

## Purpose / Big Picture

这一轮要把 `chatgpt_web_manual` 做成 `ScienceMonitor` 的正式分析后端。

目标不是自动操控浏览器，而是把“ChatGPT 网页人工中转”接进现有 harness：

- 单篇总结可用
- 多篇周报可用
- 深度解读可用
- 请求包、响应、校验、缓存、doctor、maintenance、eval 继续走同一套工程护栏

这样可以把高消耗分析从 `codex_local` 分流出去，同时不破坏现有控制面和评测治理。

## Progress

- [x] 建立 `chatgpt_web_manual` provider 和请求/响应包模型
- [x] 接入单篇总结、周报、深度解读分析链路
- [x] 增加 CLI 导入/查看命令与配置入口
- [x] 接入 doctor / config-ui / PROJECT_CONFIG / 文档
- [x] 增加测试并跑维护 gate

## Current Targets

- `src/sciencemonitor/llm.py`
- `src/sciencemonitor/cli_support.py`
- `src/sciencemonitor/config.py`
- `src/sciencemonitor/doctor.py`
- `src/sciencemonitor/config_ui.py`
- `src/sciencemonitor/config_ui_page.py`
- `PROJECT_CONFIG.md`
- `config/analysis.json`

## Plan Of Work

1. 定义 `chatgpt_web_manual` provider 的运行语义、目录结构和响应校验逻辑
2. 在 `AnalysisEngine` 中接入人工中转 provider，并保证单篇、周报、深读都能生成请求包
3. 增加人工响应导入/状态查看 CLI，让 rerun 可以消费已导入结果
4. 接入 `PROJECT_CONFIG.md`、`doctor`、`config-ui` 和用户说明
5. 增加测试，跑 `pytest`、`doctor`、`maintenance-check`

## Decision Log

- 采用“人工中转”而不是浏览器自动化；不会自动操作 ChatGPT 网页
- `chatgpt_web_manual` 作为正式 provider 接入，而不是临时脚本
- 请求包和响应文件放在项目状态目录，作为可审计工件
- 单篇/周报/深读共用同一套 bundle + import + validation 机制
- 新增 CLI：
  - `manual-llm-status`
  - `manual-llm-import`
- `PROJECT_CONFIG.md`、`config-ui`、`doctor`、README 和 runbook 已同步接入 manual 模式
- 验证结果：
  - `pytest -q`：`120 passed`
  - `doctor --consistency-only`：通过
  - `entropy-check`：通过
  - `maintenance-check --auto-repair --max-passes 2`：通过
