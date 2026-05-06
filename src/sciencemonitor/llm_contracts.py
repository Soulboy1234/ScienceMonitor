from __future__ import annotations

import json
import re
from datetime import date
from sqlite3 import Row

from .models import ArticleSummaryResult
from .research_preferences import UserPreferenceProfile
from .reporting_support import normalize_report_journal_name, top_theme_labels_for_schema
from .utils import clean_abstract_text, clean_title_text


ARTICLE_PROMPT_REQUIREMENTS = [
    "1. 只根据提供的标题、来源文本、期刊和主题标签判断。来源文本可能是全文整理稿、网页全文或摘要，不要假设还有别的材料。",
    "2. 中文题目要像研究者笔记里的简明概括，不要直译英文标题。",
    "3. 标签是检索系统，不是论文观点摘抄；闭集优先、实体优先、证据优先、父子压制。",
    "4. 标签只用简洁名词，优先覆盖明确研究对象、事件/驱动、仪器/数据、模型/方法、指数或应用/影响，不要写句子。",
    "5. 对象/ 只放实体、区域、系统、观测量或明确物理对象；不要输出 对象/物理机制、对象/现象、对象/空间天气、对象/评估、对象/卫星 这类抽象概述标签。",
    "6. 标签尽量采用便于统计的层级名词写法，外层在前、内层在后，例如 对象/电离层/TEC、仪器/GNSS、对象/极区/对流边界。",
    "7. 标签优先复用项目常用词表里的命名；如果确实没有合适标签，可以新造，但必须短、稳、具体、可检索。",
    "8. 常见 canonical 写法：地磁暴写 事件/磁暴；Joule heating 写 对象/极区/焦耳加热；磁力计写 仪器/磁强计；空间天气预报一般写 应用/预测，只有明确 operational/业务化证据才写 应用/业务化预报。",
    "9. 仪器/卫星 tag 只有在论文实际使用该仪器、任务或数据时才输出；参考文献、会议名、背景介绍或相关工作中偶然出现的缩写不能触发仪器 tag。",
    "10. 正文用一段中文说明：作者研究什么、用了什么数据/仪器、怎么做、来源文本明确给出的主要结果。第一句直接点明研究对象，不要先写泛泛背景。",
    "11. 如果来源文本信息不足，明确说证据有限，不要编造。",
    "12. 如果当前只拿到摘要和元数据，没有全文，必须按摘要级别概括；不要外推未明确给出的机制、应用效果或定量改进。",
    "13. 如果来源文本没有直接提到应用场景、业务价值或定量效果，不要主动补写“服务于……”或“可用于……”这类扩展。",
]

REPORT_PROMPT_REQUIREMENTS = [
    "1. 只根据提供的单篇总结、标题、期刊、标签和主题概括，不要编造全文细节。",
    "2. 输出适合科研工作周报，语气简洁、专业。",
    "3. 先客观总结这周论文的主要方向、共性、交叉点和新的切入角度，不要一开始就围绕用户研究偏好展开。",
    "4. 再单独指出与当前用户研究偏好最贴近的内容，优先提醒热层密度、卫星影响、应用影响、业务化预报，以及不局限于漠河的热层风研究。",
    "5. topic_insights 要尽量使用给定的具体主题候选，避免只写“电离层”“热层”这类宽泛分类。",
    "6. daily_suggestions 不再写泛泛建议，应优先输出值得继续关注的事件、物理过程、方法趋势或对当前工作的启发。",
    "7. preference_overview 单独对应“与当前工作相关的重点”，只写与用户当前工作直接相关的内容；背景性提及、间接应用场景或泛泛空间天气联系都不要写进去。",
    "8. work_implication 单独对应“对当前工作的可能启发”，要写具体的阅读价值、方法借鉴或后续工作启发，不要复述 preference_overview。",
]

