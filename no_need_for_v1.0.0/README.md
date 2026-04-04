# no_need_for_v1.0.0

这个目录用于放置 `v1.0.0` 前大清扫时，从主工作流中移出的历史材料和无用配置。

放在这里的原则：

- 不再参与当前运行链路
- 不再承担当前 docs / config 的主控制面职责
- 仍然值得保留，便于回溯旧设计、旧说明或旧实验残留

当前已归档：

- `docs_archive/`
  - 旧版设计草稿、任务清单、user journey、agent log 等历史文档
- `config_archive/codex_test_schema.json`
  - 当前仓库中没有任何引用的旧测试 schema

这里的内容默认不应再被当前 agent 当作主要 source of truth。
