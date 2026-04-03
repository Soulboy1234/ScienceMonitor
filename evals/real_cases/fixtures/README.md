# Real Case Fixtures

这里保存已经人工认可的真实案例基线。

约定：

- 每个 case 一个目录：`<case_id>/`
- 只保存已经认可的产物：
  - `summary.md`
  - `report.md`
  - `deep_read.md`
  - `status.json`
- 不要直接手改这里的内容

推荐更新方式：

```bash
./scripts/run_science_monitor.sh real-eval --update-fixtures
```

推荐检查方式：

```bash
./scripts/run_science_monitor.sh real-eval --check-fixtures
```
