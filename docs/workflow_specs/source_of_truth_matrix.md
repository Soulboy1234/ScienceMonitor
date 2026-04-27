# Source of Truth Matrix

## 目的

这份文档专门回答一个问题：

`ScienceMonitor` 里不同类型的规则，到底应该先改哪里，最终又以哪里为准。

它的作用不是重复 `AGENTS.md` 或 `ARCHITECTURE.md`，而是把“控制面”拆成可执行的修改规范，避免出现：

- 模板改了，但程序没变
- 提示词改了，但输出结构仍被 Python 固定
- 规则文档写了一套，测试和代码执行的是另一套

## 总原则

先判断你要改的是哪一类问题：

1. 研究偏好和优先级
2. 输出结构和渲染格式
3. LLM 提示词和分析口径
4. 标签归一化和主题分类
5. 测试护栏和验收标准

然后再按下面的矩阵处理。

## 当前矩阵

| 控制面 | 当前主要 source of truth | 参考/辅助文件 | 说明 |
| --- | --- | --- | --- |
| 运行路径、运行开关、LLM 提供方 | `PROJECT_CONFIG.md` + `config/*.json` + `src/sciencemonitor/config.py` | `README.md` | 真正运行时以配置文件和 `config.py` 解析结果为准 |
| 用户研究偏好、重点提醒 | `config/research_preferences.json` | `PROJECT_CONFIG.md`、`reporting.py`、`llm.py` | 运行时以这份 JSON 为准；日常编辑入口在 `PROJECT_CONFIG.md` 的研究偏好同步段 |
| 期刊监控范围 | `config/sources.json` | `README.md`、用户说明 | 监测什么期刊最终以 `sources.json` 为准 |
| 主题分类与保留逻辑 | `config/topics.json` + `src/sciencemonitor/topics.py` | `docs/workflow_specs/rules.md` | 主题和相关性判断是“配置 + 代码”共同决定，说明文档只是原则层 |
| 标签归一化与同义词映射 | 正式 tag：`config/tag/formal_tags.md`；机器规则与运行词表：`config/focus_tags.json`；预选 tag：`config/tag/pending_tags.md` + `config/pending_tags.json`；执行层：`src/sciencemonitor/tags.py` + `src/sciencemonitor/tag_review.py` + `src/sciencemonitor/tag_governance.py` | `docs/workflow_specs/literature_note_style_guide.md`、`docs/workflow_specs/hierarchical_tag_reference.md` | 正式 canonical tag 的人工 source of truth 是 `formal_tags.md`；机器规则仍保留在 `focus_tags.json`；运行时新增 tag 会先经过标签审核层，尽量归并 formal；无法覆盖时才进入 pending |
| 代码熵预算 | `config/maintenance_budget.json` + `src/sciencemonitor/entropy.py` | `docs/user_guides/maintenance_governance_runbook.md`、`docs/exec_plans/tech_debt_tracker.md` | 代码体量、超长函数和 import cycle 的预算以 `maintenance_budget.json` 为准；runbook 只解释如何使用 |
| 单篇总结最终 Markdown 展示结构 | `config/templates/article_summary_template.md` + `src/sciencemonitor/article_summaries.py` 的模板渲染器 | `docs/workflow_specs/article_summary_template_guide.md`、`docs/workflow_specs/literature_note_style_guide.md` | 模板现在控制区块顺序和展示版式；代码继续提供字段内容、兼容修复和校验契约 |
| 周报最终 Markdown 展示结构 | `config/templates/daily_report_template.md` + `src/sciencemonitor/reporting.py` 的模板渲染器 | `docs/workflow_specs/daily_report_template_guide.md`、`docs/workflow_specs/literature_note_style_guide.md` | 模板控制“周报信息 / 今日概览 / 文章推荐 / 主题推荐 / 各期刊主题汇总 / 其他”的正式结构；代码负责统计、主题聚类和块级内容生成 |
| 深度解读最终 Markdown 展示结构 | `config/templates/deep_reading_report_template.md` + `src/sciencemonitor/deep_reads.py` 的模板渲染器 | `docs/workflow_specs/deep_reading_template_guide.md`、`docs/workflow_specs/literature_note_style_guide.md` | 模板现在控制正式区块顺序和展示版式；代码继续负责 schema、字段归一化和输出校验 |
| LLM 单篇总结提示词 | `src/sciencemonitor/llm.py::_build_article_prompt` | `docs/workflow_specs/llm_prompt_contracts.md`、`docs/workflow_specs/article_summary_template_guide.md`、`docs/workflow_specs/literature_note_style_guide.md` | 单篇总结 prompt 当前并不直接读取运行时模板 |
| LLM 周报提示词 | `src/sciencemonitor/llm.py::_build_report_prompt` | `docs/workflow_specs/llm_prompt_contracts.md`、`docs/workflow_specs/daily_report_template_guide.md`、`config/research_preferences.json` | 展示结构由模板控制，但提示词和研究偏好仍由代码与运行上下文主导 |
| 周报 Markdown 合法性检查 | `src/sciencemonitor/reporting_template.py` + `src/sciencemonitor/reporting.py` | `config/templates/daily_report_template.md`、`docs/workflow_specs/report_review_rules.md` | 必需标题、表格结构、固定说明和未替换占位符由 review loop 与代码共同校验 |
| LLM 深度解读提示词与字段 schema | `src/sciencemonitor/llm.py::_build_deep_read_prompt` + `_deep_read_schema` | `docs/workflow_specs/llm_prompt_contracts.md`、`docs/workflow_specs/deep_reading_template_guide.md`、`config/research_preferences.json` | 这是当前深度解读最核心的控制面之一 |
| 深度解读 Markdown 合法性检查 | `src/sciencemonitor/deep_reads.py` | `config/templates/deep_reading_report_template.md` | 必需标题、禁用旧区块、文本收口当前都由代码校验 |
| 报告生成后格式审核规则 | `src/sciencemonitor/article_summaries.py` + `src/sciencemonitor/deep_read_markdown.py` + `src/sciencemonitor/reporting_template.py` | `docs/workflow_specs/report_review_rules.md`、`config/templates/*.md`、相关测试 | 模板表达静态骨架；编号换行、否定转折清理、摘要级来源说明、eval 链接语义等动态规则由 Python 审核层强制执行 |
| 输出索引和目录挂接 | `src/sciencemonitor/article_index.py` | `docs/workflow_specs/rules.md`、`docs/user_guides/literature_directory_integration_guide.md` | 目录整合原则写在文档里，具体挂接逻辑在代码里 |
| 运行与评测 gate | `src/sciencemonitor/harness.py` + `src/sciencemonitor/doctor.py` + `src/sciencemonitor/golden_eval.py` + `src/sciencemonitor/real_case_eval.py` | `docs/user_guides/eval_governance_runbook.md` | 运行一致性与评测治理以这些 Python 入口为准 |
| 代码维护 gate | `src/sciencemonitor/maintenance.py` + `src/sciencemonitor/entropy.py` + `tests/` | `docs/user_guides/maintenance_governance_runbook.md` | 代码级“审核 -> 调整 -> 测试 -> 再审核”以维护循环和测试结果为准 |

