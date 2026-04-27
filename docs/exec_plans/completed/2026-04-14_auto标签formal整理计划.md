# 计划：2026-04-14_auto标签formal整理

## 目的 / 大图景
- 按当前 `formal_tags.md` 的规则整理 `auto/` 输出库中的标签。
- 对能被正式标签体系描述的标签，尽量迁移到正式标签；不能稳定对应的保留为 AI 生成标签。
- 整理完成后刷新 `pending_tags.json` 和 `pending_tags.md`，让预选标签回到最新状态。

## 背景与定位
- `manual/` 目录已基本和正式标签体系对齐，当前下一步是处理 `auto/` 目录。
- `auto/` 中有大量历史输出仍保留旧标签、短标签或 AI 自定义标签，导致 formal/pending 统计混杂。
- 本轮既要修改真实输出文件，也要把整理逻辑做成可复用能力，避免以后重复写一次性脚本。

## 工作范围
- `src/sciencemonitor/tag_governance.py`
- 相关测试
- `output_root()/auto` 下的 Markdown 输出文件
- `config/pending_tags.json`
- `config/tag/pending_tags.md`

## 非目标
- 本轮不修改 `manual/` 目录。
- 本轮不重写文章正文内容，只整理标签行。
- 本轮不新增大规模 formal taxonomy 内容，只用当前 formal 体系做映射。

## 进度
- [x] 步骤 1：扫描 `auto/` 标签现状，统计 formal 未覆盖情况。
- [x] 步骤 2：实现可复用的既有输出标签整理逻辑。
- [x] 步骤 3：批量整理 `auto/` 文件标签。
- [x] 步骤 4：刷新 pending 标签文件。
- [x] 步骤 5：验证结果并归档计划。

## 计划中的工作
- 先把 formal 可复用映射规则沉淀成代码，而不是一次性脚本。
- 再对 `auto/` 目录批量执行标签整理，保留无法稳定映射的 AI 标签。
- 然后刷新 pending 标签，确保预选体系反映最新输出状态。
- 最后做定向验证，确认 `auto/` 中 formal 能覆盖的标签已经迁移完成。

## 具体步骤
1. 提取“既有标签 -> formal 标签”的可复用映射规则，包括唯一后缀匹配和少量显式别名。
2. 新增函数用于批量重写输出文件中的标签行，并返回修改报告。
3. 对 `auto/article_summaries` 与 `auto/deep_reads` 执行批量整理。
4. 刷新 `pending_tags.json` 与 `pending_tags.md`。
5. 重新统计 `auto/` 中仍未进入 formal 的标签，区分“合理保留的 AI 标签”和“遗漏映射”。

## 发现与意外
- 初始扫描显示 `auto/` 中有大量 formal 可覆盖的旧标签，例如 `磁暴`、`热层/密度`、`日地耦合`、`TEC`、`GNSS`、`MMS` 等。
- 也存在大量 formal 无法直接描述的 AI 标签，例如专题性很强的物理量、过程或天体环境标签，这些应保留为 AI 标签并进入 pending。
- `formal_tags.md` 当前存在人工友好的合并标题写法，例如 `## 应用与工具`；原同步逻辑不能正确识别，导致 `focus_tags.json` 一度漏掉 `应用/*` 标签。
- `pending` 原先会保留已经能唯一映射到 formal 的旧标签，导致使用次数校验出现假漂移；本轮已改为自动剔除。

## 决策记录
- 优先实现复用函数，不再使用一次性脚本直接改真实输出。
- formal 映射采用“唯一后缀匹配 + 少量显式别名”，避免大面积误归并。
- 对存在歧义的标签不强行改 formal，保留为 AI 标签。

## 结果与复盘
- 已把 `formal_tags.md -> focus_tags.json` 的同步兼容性补齐，支持合并标题和更宽松的正式分类识别。
- 已把 `auto/article_summaries` 与 `auto/deep_reads` 中能稳定映射到 formal 的旧标签批量改写到正式路径；第一次实跑共修改 160 个文件，补完 `应用/*` 归位后又追加修改 44 个文件。
- 当前再次扫描 `auto/` 时，`modified_now=0`，说明现有整理逻辑已经收敛。
- 仍未进入 formal 的标签共 542 种，已同步刷新到 `pending_tags.json` 与 `pending_tags.md`，按真实输出使用次数排序，等待人工审核。
- `harness-check` 的标签治理部分已通过；当前整体验证唯一剩余失败项是既有 `golden article_summary drift`，与本轮 `auto` 标签整理无关。

## 验证
- `./.venv/bin/python -m pytest tests/test_tag_candidates.py tests/test_tag_governance_review.py -q`
- `PYTHONPATH=src ./.venv/bin/python - <<'PY' ...` 扫描 `auto/` formal 未覆盖标签
