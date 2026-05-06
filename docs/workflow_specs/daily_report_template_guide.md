# Daily Report Template Guide

## 目的

`config/templates/daily_report_template.md` 现在是周报最终 Markdown 展示层的 source of truth。

这意味着：

- 正式区块顺序
- 标题层级
- 固定说明文字
- 各个统计区块在最终周报中的摆放方式

优先以运行时模板为准。

## 仍然由代码控制的内容

- 期刊分组、主题计数和重点论文选择
- 用户偏好加权
- LLM 周报分析结果的使用方式
- 各个区块内容块的生成
- 输出合法性校验

也就是说，周报现在采用的是：

- 模板主控展示层
- 代码主控筛选逻辑、字段块内容和质量边界

格式审核的统一规则见：

- `report_review_rules.md`

## 当前必须保留的区块契约

下面这些标题目前仍是硬契约，暂时不要直接改名：

- `标题：Space Physics Daily Report -`
- `统计窗口：近`
- `监控期刊：`
- `## 周报信息`
- `## 今日概览`
- `### 本周重点方向分布`
- `### 整体观察`
- `### 与当前工作相关的重点`
- `## 文章推荐`
- `### 推荐论文`
- `### 建议重点关注的事件或物理过程`
- `### 对当前工作的可能启发`
- `## 主题推荐`
- `## 各期刊主题汇总`
- `## 其他`
- `### 未完成或未获取摘要/全文的文献`
- `### 附注`
- `- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。`
- `- 生成时间：`

如果要改这些区块名，必须同步修改：

- `src/sciencemonitor/reporting.py`
- 相关测试
- `docs/workflow_specs/source_of_truth_matrix.md`

## 当前必须保留的占位符

- `{{report_date}}`
- `{{window_days}}`
- `{{journals}}`
- `{{report_info_block}}`
- `{{overview_table_block}}`
- `{{objective_overview_block}}`
- `{{preference_overview_block}}`
- `{{recommended_papers_block}}`
- `{{recommended_processes_block}}`
- `{{work_implications_block}}`
- `{{theme_recommendations_block}}`
- `{{journal_roundup_block}}`
- `{{missing_sources_block}}`
- `{{generated_at}}`

## 可以放心改的内容

- 各个正式区块的前后顺序
- 空行和版式密度
- 是否先看各期刊主题汇总再看概览
- 顶部元信息和附注的摆放方式

## 风格建议

- 周报仍然要像研究工作周报，而不是大段套话
- 概览要先客观描述本周论文分布，再单独写与当前工作相关的重点
- 主题推荐要尽量落到具体科学问题，不要只写热层、电离层这类宽泛分类
- 文章推荐要简洁可扫读，重点突出英文题目、期刊、中文题目和推荐理由
- 当前周报已进入“结构与格式强审核，内容正确性后续再增强”的阶段
- 详细风格和学科约束仍可继续参考：
  - `literature_note_style_guide.md`
  - `rules.md`
