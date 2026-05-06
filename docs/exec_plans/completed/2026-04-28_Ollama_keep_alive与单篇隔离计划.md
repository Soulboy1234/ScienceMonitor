# 计划：2026-04-28_Ollama_keep_alive与单篇隔离

## 目的 / 大图景
- 明确 Ollama 周报单篇总结是否会继承上一篇文章的对话上下文。
- 增加 Ollama 模型生命周期控制，让用户可以选择每篇文章生成后立即卸载模型内存。
- 为本地大模型批量周报提供可调的稳定性选项，避免隐性运行状态影响后续文章。

## 背景与定位
- 2026-04-28 UI 实测中，`ollama_api / gemma4:26b` 可以完成前 2 篇单篇总结，但第 3 篇单次请求超过 900 秒并进入 `paused_timeout`。
- 当前代码每次调用 `/api/chat` 都只发送当前 prompt 和 system message，没有传入上一轮 `messages` 或对话 id，因此逻辑上已经是“每篇新对话”。
- Ollama 默认会把模型在内存中保留一段时间；这不等于对话上下文继承，但可能影响显存/内存占用和后续任务稳定性。

## 工作范围
- Ollama 请求 payload 的 `keep_alive` 支持。
- UI 设置页增加 Ollama `keep_alive` 配置入口。
- 当前本机配置默认设为 `0`，用于测试“每篇生成后立即卸载模型”。
- 对应文档、PROJECT_CONFIG 同步和测试。

## 非目标
- 不重新启动周报。
- 不删除已生成的单篇总结。
- 不把 Ollama timeout 直接改成无限等待。

## 进度
- [x] 步骤 1：确认并实现 Ollama `keep_alive` 配置
- [x] 步骤 2：同步 UI、配置和文档
- [x] 步骤 3：补测试并跑 harness

## 计划中的工作
- 在 `run_ollama_structured()` 中读取 `ollama_api.keep_alive`，并写入 `/api/chat` payload。
- 支持 `0`、`5m`、`-1` 等 Ollama 官方格式；空值表示使用 Ollama 默认策略。
- 在设置页 Ollama 子面板增加 `keep_alive` 字段和说明。
- 将本机当前配置设为 `0`，用于下一次周报测试。

## 具体步骤
1. 修改 `llm_api_support.py`，增加 `keep_alive` 规范化并写入请求 payload。
2. 修改 `config_ui.py`、`config_ui_page_sections.py`、`llm.py` 默认配置和配置保存逻辑。
3. 修改 `PROJECT_CONFIG.md`、`project_config_markdown.py`、`docs/user_guides/llm_analysis_readme.md`。
4. 修改 `tests/test_llm.py` 和 `tests/test_config_ui.py`，覆盖 payload 与 UI 保存。
5. 运行定向测试、完整测试和 `harness-check`。

## 发现与意外
- 当前代码原本已经每篇文章独立调用 `/api/chat`，不会把上一篇文章的 `messages` 传给下一篇。
- 需要治理的是 Ollama 模型驻留内存，而不是对话上下文继承。
- `keep_alive=0` 会降低模型常驻内存风险，但可能增加下一篇文章的模型重新加载时间；后续周报测试要同时观察稳定性和总耗时。

## 决策记录
- 采用 `keep_alive=0` 作为当前本机测试配置，因为 Ollama 官方文档说明 `0` 会在生成后立即卸载模型。
- 不把“卸载模型”理解为“清空对话历史”；对话历史本来就没有跨文章传递。

## 结果与复盘
- `ollama_api.keep_alive` 已加入默认配置、UI 设置、PROJECT_CONFIG 同步、用户说明和 Ollama 请求 payload。
- 当前本机配置已设为 `keep_alive: 0`，下一次 Ollama 周报会在每次成功生成后要求 Ollama 立即卸载模型。
- UI 设置页新增 `Ollama keep_alive` 字段；填 `0` 表示立即卸载，留空表示使用 Ollama 默认策略，填 `5m` 或 `-1` 可控制保留策略。
- 本轮没有重跑周报，也没有改动输出文件。

## 验证
- `./.venv/bin/python -m pytest tests/test_llm.py tests/test_config_ui.py -q` 通过，39 passed。
- `./.venv/bin/python -m pytest -q` 通过，255 passed。
- `git diff --check` 通过。
- `./scripts/run_science_monitor.sh harness-check` 通过，overall=ok。
