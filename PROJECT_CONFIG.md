# Project Config

这个文件是项目的人类可读控制面板，也是推荐的日常配置入口。

程序启动时会读取这里标记为 `## Sync:` 的配置段，并同步到对应的 `config/*.json` 文件。
建议把这里当成日常调整入口；如果你直接改了 `config/*.json`，后续再次启动时这里的内容会覆盖它们。
如果你改坏了同步区的格式，程序会在启动时直接报错，并指出具体的位置。

## 当前环境与说明

- 项目根目录：`/Users/liwenbo/Documents/codex/ScienceMonitor`
- 本地 Python：`/Users/liwenbo/Documents/codex/ScienceMonitor/.venv/bin/python`
- 默认入口脚本：`./scripts/run_science_monitor.sh`
- 本地配置界面：`./scripts/run_science_monitor.sh config-ui`
- PDF 工具：`pdftotext`、`pdfinfo`、`pdftoppm` 由项目环境优先提供
- 当前 LLM provider 由下方 `config/analysis.json` 同步块控制
- 调研默认时间范围、每个来源抓取上限等由下方 `config/runtime.json` 同步块控制
- 输出目录由下方 `config/paths.json` 同步块控制

## 你通常会调的设置

- 切换 LLM 模式：修改 `provider` 为 `codex_local` 或 `openai_api`
- 切换模型：修改 `codex_local.model` 或 `openai_api.model`
- 调整 Codex 推理强度：修改 `article_summaries.reasoning_effort`、`report.reasoning_effort`、`deep_reads.reasoning_effort`
- 配置 API key：优先使用环境变量；也可写入 `openai_api.api_key`
- 调整单篇总结走 LLM 的数量：修改 `article_summaries.max_items_per_run`
- 调整周报送入 LLM 的文章数：修改 `report.max_papers_in_prompt`
- 调整默认调研窗口：修改 `cli_defaults.*_days_back` 或 `cli_defaults.*_window_days`
- 调整每个期刊的抓取上限：修改 `cli_defaults.*_max_per_source`
- 切换输出 Obsidian 仓库：修改 `config/paths.json` 中的 `output_root`

## 当前推荐理解

- 如果 `codex_local.model` 留空，项目不会显式指定模型，而是交给本机 `codex` 自己选择默认模型。
- `reasoning_effort` 只对 `codex_local` 生效；单篇总结和周报默认 `medium`，深度解读默认 `high`。
- 如果你想在不同电脑上得到更稳定一致的结果，建议直接把 `codex_local.model` 写死。
- 如果你更关心质量，建议优先提高 `article_summaries.max_items_per_run`，让更多单篇总结直接走 LLM。
- 如果你更关心速度或额度，建议先保留 `report.enabled=true`，并限制 `article_summaries.max_items_per_run`。

## Sync: config/runtime.json
```json
{
  "features": {
    "weekly_report_enabled": true
  },
  "cli_defaults": {
    "daily_days_back": 7,
    "daily_max_per_source": 20,
    "update_days_back": 7,
    "update_max_per_source": 20,
    "update_hydrate": true,
    "report_window_days": 7,
    "summaries_window_days": 7,
    "audit_window_days": 7,
    "audit_max_per_source": 100
  },
  "deep_read": {
    "search_full_text_when_pdf_missing": true,
    "pdf_page_limit": 40
  }
}
```

说明：
- `features.weekly_report_enabled`：是否真正生成周报文件
- `daily_days_back`：`daily` 命令默认回看多少天
- `update_days_back`：`update` 命令默认抓取多少天
- `report_window_days`：`report` 命令默认汇总多少天
- `summaries_window_days`：`summaries` 命令默认写多少天的单篇总结
- `audit_window_days`：`audit` 命令默认核查多少天
- `*_max_per_source`：每个期刊/来源一次最多请求多少条
- `update_hydrate`：抓取时是否默认补抓 DOI 落地页摘要
- `deep_read.search_full_text_when_pdf_missing`：没给 PDF 时是否自动按 DOI/题目找全文
- `deep_read.pdf_page_limit`：深度解读最多读取 PDF 的前多少页

## Sync: config/analysis.json
```json
{
  "provider": "codex_local",
  "article_summaries": {
    "enabled": true,
    "max_items_per_run": 0,
    "reasoning_effort": "medium"
  },
  "report": {
    "enabled": true,
    "max_papers_in_prompt": 50,
    "reasoning_effort": "medium"
  },
  "deep_reads": {
    "enabled": true,
    "max_input_chars": 28000,
    "reasoning_effort": "high"
  },
  "codex_local": {
    "model": "",
    "executable": "",
    "sandbox": "read-only",
    "timeout_seconds": 300
  },
  "openai_api": {
    "api_key": "",
    "api_key_env": "SCIENCEMONITOR_OPENAI_API_KEY",
    "model": "gpt-5-mini",
    "base_url": "https://api.openai.com/v1/responses",
    "timeout_seconds": 120
  }
}
```

