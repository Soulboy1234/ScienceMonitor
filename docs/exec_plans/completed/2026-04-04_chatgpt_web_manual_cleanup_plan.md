# ChatGPT Web Manual Cleanup Plan

## Goal

把 `chatgpt_web_manual` 从“本地长 prompt + 多文件 bundle”改成真正适合网页 ChatGPT 人工中转的轻量流程：

1. 请求包默认只保留一个 `prompt.md`。
2. 不再默认复制全文、摘要整理稿、related summary 或 PDF。
3. prompt 改成“最小定位信息 + 严格 JSON-only 输出”。
4. 响应文件命名稳定、可识别，并可从 `responses/` 直接采用标准命名结果。

## Work Items

1. 清理 request bundle 结构，只保留 `prompt.md`、`request.md`、`metadata.json`。
2. 为单篇总结、周报、深度解读分别加入 manual 专用最小 prompt。
3. 收紧 deep-read manual 路径，避免为了 manual provider 在本地先构造全文级长 prompt。
4. 为响应文件引入稳定命名，并更新导入/读取逻辑。
5. 更新工作流文档、测试，并用 `2026_jgr_polar_convection_mohe` 重新验证。

## Exit Criteria

- 请求目录不再包含 `schema.json`、`response_template.json`、`context/`、`attachments/`。
- `prompt.md` 单文件即可直接发给网页 ChatGPT。
- prompt 明确要求最终只输出一个 JSON 对象，不需要用户额外补一句。
- `responses/` 下的推荐文件名可以稳定区分任务和文章。
- 测试通过，`manual-llm-status` 可正确反映新命名和新状态。

## Result

- 已完成。`chatgpt_web_manual` 请求包默认只保留 `prompt.md`、`request.md`、`metadata.json`。
- 已为单篇总结、周报、深度解读改用 manual 专用最小 prompt。
- 已收紧深度解读 manual 路径，不再为了网页中转在本地先构造全文级长 prompt。
- 已加入稳定响应文件名，例如 `ScienceMonitor_10_1029_2025ja034386_article_summary_article_38a5a34c8e.json`。
- 已验证 `2026_jgr_polar_convection_mohe` 的单篇总结和深度解读中转结果可正常导入并生成输出。
- 验证状态：
  - `manual-llm-status`：2 个请求，均为 `ready`
  - `doctor --consistency-only`：通过
  - `entropy-check`：通过
  - `maintenance-check --auto-repair --max-passes 2`：通过
  - `pytest -q`：`121 passed`
