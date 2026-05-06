# LLM Analysis Readme

## 目标

这个项目现在采用“LLM 生成 + 规则护栏”的结构：
- LLM 层：负责单篇总结、周报和深度解读的用户可见文本。
- 规则层：负责抓取、过滤、标签归一化、模板契约和运行一致性检查。

## 配置文件

配置文件在 [config/analysis.json](../config/analysis.json)。

核心字段：
- `provider`：选择默认分析后端，可选 `codex_local`、`openai_api`、`openrouter_api`、`ollama_api`
- `article_summaries.reasoning_effort`：单篇总结推理强度
- `report.reasoning_effort`：周报推理强度
- `deep_reads.reasoning_effort`：深度解读推理强度
- `codex_local.executable`：可选，手动指定 `codex` 可执行文件
- `openai_api.*`：OpenAI Responses API 配置
- `openrouter_api.*`：OpenRouter API 配置
- `ollama_api.*`：Ollama 本地服务配置

## 使用本地 Codex

如果你想直接用当前机器上的 Codex 进行语义分析：

1. 把 `provider` 设为 `codex_local`
2. 保持本机 `codex` 可用并已登录
3. 如需指定路径，可设置 `codex_local.executable` 或环境变量 `SCIENCEMONITOR_CODEX_BIN`
4. 直接运行：

```bash
./scripts/run_science_monitor.sh doctor
./scripts/run_science_monitor.sh daily --date 2026-03-16 --days-back 7 --max-per-source 100
```

特点：
- 不需要额外 API key
- 适合在当前 Codex 环境或本机已安装 Codex CLI 的情况下直接使用

## 使用外部 API

如果你想脱离 Codex 环境运行，或者接自己的 API：

1. 把 `provider` 改成 `openai_api`
2. 优先设置环境变量 `SCIENCEMONITOR_OPENAI_API_KEY`
3. 也可以在 [config/analysis.json](../config/analysis.json) 中填入 `api_key`
4. 如有需要，改 `model` 和 `base_url`
5. 直接运行同样的命令

示例：

```json
{
  "provider": "openai_api",
  "article_summaries": {
    "reasoning_effort": "medium"
  },
  "report": {
    "reasoning_effort": "medium"
  },
  "deep_reads": {
    "reasoning_effort": "high"
  },
  "codex_local": {
    "model": "",
    "executable": "",
    "sandbox": "read-only",
    "timeout_seconds": 900
  },
  "openai_api": {
    "api_key": "YOUR_API_KEY",
    "api_key_env": "SCIENCEMONITOR_OPENAI_API_KEY",
    "model": "gpt-5-mini",
    "base_url": "https://api.openai.com/v1/responses",
    "timeout_seconds": 120
  }
}
```

如果你使用 OpenRouter 这类聚合平台，把 `provider` 改成 `openrouter_api`，并填写：

- `openrouter_api.api_key_env`
- `openrouter_api.model`
- `openrouter_api.base_url`
- 可选的 `openrouter_api.site_url`
- 可选的 `openrouter_api.app_name`

如果你使用本机 Ollama，把 `provider` 改成 `ollama_api`，并填写：

- `ollama_api.model`，默认 `gemma4:26b`
- `ollama_api.base_url`，默认 `http://127.0.0.1:11434/api/chat`
- `ollama_api.timeout_seconds`
- `ollama_api.keep_alive`，控制模型生成后在内存中保留多久。`0` 表示生成后立即卸载，留空表示使用 Ollama 默认策略
- `ollama_api.num_ctx`，控制单次请求上下文窗口。深度解读需要全文级输入，值太小会让本地模型内部截断材料
- `ollama_api.num_predict`，控制最大输出 token。深度解读结构较长，值太小容易生成半截 JSON
- `ollama_api.deep_read_num_predict`，只覆盖 Ollama 深度解读请求的最大输出 token；不影响单篇总结、周报、Codex 或其他 API provider
- `ollama_api.deep_read_quality_mode`，只增强 Ollama 深度解读：先做全文证据预分析，再生成最终深读报告。单篇总结仍按实际来源文本工作，如果只有摘要，不会强行看全文
- `ollama_api.deep_read_stage_keep_alive`，控制 Ollama 深度解读两阶段之间临时保留模型的时间。默认 `1m`，用于避免模型刚卸载后第二阶段返回空内容
- `ollama_api.deep_read_final_max_chars`，控制最终报告阶段送入的全文核对材料长度。完整全文已由第一阶段读取，最终阶段保留证据提纲和压缩核对材料

Ollama 不需要 API key，但需要先启动本机 Ollama 服务，并确保目标模型已部署。
项目不会直接使用 Ollama 的 `format: json_schema` 约束；部分本地模型在该模式下会截断 JSON。当前实现会用普通 chat 请求追加本地 JSON 字段契约，再由程序解析和校验。

更推荐的部署方式：

```bash
export SCIENCEMONITOR_OPENAI_API_KEY="YOUR_API_KEY"
./scripts/run_science_monitor.sh doctor
./scripts/run_science_monitor.sh daily --date 2026-03-31 --days-back 7 --max-per-source 100
```

