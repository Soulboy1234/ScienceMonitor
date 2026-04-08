# Agent Skill Usage

这个文件定义 `ScienceMonitor` agent 何时使用外部 skill。

原则：

- skill 是任务工具，不是项目 source of truth
- skill 不能覆盖 `AGENTS.md`、`PROJECT_CONFIG.md`、`config/*.json`、运行时模板和 `docs/workflow_specs/source_of_truth_matrix.md`
- 如果 skill 不可用，先说明缺口，再使用本地 shell、Python 或项目内命令兜底
- 如果 skill 的结果会改变源码、模板、配置或输出格式，仍然要按项目 harness 规则补测试或运行对应 gate

## Skill 决策表

| Skill | 什么时候用 | 不该什么时候用 | 典型命令或动作 |
| --- | --- | --- | --- |
| `defuddle` | 用户给网页 URL，需要读取网页正文、在线文档、文章页面或博客内容 | Crossref API、项目本地 Markdown、PDF、本地缓存已足够时 | `defuddle parse <url> --md` |
| `obsidian-cli` | 用户要求直接操作 Obsidian vault：搜索、读取、创建、追加、改属性、检查 backlinks、验证 Obsidian 实际状态 | 只是在仓库内修改 Markdown 模板或生成测试输出时 | `obsidian search query="..."`、`obsidian read file="..."` |
| `obsidian-bases` | 创建或修改 `.base` 文件、表格视图、卡片视图、过滤器、公式、summary | 普通 Markdown 笔记、Python 代码、JSON 配置 | 编写 `.base` YAML，校验 YAML 和公式引用 |
| `obsidian-markdown` | 创建或修改 Obsidian 笔记语法：wikilink、embed、callout、frontmatter、tags、Obsidian 内部链接 | 普通项目文档且不含 Obsidian 特有语法时 | 使用 `[[wikilink]]`、`![[embed]]`、callout、frontmatter |

## 触发规则

### 网页内容抽取

当任务包含网页 URL，且目标是读取或分析网页正文时，优先使用 `defuddle`。

使用方式：

```bash
defuddle parse <url> --md
```

如果需要保留中间结果，写入运行态或临时目录，不要写入源码目录：

```bash
defuddle parse <url> --md -o tmp/<name>.md
```

注意：

- `defuddle` 用于减少网页导航、广告和样式噪声，降低 token 消耗
- 不用于 PDF
- 不用于 Crossref 结构化 API 返回

### Obsidian vault 操作

当用户明确要求操作 Obsidian vault，而不是只处理项目仓库文件时，使用 `obsidian-cli`。

使用前提：

- Obsidian 应处于打开状态
- 如有多个 vault，优先显式指定 `vault=<name>`
- 写入前确认目标是 vault 内笔记，不是项目 `docs/` 或 `config/templates/`

常见动作：

```bash
obsidian search query="热层 风场" limit=10
obsidian read file="某篇文献总结"
obsidian backlinks file="某篇文献总结"
obsidian property:set name="status" value="done" file="某篇文献总结"
```

### Obsidian Bases

当用户要求创建或修改 `.base` 文件时，使用 `obsidian-bases`。

执行要求：

- `.base` 内容必须是合法 YAML
- 过滤器、公式、summary、view 的属性名必须一致
- 修改后至少做 YAML 语法校验
- 如果用户要求验证 Obsidian 渲染，再配合 `obsidian-cli` 打开或检查

### Obsidian Markdown

当任务涉及 Obsidian 特有 Markdown 语法时，使用 `obsidian-markdown`。

适用内容：

- wikilinks：`[[Note]]`
- embeds：`![[file.pdf]]`
- callouts：`> [!note]`
- frontmatter properties
- Obsidian tags
- block links 和 heading links

注意：

- 项目普通说明文档优先使用标准 Markdown
- 只有输出到 Obsidian 或需要 Obsidian 语义时，才使用 Obsidian-specific 语法

## 与 ScienceMonitor harness 的关系

使用 skill 后仍然必须遵守项目 harness：

- 改 Python 代码：运行 `./.venv/bin/python -m pytest -q`
- 改输出模板或格式：补或更新对应测试，并运行 `./scripts/run_science_monitor.sh golden-eval`
- 改配置或控制面：运行 `./scripts/run_science_monitor.sh doctor --consistency-only`
- 改结构或维护规则：运行 `./scripts/run_science_monitor.sh entropy-check`
- 做发版前检查：按 `docs/user_guides/release_checklist.md`

## 记录要求

当某个任务因为使用 skill 而改变了项目规则，应同步更新：

- `AGENTS.md`
- 本文件
- 必要时更新 `docs/exec_plans/GovernanceBoard.md`、`Todo.md` 或 `tech_debt_tracker.md`

单次普通 skill 调用不需要记录到治理文件。
