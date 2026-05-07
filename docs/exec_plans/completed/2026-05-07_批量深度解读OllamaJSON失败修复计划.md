# 计划：2026-05-07_批量深度解读OllamaJSON失败修复

## 目的 / 大图景
- 修复批量深度解读中 Ollama 输出结构化 JSON 不稳定导致的 4 篇失败。
- 目标是提高 Ollama 深度解读链路的自动恢复能力，不改变 Codex 深读效果。

## 背景与定位
- UI 状态显示 13 个 PDF 成功 9 篇、失败 4 篇。
- 失败均发生在 Ollama 深读结构化输出解析阶段，不是 PDF 抽取失败。
- 已定位到 evidence v2 阶段的 markdown bullet/残片 JSON，以及 final 阶段的 LaTeX 非法转义和对象/数组字段格式问题。

## 工作范围
- Ollama 结构化 JSON 修复：`src/sciencemonitor/llm_api_support.py`。
- Ollama 深读恢复/重试：`src/sciencemonitor/llm.py`。
- 深读与 LLM 测试：`tests/test_llm.py`、`tests/test_deep_reads.py`。

## 非目标
- 不把 Ollama 失败自动切换到 Codex。
- 不降低深度解读内容质量要求。
- 不重写已经成功的 9 篇深度解读正文，除非重跑命中缓存或用户另行要求。

## 进度
- [x] 建立计划。
- [x] 增强 Ollama JSON 修复候选。
- [x] 增加 Ollama 深读本地修复与严格重试。
- [x] 增加真实失败样本测试。
- [x] 运行真实失败 PDF 验收与 gate。
- [x] 归档计划。

## 计划中的工作
- 先补解析器修复能力，使 4 个 raw output 样本能被恢复成合法 payload。
- 再把修复能力接入 Ollama 深读 evidence/final/revision 流程。
- 最后重跑失败样本并执行测试与 harness。

## 具体步骤
1. 扩展 Ollama JSON repair candidates，处理 bullet key、孤立残片、LaTeX 转义与 fenced JSON。
2. 在 Ollama 深读 evidence/final 请求失败时读取 invalid output，先本地修复，失败再严格重试。
3. revision 失败时保留有效 final payload，并在人工复核字段追加说明。
4. 增加单元测试覆盖 4 类失败 raw output 和 Codex 路径隔离。
5. 重跑失败 PDF 或上传目录，确认失败原因不再是现有 JSON 语法问题。

## 发现与意外
- 4 篇失败均可由确定性 JSON 修复或同链路重跑恢复，不需要切换 provider。
- Hua 的 raw output 同时存在已经正确转义的 `\\le` 和未正确转义的 `\le`，原修复正则会误伤双反斜杠，因此改为逐字符扫描，只修复未成对的非法反斜杠。
- Liu 的 evidence raw 中不是单独一行 `ually,`，而是缺少开头引号的数组残行；修复层现在会删除这类不合法残行，保留其余证据项。

## 决策记录
- Ollama 深读只在 Ollama provider 下修复/重试，不影响 Codex cache key、prompt、schema 或输出契约。

## 结果与复盘
- `llm_api_support` 新增 Ollama JSON 清理候选，覆盖 markdown bullet key、数组残片、尾逗号、未引用 key 和 LaTeX 非法反斜杠，同时避免破坏已正确转义的反斜杠。
- `llm.py` 的 Ollama 深读质量路径新增本地修复和严格 JSON 重试：evidence/final 失败先读 invalid output 修复，失败再重试；revision 失败会保留有效 final 初稿并写入人工复核提醒。
- 已用历史 4 个 invalid output 文件回放验证全部可解析。
- 已真实重跑 4 个失败 PDF，全部生成深度解读：
  - Gundlach：`Gundlach 2012 - GRL - 描述高纬度热层流中晨昏不对称性非线性动力学的简单模型 深度解读.md`
  - Hua：`Hua 2024 - GRL - 基于机器学习识别控制风暴期间外辐射带电子通量骤减的关键驱动因子 深度解读.md`
  - Jenner：`Jenner 2024 - GRL - 总根电子含量：一种用于低地球轨道卫星下方电离层的新型度量指标 深度解读.md`
  - Liu：`Liu 2024 - GRL - 太阳活动极小期赤道垂直 E×B 漂移受潮汐控制的机制研究 深度解读.md`

## 验证
- `./.venv/bin/python -m pytest tests/test_llm.py tests/test_deep_reads.py tests/test_config_ui.py -q`
- `./.venv/bin/python -m pytest -q`
- `git diff --check`
- `./scripts/run_science_monitor.sh harness-check`

已完成：
- `./.venv/bin/python -m pytest tests/test_llm.py tests/test_deep_reads.py tests/test_config_ui.py -q`：113 passed。
- `./.venv/bin/python -m pytest -q`：335 passed。
- `git diff --check`：通过。
- `./scripts/run_science_monitor.sh harness-check`：通过。第一次运行发现真实输出 tag 行需按治理规则同步，已执行 `tag-candidates --reconcile-output --limit 0` 后复跑通过。