DEEP_READ_PROMPT_REQUIREMENTS = [
    "1. 必须体现真正的研究判断，不要把摘要换个说法重复。",
    "2. “关键结果”内部固定使用这四个小标题：硬结论、次级结论、合理推论、需进一步研究讨论的结论。",
    "3. 要说明：为什么做、怎么做、最关键结果、贡献、局限、可复现性、与已有工作的关系。",
    "4. 这类深度解读大多是空间物理论文，但也可能是与空间物理主线研究相关的人工智能或其他支撑学科论文。请先判断论文所属领域，再使用该领域合适的简洁标签。",
    "5. 如果是空间物理论文，标签优先用层级标签，例如 对象/热层/密度、对象/电离层/TEC、仪器/GNSS、对象/其他行星/月球；如果是相关人工智能或交叉学科论文，则使用该领域自然、稳定、便于检索的简洁标签，不要硬套空间物理标签。",
    "6. 标签是检索系统，不是论文观点摘抄；参照单篇总结的标签风格，闭集优先、具体优先、父子压制、保守不脑补。",
    "7. 对象/ 只放实体、区域、系统、观测量或明确物理对象；不要输出 对象/物理机制、对象/能量转换、对象/过程、对象/机制、对象/现象、对象/空间天气、对象/评估、对象/卫星 这类抽象判断标签。",
    "8. 抽象机制概念能稳定归到 事件/、模型/、方法/、特征/ 时才保留，否则只写在正文判断里，不进入 tags。",
    "9. 地磁指数标签必须使用 canonical 名称：D指数、D index 或 Dst 写成 指数/Dst；K指数、K index 或 Kp 写成 指数/Kp。",
    "10. 仪器/卫星 tag 只有在论文实际使用该仪器、任务或数据时才输出；参考文献、会议名、背景介绍或相关工作中偶然出现的缩写不能触发仪器 tag。",
    "11. 常见 canonical 写法：地磁暴写 事件/磁暴；Joule heating 写 对象/极区/焦耳加热；磁力计写 仪器/磁强计；空间天气预报一般写 应用/预测，只有明确 operational/业务化证据才写 应用/业务化预报；卫星再入/轨道衰减写 应用/卫星轨道衰减。",
    "12. 如果证据边界明显，要在局限或需要人工复核中明确写出，不要编造。",
    "13. 一句话总述必须直接说明研究目标、关键数据/方法和核心结果，优先用“这篇文章针对……”“这篇文章关注……”或“作者研究的是……”，不要用“不是……而是……”这类对比式开头。",
    "14. 除专有名词、仪器名、模型名、指数名、变量名和期刊名外，正文尽量使用中文，不要大量中英混写。",
    "15. 不要输出文件名、目录归档建议、证据范围、Research question、Core claims、Method summary 等旧版区块名。",
    "16. “为什么做”和“新意与贡献”也不要写“不是……而是……”这类对比式句型，直接陈述研究目标或贡献。",
    "17. 中文语境下如需强调术语，优先使用双引号，不要用单引号。",
    "18. “为什么做”必须紧扣文章直接研究问题，不要主动外推到热层密度、卫星阻力、业务化应用等下游问题，除非论文正文明确把它们作为研究目标。",
    "19. “和我已有工作的关系”只说明与用户研究主线最直接的关系；如果联系是间接的，就明确写“间接相关”，不要主动扩展到业务化风险评估、任务规划或工程影响。",
    "20. 如果“关键结果”“新意与贡献”“局限性”包含多个要点，优先输出为 1. 2. 3. 的分条形式。",
    "21. “为什么做”优先依据 Introduction / 引言 中的研究背景、已有认识不足、争议点和作者要填补的空白来总结，不要只把研究目标压成一句短句。",
    "22. 如果某一段内部需要分点，编号必须单独换行写成 1. 2. 3.，不要把“原因。1.”、“结论。1.”这种连写放在同一行。",
]

ARTICLE_ANALYSIS_REQUIRED_FIELDS = [
    "chinese_title",
    "tags",
    "body",
    "supplement",
    "recommendation",
    "one_sentence",
]

REPORT_ANALYSIS_REQUIRED_FIELDS = [
    "overview_bullets",
    "daily_suggestions",
    "preference_overview",
    "work_implication",
    "preference_paper_indices",
    "work_implication_paper_indices",
    "topic_insights",
    "journal_insights",
]

DEEP_READ_ANALYSIS_REQUIRED_FIELDS = [
    "chinese_title",
    "tags",
    "paper_type",
    "one_sentence_overview",
    "why",
    "how",
    "key_results",
    "contribution",
    "limitations",
    "reproducibility",
    "relation",
    "final_conclusion",
    "relation_to_my_work",
    "follow_up_questions",
    "needs_manual_review",
    "knowledge_position",
]

DEEP_READ_EVIDENCE_REQUIRED_FIELDS = [
    "research_problem",
    "introduction_gap",
    "method_chain",
    "result_chain",
    "evidence_limits",
    "relation_context",
]

OLLAMA_DEEP_READ_EVIDENCE_V2_REQUIRED_FIELDS = [
    "research_problem",
    "introduction_gap",
    "method_chain",
    "hard_findings",
    "secondary_findings",
    "reasonable_inferences",
    "open_questions",
    "contribution_points",
    "limitations",
    "reproducibility_notes",
    "relation_to_my_work_evidence",
    "manual_review_points",
]


