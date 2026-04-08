# LLM Analysis Readme

## 目标

这个项目现在采用“LLM 生成 + 规则护栏”的结构：
- LLM 层：负责单篇总结、周报和深度解读的用户可见文本。
- 规则层：负责抓取、过滤、标签归一化、模板契约和运行一致性检查。

## 配置文件

配置文件在 [config/analysis.json](../config/analysis.json)。

核心字段：
- `provider`：选择分析后端，可选 `codex_local`、`openai_api`、`chatgpt_web_manual`
- `article_summaries.enabled`：是否开启单篇总结的 LLM 分析
- `article_summaries.max_items_per_run`：每次运行最多让多少篇单篇总结走 LLM
- `report.enabled`：是否开启周报 LLM 分析
- `report.max_papers_in_prompt`：周报最多送给 LLM 的论文数
- `codex_local.executable`：可选，手动指定 `codex` 可执行文件
- `openai_api.api_key`：外部 API key
- `openai_api.api_key_env`：优先读取的环境变量名，默认是 `SCIENCEMONITOR_OPENAI_API_KEY`

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
    "enabled": true,
    "max_items_per_run": 10
  },
  "report": {
    "enabled": true,
    "max_papers_in_prompt": 25
  },
  "codex_local": {
    "model": "",
    "executable": "",
    "sandbox": "read-only",
    "timeout_seconds": 300
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

更推荐的部署方式：

```bash
export SCIENCEMONITOR_OPENAI_API_KEY="YOUR_API_KEY"
./scripts/run_science_monitor.sh doctor
./scripts/run_science_monitor.sh daily --date 2026-03-31 --days-back 7 --max-per-source 100
```

## 使用 ChatGPT 网页人工中转

如果你想减少本地 Codex 或 API 消耗，可以把 `provider` 设成 `chatgpt_web_manual`。

这个模式不会自动调浏览器，而是：

1. 运行原命令
2. 程序写出请求包到 `data/chatgpt_web_manual/requests/`
3. 默认只需要把 `prompt.md` 发给 ChatGPT 网页；如你自己手头有 PDF，可额外上传原始 PDF
4. 用 `manual-llm-import` 导回响应
5. 重新运行原命令

当前 manual 请求包默认不再复制全文整理稿、摘要整理稿、related summary 或 PDF。推荐按 `request.md` 里给出的文件名保存网页返回的 JSON。

常用命令：

```bash
./scripts/run_science_monitor.sh manual-llm-status --pending-only
./scripts/run_science_monitor.sh manual-llm-import --request-id <request_id> --response-file /path/to/response.txt
```

详细工作流见 [chatgpt_web_manual_workflow.md](chatgpt_web_manual_workflow.md)。

## 当前实现范围

当前 LLM 层已经接入到：
- 单篇文献总结
- 周报概览
- 周报建议
- 主题摘要
- 期刊摘要

标签规范化配置在 [config/focus_tags.json](../config/focus_tags.json)。
提示词与 schema 的审阅视图见 [../workflow_specs/llm_prompt_contracts.md](../workflow_specs/llm_prompt_contracts.md)。
这里维护的是层级标签表和别名映射，例如：
- `低纬电离层 -> 电离层/低纬`
- `ROTI -> 指数/ROTI`
- `频段/S波段 -> 仪器/射电/S波段`
- `月球重力场 -> 仪器/月球重力场模型`

当前不再保留规则法文本兜底：
- 如果 LLM 失败，单篇总结、周报和深度解读会直接报错
- 如果 `max_items_per_run` 有上限，超过上限的文章不会生成单篇总结，而不是回退到规则法

候选标签审阅：

- 运行 `./scripts/run_science_monitor.sh tag-candidates --min-count 2 --limit 50`
- 默认会把审阅报告写到 `log/tag_candidates_review.md`
- 原始候选数据保留在 `data/tag_candidates.json`

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
- `openai_api` 更适合脱离 Codex 的独立部署。
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
