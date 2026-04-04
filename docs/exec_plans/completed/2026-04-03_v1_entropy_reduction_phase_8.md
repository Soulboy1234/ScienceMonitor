# V1 Entropy Reduction Phase 8

## Purpose / Big Picture

第八阶段是在完成 `v0.1.0` 备份和第一轮大清扫之后，继续做面向 `v1.0.0` 的结构降熵。

目标不是增加新功能，而是继续降低主要大模块的复杂度，并把这种收缩持续接入维护预算。

## Progress

- [x] 选择下一批低风险高收益的大模块拆分目标
- [x] 继续降低一轮主模块体积和职责混杂度
- [x] 把新的结构变化写回 `maintenance_budget.json`
- [x] 跑完整维护检查和全量测试

## Current Priority Targets

- `llm.py`
  - 已完成 prompt/schema 合同层抽离；后续若再优化，优先保留 provider 执行器完整，不做零碎拆分
- `real_case_eval.py`
  - 主流程已经收缩；后续如果继续处理，优先保持“运行编排”和“fixture 治理”这两个边界，不再继续切碎
- `deep_reads.py`
  - 主流程已经收缩，但仍混合元数据解析、全文获取、标签归一化和输出同步；剩余部分优先做边界梳理，不再继续细碎拆分

## Decision Log

- 继续优先做“低风险、可验证、能直接反映到预算”的拆分
- 每完成一轮拆分，都同步更新预算、文档和维护检查
- 不在这一阶段引入新的业务能力，避免把结构治理和功能扩张混在一起
- 第一轮优先拆 `article_fetch.py`，把科学正文清洗与证据包抽取逻辑抽到 `article_source_text.py`
- 第二轮继续拆 `article_index.py`，把目录与行星规则抽到 `article_index_rules.py`
- 第二轮的补充拆分继续落在 `article_index.py`，把路径遍历和 wikilink 辅助层抽到 `article_index_paths.py`
- 第三轮拆 `config_ui.py`，把页面渲染层抽到 `config_ui_page.py`
- 第四轮拆 `article_summaries.py`，把 Markdown/模板逻辑抽到 `article_summary_markdown.py`
- 第五轮继续拆 `article_summaries.py`，把文本生成逻辑抽到 `article_summary_text.py` 与 `article_summary_meta.py`
- 第六轮拆 `config.py`，把 `PROJECT_CONFIG.md` 控制面正文和同步块解析抽到 `project_config_markdown.py`
- 第七轮拆 `reporting.py`，把周报模板契约、渲染和审核逻辑抽到 `reporting_template.py`
- 维护预算同时收紧了 `article_summaries.py` 单模块上限，并对总代码行数预算做了小幅重标定，以适配“主文件更小、模块更多”的结构化拆分
- 第八轮拆 `deep_reads.py`，把深度解读模板契约、文本规范化和审核闭环抽到 `deep_read_markdown.py`
- 对 `deep_reads.py` 和 `deep_read_markdown.py` 的预算采用“双模块分别收紧”的方式，避免因为合理拆分导致维护检查对总包行数报假阳性
- 第九轮拆 `real_case_eval.py`，把 fixture 比较、漂移 diff 和结果汇总抽到 `real_case_outputs.py`
- 对 `real_case_eval.py` 的后续治理不再追求继续拆成多个小工具文件，而是保持“运行主流程 + 输出治理层”的两层结构
- 第十轮拆 `llm.py`，把 prompt、schema 和输入整理合同抽到 `llm_contracts.py`
- 对 `llm.py` 的治理边界改为“执行器/缓存/标准化留在主文件，prompt/schema 留在合同层”，避免拆散 provider 逻辑
- 在 `deep_read_markdown.py`、`real_case_outputs.py`、`llm_contracts.py` 三个稳定辅助层落地后，总包行数只轻微超出旧预算 26 行，因此对 `package_total_max_lines` 做了小幅重标定，继续避免对合理拆分报假阳性

## Plan of Work

1. 当前主要大模块均已进入预算范围；后续仅在出现新的职责混杂时做边界清理
2. 对 `deep_reads.py`、`real_case_eval.py`、`llm.py` 均不再继续细碎拆分，优先依赖预算和维护检查防止反向膨胀
3. 每轮拆分后同步预算、代码地图和阶段计划
4. 跑 `entropy-check`、`maintenance-check`、全量 `pytest`