## 使用 ChatGPT 网页人工中转

如果你想减少本地 Codex 或 API 消耗，不需要把全局 `provider` 切成 `chatgpt_web_manual`。人工中转现在是独立工作流。

这个模式不会自动调浏览器，而是：

1. 运行原命令
2. 程序写出请求包到 `data/chatgpt_web_manual/requests/`
3. 默认只需要把 `prompt.md` 发给 ChatGPT 网页；如你自己手头有 PDF，可额外上传原始 PDF
4. 用 `manual-llm-import` 导回响应
5. 重新运行原命令

当前 manual 请求包默认不再复制全文整理稿、摘要整理稿、related summary 或 PDF。推荐按 `request.md` 里给出的文件名保存网页返回的 JSON，然后导入。

常用命令：

```bash
./scripts/run_science_monitor.sh manual-llm-status --pending-only
./scripts/run_science_monitor.sh manual-llm-import --request-id <request_id>
```

详细工作流见 [chatgpt_web_manual_workflow.md](chatgpt_web_manual_workflow.md)。

## 当前实现范围

当前 LLM 层已经接入到：
- 单篇文献总结
- 周报概览
- 周报建议
- 主题摘要
- 期刊摘要

标签规范化配置拆成两层：
- 正式标签人工入口在 [config/tag/formal_tags.md](../../config/tag/formal_tags.md)
- 机器规则与别名映射在 [config/focus_tags.json](../../config/focus_tags.json)
- 预选标签人工入口在 [config/tag/pending_tags.md](../../config/tag/pending_tags.md)
- 预选标签机器记录在 [config/pending_tags.json](../../config/pending_tags.json)
提示词与 schema 的审阅视图见 [../workflow_specs/llm_prompt_contracts.md](../workflow_specs/llm_prompt_contracts.md)。
这里维护的是层级标签表和别名映射，例如：
- `低纬电离层 -> 电离层/低纬`
- `ROTI -> 指数/ROTI`
- `频段/S波段 -> 仪器/射电/S波段`
- `月球重力场 -> 仪器/月球重力场模型`

当前不再保留规则法文本兜底：
- 如果 LLM 失败，单篇总结、周报和深度解读会直接报错
- 当前也不再维护旧的 `enabled`、`max_items_per_run`、`max_papers_in_prompt`、`max_input_chars` 这些历史配置项

预选标签审阅：

- 运行 `./scripts/run_science_monitor.sh tag-candidates --min-count 2 --limit 50`
- 默认会同步刷新 `config/tag/pending_tags.md`
- 原始机器记录保留在 `config/pending_tags.json`
- 只有在 `pending_tags.md` 中勾选并执行“tag转正”后，标签才会进入正式体系

## 运行输出

- 周报输出到输出根目录下的 `research_reports/`
- 单篇总结输出到输出根目录下的 `auto/article_summaries/`
- 深读输出到输出根目录下的 `auto/deep_reads/`
- 深读 PDF 资源输出到输出根目录下的 `auto/deep_reads_pdf/`
  - 默认与对应深读笔记保持同名，仅扩展名不同，便于在 Obsidian 里按名字互相定位
- 输出索引维护在输出根目录下的 `article_index/`
- 公开默认输出根目录由 [../config/paths.json](../config/paths.json) 中的 `output_root` 指定；本机私人路径可用不会上传 GitHub 的 `config/local.paths.json` 覆盖
- LLM 临时文件和源审计输出到 [../log](../log)
- 长期缓存保留在 `data/llm_cache`

## 注意事项

- 单篇总结和深度解读现在会尽量复用全文整理稿、摘要包或人工中转请求包，不再只看原始摘要。
- `codex_local` 更适合演示和本机使用。
- `openai_api` 更适合直接接 OpenAI。
- `openrouter_api` 更适合接 OpenRouter 或类似的统一 API 平台。
- `ollama_api` 更适合本机离线或低成本运行，但质量和 JSON 稳定性取决于本地模型能力。
- `chatgpt_web_manual` 更适合高成本分析的人工作业流，不适合完全无人值守运行。
- `openai_api.base_url` 默认要求使用 `https`；只有本地 `localhost` 调试接口允许 `http`
- 当前项目运行并不依赖 Codex skills；skills 只影响我在当前会话里的工作方式，不影响你把程序部署到其他电脑
- 如果要进一步提升质量，下一步最值得做的是让更多单篇总结直接走 LLM，并继续优化提示词。

## 自检

迁移到其他电脑后，建议先运行：

```bash
./scripts/run_science_monitor.sh doctor
```

它会检查：
- 当前是否真的跑在项目 `.venv`
- `pdftotext`、`pdfinfo`、`pdftoppm` 是否可用
- 当前 LLM provider 是什么
- `codex` 是否可用
- `openai_api` 的 key 是否已准备好
- `openrouter_api` 的 key 是否已准备好
- `ollama_api` 的本地服务是否可访问
