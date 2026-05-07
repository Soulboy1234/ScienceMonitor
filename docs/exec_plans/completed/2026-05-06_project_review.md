# 计划：2026-05-06_project_review

## 目的 / 大图景
- 对当前 `ScienceMonitor` 项目做一次整体只读审查，优先发现功能性 bug、安全漏洞和稳定性风险。
- 审查结果用于明确后续修复优先级，不在本轮直接修业务代码。

## 背景与定位
- 当前 `docs/exec_plans/active/` 原本为空，`GovernanceBoard.md` 未记录发布阻塞项。
- 工作树已有 `AGENTS.md` 未提交修改，本轮不回退、不覆盖该既有变更。
- 项目主风险面集中在外部抓取、LLM provider、本地配置 UI、输出目录写入、Obsidian 索引和治理 gate 覆盖。

## 工作范围
- 只读审查 `src/sciencemonitor/`、`scripts/`、`config/`、`tests/` 和关键治理文档。
- 运行基线检查和测试命令，记录结果。
- 必要时构造临时只读复现场景验证风险，不提交测试或源码改动。

## 非目标
- 不修复审查中发现的问题。
- 不迁移输出库、不修改私人 Obsidian vault 内容。
- 不读取或展示私人输出内容，除非必须验证路径安全。
- 不提交 `config/local.paths.json`。

## 进度
- [x] 建立审查 ExecPlan
- [x] 运行基线命令
- [x] 完成静态风险扫描
- [x] 完成核心链路人工审查
- [x] 汇总发现、验证结果和后续建议

## 计划中的工作
- 先跑 `git status`、doctor、harness audit、entropy、harness 和全量测试，建立当前基线。
- 扫描 subprocess、网络请求、路径写入/删除、JSON 解析、缓存、环境变量、API key、HTML 输出和 shell 脚本。
- 按主流程、LLM、输出文件、本地 UI、治理 gate 五个风险面做人工审查。
- 对高风险点用现有测试风格做最小复核，避免误报。
- 输出按 High / Medium / Low 分级的审查报告。

## 具体步骤
1. 执行基线命令并记录是否通过。
2. 阅读高风险模块的实现和相关测试，确认真实行为。
3. 对可疑点做最小复现场景或定向只读验证。
4. 把发现按影响范围、触发条件、建议修复和测试需求整理。
5. 完成后补充结果与验证，并将计划移入 `completed/`。

## 发现与意外
- 基线命令全部通过：`doctor --consistency-only` 无 warning，`harness-audit --no-write-report` overall=ok，`entropy-check` 无 violations，`harness-check` overall=ok，`pytest` 313 passed。
- `doctor` 显示当前 `output_root` 解析到私人 Obsidian vault 路径，因此输出文件路径边界是本轮重点风险面。
- 发现本地配置 UI 的 POST 操作缺少会话令牌、Origin/Referer 校验或认证边界，且 CLI 允许绑定非 loopback host。
- 发现本地 UI 上传、远程 HTTP/PDF 下载和深读 PDF 缓存路径缺少大小上限，存在内存或磁盘耗尽风险。
- 发现深读 PDF 主抽取路径会绕过 `pdf_page_limit`，UI 和配置中的页数限制在成功抽取路径上不生效。
- 发现同步后的公开运行配置把 `allow_output_deletions` 设为 `true`，与 README/PROJECT_CONFIG 中默认保护语义不一致；结合私人 Obsidian `output_root`，删除操作风险高于文档预期。
- 发现 `/local-file` 对 project/output_root 下任意文件的读取边界过宽，索引 wikilink 目标解析也缺少 resolve 后的 output_root containment 校验。
- `harness-check`/测试链路曾刷新 `config/pending_tags.json` 的 tag 计数和时间戳；已按命令前 diff 恢复，保持本轮只读审查边界。

## 决策记录
- 本轮按用户要求只做审查，不做业务代码修复。
- `config/local.paths.json` 只作为路径安全检查点，不作为可提交配置。

## 结果与复盘
- 已完成只读审查，未修改业务源码。
- 审查输出 6 条实质风险：1 条本地 UI 未认证/CSRF 风险、1 条大文件/下载资源耗尽风险、1 条 PDF 页数限制失效、1 条输出删除保护配置漂移、1 条本地文件读取边界过宽、1 条 wikilink 路径穿越读取风险。
- 未发现 `shell=True`/字符串 shell 拼接、明显 API key 直出、SQL 字符串拼接注入或 OpenAI/OpenRouter 非 HTTPS base_url 被常规调用接受的问题。
- `config/local.paths.json` 当前未被 git 跟踪，公开示例文件仍为 `config/local.paths.example.json`。

## 验证
- `./scripts/run_science_monitor.sh doctor --consistency-only`：通过，无 warning。
- `./scripts/run_science_monitor.sh harness-audit --no-write-report`：通过，overall=ok。
- `./scripts/run_science_monitor.sh harness-check`：通过，overall=ok。
- `./scripts/run_science_monitor.sh entropy-check`：通过，issues=0。
- `./.venv/bin/python -m pytest -q`：通过，313 passed。
- `./scripts/run_science_monitor.sh real-eval --check-fixtures`：未运行；本轮未改真实案例链路，且已按计划完成必要基线。