说明：
- `provider`：当前分析后端，可选 `codex_local`、`openai_api`
- `article_summaries.enabled`：是否启用单篇总结的 LLM 分析
- `article_summaries.max_items_per_run`：每次运行最多多少篇走 LLM；`0` 表示不设上限
- `article_summaries.reasoning_effort`：单篇总结使用 codex_local 时的推理强度
- `report.enabled`：是否启用周报的 LLM 分析
- `report.max_papers_in_prompt`：周报提示词最多放多少篇文章
- `report.reasoning_effort`：周报使用 codex_local 时的推理强度
- `deep_reads.enabled`：是否启用深度解读功能
- `deep_reads.max_input_chars`：深度解读送入 LLM 的全文最大字符数
- `deep_reads.reasoning_effort`：深度解读使用 codex_local 时的推理强度
- `codex_local.executable`：手动指定 `codex` 可执行文件路径
- `openai_api.api_key_env`：优先读取的 API key 环境变量名
- `openai_api.base_url`：兼容接口地址，默认是 OpenAI Responses API

## Sync: config/paths.json
```json
{
  "output_root": "../../../Library/Mobile Documents/iCloud~md~obsidian/Documents/AI/ScienceMonitorOut"
}
```

说明：
- `output_root`：最终输出目录。周报、单篇总结、深度解读、article_index、my_work 都会写到这里

## 常见推荐配置档

这些不是自动同步块，而是推荐的改法。你可以把下面的值手动复制到对应的 `## Sync:` JSON 配置块里。

### 配置档 A：质量优先

适合正式周报、完整单篇总结、深度阅读较多的阶段。

- `provider`：`codex_local`
- `article_summaries.max_items_per_run`：`0`
- `report.max_papers_in_prompt`：`50` 或更高
- `daily_days_back` / `report_window_days`：`7`
- `update_max_per_source`：`50` 到 `100`

### 配置档 B：速度优先

适合平时快速扫读，先看趋势，再决定是否补跑全量 LLM。

- `provider`：`codex_local`
- `article_summaries.max_items_per_run`：`5` 到 `10`
- `report.max_papers_in_prompt`：`20` 到 `30`
- `daily_days_back` / `report_window_days`：`7`
- `update_max_per_source`：`20` 到 `50`

### 配置档 C：脱离 Codex 独立部署

适合其他电脑没有本地 Codex，改为外部 API 运行。

- `provider`：`openai_api`
- `openai_api.api_key_env`：推荐保留为 `SCIENCEMONITOR_OPENAI_API_KEY`
- `openai_api.model`：按你自己的接口能力设置
- `codex_local.model` / `codex_local.executable`：可留空

### 配置档 D：无 Codex 的独立运行

适合没有本地 Codex、但希望继续生成高质量单篇总结和周报的环境。

- `provider`：`openai_api`
- `article_summaries.enabled`：`true`
- `report.enabled`：`true`
- `openai_api.api_key_env`：推荐保留为 `SCIENCEMONITOR_OPENAI_API_KEY`

## 建议的模型策略

- `codex_local.model` 留空：使用本机 Codex 默认模型，最省心，但不同机器上不一定完全一致。
- `codex_local.model` 写死：结果更稳定，更适合长期运行和多机部署。
- `openai_api.model`：适合需要跨机器一致、且明确控制外部接口模型的情况。

## 其他可配置文件

这些内容目前不建议直接塞进这个 Markdown 同步块里，因为体量较大、编辑风险也更高；请直接编辑对应文件：

- `config/sources.json`：期刊监控列表、期刊层级、抓取模式、ISSN 等
- `config/topics.json`：空间物理主题分类与关键词规则
- `config/focus_tags.json`：标签体系、层级标签、同义词归一化
- `config/research_preferences.json`：运行时落地文件，通常由上面的研究偏好同步段自动生成，不建议手改
- `config/templates/article_summary_template.md`：单篇总结运行时模板
- `config/templates/daily_report_template.md`：周报运行时模板
- `config/templates/deep_reading_report_template.md`：深度解读运行时模板
- `docs/workflow_specs/*.md`：风格参考、prompt 契约与标签参考

## Sync: config/research_preferences.json

这里是研究偏好的日常编辑入口。程序启动时会把下面内容同步到 `config/research_preferences.json`，不需要直接改 JSON。

### 当前研究重心
- 热层密度及其变化机制
- 空间环境对卫星运行、轨道衰减、阻力环境和任务安全的影响
- 空间天气对人类生产生活的影响
- 与应用相关的空间环境风险评估、预报和响应
- 热层风相关研究，但不再局限于漠河区域

### 特别提醒策略
- 热层质量密度异常、长期变化、建模和数据同化
- 磁暴、亚暴、行星际环境变化对卫星阻力和轨道环境的影响
- 空间天气导致的卫星故障、通信导航受扰、轨道维持压力增加等应用问题
- 空间环境对低轨卫星星座、姿轨控和任务规划的影响
- 面向业务化或准业务化的预报模型、经验模型、机器学习模型
- 热层风与热层密度、卫星阻力、能量沉降之间的耦合关系

### 高优先级文章信号
- 直接讨论 TMD、satellite drag、orbit decay、thermospheric forcing 的文章
- 讨论 space weather societal impacts、operational impacts、infrastructure impacts 的文章
- 讨论上游空间环境信息如何改善卫星环境建模和预报的文章

### 监测范围
- 监测：space_physics
- 单篇总结：space_physics
- 周报：space_physics

### 深度解读范围
- 主领域：space_physics
- 允许相关学科：是
- 优先相关学科：artificial_intelligence

## 推荐操作方式

1. 日常运行参数、路径、LLM 后端：优先改这个文件里的三个 `## Sync:` 配置块。
2. 学科知识和产出风格：改 `config/*.json` 的学科配置文件、`config/templates/*.md` 与相关 workflow specs。
3. 用户偏好与重点提醒：改这个文件里的 `## Sync: config/research_preferences.json` 段。

