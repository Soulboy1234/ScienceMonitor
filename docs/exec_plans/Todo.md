# Todo

这个文件记录“已经明确、但暂不立项”的近期待办。

使用原则：

- `active/`：已经正式开工的阶段计划
- `completed/`：已经完成的阶段计划
- `Todo.md`：近期明确排队项
- `tech_debt_tracker.md`：长期工程债和方向性问题

## 当前排队项

- 周报审核继续优化：
  当前只接入了轻量格式审核。等真实案例和额度条件允许后，再补内容层强审核、真实案例基线和周报语气校准。

- `config-ui` 接入研究偏好同步段：
  让用户不必手改 `PROJECT_CONFIG.md` 中的研究偏好块。

- `chatgpt_web_manual` 人工中转模式：
  程序生成标准化 prompt 包，用户在 ChatGPT 网页执行后回填结果，作为高成本深读和校准的备用后端。

- 历史输出迁移：
  等代码和审核规则稳定后，再统一把旧的单篇总结、周报、深度解读输出迁移到当前命名和格式体系。

- 大文件拆分：
  `article_summaries.py`、`reporting.py`、`deep_reads.py`、`llm.py`、`article_index.py` 仍然偏大，后续要继续拆分模块职责。

- `codex_local` 首轮全文分析时延优化：
  当前缓存命中后已较稳定，但首轮全文级分析仍偏慢。
