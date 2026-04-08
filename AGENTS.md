# AGENTS.md

## 项目定位

`ScienceMonitor` 是一个面向空间物理文献监测的本地工程，负责：

- 从期刊源抓取论文元数据
- 生成单篇总结、深度解读和周报
- 维护适配 Obsidian 的输出目录与索引

工作主线说明：

- 监测、单篇总结、周报的默认范围是空间物理文献
- 深度解读通常也是空间物理论文，但可以覆盖与主线研究相关的其他学科论文
- 当前特别允许并鼓励把与空间物理研究相关的人工智能论文作为深度解读对象

## 先读什么

1. [README.md](README.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [PLANS.md](PLANS.md)
4. [PROJECT_CONFIG.md](PROJECT_CONFIG.md)
5. [docs/exec_plans/GovernanceBoard.md](docs/exec_plans/GovernanceBoard.md)
6. [docs/README.md](docs/README.md)

如果任务涉及输出风格、标签、研究偏好，再继续读：

- [PROJECT_CONFIG.md](PROJECT_CONFIG.md) 中的研究偏好同步段
- 如需核对运行时结果，再读 [config/research_preferences.json](config/research_preferences.json)
- [docs/workflow_specs/rules.md](docs/workflow_specs/rules.md)
- [docs/workflow_specs/llm_prompt_contracts.md](docs/workflow_specs/llm_prompt_contracts.md)
- [docs/workflow_specs/literature_note_style_guide.md](docs/workflow_specs/literature_note_style_guide.md)
- [docs/workflow_specs/source_of_truth_matrix.md](docs/workflow_specs/source_of_truth_matrix.md)

## 标准命令

- 环境自检：`./scripts/run_science_monitor.sh doctor`
- 代码熵检查：`./scripts/run_science_monitor.sh entropy-check`
- 维护循环：`./scripts/run_science_monitor.sh maintenance-check --auto-repair`
- 统一 harness gate：`./scripts/run_science_monitor.sh harness-check`
- Golden eval：`./scripts/run_science_monitor.sh golden-eval`
- 真实案例评测：`./scripts/run_science_monitor.sh real-eval`
- 人工中转请求状态：`./scripts/run_science_monitor.sh manual-llm-status`
- 人工中转响应导入：`./scripts/run_science_monitor.sh manual-llm-import --request-id <id>`，必要时追加 `--response-file /path/to/response.txt`
- 发版前清单：`docs/user_guides/release_checklist.md`
- 列出期刊：`./scripts/run_science_monitor.sh sources`
- 跑测试：`./.venv/bin/python -m pytest -q`
- 本地运行：`./scripts/run_science_monitor.sh <command>`

## 代码与文档导航

- 主入口：`science_monitor.py`
- CLI：`src/sciencemonitor/cli.py`
- 主流程：`src/sciencemonitor/pipeline.py`
- 环境与一致性自检：`src/sciencemonitor/doctor.py`
- 代码熵审计：`src/sciencemonitor/entropy.py`
- 维护循环：`src/sciencemonitor/maintenance.py`
- 统一 harness gate：`src/sciencemonitor/harness.py`
- Golden eval：`src/sciencemonitor/golden_eval.py`
- 真实案例评测：`src/sciencemonitor/real_case_eval.py`
- 治理总览：`docs/exec_plans/GovernanceBoard.md`
- 抓取：`src/sciencemonitor/crossref.py`
- 网页全文/摘要抓取：`src/sciencemonitor/article_fetch.py`
- 配置：`src/sciencemonitor/config.py`
- 本地配置面板：`src/sciencemonitor/config_ui.py`
- ChatGPT 网页人工中转：`src/sciencemonitor/chatgpt_web_manual.py`
- 单篇总结：`src/sciencemonitor/article_summaries.py`
- 周报：`src/sciencemonitor/reporting.py`
- 深读：`src/sciencemonitor/deep_reads.py`
- 标签执行层：`src/sciencemonitor/tags.py`
- 候选标签审阅：`src/sciencemonitor/tag_candidates.py`
- 输出索引：`src/sciencemonitor/article_index.py`
- 来源审计：`src/sciencemonitor/source_audit.py`
- 全量 Python 文件说明：`docs/user_guides/python_module_map.md`

## 当前 source of truth

- 运行参数与路径：`PROJECT_CONFIG.md` 和 `config/*.json`
- 维护预算：`config/maintenance_budget.json`
- 用户研究偏好：`PROJECT_CONFIG.md` 的研究偏好同步段，运行时落地到 `config/research_preferences.json`
- 标签归一化：`config/focus_tags.json`
- 期刊源与主题：`config/sources.json`、`config/topics.json`

注意：

- `config/templates/article_summary_template.md` 现在是单篇总结展示层的 source of truth。
- `config/templates/daily_report_template.md` 现在是周报展示层的 source of truth。
- `config/templates/deep_reading_report_template.md` 现在是深度解读展示层的 source of truth。
- 模板、提示词、规则文档和 Python 实现的优先级，以 `docs/workflow_specs/source_of_truth_matrix.md` 为准。
- 当前无 PDF 策略：
  - `src/sciencemonitor/article_summaries.py` 会优先尝试网页全文，失败则退回摘要，并为仅摘要总结打 `#信息来源/仅摘要`
  - `src/sciencemonitor/deep_reads.py` 只做简单网页搜索；没有可用全文时直接提示用户提供 PDF
- 当前支持 `chatgpt_web_manual` 人工中转模式：
  - 程序会在 `data/chatgpt_web_manual/requests/` 下生成请求包
  - 固定工作流是上传 `prompt.md`，深度解读可按需额外上传原始 PDF，再把网页端 JSON 放到 `responses/`
  - 用户在 ChatGPT 网页完成分析后，用 `manual-llm-import` 导入响应
  - 重新执行原命令后，结果继续走现有缓存、审核和输出链路
  - 深度解读不继承单篇总结的 `信息来源/*` 状态标签；这类标签只描述单篇总结自身的证据边界
- 现阶段真实输出行为由“运行时模板 + Python 逻辑”共同决定：
  - `src/sciencemonitor/reporting.py` 仍负责周报的筛选逻辑、统计、块级内容生成和模板渲染
  - `src/sciencemonitor/deep_reads.py` 仍负责深度解读的 schema 落地、归一化和模板渲染
  - `src/sciencemonitor/article_summaries.py` 仍负责单篇总结的字段生成、兼容修复和模板渲染

额外原则：

- 运行时直接消费的模板、配置和机器资产，优先放 `config/`
- `docs/` 尽量只保留规范、说明、计划和人类阅读材料

## 什么时候必须写 ExecPlan

出现以下任一情况时，先在 `docs/exec_plans/active/` 新建或更新计划：

- 预计会改 3 个以上文件
- 预计会工作 30 分钟以上
- 会改变架构、source of truth 或目录结构
- 会引入迁移步骤或分阶段治理

完成后，把计划移到 `docs/exec_plans/completed/`。

## 修改规则

- 不要把运行态数据、缓存、日志、临时文件当作源码修改对象
- 不要默认认为模板文档已经被代码消费，修改前先核实
- 涉及输出格式时，优先补测试，再改行为
- 涉及研究偏好时，优先更新 `PROJECT_CONFIG.md` 里的 `## Sync: config/research_preferences.json` 段
- 涉及长期工程规则时，优先更新 `AGENTS.md`、`ARCHITECTURE.md`、`PLANS.md`