## 修改时的操作规范

### 1. 改研究偏好

优先修改：

- `config/research_preferences.json`

然后核对：

- `src/sciencemonitor/config.py` 是否仍能正确提取对应章节
- `src/sciencemonitor/llm.py` 和 `src/sciencemonitor/reporting.py` 的偏好使用方式是否还匹配

### 2. 改单篇总结、周报、深度解读的“正式结构”

先区分是哪一种：

#### 2A. 改单篇总结的展示结构

优先修改：

- `config/templates/article_summary_template.md`

然后同步核对：

- `docs/workflow_specs/article_summary_template_guide.md`
- `src/sciencemonitor/article_summaries.py`
- 相关测试

原因：

- 单篇总结现在已经接入模板渲染
- 区块顺序和最终版式优先以模板为准
- 但如果改动触及区块名、占位符契约或兼容逻辑，仍要同步修改代码

#### 2B. 改周报的展示结构

优先修改：

- `config/templates/daily_report_template.md`

然后同步：

- `docs/workflow_specs/daily_report_template_guide.md`
- `src/sciencemonitor/reporting.py`
- 相关测试

原因：

- 周报现在已经进入模板直渲染
- 区块顺序和最终版式优先以模板为准
- 但如果改动触及区块名、占位符契约或统计块生成方式，仍要同步修改代码

