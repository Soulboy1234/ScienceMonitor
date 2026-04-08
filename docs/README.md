# ScienceMonitor Docs

根目录文件与 `docs/` 的分工如下：

- 根目录 `README.md`
  面向人类，讲项目是什么、怎么部署、怎么运行
- 根目录 `AGENTS.md`
  面向 agent，讲先读什么、去哪找规则、什么文件当前最可信
- 根目录 `ARCHITECTURE.md`
  讲系统边界和主数据流
- 根目录 `PLANS.md`
  讲复杂任务的计划写法
- `config/`
  放程序直接消费的配置、运行时模板和运行时偏好
- `evals/`
  放 golden eval 基线样例和真实论文集成评测清单
- `docs/`
  放项目内部规范、用户说明和执行计划

当前目录按职责分成三层：

- [workflow_specs](workflow_specs)
  - 输出规范、风格指南、标签参考、prompt 契约和 source-of-truth 说明
- [user_guides](user_guides)
  - 面向用户阅读的说明文档
- [exec_plans](exec_plans)
  - 复杂任务的执行计划、迁移记录和工程债追踪

运行时直接读取的关键文件不再放在 `docs/` 下：

- [config/research_preferences.json](../config/research_preferences.json)
- [config/focus_tags.json](../config/focus_tags.json)
- [config/maintenance_budget.json](../config/maintenance_budget.json)
- [config/templates/article_summary_template.md](../config/templates/article_summary_template.md)
- [config/templates/daily_report_template.md](../config/templates/daily_report_template.md)
- [config/templates/deep_reading_report_template.md](../config/templates/deep_reading_report_template.md)

## 建议阅读顺序

1. [../README.md](../README.md)
2. [../AGENTS.md](../AGENTS.md)
3. [../ARCHITECTURE.md](../ARCHITECTURE.md)
4. [../PROJECT_CONFIG.md](../PROJECT_CONFIG.md)
5. 如需核实运行时研究偏好，再看 [../config/research_preferences.json](../config/research_preferences.json)
6. [workflow_specs/source_of_truth_matrix.md](workflow_specs/source_of_truth_matrix.md)
7. [workflow_specs/llm_prompt_contracts.md](workflow_specs/llm_prompt_contracts.md)
8. [workflow_specs/rules.md](workflow_specs/rules.md)
9. [user_guides/llm_analysis_readme.md](user_guides/llm_analysis_readme.md)
10. [exec_plans/README.md](exec_plans/README.md)
11. [exec_plans/GovernanceBoard.md](exec_plans/GovernanceBoard.md)
12. [user_guides/release_checklist.md](user_guides/release_checklist.md)

## 目录说明

### Workflow Specs

- [README.md](workflow_specs/README.md)
- [rules.md](workflow_specs/rules.md)
- [literature_note_style_guide.md](workflow_specs/literature_note_style_guide.md)
- [llm_prompt_contracts.md](workflow_specs/llm_prompt_contracts.md)
- [report_review_rules.md](workflow_specs/report_review_rules.md)
- [article_summary_template_guide.md](workflow_specs/article_summary_template_guide.md)
- [daily_report_template_guide.md](workflow_specs/daily_report_template_guide.md)
- [deep_reading_template_guide.md](workflow_specs/deep_reading_template_guide.md)
- [source_of_truth_matrix.md](workflow_specs/source_of_truth_matrix.md)
- [literature_codex_quick_guide.md](workflow_specs/literature_codex_quick_guide.md)
- [deep_reading_comparison_and_fusion.md](workflow_specs/deep_reading_comparison_and_fusion.md)
- [常用分级标签参考.md](workflow_specs/%E5%B8%B8%E7%94%A8%E5%88%86%E7%BA%A7%E6%A0%87%E7%AD%BE%E5%8F%82%E8%80%83.md)

### User Guides

- [literature_directory_integration_guide.md](user_guides/literature_directory_integration_guide.md)
- [llm_analysis_readme.md](user_guides/llm_analysis_readme.md)
- [chatgpt_web_manual_workflow.md](user_guides/chatgpt_web_manual_workflow.md)
- [eval_governance_runbook.md](user_guides/eval_governance_runbook.md)
- [maintenance_governance_runbook.md](user_guides/maintenance_governance_runbook.md)
- [release_checklist.md](user_guides/release_checklist.md)
- [python_module_map.md](user_guides/python_module_map.md)
- [agent_skill_usage.md](user_guides/agent_skill_usage.md)

### Exec Plans

- [README.md](exec_plans/README.md)
- [GovernanceBoard.md](exec_plans/GovernanceBoard.md)
- [tech_debt_tracker.md](exec_plans/tech_debt_tracker.md)
- [active](exec_plans/active)
- [completed](exec_plans/completed)

### Local Cleanup Archive

`v1.0.0` 前清扫时移出的历史材料属于本地开发归档，不再作为公开仓库内容上传。
