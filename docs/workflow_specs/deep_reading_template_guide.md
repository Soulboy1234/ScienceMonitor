# Deep Reading Template Guide

## 目的

`config/templates/deep_reading_report_template.md` 现在是深度解读最终 Markdown 展示层的 source of truth。

这意味着：

- 正式区块顺序
- 标题层级
- 各字段在最终笔记中的摆放方式

优先以运行时模板为准。

## 仍然由代码控制的内容

- LLM 返回字段 schema
- 字段文本的归一化与收口
- 旧版区块拦截
- 输出合法性校验
- 文件命名和资源挂接

也就是说，深度解读现在采用的是：

- 模板主控展示层
- 代码主控字段契约和质量边界

格式审核的统一规则见：

- `report_review_rules.md`

## 当前必须保留的区块契约

下面这些标题目前仍是硬契约，暂时不要直接改名：

- `# 论文深度阅读报告`
- `## 论文信息`
- `### 一句话总述`
- `## 论文详解`
- `### 为什么做`
- `### 如何做`
- `### 关键结果`
- `### 新意与贡献`
- `### 局限性`
- `### 可复现性`
- `### 与已有工作的关系`
- `## 总结`
- `### 最终结论`
- `### 补充信息`
- `记录时间戳:`

如果要改这些区块名，必须同步修改：

- `src/sciencemonitor/deep_reads.py`
- `src/sciencemonitor/deep_read_markdown.py`
- 相关测试
- `docs/workflow_specs/source_of_truth_matrix.md`

`### 关键结果` 内部还必须稳定渲染四个 `####` 四级标题：

- `#### 硬结论`
- `#### 次级结论`
- `#### 合理推论`
- `#### 需进一步研究讨论的结论`

当前这四个四级标题由 `{{key_results}}` 字段的 Python 归一化和审核层生成，不直接写死在模板中。原因是模型和人工网页中转返回的内容可能是旧格式，必须由本地审核层统一修正。

## 当前必须保留的占位符

- `{{entry_line}}`
- `{{apa_citation}}`
- `{{title}}`
- `{{authors}}`
- `{{journal}}`
- `{{year}}`
- `{{paper_type}}`
- `{{one_sentence_overview}}`
- `{{why}}`
- `{{how}}`
- `{{key_results}}`
- `{{contribution}}`
- `{{limitations}}`
- `{{reproducibility}}`
- `{{relation}}`
- `{{final_conclusion}}`
- `{{relation_to_my_work}}`
- `{{follow_up_questions}}`
- `{{needs_manual_review}}`
- `{{knowledge_position}}`
- `{{timestamp}}`

## 可以放心改的内容

- 空行和版式
- APA 与入口行的位置
- 各个大区块的视觉疏密
- “补充信息”里的条目顺序

## 补充信息里的索引语义

- `{{knowledge_position}}` 应优先展示真实的 Obsidian `article_index/sub_index/` 挂接链接
- 如果当前是评测输出，没有写入 `output_root`，则应明确说明“未生成 article_index 索引链接”
- 这里不应再使用模糊的“建议挂接到某目录”作为最终展示文本

## 风格建议

- 深度解读仍然要保持科研卡片感，而不是模板作文
- 允许长，但每一节都必须有判断
- `为什么做` 直接写作者要解决的问题，不写“不是……而是……”
- `新意与贡献` 直接写新意和贡献，不写“不是……而是……”或“不在于……而在于……”
- 编号列表必须逐条换行，不能和前一句挤在同一行
- 详细风格和目标结构仍可参考：
  - `literature_note_style_guide.md`
  - `deep_reading_comparison_and_fusion.md`
