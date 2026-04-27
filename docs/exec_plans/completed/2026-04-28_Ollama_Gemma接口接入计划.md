# 计划：2026-04-28_Ollama_Gemma接口接入

## 目的 / 大图景
- 为项目新增本地 Ollama 自动分析后端，使单篇总结、周报和深度解读可以调用本机 `gemma4:26b`。
- 在 UI 设置页补充 Ollama 配置入口，并纳入 doctor、token 记录和 harness 测试。

## 背景与定位
- 当前自动 provider 包括 `codex_local`、`openai_api`、`openrouter_api`。
- Ollama 是本地 HTTP 服务，不需要 API key，但需要检查服务可达性和模型名配置。
- 用户当前本机已部署 `gemma4:26b`，默认配置应直接指向该模型。

## 工作范围
- `src/sciencemonitor/analysis_providers.py`
- `src/sciencemonitor/llm.py`
- `src/sciencemonitor/llm_api_support.py`
- `src/sciencemonitor/config_ui.py`
- `src/sciencemonitor/config_ui_page_sections.py`
- `src/sciencemonitor/config_ui_functional_review.py`
- `src/sciencemonitor/doctor.py`
- `src/sciencemonitor/cli_support.py`
- `src/sciencemonitor/token_monitor.py`
- `src/sciencemonitor/ui_assets/config_ui.css`
- `config/analysis.json`
- `PROJECT_CONFIG.md`
- 相关测试

## 非目标
- 不默认切换当前 provider，避免影响现有工作流。
- 不强制启动 Ollama 服务。
- 不重跑真实文章总结或周报。

## 进度
- [x] 步骤 1：新增 Ollama provider 配置、调用与状态检查
- [x] 步骤 2：补充 UI 保存、显示、功能审查和 token 记录
- [x] 步骤 3：补测试、harness 验证并归档计划

## 计划中的工作
- 先实现 `run_ollama_structured()`，使用 Ollama `/api/chat` 的非流式 JSON 输出。
- 再把 `ollama_api` 加入自动 provider 列表、默认配置、provider 状态和 cache signature。
- 最后补 UI 设置面板、保存逻辑、token 统计和回归测试。

## 具体步骤
1. 扩展 provider 列表和默认配置，添加 `ollama_api`。
2. 实现 Ollama 结构化调用、usage 解析和本地服务可达检查。
3. 将 `AnalysisEngine` 的 `_run_structured()`、`provider_status()`、`_analysis_signature()` 接入 Ollama。
4. 更新 UI 设置页和保存逻辑，支持模型名、base_url、超时时间。
5. 更新 doctor、CLI 状态输出、token monitor 和 provider 图例。
6. 补充单元测试、UI 功能审查覆盖和 harness 验证。

## 发现与意外
- Ollama 的调用形态更接近 chat completions，本轮使用 `/api/chat`、`stream=false` 和 JSON schema `format`。
- 全量测试暴露了一个既有标签继承回归：深度解读继承相关单篇总结的 `#磁暴` 时会被全文片段误删。本轮限定为“相关单篇总结标签证据”场景修复，没有放宽普通文章总结的磁暴主旨判断。

## 决策记录
- `ollama_api` 作为自动 provider，不归入人工中转。
- 默认模型写为 `gemma4:26b`，默认地址写为 `http://127.0.0.1:11434/api/chat`。
- Ollama 不需要 API key，doctor 只在当前 provider 为 `ollama_api` 时检查服务可达性，避免常规自检被本地网络探测拖慢。

## 结果与复盘
- 已新增 `ollama_api` 自动 provider，默认模型为 `gemma4:26b`，默认地址为 `http://127.0.0.1:11434/api/chat`。
- UI 设置页已支持 Ollama 模型名、base_url 和超时时间保存；人工中转仍保持独立工作流，不混入全局自动 provider 切换。
- doctor、CLI 状态输出、token monitor、UI provider 显示、PROJECT_CONFIG 和用户指南已同步补齐。
- 本机 `ollama list` 可看到 `gemma4:26b`，本轮未执行真实生成请求，避免额外模型运行成本。

## 验证
- `./.venv/bin/python -m pytest tests/test_llm.py tests/test_config_ui.py tests/test_config_ui_functional_review.py tests/test_doctor.py tests/test_token_monitor.py tests/test_docs_review.py -q`：52 passed
- `./.venv/bin/python -m pytest tests/test_deep_reads.py::DeepReadTest::test_deep_read_can_write_to_eval_local_overrides_without_sync tests/test_tag_review.py::TagReviewTest::test_review_generated_tags_drops_storm_tag_when_storm_is_not_main_topic -q`：2 passed
- `./.venv/bin/python -m pytest -q`：251 passed
- `git diff --check`：通过
- `./scripts/run_science_monitor.sh harness-check`：overall=ok
- `ollama list`：可见 `gemma4:26b`
