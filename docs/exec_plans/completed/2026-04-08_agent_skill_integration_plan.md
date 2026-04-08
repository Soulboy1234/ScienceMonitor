# Agent Skill Integration Plan

## 目标

把当前可用的四个外部 skill 纳入 `ScienceMonitor` 的 agent 工作流，使 agent 在合适任务中主动调用 skill，而不是只依赖项目内 Python 代码和通用 shell 操作。

当前要接入的 skill：

- `defuddle`
- `obsidian-cli`
- `obsidian-bases`
- `obsidian-markdown`

## 范围

- 更新 `AGENTS.md` 的 skill 使用入口
- 新增一份面向 agent 的 skill 使用 runbook
- 更新 `docs/README.md` 和治理记录，确保后续 agent 能找到这套规则

## 非目标

- 不改运行时代码
- 不把 skill 作为项目硬依赖
- 不把本地 skill 的绝对路径写入公开文档
- 不用 skill 规则覆盖项目已有 source of truth

## 验收

- agent 能明确判断什么时候该用哪个 skill
- skill 使用边界清楚：能用、不能用、用了之后还要跑什么 harness 检查
- 文档不引入本机绝对路径或个人信息

## 完成记录

- 已新增 `docs/user_guides/agent_skill_usage.md`
- 已更新 `AGENTS.md` 的 skill 使用入口
- 已更新 `docs/README.md`、`GovernanceBoard.md` 和 `CHANGELOG.md`
- 本轮不改运行代码
