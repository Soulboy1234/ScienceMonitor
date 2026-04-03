# Golden Evals

这里保存 `ScienceMonitor` 的稳定样例输出基线。

用途：

- 给单篇总结、周报、深度解读提供可比对的基线输出
- 在模板、提示词、标签规则或渲染逻辑调整后，快速发现行为漂移

生成方式：

- 本地校验：`./scripts/run_science_monitor.sh golden-eval`
- 刷新基线：`./scripts/run_science_monitor.sh golden-eval --update`

说明：

- 这些文件不是人工手写样例，而是程序按当前规则生成后再做轻量归一化的结果
- 时间戳等不稳定字段会被规范化成占位文本，避免无意义漂移
- 如果 golden eval 失败，应先看 `log/golden_eval/diffs/` 下的 diff，再决定是修代码还是更新基线
