# 计划：2026-04-14_标签审核agent与auto重审

## 目的 / 大图景
- 建立一个稳定的标签审核 agent，把模型生成的自由标签尽可能收敛到正式标签体系。
- 让标签治理从“事后人工清洗”前移到“生成后立即审核”，减少 pending 标签噪声。
- 用同一套规则重新整理现有 `auto` 输出，统一历史和未来的标签风格。

## 背景与定位
- 当前 `formal_tags.md` 已形成较稳定的分层风格，但 `auto` 输出仍存在大量自由标签。
- 现有 `tags.py` 主要做归一化和 pending 记录，缺少“尽量映射 formal、只把无法覆盖项留给 pending”的审核层。
- 这轮工作需要同时修改标签执行层、生成链路、harness 与历史输出。

## 工作范围
- `src/sciencemonitor/tags.py`
- `src/sciencemonitor/tag_governance.py`
- 新增或调整标签审核模块
- `src/sciencemonitor/article_summaries.py`
- `src/sciencemonitor/deep_reads.py`
- `src/sciencemonitor/harness.py`
- `tests/` 下标签治理与输出相关测试
- `config/tag/pending_tags.md` 与 `config/pending_tags.json`
- `auto` 输出目录下文章总结与深度解读标签

## 非目标
- 这轮不重写 formal 标签体系本身。
- 这轮不修改 `manual` 输出文件。
- 这轮不处理与标签无关的周报正文质量问题。

## 进度
- [x] 写入计划并核对现状
- [x] 分析 formal 标签风格与现有生成链路
- [x] 实现标签审核 agent
- [x] 接入单篇总结、深度解读与 pending 记录
- [x] 纳入 harness 并补测试
- [x] 重审 `auto` 输出并刷新 pending

## 计划中的工作
- 先把 formal 标签的结构特征提炼成可执行规则。
- 再在生成后的归一化阶段增加“审核 / 归并 / 风格化”步骤。
- 让 pending 只保留 formal 无法覆盖的新标签。
- 用同一套审核逻辑批量重写现有 `auto` 标签。
- 最后跑 harness、测试和 pending 刷新，确认治理闭环成立。

## 具体步骤
1. 审读 `formal_tags.md`、`focus_tags.json`、`tags.py`、`article_summaries.py`、`deep_reads.py` 与现有 pending。
2. 提炼 formal 风格规则：优先级、父类补全、根节点约束、别名吸收、保留 pending 的边界。
3. 新增标签审核模块，并提供单篇 / 深读实时调用接口和批量重审接口。
4. 修改生成链路，让模型原始标签先经过审核 agent，再写入输出与 pending。
5. 扩展 harness，让其检查“可映射 formal 却未映射”的漂移。
6. 用新逻辑重审 `auto` 输出，刷新 pending，并记录残余未覆盖标签。
7. 跑测试、`harness-check`、必要的标签治理命令，最后归档计划。

## 发现与意外
- `tags.py` 原先对正式标签和 alias 用的是子串匹配，formal 根标签会误吞掉更长的未知标签；这会把 `对象/电离层/电子密度` 错误压成 `对象`。
- 现有 `focus_tags.json` 中很多正式标签没有英文 `patterns`，仅靠原始 `infer_preferred_tags_from_text` 很难覆盖英文题目和摘要，因此补了一层轻量英文规则推断。
- `golden` 基线中的单篇总结和深度解读标签行因 formal 化发生了预期漂移，需要在代码稳定后刷新 fixture。

## 决策记录
- 不把审核逻辑直接塞进 `tag_governance.py`，而是新增独立 `tag_review.py`，让生成链路、历史重审和 harness 审查共用同一实现。
- 正式标签的 source of truth 仍然保持 `formal_tags.md` + `focus_tags.json`，审核 agent 只负责“尽量归并 formal、剩余项风格化为 pending”。
- `llm.py` 的标签标准化也接入审核 agent，避免缓存层继续保留旧风格标签。
- 历史 `auto` 标签重审完成后立即刷新 pending，再以 golden fixture 更新作为正式收口，而不是让 harness 长期背着已知漂移。

## 结果与复盘
- 新增 `src/sciencemonitor/tag_review.py`，形成确定性标签审核层：formal 归并、上下文分支选择、pending 风格化、auto 批量重审和标签输出审查都走同一套逻辑。
- 单篇总结、深度解读和 `llm` 标签标准化已全部接入这套审核层，未来新生成标签会优先落到 formal 风格。
- `auto` 输出已完成一次全量重审：扫描 126 个文件，重写 114 个文件，重审后 `tag_output_review` 问题数降为 0。
- 文档、source-of-truth 矩阵和 harness 总览已同步；golden fixture 已刷新到新的 formal 标签风格。
- 当前仍保留 407 个未正式收录的 pending 标签，这部分是 formal 还覆盖不到的范围，后续继续人工审阅即可。

## 验证
- `./.venv/bin/python -m pytest -q`
- `./scripts/run_science_monitor.sh harness-check`
