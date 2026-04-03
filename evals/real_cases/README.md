# Real Cases

这组真实案例用于手动集成评测，不进入 CI。

当前范围只覆盖：

- 无 PDF 时的单篇总结链路
- 无 PDF 时的周报链路
- 有本地 PDF 时的 repo 内深度解读评测链路

评测目标：

- 尝试通过文章页或 DOI 补全文或摘要
- 如果拿到网页全文，单篇总结应按全文路径生成
- 如果拿不到全文但能拿到摘要，单篇总结仍应生成，并显式标注 `#信息来源/仅摘要`
- 如果连摘要也拿不到，案例应判为失败

当前默认只跟踪两篇校准样例：

- `2023_sw_resnet_tmd`
- `2026_jgr_polar_convection_mohe`

说明：

- `cases.json` 是当前激活的真实论文清单，默认只保留用于当前校准与基线讨论的案例
- `cases_catalog.json` 保存更完整的候选案例目录，后续需要扩展样例集时再从这里挑选
- `fixtures/` 保存人工认可后的真实案例基线；只有确认“当前输出更正确”时才更新
- `assets/` 下的 PDF 只作为本地评测资产，为后续 deep-read 评测预留；该目录默认不纳入 Git
- 运行命令：`./scripts/run_science_monitor.sh real-eval`
- 基线比较：`./scripts/run_science_monitor.sh real-eval --check-fixtures`
- 基线刷新：`./scripts/run_science_monitor.sh real-eval --update-fixtures`
- 如需在项目内生成深度解读评测产物：`./scripts/run_science_monitor.sh real-eval --case-ids 2026_jgr_polar_convection_mohe --include-deep-read`
- 深度解读评测产物会写到 `log/real_case_eval/<case_id>/deep_reads/`，不会写入生产 `output_root`
