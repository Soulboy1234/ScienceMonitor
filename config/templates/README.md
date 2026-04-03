# Runtime Templates

这个目录存放会被 `ScienceMonitor` 运行时直接消费的模板资产。

当前包括：

- `article_summary_template.md`
- `daily_report_template.md`
- `deep_reading_report_template.md`

放在这里的原因是：

- 这些文件会进入真实运行链路
- 它们属于运行配置资产，而不只是说明文档
- 项目在脱离 Codex 环境、仅使用标准 Python + LLM provider 时，也应保留同样的运行入口

`docs/workflow_specs/` 中的模板则更多承担：

- 目标结构说明
- 风格参考
- 未来迁移前的规范文档
