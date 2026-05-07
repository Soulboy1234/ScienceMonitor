# 计划：2026-05-08_test_harness_second_pass_cleanup

## 目的 / 大图景
- 在上一轮 harness 分层基础上做第二轮积极清理：保留高价值 tag 输出复审，移除旧 tag candidates 兼容层，降低 UI 检查脆弱度，并压缩深度阅读慢测试。

## 背景与定位
- `tag_output_review` 仍负责文章总结、深度阅读和周报输出 tag 复审，但只应在 output/release 或显式参数下运行。
- 旧 `sciencemonitor.tag_candidates` 只是 re-export 兼容层；当前 source of truth 已是 `config/pending_tags.json` 与 `config/tag/pending_tags.md`。
- UI 检查仍有展示文案和精确 CSS 字符串绑定。
- 深读模板相关测试走完整 `run_deep_read()`，在全量测试慢项中排名靠前。

## 工作范围
- 修改 tag governance 入口、CLI 导入、测试命名和相关文档。
- 为 UI 设置页和面板补稳定 data attribute，并调整 UI review 测试。
- 重写深读模板测试为模板/渲染层测试。
- 保留本机 `data/tag_candidates.json` 运行态文件，不删除用户数据。

## 非目标
- 不改变 tag 审核算法语义。
- 不把私人输出库扫描放回 default profile。
- 不删除核心业务单测或真实案例评测。
- 不迁移、移动或删除运行态 `data/tag_candidates.json`。

## 进度
- [x] 建立活跃 ExecPlan
- [x] 清理 tag candidates 兼容层和旧迁移测试
- [x] 加固 `tag_output_review` 覆盖测试
- [x] 降低 UI review 文案/CSS 绑定
- [x] 压缩深读模板慢测试
- [x] 更新治理文档、运行验证并归档

## 计划中的工作
- 先收口 tag governance 代码入口和测试文件命名。
- 再补 tag output profile 的覆盖回归。
- 然后调整 UI 语义 hook 和 review 检查。
- 最后重写慢测试、同步文档并验证。

## 具体步骤
1. 将 CLI 从 `tag_candidates` re-export 改为直接导入 `tag_governance`。
2. 删除旧 re-export 模块和 legacy pending 迁移路径，测试改为当前 pending source of truth。
3. 保留 `tag-candidates` CLI 命令名与输出行为。
4. 给 UI tag 管理入口与关键面板补稳定 data attribute，review 逻辑改查 hook。
5. 将深读模板顺序/缺字段测试改为调用模板加载和渲染层。
6. 运行定向测试、profile gate、entropy、harness audit 和全量测试。

## 发现与意外
- 本机 `data/tag_candidates.json` 仍存在，按计划保留但不再由源码自动迁移。
- `config_ui_page_sections.py` 因新增 hook 一度超过 entropy 行数预算；通过压缩写法恢复预算，没有放宽 budget。
- UI profile 首次失败是 Playwright Chromium 缓存缺失；已用 `./.venv/bin/python -m playwright install chromium` 安装到本机缓存后复跑通过。

## 决策记录
- 旧 `data/tag_candidates.json` 保留但忽略，不作为运行时 source of truth。
- `tag_output_review` 继续只在 output/release 或显式参数下运行。

## 结果与复盘
- 已移除旧 `sciencemonitor.tag_candidates` re-export 模块，CLI 保留 `tag-candidates` 命令并直接使用 `tag_governance`。
- 已将 `tests/test_tag_candidates.py` 收束为 `tests/test_tag_governance.py`，移除旧 `data/tag_candidates.json` 迁移用例，保留当前 pending source-of-truth 行为测试。
- 已补 `tag_output_review` 三类输出覆盖测试，确认文章总结、深度解读和周报输出都在 output review 范围内。
- 已为 UI 关键面板和 tag 管理入口补稳定 data attribute，functional/visual review 改为检查语义 hook。
- 已将两个深读模板慢测试改到模板加载/渲染层；全量 durations 中不再出现这两个模板测试。
- 本计划已完成并归档到 `docs/exec_plans/completed/`。

## 验证
- `./.venv/bin/python -m pytest -q tests/test_tag_governance.py tests/test_tag_governance_review.py tests/test_tag_review.py`
- `./.venv/bin/python -m pytest -q tests/test_config_ui.py tests/test_config_ui_review.py tests/test_config_ui_functional_review.py tests/test_config_ui_visual_review.py`
- `./.venv/bin/python -m pytest -q tests/test_deep_reads.py tests/test_golden_eval.py`
- `./scripts/run_science_monitor.sh harness-check --profile output`
- `./scripts/run_science_monitor.sh harness-check --profile ui`
- `./scripts/run_science_monitor.sh harness-check --profile default`
- `./scripts/run_science_monitor.sh entropy-check`
- `./scripts/run_science_monitor.sh harness-audit --no-write-report`
- `./.venv/bin/python -m pytest -q --durations=30`
- `git diff --check`
