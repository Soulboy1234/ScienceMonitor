# Harness Migration Phase 1

## Purpose / Big Picture

为 `ScienceMonitor` 补上最小可用的 harness 骨架，让后续重构不再依赖聊天上下文或个人记忆。

这一阶段先不改业务逻辑，只补工程控制面。

## Progress

- [x] 安装 `pytest` 并补回依赖文件
- [x] 初始化 Git 仓库
- [x] 提交并标记 `v0.0.0`
- [x] 增加 `AGENTS.md`
- [x] 增加 `ARCHITECTURE.md`
- [x] 增加 `PLANS.md`
- [x] 建立 `docs/exec_plans/` 目录
- [x] 统一到 `docs/` 目录并澄清文档边界
- [x] 明确主线范围：监测/总结/周报只服务空间物理，深度解读可扩展到 AI 和其他支撑学科

## Surprises & Discoveries

- 项目在补 Git 之前并不是仓库
- 旧的文档体系已经有不错的控制文档分层，但缺少执行计划系统
- 模板文档与真实渲染逻辑目前仍是双轨状态

## Decision Log

- 统一改成 `docs/` 目录，并把职责重新切分为 `runtime_context/`、`workflow_specs/`、`user_guides/`、`exec_plans/`
- 第一阶段只补骨架，不移动现有业务文档
- `v0.0.0` 采用“只纳入项目本体文件，不纳入运行态目录”的快照策略

## Outcomes & Retrospective

- 已完成最小 harness 骨架，后续任务不再只能依赖聊天上下文
- 根目录入口文件和 `docs/` 内部分层已经固定下来
- 第二阶段不再继续补骨架，而是开始治理模板、提示词、规则文档和代码之间的 source-of-truth 漂移

## Context and Orientation

- 根级入口文件现在包括：`AGENTS.md`、`ARCHITECTURE.md`、`PLANS.md`
- 现有运行逻辑仍以 `src/sciencemonitor/*.py` 为准
- 后续要优先解决模板、提示词、索引树的真实 source-of-truth 问题

## Plan of Work

1. 先搭好工程骨架
2. 再把规则/模板/代码的职责边界说清
3. 然后开始拆分大文件和外置硬编码规则
4. 最后补 CI、golden eval 和持续清扫

## Concrete Steps

1. 保持 `AGENTS.md` 作为 agent 总入口
2. 复杂任务开始前先在 `active/` 写计划
3. 每一轮迁移都新增测试或评估护栏
4. 第一阶段完成后，把本计划移到 `completed/`
