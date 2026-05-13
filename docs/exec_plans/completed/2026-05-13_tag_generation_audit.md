# 计划：2026-05-13_tag_generation_audit

## 目的 / 大图景
- 审核这次周报后所有文章总结中的 tag 输出，识别异常 tag、模糊 tag、与正式 tag 有意义重合的 pending tag，以及未被正常记录的 tag。
- 将发现落实为 tag 生成、归一化和审查规则的改进，避免后续单篇总结继续产生同类问题。

## 背景与定位
- 用户刚重新运行了周报和文章总结链路，`config/pending_tags.json` 与 `config/tag/pending_tags.md` 已出现新的未提交变更。
- 本轮不只做一次性清理，需要把问题沉淀到 prompt、归一化、治理检查或测试护栏中。

## 工作范围
- 审计输出库中的文章总结 tag 与 pending tag 记录。
- 核对 `config/tag/formal_tags.md`、`config/focus_tags.json`、`config/pending_tags.json` 和 tag 治理代码。
- 必要时修改 tag 生成 / 归一化 / 审查规则、相关文档和测试。

## 非目标
- 不删除用户输出库中的文章总结文件。
- 不把所有专业细分 pending tag 强行转正。
- 不改变当前监测期刊范围、抓取流程或周报主体结构。

## 进度
- [x] 建立上下文并定位输出根目录与文章总结文件
- [x] 审计文章总结 tag、pending 记录和 formal 重合关系
- [x] 制定并落地生成与审查规则修正
- [x] 运行针对性验证和必要 gate
- [x] 归档结果到 completed 计划

## 计划中的工作
- 先读取项目启动文档、tag source of truth 和当前 dirty diff。
- 再用结构化脚本扫描所有文章总结 Markdown，比较输出 tag、formal tag 和 pending tag。
- 将发现按“应归一化 / 应拒收 / 可保留 pending / 记录异常”分类。
- 修改运行时规则、prompt 或审核层，并补测试保护典型问题。
- 跑定向测试、tag 候选刷新或 harness gate，确认规则能约束后续输出。

## 具体步骤
1. 解析运行时 output_root，收集所有文章总结 Markdown 的 tag 字段。
2. 对比正式 canonical tag 与 pending tag，识别前缀重复、同义重复、层级误分和过宽泛词。
3. 阅读 tag 生成、归一化、pending 记录和审核代码，定位规则缺口。
4. 实施规则修正并补充测试样例。
5. 运行验证命令，更新本计划结果并归档。

## 发现与意外
- 运行时输出根目录来自 `config/local.paths.json`，指向本机 Obsidian 输出库；本轮只处理自动输出与 tag 治理，不删除输出文件。
- 初始审计覆盖 `auto/article_summaries/` 下 118 篇文章总结，共 553 次 tag 使用、281 个唯一 tag。
- 使用项目解析器解码 Obsidian tag 后，文章总结中未发现“非正式 tag 未进入 pending 记录”的问题；此前看似未记录的 `O＋/O2＋` 是 Obsidian 安全字符编码造成，解析层能正常解码为 `O+ / O2+`。
- 初始审核发现 2 篇文章总结会被旧规则误删 `对象/电离层/TEC`，原因是 `\btec\b` 不能覆盖 `TEC` 与中文字符贴连的场景。
- 与 formal tag 重合或根类错误的主要问题包括：`仪器/TIE-GCM`、`事件/SC`、`事件/HILDCAA`、`对象/热层/水平风`、`对象/热层/一氧化氮`、`对象/地磁场`、`对象/电网`、`对象/电离层/F层/F2层/F层峰高`、`对象/金星/感应磁层`、`对象/水星/磁尾`、`对象/磁尾/O+ / O2+`、`对象/高能粒子/相对论性电子`。
- 宽泛或模糊方法词主要包括：`方法/交叉对比`、`方法/趋势拟合`、`方法/观测基准`、`方法/模型验证`、`方法/模式识别`、`方法/数据增强`、`方法/MHD模拟`、`方法/PIC模拟`、`模型/MHD模拟`。
- 落地规则后，文章总结复扫从 167 个非正式唯一 tag 收敛到 129 个，审核层建议改写的文章总结从 36 篇降为 0 篇。

## 决策记录
- 不把所有低频专业 pending tag 直接转正；本轮只归并明显错类、明显与 formal 重合、或过宽泛且已有 formal 承接的 tag。
- `事件/日食`、`模型/E-CHAIM` 等仍保留为 pending，因为它们有明确检索意义但尚未进入 formal；`对象/日食` 和 `方法/E-CHAIM` 会归一到这些更稳定写法。
- `TEC` 中文贴连问题在审核正则层修复，而不是靠输出层人工改写，避免以后标题或正文中出现 `GNSS-TEC约束`、`载波相位TEC的...` 时被误删。
- 对当前输出库使用项目内正式重审命令 `tag-candidates --reconcile-output --limit 0`，让本次文章总结与深度解读自动输出同步受新规则约束，并刷新 pending tag 报告与索引。

## 结果与复盘
- 已修改 tag 归一化、pending 候选治理和单篇总结 prompt 规则。
- 已补充回归测试，覆盖中文贴连 `TEC`、错类 tag 归并、宽泛方法词收束、模型根类改写和 pending 根类改写。
- 已执行自动输出 tag 重审：扫描 226 个自动输出文件，改写 43 个，修复索引链接 5 个，刷新 `config/pending_tags.json` 与 `config/tag/pending_tags.md`。
- 完成后复扫 118 篇文章总结：`REVIEW_ISSUES=0`，`UNRECORDED=0`。

## 验证
- `git diff --check`
- `./.venv/bin/python -m pytest tests/test_tag_review.py tests/test_llm.py -q`：95 passed
- `./.venv/bin/python -m pytest -q`：365 passed
- `./scripts/run_science_monitor.sh tag-candidates --reconcile-output --limit 0`
- `./scripts/run_science_monitor.sh harness-check --profile output`：overall=ok
