# 计划：2026-04-28_Ollama结构化JSON失败跳过

## 目的 / 大图景
- 解决 Ollama 本地模型偶发返回不完整 JSON 时导致整份周报失败的问题。
- 将单篇文章的结构化输出解析失败纳入“未完成项”处理，保持周报任务可继续运行。
- 保留错误原因，便于后续判断是否需要补做该篇或调整模型参数。

## 背景与定位
- 2026-04-28 UI 周报运行失败，状态显示 `Unterminated string starting at: line 2 column 539 (char 585)`。
- 状态显示当时已处理 8/35，已跳过 2 篇，当前单篇为 `Comprehensive and Open Assessment of Thermospheric Models...`。
- 该错误不是抓取失败，也不是周报渲染失败，而是 Ollama 单篇总结返回内容不是合法 JSON。

## 工作范围
- Ollama 结构化输出解析错误分类。
- 单篇总结循环中的可跳过错误处理。
- 周报未完成项原因展示。
- 对应测试与 harness 验证。

## 非目标
- 不修改周报内容风格。
- 不删除或重写已有输出文件。
- 不把所有 provider 的 JSON 错误都静默跳过；本轮只处理周报单篇 Ollama 输出失败。

## 进度
- [x] 步骤 1：把 Ollama JSON 解析失败转换为明确的 provider 输出错误
- [x] 步骤 2：单篇总结遇到 Ollama 输出错误时记录未完成并继续
- [x] 步骤 3：补充测试并验证周报不会整体失败
- [x] 步骤 4：运行 harness 并重启 UI

## 计划中的工作
- 在 API 支撑层识别结构化 JSON 解析失败，保留 provider 和原始输出预览。
- 在分析层转换成面向 UI 和周报的 `AnalysisProviderInvalidOutput`。
- 在单篇总结循环中复用已建立的 skipped summary 机制。
- 更新测试覆盖真实报错类型。

## 具体步骤
1. 修改 `llm_api_support.py` 和 `llm.py`，新增结构化输出解析错误类型。
2. 修改 `article_summaries.py`，让 Ollama 单篇输出错误被写入 `SkippedArticleSummary`。
3. 补充 `test_llm.py` 和 `test_pipeline.py`。
4. 运行针对性测试、全量测试、`git diff --check` 和 `harness-check`。

## 发现与意外
- 当前 UI 状态显示错误发生在单篇总结阶段，不是周报渲染阶段；已处理 8/35，已跳过 2 篇。
- Ollama API 返回的外层响应可解析，但 `message.content` 内部的结构化 JSON 不完整，因此原先会作为普通异常终止整个周报。

## 决策记录
- 只在周报单篇总结循环内跳过 Ollama 输出错误；报告级 LLM 分析仍应失败并暴露。

## 结果与复盘
- 新增结构化输出解析错误类型，能够保留 provider、请求名和原始输出预览。
- Ollama 单篇总结返回坏 JSON 时会被记录为未完成单篇，不再终止整份周报。
- 周报中的未完成项会写明“Ollama 本地模型返回的结构化 JSON 不完整或格式错误”。

## 验证
- `./.venv/bin/python -m pytest tests/test_llm.py tests/test_pipeline.py -q`：通过，26 passed。
- `./.venv/bin/python -m pytest -q`：通过，259 passed。
- `git diff --check`：通过。
- `./scripts/run_science_monitor.sh harness-check`：通过，overall=ok。
