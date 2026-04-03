# Article Summary Template Guide

## 目的

`config/templates/article_summary_template.md` 现在是单篇总结最终 Markdown 展示层的 source of truth。

这意味着：

- 区块顺序
- 固定标题
- 空行位置
- 哪些内容放在一起显示

优先以模板文件为准。

但这不意味着模板负责一切。下面这些仍由代码控制：

- 中文标题、标签、正文和补充信息的生成
- 标签归一化
- 文件命名
- 旧文件修复
- 测试与兼容性校验

## 可以放心改的内容

- 区块顺序
- 空行和版式
- 引用、正文、补充信息、关联报告的上下排列
- 是否要在模板里显示 `{{note_title}}`、`{{resource_line}}`、`{{tag_line}}` 这类占位字段

## 当前必须保留的区块契约

下面这些标题目前仍被代码解析或依赖，暂时不要改名：

- `- 「补充信息」`
- `- 「文中引用」`
- `- 「好句子」`
- `- 「关联报告」`
- `记录时间戳:`

如果要改这些区块名，必须同步修改：

- `src/sciencemonitor/article_summaries.py`
- 相关测试
- `docs/workflow_specs/source_of_truth_matrix.md`

## 当前必须保留的占位符

- `{{resource_line}}`
- `{{apa_citation}}`
- `{{body}}`
- `{{supplement}}`
- `{{references_block}}`
- `{{quotes_block}}`
- `{{related_reports_block}}`
- `{{timestamp_date}}`
- `{{timestamp_time}}`

## 常用可选占位符

当前渲染器还额外提供这些字段，模板需要时可以使用：

- `{{note_title}}`
- `{{resource_link}}`
- `{{tag_line}}`
- `{{timestamp}}`

## 风格建议

- 单篇总结仍应保持 Obsidian 科研卡片风格
- 优先高密度结论，而不是模板作文
- 标签仍遵守现有层级标签和闭集优先原则
- 详细风格请继续参考：
  - `literature_note_style_guide.md`
  - `rules.md`
