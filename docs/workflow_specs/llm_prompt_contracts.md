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
- 常见 tag 必须优先归到 canonical：`SC/sudden commencement` 写 `事件/磁暴/急始`，`HILDCAA` 写 `事件/HILDCAAs`，`TIE-GCM` 写 `模型/TIEGCM`，`E-CHAIM` 这类模型写 `模型/E-CHAIM`，`NO/一氧化氮` 写 `对象/热层/成分`
- 不用 `交叉对比`、`趋势拟合`、`观测基准`、`模型调优` 这类宽泛动作词新造临时 tag；优先归到 `方法/统计研究`、`数据/数据对比` 或 `方法/误差估计`
- `F层/F2层` 这类宽泛层位通常写 `对象/电离层`；只有明确指向 `foF2/hmF2` 时才用对应 canonical
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
- 先客观总结本周论文的主要方向、共性、交叉点和新的切入角度
- 再单独指出与当前研究偏好最贴近的内容，优先提醒热层密度、卫星影响、应用影响、业务化预报等方向
- `topic_insights` 应尽量对应具体科学问题，而不是只写“电离层”“热层”这类宽泛分类
- `daily_suggestions` 当前主要服务于“建议重点关注的事件或物理过程 / 对当前工作的可能启发”，不再是旧版泛泛建议区

### 当前 schema

- `overview_bullets`
- `daily_suggestions`
- `topic_insights`
- `journal_insights`

说明：

- 周报的最终 Markdown 结构现在由 `config/templates/daily_report_template.md` 控制
- LLM 这里只负责给周报中的“客观概览 / 重点关注过程 / 主题摘要 / 期刊摘要”提供分析块

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
- tag 参照单篇总结口径：闭集优先、具体优先、父子压制、保守不脑补，标签是检索系统，不是论文观点摘抄
- `对象/` 只放实体、区域、系统、观测量或明确物理对象；抽象机制概念不能写成 `对象/物理机制/*`、`对象/能量转换/*`、`对象/过程/*`
- 地磁指数必须使用 canonical tag：`D指数` / `D index` / `Dst` 归一为 `#指数/Dst`，`K指数` / `K index` / `Kp` 归一为 `#指数/Kp`
- 仪器 tag 必须有论文实际使用该仪器或数据的证据；参考文献、会议名、背景介绍或相关工作中的偶然缩写不能触发 `#仪器/...`
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

### Ollama 深度解读质量模式

`ollama_api` 在 `deep_read_quality_mode=true` 时使用独立增强链路，不影响 `codex_local`：

- 第一阶段使用 Ollama-only evidence v2 schema，拆分研究问题、引言空白、方法链、硬结论、次级结论、合理推论、待验证问题、贡献、局限、可复现性、与用户工作的关系和人工复核点。
- 第二阶段使用 Ollama-only final prompt，优先读取 Introduction、Methods/Data、Results、Discussion/Conclusion 等分段核对材料。
- 如果本地质量审计发现输出过短、关键结果分层不足、列表格式错误或“直接相关”缺少证据，会触发一次 Ollama-only 修订。
- `codex_local` 仍使用上面的通用深度解读 prompt 和 schema，不调用 Ollama-only prompt/schema。

## 标签参考文件怎么理解

- `config/focus_tags.json` 是机器归一化和别名映射的 source of truth
- `docs/workflow_specs/hierarchical_tag_reference.md` 是人类阅读参考，不参与运行时匹配

所以：

- 机器要用的首选词表、canonical 命名、开放词表约束和候选记录路径，改 `config/focus_tags.json`
- 人想快速查“常用标签一般长什么样”，看 `docs/workflow_specs/hierarchical_tag_reference.md`

它不应该搬到 `config/`，因为它不是程序直接消费的运行时资产。