def _prepare_article_source_text_for_prompt(value: str, *, preserve_blocks: bool) -> str:
    if not preserve_blocks:
        return clean_abstract_text(value)
    lines = [re.sub(r"\s+", " ", line).strip() for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def build_article_prompt(row: Row, user_preferences: UserPreferenceProfile) -> str:
    cleaned_title = clean_title_text(str(row["title"] or ""))
    preference_lines: list[str] = []
    if user_preferences.priority_themes:
        preference_lines.append(f"用户重点：{'、'.join(user_preferences.priority_themes[:6])}。")
    if user_preferences.priority_alerts:
        preference_lines.append(f"优先提醒：{'；'.join(user_preferences.priority_alerts[:4])}。")
    source_kind = str(row["summary_source_kind"] or "").strip().lower() if "summary_source_kind" in row.keys() else ""
    full_text_kinds = {"html_full_text", "local_pdf_full_text"}
    source_label = {
        "html_full_text": "网页全文整理稿",
        "local_pdf_full_text": "本地PDF全文整理稿",
        "page_abstract": "网页摘要",
        "crossref_abstract": "Crossref摘要",
        "stored_abstract": "存量摘要",
        "openalex_abstract": "OpenAlex摘要",
        "semantic_scholar_abstract": "Semantic Scholar摘要",
        "arxiv_abstract": "arXiv摘要",
        "publisher_redirect_only": "出版商跳转页（未取得摘要或全文）",
    }.get(source_kind, "未标明")
    cleaned_source_text = _prepare_article_source_text_for_prompt(
        str(row["abstract"] or ""),
        preserve_blocks=source_kind in full_text_kinds,
    )
    max_chars = 7000 if source_kind in full_text_kinds else 2200
    if len(cleaned_source_text) > max_chars:
        suffix = "\n..." if source_kind in full_text_kinds else " ..."
        cleaned_source_text = cleaned_source_text[:max_chars].rsplit(" ", 1)[0].strip() + suffix
    if source_kind and source_kind not in full_text_kinds:
        preference_lines.append("当前仅有摘要级资料，请把结论限定在摘要明确写出的内容。")
    elif source_kind in full_text_kinds:
        preference_lines.append("当前已有全文级材料，来源文本是从全文提取的证据整理稿，请优先根据文中明确写出的研究问题、数据、方法和结果概括。")
    topic_line = row["topic_labels"].replace(chr(10), ", ")
    return "\n".join(
        [
            "请为一篇空间物理相关论文生成中文文献卡片字段。",
            "要求：",
            *ARTICLE_PROMPT_REQUIREMENTS,
            "",
            *preference_lines,
            "",
            f"期刊：{row['source_name']}",
            f"日期：{row['published_date']}",
            f"题目：{cleaned_title}",
            f"作者：{row['authors'].replace(chr(10), ', ')}",
            f"主题标签：{topic_line or '未提供'}",
            f"资料来源：{source_label}",
            f"来源文本：{cleaned_source_text or '资料缺失'}",
        ]
    )


def build_report_prompt(
    report_date: date,
    summaries: list[ArticleSummaryResult],
    user_preferences: UserPreferenceProfile,
) -> str:
    theme_candidates = top_theme_labels_for_schema(summaries, limit=10)
    blocks = [
        "请基于下面近7天已经完成的单篇空间物理论文总结，为周报生成中文分析。",
        "要求：",
        *REPORT_PROMPT_REQUIREMENTS,
        "",
        f"报告日期：{report_date.isoformat()}",
        f"论文数：{len(summaries)}",
        "",
        "当前用户研究偏好：",
    ]
    if user_preferences.research_focus:
        blocks.extend(f"- {item}" for item in user_preferences.research_focus[:6])
    if user_preferences.priority_alerts:
        blocks.append("特别提醒主题：")
        blocks.extend(f"- {item}" for item in user_preferences.priority_alerts[:8])
    if theme_candidates:
        blocks.extend(["", "候选具体主题（优先从中选择 topic_insights.label）："])
        blocks.extend(f"- {item}" for item in theme_candidates)
    blocks.extend(["", "单篇总结清单："])
    for index, summary in enumerate(summaries, start=1):
        row = summary.row
        core_body = re.sub(r"\s+", " ", str(summary.body or "")).strip()
        if len(core_body) > 220:
            core_body = core_body[:220].rsplit(" ", 1)[0].strip() + " ..."
        tags = ", ".join(summary.tags[:8])
        blocks.extend(
            [
                f"[{index}] 期刊：{row['source_name']}",
                f"题目：{row['title']}",
                f"中文概括：{summary.chinese_title}",
                f"日期：{row['published_date']}",
                f"主题：{row['topic_labels'].replace(chr(10), ', ')}",
                f"标签：{tags}",
                f"核心信息：{summary.one_sentence} {core_body}".strip(),
                "",
            ]
        )
    blocks.extend(
        [
            "输出字段提醒：",
            "1. overview_bullets 用于客观概览。",
            "2. daily_suggestions 用于值得继续关注的事件、过程或方法趋势。",
            "3. preference_overview 单独对应“与当前工作相关的重点”，只写直接相关内容。",
            "4. work_implication 单独对应“对当前工作的可能启发”，写具体启发，不要重复上一字段。",
            "5. preference_paper_indices 用整数编号返回最能支撑 preference_overview 的论文序号。",
            "6. work_implication_paper_indices 用整数编号返回最能支撑 work_implication 的论文序号。",
        ]
    )
    return "\n".join(blocks)


def build_manual_article_prompt(row: Row) -> str:
    cleaned_title = clean_title_text(str(row["title"] or ""))
    topic_line = row["topic_labels"].replace(chr(10), "、")
    lines = [
        "任务：为这篇论文生成单篇中文文献卡片。",
        "你需要先自行尝试通过 DOI、网页或题目检索论文。",
        "如果本轮用户另外上传了 PDF，请优先以 PDF 为准。",
        "如果拿不到全文，允许退回摘要级总结，但必须在 supplement 中明确写出“仅基于摘要/元数据整理”，并在 tags 中加入“信息来源/仅摘要”。",
        "不要编造正文中不存在的机制、应用价值或定量结果。",
        "",
        "检索线索：",
        f"- 题目：{cleaned_title or '未提供'}",
        f"- DOI：{row['doi'] or '未提供'}",
        f"- 网页：{row['url'] or '未提供'}",
        f"- 期刊：{row['source_name'] or '未提供'}",
        f"- 日期：{row['published_date'] or '未提供'}",
        f"- 作者：{row['authors'].replace(chr(10), ', ') or '未提供'}",
        f"- 主题标签：{topic_line or '未提供'}",
        "",
        "输出要求补充：",
        "1. chinese_title 用简洁中文研究笔记风格，不直译。",
        "2. tags 用短标签，优先层级名词；闭集优先、实体优先、证据优先，不要写 对象/物理机制、对象/现象、对象/空间天气、对象/评估、对象/卫星 这类抽象概述标签。",
        "3. body 直接写研究对象、数据/方法和关键结果，不先写泛泛背景。",
        "4. recommendation 只给与阅读价值直接相关的建议，不扩写到无证据的应用前景。",
    ]
    return "\n".join(lines)


def build_manual_report_prompt(
    report_date: date,
    summaries: list[ArticleSummaryResult],
) -> str:
    theme_candidates = top_theme_labels_for_schema(summaries, limit=10)
    lines = [
        "任务：基于下面这批论文生成一份中文科研周报。",
        "你需要优先根据 DOI、网页或题目自行检索论文；不要假设本地还有别的上下文。",
        "如果个别论文拿不到全文，可以结合摘要和公开元数据，但不要编造细节。",
        "",
        f"报告日期：{report_date.isoformat()}",
        f"论文数：{len(summaries)}",
        "",
        "周报风格要求：",
        "1. 先客观总结本周论文的方向分布、共性和新切入点，再单独写与用户当前工作最贴近的内容。",
        "2. 推荐论文部分要突出英文题目、期刊、中文题目和推荐理由。",
        "3. 主题推荐要优先落在具体科学问题，而不是宽泛分类。",
        "4. 各期刊主题汇总要写清楚该期刊本周有几篇文章分别关注什么问题。",
        "",
        "候选具体主题：",
        *([f"- {item}" for item in theme_candidates] if theme_candidates else ["- 暂无"]),
        "",
        "论文清单：",
    ]
    for index, summary in enumerate(summaries, start=1):
        row = summary.row
        lines.extend(
            [
                f"[{index}] 题目：{clean_title_text(str(row['title'] or '')) or '未提供'}",
                f"    DOI：{row['doi'] or '未提供'}",
                f"    网页：{row['url'] or '未提供'}",
                f"    期刊：{normalize_report_journal_name(row['source_name'] or row['journal_title'] or '未提供')}",
                f"    日期：{row['published_date'] or '未提供'}",
            ]
        )
    lines.extend(
        [
            "",
            "输出要求补充：",
            "1. 周报只根据你实际查到的内容写，不要把单篇不存在的结果扩成趋势。",
            "2. 重点关注真正重复出现的研究主题、事件、仪器、方法和现象。",
            "3. overview_bullets 用于客观概览，daily_suggestions 用于值得继续关注的事件、过程或工作启发。",
            "4. preference_overview 单独对应“与当前工作相关的重点”，只写直接相关内容。",
            "5. work_implication 单独对应“对当前工作的可能启发”，写具体启发，不要重复上一字段。",
            "6. preference_paper_indices 用整数编号返回最能支撑 preference_overview 的论文序号。",
            "7. work_implication_paper_indices 用整数编号返回最能支撑 work_implication 的论文序号。",
        ]
    )
    return "\n".join(lines)


def _deep_read_preference_lines(user_preferences: UserPreferenceProfile, *, lead: str) -> list[str]:
    lines: list[str] = []
    if user_preferences.research_focus:
        lines.append(lead)
        lines.extend(f"- {item}" for item in user_preferences.research_focus[:6])
    return lines


def _deep_read_related_summary_lines(related_summary: dict[str, str] | None, *, lead: str) -> list[str]:
    lines: list[str] = []
    if related_summary:
        lines.extend(
            [
                lead,
                f"- 中文概括：{related_summary.get('chinese_title', '')}",
                f"- 标签：{related_summary.get('tags', '')}",
                f"- 概括：{related_summary.get('one_sentence', '')}",
            ]
        )
    return lines


def build_deep_read_prompt(
    metadata: dict[str, str],
    full_text: str,
    related_summary: dict[str, str] | None,
    user_preferences: UserPreferenceProfile,
    evidence_context: str = "",
) -> str:
    preference_lines: list[str] = []
    if user_preferences.research_focus:
        preference_lines.append("用户研究主线仅用于补充“和我已有工作的关系”，不要改写论文本身的研究目标、关键结果或新意：")
        preference_lines.extend(f"- {item}" for item in user_preferences.research_focus[:6])

    related_lines: list[str] = []
    if related_summary:
        related_lines.extend(
            [
                "已有单篇总结可作为辅助背景：",
                f"- 中文概括：{related_summary.get('chinese_title', '')}",
                f"- 标签：{related_summary.get('tags', '')}",
                f"- 概括：{related_summary.get('one_sentence', '')}",
            ]
        )

    introduction_excerpt = _extract_introduction_excerpt(full_text, max_chars=4200)
    introduction_lines: list[str] = []
    if introduction_excerpt:
        introduction_lines.extend(["Introduction / 引言相关内容：", introduction_excerpt, ""])
    evidence_lines: list[str] = []
    if evidence_context:
        evidence_lines.extend(
            [
                "Ollama 深度解读证据预分析（仅作为辅助提纲；最终结论仍必须回到全文核对）：",
                evidence_context.strip(),
                "",
            ]
        )

    return "\n".join(
        [
            "请基于下面提供的论文全文或全文级长文本，生成一份中文深度阅读结构化结果。",
            "要求：",
            *DEEP_READ_PROMPT_REQUIREMENTS,
            "",
            *preference_lines,
            "",
            f"题目：{metadata.get('title', '')}",
            f"期刊：{metadata.get('journal', '')}",
            f"DOI：{metadata.get('doi', '')}",
            f"作者：{metadata.get('authors', '')}",
            f"发表日期：{metadata.get('published_date', '')}",
            "",
            *related_lines,
            "",
            *introduction_lines,
            *evidence_lines,
            "全文内容：",
            full_text,
        ]
    )


def build_deep_read_evidence_prompt(
    metadata: dict[str, str],
    full_text: str,
    related_summary: dict[str, str] | None,
    user_preferences: UserPreferenceProfile,
) -> str:
    preference_lines: list[str] = []
    if user_preferences.research_focus:
        preference_lines.append("用户研究主线仅用于判断“和我已有工作的关系”，不要改写论文本身的研究目标：")
        preference_lines.extend(f"- {item}" for item in user_preferences.research_focus[:6])
    related_lines: list[str] = []
    if related_summary:
        related_lines.extend(
            [
                "已有单篇总结可作为辅助背景，但不能替代全文证据：",
                f"- 中文概括：{related_summary.get('chinese_title', '')}",
                f"- 标签：{related_summary.get('tags', '')}",
                f"- 概括：{related_summary.get('one_sentence', '')}",
            ]
        )
    return "\n".join(
        [
            "这是 Ollama 深度解读的第一阶段：请只做全文证据预分析，不要写最终报告。",
            "目标是帮助第二阶段生成更接近正式深度解读的结果。",
            "要求：",
            "1. 必须基于下面的全文级文本，不要退化成摘要复述。",
            "2. 每个字段用中文写 2 到 5 条具体证据或判断，尽量包含论文中的对象、方法、因果链和证据边界。",
            "3. 不要输出 markdown 章节标题，不要输出最终报告，只输出 JSON 字段内容。",
            "4. 如果全文抽取缺损，要在 evidence_limits 中明确写出缺损位置或不确定性。",
            "",
            *preference_lines,
            "",
            f"题目：{metadata.get('title', '')}",
            f"期刊：{metadata.get('journal', '')}",
            f"DOI：{metadata.get('doi', '')}",
            f"作者：{metadata.get('authors', '')}",
            f"发表日期：{metadata.get('published_date', '')}",
            "",
            *related_lines,
            "",
            "全文内容：",
            full_text,
        ]
    )


def build_ollama_deep_read_evidence_prompt_v2(
    metadata: dict[str, str],
    full_text: str,
    related_summary: dict[str, str] | None,
    user_preferences: UserPreferenceProfile,
) -> str:
    preference_lines = _deep_read_preference_lines(
        user_preferences,
        lead="用户研究主线只用于判断“和我已有工作的关系”，不能改写论文本身的研究目标、结论或贡献：",
    )
    related_lines = _deep_read_related_summary_lines(
        related_summary,
        lead="已有单篇总结可作为辅助背景，但不能替代全文证据：",
    )
    return "\n".join(
        [
            "这是 Ollama 深度解读质量模式的第一阶段：只做全文证据预分析，不写最终报告。",
            "目标是给第二阶段提供足够密的证据包，使最终报告接近 Codex 深度解读的判断密度。",
            "要求：",
            "1. 必须基于下面的全文级文本；不要退化为摘要复述，也不要编造正文中没有的对象、定量结果或应用价值。",
            "2. 每个字段尽量写 2 到 4 条，使用具体对象、方法、因果链、证据边界和待验证点。",
            "3. hard_findings 只放论文直接支撑的结论；reasonable_inferences 只放合理外推；open_questions 只放还需要验证的判断。",
            "4. relation_to_my_work_evidence 必须区分直接相关和间接相关。除非论文直接研究热层密度、热层风、卫星阻力、业务化预报或空间环境风险，不要写“直接相关”。",
            "5. manual_review_points 要列出图表、公式、OCR/抽取缺损、定量参数或争议性解释中需要人工复核的点。",
            "6. JSON 字段名必须严格使用 schema 中的英文字段名并用双引号包裹，例如 \"open_questions\"；不要写 _open_questions、open_questions\" 或中文字段名。",
            "7. 只输出 JSON 字段内容，不要输出 Markdown 标题。",
            "",
            *preference_lines,
            "",
            f"题目：{metadata.get('title', '')}",
            f"期刊：{metadata.get('journal', '')}",
            f"DOI：{metadata.get('doi', '')}",
            f"作者：{metadata.get('authors', '')}",
            f"发表日期：{metadata.get('published_date', '')}",
            "",
            *related_lines,
            "",
            "全文级材料：",
            full_text,
        ]
    )


def build_ollama_deep_read_final_prompt_v2(
    metadata: dict[str, str],
    final_context: str,
    related_summary: dict[str, str] | None,
    user_preferences: UserPreferenceProfile,
    *,
    evidence_context: str,
) -> str:
    preference_lines = _deep_read_preference_lines(
        user_preferences,
        lead="用户研究主线仅用于“和我已有工作的关系”，不要把间接背景扩写成论文目标或硬结论：",
    )
    related_lines = _deep_read_related_summary_lines(
        related_summary,
        lead="已有单篇总结可作为辅助背景：",
    )
    return "\n".join(
        [
            "请基于下面的证据预分析和全文分段材料，生成中文深度阅读结构化结果。",
            "这是 Ollama 深度解读质量模式的最终报告阶段，目标是接近 Codex 深读的质量：判断要具体，证据边界要清楚，不能只写栏目摘要。",
            "要求：",
            *DEEP_READ_PROMPT_REQUIREMENTS,
            "23. 关键结果四类中，除非证据确实不足，每类至少写 2 条；如果不足，要在该类和需要人工复核中说明证据不足。",
            "24. 局限性至少区分论文自身局限和本次全文抽取/证据边界；可复现性要说明能复核什么、不能复现实算什么。",
            "25. “和我已有工作的关系”必须保守。若论文没有直接研究热层密度、热层风、卫星阻力、业务化预报或空间环境风险，就明确写“间接相关”。",
            "26. relation 字段必须解释本文相对已有工作的承接、差异或补充证据，不要只输出“直接相关/间接相关/弱相关/不相关”这类等级词。",
            "27. 输出字段内容要有信息密度，避免每个字段只有一句泛泛判断。",
            "",
            *preference_lines,
            "",
            f"题目：{metadata.get('title', '')}",
            f"期刊：{metadata.get('journal', '')}",
            f"DOI：{metadata.get('doi', '')}",
            f"作者：{metadata.get('authors', '')}",
            f"发表日期：{metadata.get('published_date', '')}",
            "",
            *related_lines,
            "",
            "Ollama 深度解读证据预分析 v2（必须作为主证据提纲，最终结论仍需与下方全文分段材料核对）：",
            evidence_context.strip(),
            "",
            "全文分段核对材料：",
            final_context,
        ]
    )


def build_ollama_deep_read_revision_prompt_v2(
    metadata: dict[str, str],
    current_payload: dict,
    issues: list[str],
    evidence_context: str,
    user_preferences: UserPreferenceProfile,
) -> str:
    preference_lines = _deep_read_preference_lines(
        user_preferences,
        lead="用户研究主线只用于修正“和我已有工作的关系”的边界：",
    )
    return "\n".join(
        [
            "请修订下面这份 Ollama 深度解读 JSON。只输出完整 JSON 对象，字段名必须保持 deep_read_analysis schema。",
            "修订目标：补足判断密度，修正证据边界，不改变论文本身事实。",
            "本地质量审计发现的问题：",
            *[f"- {issue}" for issue in issues],
            "",
            "修订规则：",
            "1. 如果关键结果某类少于 2 条，请根据证据包补足；证据不足时明确写“证据不足，需人工复核”。",
            "2. 如果“和我已有工作的关系”缺少直接证据，不要写“直接相关”或“高度相关”，改成“间接相关”并说明边界。",
            "3. 修复列表格式，不要输出 Python/JSON 数组字符串，例如 [\"...\"]。",
            "4. 修正 tags：标签是检索系统，不是观点摘抄；对象/ 只放实体、区域、系统、观测量或明确物理对象，不要写 对象/物理机制、对象/能量转换、对象/过程、对象/现象、对象/空间天气、对象/评估、对象/卫星；D指数/D index 写成 指数/Dst，K指数/K index/Kp 写成 指数/Kp；仪器 tag 必须有论文实际使用该仪器或数据的证据。",
            "5. 后续问题字段必须命名为 follow_up_questions，不要写 follow_up_args、follow_up 或 next_questions。",
            "6. relation 字段必须解释本文相对已有工作的承接、差异或补充证据，不要只输出“直接相关/间接相关/弱相关/不相关”这类等级词。",
            "7. JSON 字段名必须严格使用 schema 中的英文字段名并用双引号包裹。",
            "8. 保持中文科研笔记风格，不要新增模板外字段。",
            "",
            *preference_lines,
            "",
            f"题目：{metadata.get('title', '')}",
            f"期刊：{metadata.get('journal', '')}",
            f"DOI：{metadata.get('doi', '')}",
            "",
            "证据预分析 v2：",
            evidence_context.strip(),
            "",
            "当前 JSON：",
            json.dumps(current_payload, ensure_ascii=False, indent=2),
        ]
    )


def build_manual_deep_read_prompt(
    metadata: dict[str, str],
    related_summary: dict[str, str] | None,
) -> str:
    lines = [
        "任务：为这篇论文生成中文深度解读。",
        "你需要优先通过 DOI、网页或题目自行检索全文；如果本轮用户另外上传了 PDF，请优先以 PDF 为准。",
        "如果无法可靠获得全文，不要假装完成深读。请在相关字段中明确写出“未能可靠获取全文，需用户提供 PDF 后再继续”。",
        "关键结果字段内部固定分成四段：硬结论、次级结论、合理推论、需进一步研究讨论的结论。",
        "“为什么做”直接写作者要解决的问题和引言中的空白，不要写“不是……而是……”。",
        "",
        "检索线索：",
        f"- 题目：{metadata.get('title', '') or '未提供'}",
        f"- DOI：{metadata.get('doi', '') or '未提供'}",
        f"- 网页：{metadata.get('url', '') or '未提供'}",
        f"- 期刊：{metadata.get('journal', '') or '未提供'}",
        f"- 日期：{metadata.get('published_date', '') or '未提供'}",
        f"- 作者：{metadata.get('authors', '') or '未提供'}",
    ]
    if related_summary:
        lines.extend(
            [
                "",
                "已有单篇总结可作为辅助线索，但不能替代你自己查全文：",
                f"- 中文概括：{related_summary.get('chinese_title', '') or '未提供'}",
                f"- 标签：{related_summary.get('tags', '') or '未提供'}",
                f"- 一句话总结：{related_summary.get('one_sentence', '') or '未提供'}",
            ]
        )
    return "\n".join(lines)


def build_deep_read_schema() -> dict:
    return {
        "name": "deep_read_analysis",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": DEEP_READ_ANALYSIS_REQUIRED_FIELDS,
            "properties": {
                "chinese_title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 10},
                "paper_type": {"type": "string"},
                "one_sentence_overview": {"type": "string"},
                "why": {"type": "string"},
                "how": {"type": "string"},
                "key_results": {"type": "string"},
                "contribution": {"type": "string"},
                "limitations": {"type": "string"},
                "reproducibility": {"type": "string"},
                "relation": {"type": "string"},
                "final_conclusion": {"type": "string"},
                "relation_to_my_work": {"type": "string"},
                "follow_up_questions": {"type": "string"},
                "needs_manual_review": {"type": "string"},
                "knowledge_position": {"type": "string"},
            },
        },
    }


