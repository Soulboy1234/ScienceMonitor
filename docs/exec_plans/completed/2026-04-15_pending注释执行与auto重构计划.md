# 计划：2026-04-15_pending注释执行与auto重构

## 目的 / 大图景
- 按当前 `config/tag/pending_tags.md` 中的勾选和注释，重写 `auto` 输出中的标签，并重建 `pending`。
- 让 pending 的人工批注真正参与执行，而不是只停留在 Markdown 展示层。

## 背景与定位
- 当前 `pending` 的勾选转正链路已经存在，但注释解析只支持很少几种格式。
- 用户这次在 `pending_tags.md` 里加入了大量“目标标签 / 删除 / 问题备注”型注释，现有逻辑不足以完整执行。

## 工作范围
- `src/sciencemonitor/tag_governance.py`
- `tests/test_tag_candidates.py`
- 刷新真实 `auto` 输出
- 重建 `config/tag/pending_tags.md` 与 `config/pending_tags.json`

## 非目标
- 不调整 `manual` 输出
- 不扩展 formal 体系结构，只执行当前勾选转正和注释指向

## 进度
- [x] 步骤 1：补强 pending 注释解析规则
- [x] 步骤 2：补测试并验证注释语义
- [x] 步骤 3：执行真实 auto 标签修订与 pending 重建
- [x] 步骤 4：跑 harness 收尾

## 计划中的工作
- 先让程序能正确读懂这版注释。
- 再用同一套规则执行真实输出修订。
- 最后刷新 pending，确认结果收敛。

## 具体步骤
1. 支持“`- 目标标签`”“`- 删除`”“无连接符直接跟目标标签”“问题型备注保留不执行”等情况。
2. 补测试覆盖这些注释格式。
3. 对真实仓库执行标签修订和转正。
4. 跑测试与 `harness-check`。

## 发现与意外
- 用户这版 `pending_tags.md` 同时使用了三种注释写法：`- 删除`、`- 目标标签`、不带连接符直接跟目标标签。
- 真实输出在第一次批量改写后，仍有 8 个文件的标签与审核结果不一致，需要额外跑一次 review reconcile 才能让 `tag_output_review` 归零。

## 决策记录
- 问题型备注只保留在 pending，不自动改写输出。
- 显式目标标签注释优先于启发式映射规则。
- `删除` 注释直接删除对应 `auto` 输出文件，不保留空壳记录。

## 结果与复盘
- 已补强 pending 注释解析，支持“删除 / 目标标签 / 无连接符目标标签 / 问题备注”四类输入。
- 已新增回归测试，验证目标标签改写、无分隔符注释改写和问题备注保留三种行为。
- 已对真实 `auto` 输出执行本轮批注：转正并吸收 45 个标签，之后重建 pending。
- 已对 8 个首轮未完全收敛的输出文件再次执行 review reconcile，最终 `tag_output_review=ok`。
- 当前 pending 收敛为 6 个真实残留标签：`事件/磁暴/正暴`、`事件/磁暴/负暴`、`指数/EUV`、`对象/外逸层`、`对象/电离层/扩展F`、`应用/卫星轨道`。

## 验证
- `./.venv/bin/python -m pytest tests/test_tag_candidates.py -q`
- `./scripts/run_science_monitor.sh harness-check`
