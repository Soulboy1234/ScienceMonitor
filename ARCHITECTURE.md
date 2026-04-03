# Architecture

## 1. 系统目标

`ScienceMonitor` 把“抓取空间物理论文 -> 过滤分类 -> 生成总结/周报/深读 -> 同步 Obsidian 输出索引”串成一个本地可运行的流水线。

## 2. 主数据流

1. `cli.py` 解析命令
2. `pipeline.py` 调度主流程
3. `crossref.py` + `http.py` 抓取近期论文
4. `topics.py` 做规则分类和相关性过滤
5. `storage.py` 写入 SQLite
6. `article_summaries.py` 生成单篇总结
7. `reporting.py` 生成周报
8. `deep_reads.py` 在用户点名需要时生成深度解读
9. `article_index.py` 修复链接并维护输出侧索引

## 3. 主要子系统

### 3.1 配置层

- `PROJECT_CONFIG.md`
- `config/runtime.json`
- `config/analysis.json`
- `config/paths.json`
- `config/sources.json`
- `config/topics.json`
- `config/focus_tags.json`
- `config/templates/`

`config.py` 负责把这些配置解析为运行时路径和行为开关。

### 3.2 文档控制层

- `config/research_preferences.json`
  放运行时会影响程序判断的研究偏好，当前内容会被代码直接读取
- `docs/workflow_specs/`
  放输出规则、风格指南、参考模板与工作流规范，主要约束 agent 和人的执行方式
- `docs/user_guides/`
  面向人类阅读
- `docs/exec_plans/`
  承担复杂任务计划与迁移记录

这两层最容易混淆，区别可以这样理解：

- `config/research_preferences.json`
  回答“当前项目应该重点关注什么”。这里放研究偏好、优先级和会影响推荐判断的背景信息。
  人类编辑入口在 `PROJECT_CONFIG.md` 的研究偏好同步段，这个 JSON 是运行时落地文件。
- `workflow_specs/`
  回答“开始生成内容后，应该按什么规则写”。这里放模板、风格、标签说明和执行规范。

一个更直接的判断方法：

- 如果内容更像“研究方向和偏好”，放 `config/research_preferences.json`
- 如果内容更像“输出格式和工作规则”，放 `workflow_specs/`

如果还要继续问“修改时到底先改哪边”，再看：

- `docs/workflow_specs/source_of_truth_matrix.md`

### 3.3 抓取与过滤层

- `crossref.py`
- `topics.py`
- `pipeline.py`

这里决定“什么论文进库，什么论文被丢弃”。

### 3.4 分析与生成层

- `llm.py`
- `article_summaries.py`
- `reporting.py`
- `deep_reads.py`

这里决定“输出写成什么样”。

补充说明：

- 监测、单篇总结、周报默认只围绕空间物理主线
- 深度解读是手动触发的，不是默认自动链路
- 深度解读对象以空间物理论文为主，但可以扩展到与主线研究相关的人工智能或其他支撑学科论文

### 3.5 输出与索引层

- 输出根目录由 `config/paths.json` 控制
- `article_index.py` 负责维护 `article_index/` 和相关回链

### 3.6 治理与维护层

- `doctor.py`
- `golden_eval.py`
- `real_case_eval.py`
- `harness.py`
- `entropy.py`
- `maintenance.py`

这里不直接生成业务内容，而是回答两个问题：

- 当前系统还能不能稳定运行
- 当前代码结构有没有继续失控

其中：

- `harness.py` 负责运行与评测 gate
- `entropy.py` 负责代码熵预算
- `maintenance.py` 负责“审核 -> 调整 -> 测试 -> 再审核”的维护循环

## 4. 当前几个重要边界

### 4.1 源码 vs 运行态

源码主要在：

- `src/`
- `tests/`
- `config/`
- `docs/`
- `scripts/`

运行态主要在：

- `data/`
- `log/`
- `tmp/`
- `.venv/`

### 4.2 文档参考 vs 文档控制

当前仓库里既有“真正控制程序”的文档，也有“描述目标风格”的文档。

最明确会被代码消费的文档包括：

- `PROJECT_CONFIG.md`
- `config/research_preferences.json`
- `config/templates/article_summary_template.md`
- `config/templates/daily_report_template.md`
- `config/templates/deep_reading_report_template.md`

其中：

- `config/templates/article_summary_template.md` 已经进入单篇总结的真实渲染链路
- `config/templates/daily_report_template.md` 已经进入周报的真实渲染链路
- `config/templates/deep_reading_report_template.md` 已经进入深度解读的真实渲染链路

更细的优先级和修改顺序，统一记录在：

- `docs/workflow_specs/source_of_truth_matrix.md`

## 5. 当前已知架构债

- 周报的 LLM 提示词、模板展示层和统计逻辑仍然是多层控制面，需要继续保持同步
- 多个核心文件体积过大，agent 阅读成本偏高
- 当前仍保留一个历史 import cycle：`article_summaries <-> llm`
- 计划系统是刚补上的，后续还要形成稳定使用习惯

这里的“架构债”指的是：

- 当前系统还能运行
- 但结构上不够清晰、稳定或不够适合长期演化
- 后续应逐步消化的修改项

可以把它理解为“后续要做、但不一定要立刻做”的结构性改进清单。

它不是说系统现在不能用，而是提醒我们：

- 这些地方目前还能工作
- 但以后继续扩展时，维护成本会越来越高
- 所以值得排期逐步修正

这些债务请优先记录到：

- `docs/exec_plans/tech_debt_tracker.md`
- 对应的活跃 ExecPlan