def build_deep_read_evidence_schema() -> dict:
    return {
        "name": "deep_read_evidence",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": DEEP_READ_EVIDENCE_REQUIRED_FIELDS,
            "properties": {
                "research_problem": {"type": "string"},
                "introduction_gap": {"type": "string"},
                "method_chain": {"type": "string"},
                "result_chain": {"type": "string"},
                "evidence_limits": {"type": "string"},
                "relation_context": {"type": "string"},
            },
        },
    }


def build_ollama_deep_read_evidence_schema_v2() -> dict:
    text_or_items = {
        "oneOf": [
            {"type": "string"},
            {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
        ]
    }
    return {
        "name": "ollama_deep_read_evidence_v2",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": OLLAMA_DEEP_READ_EVIDENCE_V2_REQUIRED_FIELDS,
            "properties": {field: text_or_items for field in OLLAMA_DEEP_READ_EVIDENCE_V2_REQUIRED_FIELDS},
        },
    }


def build_article_schema() -> dict:
    return {
        "name": "article_analysis",
        "schema": {
            "type": "object",
            "properties": {
                "chinese_title": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 8,
                },
                "body": {"type": "string"},
                "supplement": {"type": "string"},
                "recommendation": {"type": "string"},
                "one_sentence": {"type": "string"},
            },
            "required": ARTICLE_ANALYSIS_REQUIRED_FIELDS,
            "additionalProperties": False,
        },
    }


