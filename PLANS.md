# PLANS.md

## 目的

这个文件规定 `ScienceMonitor` 里复杂任务的 `ExecPlan` 怎么写、放在哪里、什么时候必须更新。

## 存放位置

- 进行中的计划：`docs/exec_plans/active/`
- 已完成的计划：`docs/exec_plans/completed/`
- 持续存在但未立项的工程债：`docs/exec_plans/tech_debt_tracker.md`

## 什么时候必须写计划

满足以下任一条件就要写：

- 改动 3 个以上文件
- 工作预计超过 30 分钟
- 涉及迁移、重构、目录调整或 source-of-truth 变化
- 需要分阶段交付

## 计划文件命名

推荐格式：

`YYYY-MM-DD_<topic>.md`

例如：

`2026-04-02_harness_migration_phase_1.md`

## 最小结构

每份 ExecPlan 至少保留这些标题：

```md
# Title

## Purpose / Big Picture
## Progress
## Surprises & Discoveries
## Decision Log
## Outcomes & Retrospective
## Context and Orientation
## Plan of Work
## Concrete Steps
```

## 维护规则

- `Progress` 持续更新，不要只在开始时写一次
- 新发现写到 `Surprises & Discoveries`
- 关键取舍写到 `Decision Log`
- 做完后补 `Outcomes & Retrospective`
- 完成后把文件从 `active/` 移到 `completed/`

## 与普通文档的区别

- `no_need_for_v1.0.0/docs_archive/user_guides/implementation plan.md` 是历史说明，不等于活跃 ExecPlan
- `no_need_for_v1.0.0/docs_archive/user_guides/tasks.md` 是旧待办清单，不等于可恢复计划
- ExecPlan 必须足够具体，让新的 agent 接手时不用回读整段聊天记录

## 什么是 source of truth

`source of truth` 指“某件事情最终以哪个文件或系统为准”。

例如：

- 如果运行参数以 `PROJECT_CONFIG.md` 同步块为准，那么它就是这部分配置的 source of truth
- 如果深读最终输出结构以 Python 渲染代码为准，而模板文档只是参考，那么代码才是 source of truth

一件事情最好只有一个主要 source of truth。

否则就会出现：

- 文档这样写
- 配置那样写
- 代码又是第三种行为

这就是我们后面要持续治理的重点。

如果某项 source of truth 发生变化，除了改代码或文档本身，还要同步更新：

- `docs/workflow_specs/source_of_truth_matrix.md`
- `AGENTS.md`
- `ARCHITECTURE.md`
- 对应 ExecPlan
