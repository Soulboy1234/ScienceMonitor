# 计划：2026-04-09_workflow_specs标签参考统一

## 目的 / 大图景
- 统一 `docs/workflow_specs/` 目录中的文件命名风格，消除唯一的中文文件名。
- 把标签参考文档整理成更稳定、可审阅、可监管的规范文档结构。
- 同步更新文档监管规则，确保后续这类文件名和摆放位置不会再次漂移。

## 背景与定位
- 当前 `docs/workflow_specs/常用分级标签参考.md` 是该目录唯一中文文件名，和其他规范文件风格不一致。
- 这份文档是人工阅读参考，不参与运行时匹配，但它仍然指导标签命名和人工审阅，属于 workflow spec。
- 现有文档监管规则、README、source of truth 说明、prompt 合同都仍引用旧文件名。

## 工作范围
- 重命名标签参考文档为英文文件名。
- 重构该文档的标题结构和内容组织。
- 更新 `docs_review`、测试、README、workflow spec 引用和必要的历史文档链接。

## 非目标
- 不修改 `config/focus_tags.json` 的运行时标签逻辑。
- 不调整标签 canonical 命名本身。
- 不对整个 `docs/` 目录做全面搬迁，只处理与这份文档直接相关的放置与监管。

## 进度
- [x] 确定英文文件名和保留位置
- [x] 重构标签参考文档结构
- [x] 更新监管规则与测试
- [x] 更新现有引用与入口说明
- [x] 跑验证并归档计划

## 计划中的工作
- 先确认该文档是否仍应留在 `workflow_specs/`。
- 再确定英文文件名并重写文档结构。
- 接着更新 `docs_review` 和测试，让监管规则识别新文件。
- 最后同步 README、workflow spec 入口和相关说明，再跑 harness 检查。

## 具体步骤
1. 审查当前引用，判断哪些需要同步更新。
2. 重命名文件并重构内容结构，使其和其他 workflow spec 文档更一致。
3. 更新 `docs_review.py` 与 `test_docs_review.py` 的白名单和断言。
4. 更新 README、`source_of_truth_matrix`、`llm_prompt_contracts` 等引用。
5. 跑相关测试、`harness-check`，完成后归档计划。

## 发现与意外
- 这份标签参考虽然不参与运行时匹配，但它直接影响标签命名风格和人工审阅，因此更适合继续留在 `workflow_specs/`。
- 现有 `docs_review` 之前只检查“应有文件是否存在”，没有检查“已知文件是否放错目录”，这是文档治理的实际盲区。

## 决策记录
- 文件名统一改为 `hierarchical_tag_reference.md`，突出“层级标签参考表”的语义。
- 保留在 `docs/workflow_specs/`，不迁到 `user_guides/`，因为它仍然属于输出与标签治理规范。
- 文档内容补齐“目的 / 当前定位 / 数量与顺序建议”等结构，使它和其他 workflow spec 文档更一致。

## 结果与复盘
- 旧中文文件名已移除，README、workflow spec 入口、source of truth 说明和标签相关说明均已同步新文件名。
- `docs_review` 已升级为同时检查“缺失文件”和“已知文件放错目录”。
- 这轮之后，类似文档放置错误会进入 harness gate，而不再只靠人工记忆。

## 验证
- `./.venv/bin/python -m pytest tests/test_docs_review.py -q`：`4 passed`
- `./scripts/run_science_monitor.sh harness-check`：通过
