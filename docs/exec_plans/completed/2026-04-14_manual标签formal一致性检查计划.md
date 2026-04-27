# 计划：2026-04-14_manual标签formal一致性检查

## 目的 / 大图景
- 检查 `manual` 输出库中的文章总结标签，确认它们是否已经和当前 `formal_tags.md` 对齐。
- 找出仍未被正式标签体系收录的 `manual` 标签，作为后续标签治理的剩余问题清单。
- 补足本轮维护记录，避免“做了检查但没有计划与归档”的情况再次出现。

## 背景与定位
- 用户已经手动调整过 `manual` 目录中的标签，并同步修订了 `formal_tags.md`。
- 上一轮处理中已经批量迁移过 `manual` 标签，但 formal 标题解析和层级迁移曾出现过偏差，因此需要重新核查最终状态。
- 本轮是“检查与记录”任务，不重做一整轮标签重构。

## 工作范围
- `manual/` 实际输出库中的 Markdown 文章总结
- `config/tag/formal_tags.md`
- `config/focus_tags.json`
- `config/pending_tags.json`
- `docs/exec_plans/completed/`

## 非目标
- 本轮不批量新增正式标签。
- 本轮不自动修改剩余未收录标签的内容定义。
- 本轮不重写 `manual` 文章正文，只检查标签是否已被 formal 收录。

## 进度
- [x] 步骤 1：检查当前是否存在 active plan，确认这轮任务没有单独记录。
- [x] 步骤 2：扫描 `manual` 目录中的全部 Markdown，统计实际使用标签。
- [x] 步骤 3：对照 `focus_tags.json` 中的正式标签集合，找出未被收录的标签。
- [x] 步骤 4：检查剩余未收录标签是否已进入 `pending_tags.json`。
- [x] 步骤 5：补写完成态计划，归档这轮检查与结论。

## 计划中的工作
- 先确认这轮任务之前是否缺少 exec plan 记录。
- 再把 `manual` 实际标签与 formal 机器侧标签集合逐一比对。
- 然后区分“仍有问题的文件数”和“未收录标签种类数”。
- 最后检查这些剩余标签是否已进入 pending，并把结果写入归档计划。

## 具体步骤
1. 读取 `docs/exec_plans/active/`，确认本轮任务开始前没有单独的 active plan。
2. 扫描 `manual` 目录下全部 Markdown 文件，提取标签并统计标签种类数与文件数。
3. 读取 `config/focus_tags.json` 中的正式标签集合，检查哪些 `manual` 标签尚未进入 formal。
4. 读取 `config/pending_tags.json`，确认剩余未收录标签是否已经进入 pending 工作流。
5. 输出结论，并将本次检查写入 `docs/exec_plans/completed/`。

## 发现与意外
- `manual` 目录当前共有 170 个 Markdown 文件，实际使用了 202 种标签。
- 当前仅剩 4 种标签未进入 formal：
  - `工具`
  - `场论`
  - `对象/电离层/foF2`
  - `对象/电离层/hmF2`
- 这 4 个标签也尚未进入 `pending_tags.json`，说明它们目前既不在正式体系，也不在预选体系中。

## 决策记录
- 本轮只做检查与记录，不擅自把剩余 4 个标签自动加入 formal 或 pending。
- 对“manual 中未被收录的标签”按实际输出库和机器侧正式标签集合比对，不以人工印象判断。
- 计划记录直接写入 `completed`，因为本轮检查在当前回合内已完成，不再保留 active 状态。

## 结果与复盘
- 检查结果显示：`manual` 标签体系已经基本和 formal 对齐，只剩 4 个标签未被 formal 收录。
- 仍有问题的文件共有 4 个：
  - `Acciarini 2023 - SW - 热层密度建模及框架.md`：`工具`
  - `Laundal 2024 - GRL - B & V 范式描述电离层变化.md`：`场论`
  - `Lei 2008 - JGR.SP - CMIT 模拟TID探究多因素贡献.md`：`对象/电离层/foF2`、`对象/电离层/hmF2`
  - `Lu 2001 - JGR.SP - 磁暴期间TID的hmF2和foF2相对变化.md`：`对象/电离层/foF2`、`对象/电离层/hmF2`
- 下一步如果继续推进，应由用户决定：
  - 把这 4 个标签加入 formal；
  - 或先进入 pending；
  - 或将其改写为已有正式标签。

## 验证
- `PYTHONPATH=src ./.venv/bin/python - <<'PY' ...`：扫描 `manual` 目录并统计实际标签
- `PYTHONPATH=src ./.venv/bin/python - <<'PY' ...`：比对 `focus_tags.json` 中的正式标签集合
- `PYTHONPATH=src ./.venv/bin/python - <<'PY' ...`：检查剩余标签是否已进入 `pending_tags.json`
