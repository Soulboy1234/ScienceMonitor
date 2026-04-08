# ChatGPT Web Manual Workflow

这个模式用于把高消耗分析从 `codex_local` 或 `openai_api` 分流到 ChatGPT 网页人工处理中转。

它不是浏览器自动化，也不会自动登录或抓取 ChatGPT 网页。

## 适用场景

- 单篇总结想减少本地 Codex 消耗
- 多篇周报想把整体分析交给 ChatGPT 网页
- 深度解读想复用 ChatGPT 网页额度

## 运行方式

先把 [PROJECT_CONFIG.md](../../PROJECT_CONFIG.md) 或 [config/analysis.json](../../config/analysis.json) 中的：

- `provider`

改成：

- `chatgpt_web_manual`

## 运行后会发生什么

当你运行以下命令时：

- `./scripts/run_science_monitor.sh summaries ...`
- `./scripts/run_science_monitor.sh report ...`
- `./scripts/run_science_monitor.sh deep-read ...`
- `./scripts/run_science_monitor.sh daily ...`

程序不会直接调用 LLM，而是：

1. 在 `data/chatgpt_web_manual/requests/` 下生成请求包
2. 输出 `request_id` 和请求目录
3. 等待你把 ChatGPT 网页结果导回本地

请求包里会有：

- `request.md`
- `prompt.md`
- `metadata.json`

默认不会再自动复制全文整理稿、摘要整理稿、related summary 或 PDF。

你真正需要上传到网页 ChatGPT 的通常只有：

- `prompt.md`
- 原始 PDF（只有在你自己想提供时才上传）

首选流程是“上传 `prompt.md` 文件 -> 让 ChatGPT 网页创建可下载 JSON 文件 -> 把 JSON 文件放进 `responses/`”。不需要手动复制 prompt 内容，也不需要手动新建 JSON。

## 固定工作流合同

后续人工中转固定采用下面这套风格：

- 程序只生成轻量请求包，默认只包含 `prompt.md`、`request.md`、`metadata.json`
- 默认只把 `prompt.md` 上传到 ChatGPT 网页
- 如果是深度解读，且用户手头有原始 PDF，可以额外上传 PDF
- 不默认上传程序抽取的全文、摘要整理稿、related summary 或缓存文件
- ChatGPT 网页应返回或创建一个 JSON 文件；如果网页只把 JSON 展开在正文里，这是兜底路径，不是首选路径
- JSON 放进 `data/chatgpt_web_manual/responses/` 后，用 `manual-llm-import --request-id <request_id>` 导入
- 导入后的内容必须继续经过本地 schema 校验、标签归一化、模板渲染和报告审核闭环
- 深度解读不继承单篇总结的 `信息来源/*` 状态标签；这类标签只描述单篇总结自身的证据边界
- 单篇总结如果网页响应自述只基于摘要/元数据，仍应保留 `#信息来源/仅摘要`

## 单篇总结工作流

1. 运行 `summaries` 或 `daily`
2. 程序会为每篇待分析论文生成一个请求包
3. 打开对应请求目录中的 `prompt.md`
4. 把 `prompt.md` 作为文件上传给 ChatGPT 网页
5. 如你自己手头有 PDF，可额外上传原始 PDF
6. 要求网页端创建可下载 JSON 文件，并按 `request.md` 里写的推荐文件名放到 `data/chatgpt_web_manual/responses/`
7. 运行 `manual-llm-import --request-id <request_id>`，或直接重新运行原命令

## 周报工作流

1. 先确保对应单篇总结已经有结果
2. 运行 `report`
3. 程序会为本次周报生成一个请求包
4. 在 ChatGPT 网页完成分析后导入响应
5. 重新运行 `report`

## 深度解读工作流

1. 运行 `deep-read`
2. 程序会生成一个深度解读请求包
3. 默认只使用 `prompt.md`；如果你自己有原始 PDF，可手动上传
4. 在 ChatGPT 网页完成分析后，把可下载 JSON 文件按推荐文件名放进 `responses/`
5. 重新运行 `deep-read`

## 导入命令

查看当前请求状态：

```bash
./scripts/run_science_monitor.sh manual-llm-status
```

只看待处理请求：

```bash
./scripts/run_science_monitor.sh manual-llm-status --pending-only
```

导入响应文件：

```bash
./scripts/run_science_monitor.sh manual-llm-import --request-id <request_id>
```

如果网页端仍只给了可复制文本，而不是可下载 JSON 文件，可以把文本保存成推荐文件名，或指定文件/从剪贴板导入：

```bash
./scripts/run_science_monitor.sh manual-llm-import --request-id <request_id> --response-file /path/to/response.txt
```

也可以从标准输入导入：

```bash
pbpaste | ./scripts/run_science_monitor.sh manual-llm-import --request-id <request_id> --response-file -
```

## 状态说明

- `pending`：请求包已生成，但还没有导入响应
- `ready`：已导入可用响应，或 `responses/` 中已经有可直接采用的标准 JSON，重新运行原命令即可继续
- `stale`：之前导入过响应，但 prompt 或 schema 已变化，需要重新导入

## 注意事项

- 这是人工中转，不是自动化运行
- 程序会校验导入响应是否符合 schema；不符合时会拒绝导入
- prompt 里已经强制要求“创建可下载 JSON 文件，不要在聊天正文展开完整 JSON”
- 导入成功后，正常分析结果仍会进入现有 cache、审核和输出链路
- 如果 prompt 或 schema 变化，旧响应会自动变成 `stale`