#### 2C. 改深度解读的正式结构

优先修改：

- `config/templates/deep_reading_report_template.md`
- 深度解读字段契约与校验：
  - `src/sciencemonitor/deep_reads.py`
  - `src/sciencemonitor/llm.py`

然后同步：

- `docs/workflow_specs/deep_reading_template_guide.md`
- 相关测试

原因：

- 深度解读已经进入模板直渲染，但 schema、字段和校验仍在代码里

### 3. 改写作风格、标签习惯、Obsidian 适配原则

优先修改：

- `docs/workflow_specs/literature_note_style_guide.md`
- `docs/workflow_specs/rules.md`

如果改的是生成后格式审核、自动修复或失败条件，再同步修改：

- `docs/workflow_specs/report_review_rules.md`

如果这会影响真实输出，再继续修改：

- `src/sciencemonitor/article_summaries.py`
- `src/sciencemonitor/deep_reads.py`
- `src/sciencemonitor/llm.py`
- `tests/`

### 4. 改主题分类和标签归一化

优先修改：

- 主题分类：`config/topics.json`
- 正式 canonical tag 集合：`config/tag/formal_tags.md`
- 预选 tag 审阅与转正：`config/tag/pending_tags.md`
- 机器规则、别名、patterns、suppression：`config/focus_tags.json`

必要时再修改：

- `src/sciencemonitor/topics.py`
- `src/sciencemonitor/article_summaries.py`
- `src/sciencemonitor/llm.py`
- `src/sciencemonitor/tag_governance.py`

### 5. 改提示词但不想改最终 Markdown 结构

优先修改：

- `src/sciencemonitor/llm.py`

同时确认：

- 生成结果是否仍能通过 `article_summaries.py` / `deep_reads.py` 的后处理和校验
- 是否需要补测试样例

## 当前最重要的现实判断

### 单篇总结

当前状态：

- 最终 Markdown 版式由 `config/templates/article_summary_template.md` 控制
- `render_article_summary()` 负责把生成好的字段填进模板
- 标签、正文、补充信息等字段内容仍由代码和分析结果决定

所以当前应认定为：

- 模板是展示层主 source of truth
- 代码是字段内容、兼容性和校验契约的主 source of truth

### 周报

当前状态：

- 最终 Markdown 版式由 `config/templates/daily_report_template.md` 控制
- `build_report()` 负责把统计结果、建议块、主题块和期刊块填进模板
- 高亮选择、主题统计和用户偏好加权仍由代码负责

所以当前应认定为：

- 模板是展示层主 source of truth
- `reporting.py` 是筛选逻辑、统计、块级内容和校验契约的主 source of truth

### 深度解读

当前状态：

- 提示词和 schema 决定 LLM 返回字段
- `config/templates/deep_reading_report_template.md` 决定最终 Markdown 结构
- `_render_deep_read_markdown()` 负责把字段填进模板
- `_validate_deep_read_markdown()` 决定什么输出算合法

所以当前应认定为：

- 模板是展示层主 source of truth
- `llm.py` + `deep_reads.py` 是字段契约、归一化和校验的主 source of truth

## 后续治理方向

第二阶段先做到“说清楚谁说了算”。

后续如果继续推进，可以选择两条路中的一条：

1. 保持“代码主控”
   - 文档主要表达规范
   - Python 负责真实渲染
   - 优点是稳定、直接
   - 代价是模板容易漂移

2. 逐步转向“模板/配置主控”
   - 让更多结构从模板或 schema 驱动
   - 代码更多只做填充和校验
   - 优点是规则更集中
   - 代价是迁移成本更高，需要更强测试护栏

当前项目已经进入折中状态：

- 单篇总结、周报和深度解读都采用“模板主控展示层 + 代码主控契约与校验”

所以下一步更适合按模块逐个推进，而不是一次性把所有输出都改成模板直渲染。

## 使用规则

- 只要改动涉及模板、提示词、规则文档、输出结构中的任意两个以上面向，就先回看这份矩阵
- 如果某项 `source of truth` 发生了变化，必须同步更新：
  - `AGENTS.md`
  - `ARCHITECTURE.md`
  - 本文档
  - 对应 ExecPlan
