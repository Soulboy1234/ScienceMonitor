# 计划：2026-04-11_tag维护可读性与manual词表补全

## 目的 / 大图景
- 提升正式/预选标签文件的人类可维护性，降低阅读和手工编辑成本。
- 把 `manual/` 输出目录中真实使用过的标签补入正式标签体系，先把现有人工产出沉淀成正式词表基线。

## 背景与定位
- 当前标签 Markdown 里仍有反引号和部分“分组”节点，人工审阅体验一般。
- 用户要求正式标签中所有父标签都必须有实体对应，不能只作为结构占位。
- 用户要求先统计 `output/manual` 下 `.md` 文件实际使用的标签，并统一纳入正式标签，但不能改动这些 manual 文件本身。

## 工作范围
- `src/sciencemonitor/tag_governance.py`
- `src/sciencemonitor/tag_governance_review.py`
- `tests/test_tag_candidates.py`
- `tests/test_tag_governance_review.py`
- `config/tag/formal_tags.md`
- `config/focus_tags.json`
- `config/tag/pending_tags.md`
- `config/pending_tags.json`

## 非目标
- 本轮不修改 `manual/` 目录下任何文章文件内容。
- 本轮不做 tag 语义优劣判断，只先按用户要求补齐正式词表。

## 进度
- [x] 步骤 1：重构标签 Markdown 渲染与解析规则。
- [x] 步骤 2：实现 formal 自动补父标签与 manual 标签并入。
- [x] 步骤 3：回写正式/预选文件并补测试。
- [x] 步骤 4：运行 pytest 和 harness-check 收尾。

## 计划中的工作
- 先去掉标签 Markdown 中的反引号，保留纯文本层级结构。
- 再保证正式标签集合总是自动补全所有父标签。
- 然后统计 `manual/` 中真实使用的标签并并入正式体系。
- 最后刷新 formal/pending 文件、清理预选重叠并跑回归验证。

## 具体步骤
1. 修改 formal/pending Markdown 的渲染与解析逻辑，兼容无反引号写法。
2. 在 formal 同步链路中自动补齐所有父标签。
3. 新增 `manual/` 标签统计与正式标签并入动作。
4. 更新测试，验证父标签自动补齐、预选 Markdown 渲染、manual 标签并入。

## 发现与意外
- `manual/` 输出库中的实际标签规模比预期大，共统计到 208 个唯一标签、143 个含标签的 Markdown 文件。
- 旧 formal 文件的主要问题不是标签缺失，而是部分已入库标签的分类被历史逻辑错误保留，需要先做重分类再重写 formal。
- `focus_tags.json` 的机器规则与 formal Markdown 的正式标签集合必须继续分离维护，不能直接互相覆盖全部字段。

## 决策记录
- formal/pending Markdown 中的标签条目统一改为纯文本，不再使用反引号包裹标签名。
- formal 侧不再保留“仅分组父节点”的概念，所有层级父标签在同步时自动补成真实正式标签。
- `manual/` 下真实输出文件的标签全部并入正式标签，但不改动 `manual/` 目录内任何文件。
- 分类归属优先按父前缀和规则重判，再回写 formal/focus，避免历史错误分类继续固化。

## 结果与复盘
- 已完成 formal/pending 可读性重构：正式和预选标签文件中的标签条目均已改为纯文本显示。
- 已完成 formal 自动补父标签：formal 中不再显示 `（分组）`，父标签全部作为真实正式标签存在。
- 已完成 `manual/` 标签并入：统计 `manual/` 输出库后，所有 208 个实际使用过的标签均已纳入 formal，缺失数为 0。
- 已修正 formal 旧分类漂移：如 `太阳风`、`磁暴`、`SEP`、`Space-X事件` 已归入“事件 / 驱动”，`工具`、`数据分析`、`统计研究`、`深度学习` 已归入“模型 / 方法”。
- 本轮未改动 `manual/` 输出文件，只更新了标签治理代码、formal/pending 文件与测试。

## 验证
- `./.venv/bin/python -m pytest -q`
- `./scripts/run_science_monitor.sh harness-check`
- `manual_tag_count=208`
- `missing_count=0`
