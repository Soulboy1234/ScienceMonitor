# LLM Prompt Contracts

## 目的

这份文档用于把当前 `ScienceMonitor` 的 LLM 提示词契约从代码里“显出来”，方便审阅和后续治理。

它回答的是：

- 单篇总结、周报、深度解读分别把什么送进 LLM
- LLM 被要求输出什么
- 哪些规则仍然只存在于 `llm.py`

注意：

- 这份文档是审阅视图，不是运行时 source of truth
- 当前真正的 prompt 和 schema 仍以 `src/sciencemonitor/llm.py` 为准

## 当前 source of truth

- 单篇总结 prompt：`src/sciencemonitor/llm.py::_build_article_prompt`
- 周报 prompt：`src/sciencemonitor/llm.py::_build_report_prompt`
- 深度解读 prompt：`src/sciencemonitor/llm.py::_build_deep_read_prompt`
- 单篇总结 schema：`src/sciencemonitor/llm.py::_article_schema`
- 周报 schema：`src/sciencemonitor/llm.py::_report_schema`
- 深度解读 schema：`src/sciencemonitor/llm.py::_deep_read_schema`

## 单篇总结

### 输入边界

- 只送标题、摘要、期刊、日期、作者、主题标签
- 不送全文
- 会带入当前用户偏好的优先主题和特别提醒

### 当前硬要求

- 只根据已提供元数据和摘要判断
- 中文题目要更像研究笔记里的概括，不是英文标题直译
- 标签优先写成稳定、可统计的层级名词
- 正文需要压缩研究问题、数据或仪器、方法和主要结论
- 摘要不足时必须明说信息有限

### 当前 schema

- `chinese_title`
- `tags`
- `body`
- `supplement`
- `recommendation`
- `one_sentence`

## 周报

### 输入边界

- 只送单篇总结结果，不送全文
- 输入包括期刊、标题、中文概括、日期、主题、标签、一句话总结、正文总结、补充信息
- 会带入当前用户研究偏好和特别提醒

### 当前硬要求

- 只能基于已有单篇总结归纳，不允许编造全文细节
- 输出要适合科研工作周报
- 概览和建议要突出真正值得继续跟踪的主题、事件、仪器、方法或趋势
- 要结合当前研究偏好，优先提醒热层密度、卫星影响、应用影响、业务化预报等方向

### 当前 schema

- `overview_bullets`
- `daily_suggestions`
- `topic_insights`
- `journal_insights`

说明：

- 周报的最终 Markdown 结构现在由 `config/templates/daily_report_template.md` 控制
- LLM 这里只负责给周报中的“概览 / 建议 / 主题摘要 / 期刊摘要”提供分析块

## 深度解读

### 输入边界

- 送的是全文或全文级长文本
- 会带入题目、期刊、DOI、作者、发表日期
- 如果已有单篇总结，也会把相关单篇总结作为辅助背景送入
- 会带入用户研究重心和优先提醒方向

### 当前硬要求

- 必须体现研究判断，而不是复述摘要
- 要区分硬结论、次级结论、合理解释和仍需保留的部分
- 要覆盖研究动机、方法、关键结果、贡献、局限、可复现性和与已有工作的关系
- 大多数是空间物理论文，但也允许与空间物理主线相关的 AI 或其他支撑学科论文
- 空间物理论文优先用层级标签；AI 或交叉学科论文使用该领域自然、稳定、便于检索的标签
- 一句话总述禁止“不是……而是……”式开头
- 不允许输出旧版区块名

### 当前 schema

- `chinese_title`
- `tags`
- `paper_type`
- `one_sentence_overview`
- `why`
- `how`
- `key_results`
- `contribution`
- `limitations`
- `reproducibility`
- `relation`
- `final_conclusion`
- `relation_to_my_work`
- `follow_up_questions`
- `needs_manual_review`
- `knowledge_position`

## 标签参考文件怎么理解

- `config/focus_tags.json` 是机器归一化和别名映射的 source of truth
- `docs/workflow_specs/hierarchical_tag_reference.md` 是人类阅读参考，不参与运行时匹配

所以：

- 机器要用的首选词表、canonical 命名、开放词表约束和候选记录路径，改 `config/focus_tags.json`
- 人想快速查“常用标签一般长什么样”，看 `docs/workflow_specs/hierarchical_tag_reference.md`

它不应该搬到 `config/`，因为它不是程序直接消费的运行时资产。
