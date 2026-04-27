# Report Review Rules

## 目的

这份文件集中记录 `ScienceMonitor` 报告生成后的格式审核规则。

它解决的问题是：报告格式不能只靠 prompt、模板说明或人工记忆约束。单篇总结、周报和深度解读在进入最终输出前，都应该经过确定性的本地审核层。

## 分层原则

报告格式治理分四层：

1. `config/templates/*.md`
   控制最终 Markdown 的静态骨架，包括区块顺序、固定标题和占位符位置。

2. `docs/workflow_specs/*_template_guide.md`
   说明模板如何编辑、哪些标题和占位符是硬契约。

3. Python 审核层
   对模型、人工网页中转和模板渲染后的 Markdown 做确定性修复与校验。这里负责动态规则，例如编号换行、旧说法清理和状态标签边界。

4. 测试与 eval
   固化规则，防止格式约束在后续重构中回退。

不要把动态规则只写进 prompt 或模板说明。prompt 可以引导输出，模板可以表达骨架，但最终稳定性必须由 Python 审核层和测试兜底。

## 共同规则

- 渲染后不得残留 `{{placeholder}}`。
- 必需标题和固定区块不能缺失。
- 生成后应进入“审核 -> 自动修正 -> 再审核”循环。
- 如果审核循环无法在限定轮数内修正，程序应报错，而不是静默写出坏格式。
- 真实生产输出和 eval 输出的链接语义应区分；eval 输出不能伪装成生产态 Obsidian 挂接结果。
- 人工网页中转结果不能绕过本地审核层。

## 单篇总结

### 模板层

模板 source of truth：

- `config/templates/article_summary_template.md`

模板控制：

- APA / 资源行 / 正文 / 补充信息 / 引用 / 好句子 / 关联报告的展示顺序
- `- 「补充信息」`
- `- 「文中引用」`
- `- 「好句子」`
- `- 「关联报告」`
- `记录时间戳:`

### Python 审核层

主要入口：

- `src/sciencemonitor/article_summaries.py::_run_article_summary_review_loop`
- `src/sciencemonitor/article_summaries.py::_autofix_article_summary_markdown`
- `src/sciencemonitor/article_summaries.py::_validate_article_summary_markdown`

审核规则：

- 单篇总结必须有正文概括，不能保留空泛套话。
- 摘要级总结必须包含 `#信息来源/仅摘要`。
- 摘要级总结的补充信息必须明确说明“当前总结仅基于摘要和元数据生成”。
- 全文级总结不应保留 `#信息来源/仅摘要`，除非补充信息明确仍为摘要边界。
- 补充信息不能保留“结果片段”这类旧表述。
- 标签仍由 `config/focus_tags.json` 和标签执行层归一化，不由模板决定。

### 测试护栏

主要测试：

- `tests/test_article_summaries.py`

重点覆盖：

- 自定义模板是否真正控制展示顺序。
- 模板缺少必需占位符时是否快速失败。
- 摘要级总结是否自动补 `#信息来源/仅摘要` 和来源说明。
- 旧表述和空泛正文是否被审核层拦截。

## 深度解读

### 模板层

模板 source of truth：

- `config/templates/deep_reading_report_template.md`

模板控制：

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

### Python 审核层

主要入口：

- `src/sciencemonitor/deep_read_markdown.py::_run_deep_read_review_loop`
- `src/sciencemonitor/deep_read_markdown.py::_autofix_deep_read_markdown`
- `src/sciencemonitor/deep_read_markdown.py::_audit_deep_read_markdown`
- `src/sciencemonitor/deep_read_markdown.py::_validate_deep_read_markdown`

审核规则：

- `为什么做` 必须直接陈述“作者要解决的问题是：...”，不写“不是……而是……”。
- `关键结果` 必须包含四个 `####` 四级标题：
  - `#### 硬结论`
  - `#### 次级结论`
  - `#### 合理推论`
  - `#### 需进一步研究讨论的结论`
- `关键结果` 四级标题后必须换行，编号列表必须逐条分行。
- `新意与贡献` 不写“不是……而是……”或“不在于……而在于……”；直接写新意和贡献。
- `补充信息` 的小标题后必须换行，编号列表必须逐条分行。
- 中文强调优先使用双引号。
- 旧英文模板标题和旧版报告区块不得出现在最终报告中。
- 深度解读不继承单篇总结的 `信息来源/*` 状态标签；这类标签只描述单篇总结的证据边界。
- eval 输出中的 PDF 和单篇总结链接应使用 eval 目录内可解析的本地链接；生产输出才使用 Obsidian 挂接语义。

说明：

- `关键结果` 的四个四级标题虽然是稳定结构，但当前由 `{{key_results}}` 字段的 Python 归一化层生成，而不是直接写死在模板中。这样可以让审核层处理网页人工中转或 LLM 返回的旧格式，并避免模板和字段内容重复。

### 测试护栏

主要测试：

- `tests/test_deep_reads.py`

重点覆盖：

- `为什么做` 的直接问题陈述。
- `关键结果` 四个四级标题和编号换行。
- `新意与贡献` 的否定转折清理。
- `补充信息` 小标题和编号分行。
- eval 链接语义。
- 深度解读不继承 `信息来源/仅摘要`。
- 自定义模板是否真正控制展示顺序。
- 模板缺少必需占位符时是否快速失败。

## 周报

### 模板层

模板 source of truth：

- `config/templates/daily_report_template.md`

模板控制：

- 顶部元信息
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
- `### 未获取摘要/全文的文献`
- `### 附注`

### Python 审核层

主要入口：

- `src/sciencemonitor/reporting_template.py::run_report_review_loop`
- `src/sciencemonitor/reporting_template.py::autofix_report_markdown`
- `src/sciencemonitor/reporting_template.py::audit_report_markdown`

当前审核规则：

- 折叠多余空行。
- 避免三级标题与后续表格或列表之间出现多余空行。
- 确认模板必需标题和占位符已被正确渲染。
- `## 周报信息` 下必须有期刊统计表。
- `### 本周重点方向分布` 下必须有“重点方向 / 文章数 / 重点期刊”表。
- 缺失主题推荐时，必须明确写出“无共同主题”。
- 未获取摘要/全文的文献必须以列表形式展示，不再写散乱说明块。

当前仍未做“真实内容正确性”的强审核；本轮先把新版周报结构、格式和统计组织稳定下来，后续在真实周报案例校准后再增强内容层 gate。

### 测试护栏

主要测试：

- `tests/test_reporting.py`

重点覆盖：

- 自定义模板是否真正控制展示顺序。
- 模板缺少必需占位符时是否快速失败。
- 周报审核是否能收敛表格、列表和章节间的多余空行。
- 新版周报是否稳定输出信息表、方向表、文章推荐、主题推荐和期刊汇总。

## 修改规范

以后新增或修改报告格式规则时，按下面顺序处理：

1. 如果是静态结构，先改对应 `config/templates/*.md`。
2. 如果是动态格式或语言质量边界，先改 Python 审核层。
3. 同步更新对应 template guide 和本文件。
4. 补或更新测试。
5. 如输出基线发生预期变化，更新 `golden-eval` 或真实案例 fixture。
6. 运行至少一层 gate：
   - 格式/文档改动：`git diff --check`
   - 代码或测试改动：`./.venv/bin/python -m pytest -q`
   - 涉及 harness：`./scripts/run_science_monitor.sh harness-check`
