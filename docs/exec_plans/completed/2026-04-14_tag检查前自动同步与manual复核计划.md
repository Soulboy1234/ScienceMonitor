# 计划：2026-04-14_tag检查前自动同步与manual复核

## 目的 / 大图景
- 修正“formal_tags.md 已人工更新，但标签检查仍直接拿旧 `focus_tags.json` 判断”的同步缺口。
- 保证运行期与日常检查时，formal Markdown 变更能够先同步到机器 JSON，再执行标签检查。
- 在修好同步逻辑后，重新核查 `manual` 输出库中还有哪些标签未被正式标签体系收录。

## 背景与定位
- 用户已经把剩余标签补进了 `formal_tags.md`，但检查结果仍显示部分 `manual` 标签“未收录”，说明检查逻辑可能没有优先同步 formal Markdown。
- `tag_governance_review` 原本直接读取 `focus_tags.json` 和 `formal_tags.md` 做比对；`load_focus_tags()` 也会无条件尝试同步，但没有显式区分“Markdown 更新更晚时应先同步”和“JSON 自己漂移时仍应报错”。
- 这轮重点是把“运行期自动同步”和“审核期保留漂移检测”这两个目标同时满足。

## 工作范围
- `src/sciencemonitor/tag_governance.py`
- `src/sciencemonitor/config.py`
- `src/sciencemonitor/tag_governance_review.py`
- `tests/test_tag_governance_review.py`
- `manual/` 输出库标签复核

## 非目标
- 本轮不再次批量改写 `manual` 全部文件。
- 本轮不重构标签 taxonomy 内容，只修同步时机与检查逻辑。
- 本轮不处理与标签无关的 harness 或 UI 工作。

## 进度
- [x] 步骤 1：定位 formal Markdown 与 JSON 不一致时，哪些检查入口会直接读取旧 JSON。
- [x] 步骤 2：新增“仅当 formal Markdown 更新更晚时才先同步”的 helper。
- [x] 步骤 3：让运行期加载与标签治理检查都接入该 helper。
- [x] 步骤 4：补回归测试，覆盖“Markdown 更新更晚自动同步”和“JSON 自己漂移仍可报错”。
- [x] 步骤 5：重新核查 `manual` 标签收录状态并记录结果。

## 计划中的工作
- 先抽出一个按文件修改时间判断的同步 helper。
- 再把运行期加载和 tag governance review 接到这个 helper 上。
- 然后加测试，确保不会把 JSON 自己的漂移问题静默吞掉。
- 最后重新扫描 `manual`，确认还剩哪些标签未和 formal 对齐。

## 具体步骤
1. 在 `tag_governance.py` 中新增 `sync_formal_tags_to_focus_tags_json_if_markdown_newer()`。
2. 在 `config.py` 的 `load_focus_tags()` 中改为调用上述 helper，而不是每次无条件同步。
3. 在 `tag_governance_review.py` 中，先执行“Markdown 更新更晚时自动同步”，再继续检查。
4. 在 `tests/test_tag_governance_review.py` 中补：
   - formal Markdown 更新更晚时自动同步后通过；
   - JSON 更新更晚且内容漂移时仍报 `formal_drift`。
5. 重新扫描 `manual` 目录中的全部 Markdown 标签，统计剩余未收录项。

## 发现与意外
- 用户补进的 `工具`、`对象/电离层/foF2`、`对象/电离层/hmF2` 已经成功进入正式体系。
- 剩余唯一未对齐项不是“没同步”，而是命名差异：
  - `formal_tags.md` / `focus_tags.json` 中存在的是 `对象/场论`
  - `manual` 中仍保留的是 `场论`
- 也就是说，当前剩余问题是 `manual` 文件里的旧标签写法未迁移，而不是 formal 没同步。

## 决策记录
- 自动同步只在 `formal_tags.md` 的修改时间晚于 `focus_tags.json` 时触发。
- `tag_governance_review` 仍然保留 drift 检测能力；如果是 JSON 自己更新更晚并漂移，review 继续报错。
- `manual` 标签复核按“实际输出标签是否出现在正式标签集合中”判断，不用模糊印象替代机器检查。

## 结果与复盘
- 运行期与日常标签检查现在会在必要时先同步 formal Markdown，再检查。
- 回归测试通过，确认同步逻辑和 drift 检测可以同时成立。
- 重新扫描 `manual` 后，仅剩 1 个未对齐标签：
  - `Laundal 2024 - GRL - B & V 范式描述电离层变化.md` 中的 `场论`
- 当前机器侧正式标签中已有 `对象/场论`，因此剩余动作是把这篇 `manual` 文件里的 `场论` 改成 `对象/场论`，或由用户决定是否保留这一旧写法。

## 验证
- `./.venv/bin/python -m pytest tests/test_tag_governance_review.py tests/test_tag_candidates.py -q` -> 通过（12 passed）
- `git diff --check` -> 通过
- `PYTHONPATH=src ./.venv/bin/python - <<'PY' ...`：重新扫描 `manual` 标签后，仅剩 `场论` 1 项未对齐
