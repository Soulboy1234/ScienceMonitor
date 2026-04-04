# V1 Cleanup Phase 7

## Purpose / Big Picture

第七阶段是在 `v0.1.0` 备份之后，开始做 `v1.0.0` 前的大清扫。

目标是三件事：

- 把不再属于主工作流的历史文件归档到根目录 `no_need_for_v1.0.0/`
- 清理已经没有现实价值的旧兼容代码和未使用配置
- 在不改变功能的前提下，继续降低代码熵，并让维护检查持续生效

## Progress

- [x] 建立根目录归档区 `no_need_for_v1.0.0/`
- [x] 移走主工作流不再需要的历史文档和无用配置
- [x] 清理旧兼容代码
- [x] 降低一轮结构熵，优先处理循环依赖与明显冗余
- [x] 跑完整维护检查和全量测试

## Surprises & Discoveries

- `docs/archive/` 已经是明显的历史材料，但仍挂在主 docs 导航里
- `config/codex_test_schema.json` 当前没有任何引用
- `config.py` 仍保留旧 `master plan` 格式的研究偏好回退逻辑
- 当前唯一显式 import cycle 是 `article_summaries <-> llm`
- `cli.py` 的命令注册和命令处理长期混在一起，导致入口层很难继续收缩

## Decision Log

- 清扫优先移除“旧兼容”和“主工作流不再消费”的内容
- 归档区放在根目录，避免继续污染 `docs/` 和 `config/`
- 结构优化优先做低风险高收益项，不在这一轮做大规模重构

## Outcomes & Retrospective

- 根目录已建立 `no_need_for_v1.0.0/`，旧文档和无引用配置已移入归档区
- `config.py` 已删除旧 `research_preferences.md` 回退逻辑
- `article_summaries <-> llm` 显式循环依赖已通过抽取 `ArticleSummaryResult` 到 `models.py` 消除
- `cli.py` 已收缩为薄入口，命令定义与分发迁入 `cli_support.py`
- `config.py` 中的研究偏好标准化、解析和画像逻辑已抽到 `research_preferences.py`
- `entropy-check`、`maintenance-check`、全量 `pytest` 已通过，新的预算已反映当前真实体积

## Context and Orientation

- 备份版本：`v0.1.0`
- 当前维护 gate：`maintenance-check`
- 当前代码熵预算：`config/maintenance_budget.json`

## Plan of Work

1. 建归档区并迁移历史材料
2. 清理旧兼容代码和未使用配置
3. 处理一轮低风险结构降熵
4. 更新文档和维护预算
5. 跑维护检查收口

## Concrete Steps

1. 新建 `no_need_for_v1.0.0/README.md`
2. 把 `docs/archive/` 迁入归档区
3. 把未使用配置转入归档区
4. 删除 `config.py` 中的 legacy `master plan` 回退逻辑
5. 处理 `article_summaries <-> llm` 循环依赖
6. 补测试并更新维护文档
