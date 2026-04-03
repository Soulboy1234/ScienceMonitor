# Real Case Harness Phase 4

## Purpose / Big Picture

第四阶段把 harness engineering 从“合成样例回归”推进到“真实论文集成评测”。

目标是明确两条运行边界：

- 单篇总结 / 周报：无 PDF 时优先尝试网页全文，失败则退回摘要，并显式标记仅摘要
- 深度解读：无 PDF 时只做简单网页搜索；拿不到可用全文就直接要求用户提供 PDF

## Scope

- `src/sciencemonitor/article_fetch.py`
- `src/sciencemonitor/article_summaries.py`
- `src/sciencemonitor/deep_reads.py`
- `src/sciencemonitor/real_case_eval.py`
- `evals/real_cases/`
- 相关测试与说明文档

## Progress

- [x] 新增 DOI/落地页候选 URL 解析与网页内容抓取层
- [x] 给单篇总结接入“网页全文优先、摘要回退”
- [x] 给仅摘要单篇总结打上 `#信息来源/仅摘要`
- [x] 将 `deep-read` 的无 PDF 路径收缩为简单搜索后失败即要求 PDF
- [x] 用 8 篇真实论文建立 `evals/real_cases/cases.json`
- [x] 新增 `real-eval` 命令，生成真实案例的单篇总结和周报
- [x] 把 deep-read 的真实 PDF 案例接入 repo 内评测目录
- [x] 将真实案例默认收敛到当前校准用的 2 篇论文
- [x] 把真实案例深度解读从生产 `output_root` 隔离到 `log/real_case_eval/`
- [x] 给真实案例深度解读接入评测态 PDF/单篇总结本地链接

## Success Criteria

- 单篇总结 / 周报在无 PDF 场景下有稳定回退
- `deep-read` 在无 PDF 场景下失败边界清晰，不再隐式重试过多路径
- 真实论文样例可重复运行并留下结果记录

## Completion Note

这一阶段已经完成。

完成标志：

- 真实案例评测已经覆盖单篇总结和深度解读
- 评测输出与生产输出目录已经隔离
- 当前使用的 2023 / 2026 两篇论文已经形成稳定的真实案例校准入口
- 周报真实案例仍保留轻量状态，但这属于后续样例不足下的内容优化问题，不再阻塞第四阶段收尾
