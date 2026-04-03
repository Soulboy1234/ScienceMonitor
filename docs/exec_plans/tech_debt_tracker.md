# Tech Debt Tracker

## 高优先级

- `article_summaries.py`、`article_index.py`、`llm.py`、`deep_reads.py` 文件过大
- 运行态目录和源码目录虽然已开始隔离，但默认边界仍可继续收紧
- `config-ui` 还没有接入研究偏好同步段；当前人类编辑入口已统一到 `PROJECT_CONFIG.md`，但网页配置面板尚未覆盖这部分
- 可补一个 `chatgpt_web_manual` 人工中转模式：程序生成标准化 prompt 包，用户在 ChatGPT 网页执行后再把结果回填，作为高成本深读和校准时的备用运行模式
- `codex_local` 在全文级单篇总结上的首轮推理延迟仍偏高，后续需要继续优化 prompt 包裁剪、执行目录隔离，或补充人工中转/替代后端

## 当前活跃治理项

- 当前没有单独立项中的治理计划；Phase 5 与 Phase 6 已完成并归档到 `completed/`

## 与 Todo 的分工

- `Todo.md` 记录近期明确排队、但暂未立项的事项
- 这里继续记录长期工程债、结构性问题和方向性改进

## 使用规则

- 这里记录长期存在但暂未拆成独立 ExecPlan 的工程债
- 一旦某项开始正式处理，就在 `active/` 新建对应计划
