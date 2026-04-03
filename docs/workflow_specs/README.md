# Workflow Specs

这个目录放“如何产出内容、如何执行工作流”的规范。

和 `PROJECT_CONFIG.md` / `config/research_preferences.json` 的区别是：

- `PROJECT_CONFIG.md` 的研究偏好同步段是人类编辑入口，`config/research_preferences.json` 是程序消费的落地结果
- `workflow_specs/` 解决的是“内容应该怎么写、流程应该怎么做”

这里的文件主要约束：

- agent 的执行口径
- 输出格式与写作风格
- LLM prompt 契约的审阅视图
- 模板结构
- 标签和目录整合规则
- 控制面之间谁是主 source of truth

注意：

- 单篇总结运行时模板已经迁到 `config/templates/article_summary_template.md`
- 周报运行时模板已经迁到 `config/templates/daily_report_template.md`
- 深度解读运行时模板已经迁到 `config/templates/deep_reading_report_template.md`
- `常用分级标签参考.md` 是人工参考，不是运行时模板，因此保留在 `docs/workflow_specs/`
- 这样做是为了把“程序直接消费的资产”和“说明文档”分开，便于脱离 Codex 环境独立运行
- 其余模板并不天然等于真实渲染源
- 如果代码没有直接消费模板文件，那么模板就是“规范参考”，真实行为仍要以代码和测试核实
- 如果不确定应该先改模板、规则文档、提示词还是 Python 实现，先看 `source_of_truth_matrix.md`