def build_report_schema(summaries: list[ArticleSummaryResult]) -> dict:
    journals = sorted({normalize_report_journal_name(summary.row["source_name"] or summary.row["journal_title"]) for summary in summaries})[:12]
    labels = top_theme_labels_for_schema(summaries, limit=12)
    return {
        "name": "report_analysis",
        "schema": {
            "type": "object",
            "properties": {
                "overview_bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 4,
                },
                "daily_suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 4,
                },
                "preference_overview": {
                    "type": "string",
                },
                "work_implication": {
                    "type": "string",
                },
                "preference_paper_indices": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": len(summaries) if summaries else 1},
                    "maxItems": 4,
                },
                "work_implication_paper_indices": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": len(summaries) if summaries else 1},
                    "maxItems": 4,
                },
                "topic_insights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "enum": labels or ["暂无"]},
                            "summary": {"type": "string"},
                        },
                        "required": ["label", "summary"],
                        "additionalProperties": False,
                    },
                    "maxItems": min(6, len(labels)) if labels else 1,
                },
                "journal_insights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "journal": {"type": "string", "enum": journals or ["暂无"]},
                            "summary": {"type": "string"},
                        },
                        "required": ["journal", "summary"],
                        "additionalProperties": False,
                    },
                    "maxItems": min(10, len(journals)) if journals else 1,
                },
            },
            "required": REPORT_ANALYSIS_REQUIRED_FIELDS,
            "additionalProperties": False,
        },
    }


def _extract_introduction_excerpt(text: str, *, max_chars: int = 4200) -> str:
    source = str(text or "").strip()
    if not source:
        return ""
    patterns = [
        r"(?ims)^(?:1\.\s*Introduction|Introduction)\s*$",
        r"(?ims)^(?:I\.\s*Introduction)\s*$",
    ]
    start_match = None
    for pattern in patterns:
        start_match = re.search(pattern, source)
        if start_match:
            break
    if not start_match:
        return ""
    tail = source[start_match.end():]
    end_patterns = [
        r"(?im)^\d+\.\s+[A-Z][A-Za-z0-9,()\\-–/& ]{2,90}$",
        r"(?im)^(Methods?|Data|Results?|Discussion|Conclusions?|Summary)\b",
    ]
    end_index = len(tail)
    for pattern in end_patterns:
        match = re.search(pattern, tail)
        if match:
            end_index = min(end_index, match.start())
    excerpt = clean_abstract_text(tail[:end_index])
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rsplit(" ", 1)[0].strip() + " ..."
    return excerpt.strip()
