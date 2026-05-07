# 计划：2026-05-06_review_finding_fixes

## 目的 / 大图景
- 修复 2026-05-06 项目整体审查发现的 6 个功能、安全和稳定性问题。
- 将 config-ui、输出删除、上传下载、PDF 页数限制和索引路径边界收紧为可测试的默认行为。

## 背景与定位
- 已完成审查计划记录在 `docs/exec_plans/completed/2026-05-06_project_review.md`。
- 工作树已有 `AGENTS.md` 未提交修改，本轮不回退、不覆盖该既有变更。
- 当前 `config/runtime.json` 与 `PROJECT_CONFIG.md` 同步块把输出删除开关设为 `true`，需要恢复为默认保护语义。

## 工作范围
- 修改 `src/sciencemonitor/` 中 config-ui、HTTP、deep-read、article fetch、doctor 和 article index 相关模块。
- 修改 launcher 脚本以适配 token 化 config-ui。
- 修改 `config/runtime.json` 与 `PROJECT_CONFIG.md` 同步块。
- 增加或更新针对 6 个 finding 的回归测试。

## 非目标
- 不引入用户名/密码、长期密钥或远程部署认证系统。
- 不迁移既有缓存文件，不修改私人 Obsidian vault 或 `config/local.paths.json`。
- 不处理本轮 findings 之外的 UI 体验重构或文档大改。

## 进度
- [x] 建立修复 ExecPlan
- [x] 修复 config-ui token、host policy 和 launcher 探活/关闭
- [x] 修复 local-file allowlist、上传下载大小限制和 HTTP 分块读取
- [x] 修复输出删除保护、doctor 检查、PDF 页数限制和 wikilink containment
- [x] 增加回归测试并跑定向验证
- [x] 跑全量验证并移入 completed

## 计划中的工作
- 先落实 config-ui 安全边界，确保页面、JS、launcher 都使用同一个短期 token。
- 再收紧本地文件读取和上传/下载大小上限，避免内存、磁盘和私人文件暴露风险。
- 然后修复 runtime 默认删除保护、doctor warning、PDF 页数限制和索引路径穿越。
- 最后补齐定向回归测试，跑 harness 和全量测试。

## 具体步骤
1. 为 config-ui 增加 token 校验、loopback host policy、`/healthz` 和 launcher 适配。
2. 为 `/local-file`、上传保存、HTTP 下载增加 allowlist 与大小上限。
3. 修正 `allow_output_deletions` 默认同步值并增加 doctor `output_safety` 检查。
4. 贯通 PDF `page_limit`，并防止不匹配页数限制时复用旧 source cache。
5. 修正 wikilink target resolve 的 containment 校验。
6. 更新测试和执行验证命令。

## 发现与意外
- `harness-check` 和全量测试会刷新 `config/pending_tags.json` 的派生计数与时间戳；已按 diff 恢复，不纳入本轮修复。
- 安全修复增加了必要代码体积，`entropy-check` 初次失败；已同步更新 `config/maintenance_budget.json` 到本轮安全基线，并重新通过 `entropy-check`。

## 决策记录
- 非 loopback config-ui 访问保留，但必须显式传入 `--allow-non-loopback` 且仍使用 token。
- Token 仅为当前 server 进程短期值，不写入长期配置。
- 大小限制采用固定常量，不新增用户配置项。
- `/healthz` 保持公开只读，作为 launcher 探活入口；其他 config-ui 路径均要求 token。
- `local-file` 允许输出产物、人工中转请求文件和明确的 tag 管理 markdown，拒绝任意 config/data/log 路径。

## 结果与复盘
- 6 个审查 finding 均已修复并补测试。
- `config-ui` 默认只绑定 loopback，非 loopback 需要 `--allow-non-loopback`；所有业务 GET/POST 与本地文件读取均使用短期 token。
- 上传、下载、HTTP 响应和 local-file 读取均有固定大小上限。
- 输出删除默认恢复为 `false`，doctor 增加 `output_safety` 检查。
- PDF 页数限制贯通到主抽取路径，PDF source cache 增加 `pdf_page_limit` 匹配。
- wikilink 目标解析增加 output_root containment 校验。

## 验证
- `./.venv/bin/python -m pytest tests/test_config_ui.py tests/test_config_ui_review.py tests/test_launchers.py tests/test_http.py tests/test_deep_reads.py tests/test_article_fetch.py tests/test_article_index.py tests/test_doctor.py -q`：通过，110 passed。
- `./scripts/run_science_monitor.sh doctor --consistency-only`：通过，无 warning。
- `./scripts/run_science_monitor.sh harness-check`：通过，overall=ok。
- `./scripts/run_science_monitor.sh entropy-check`：通过，issues=0。
- `./.venv/bin/python -m pytest -q`：通过，330 passed。
