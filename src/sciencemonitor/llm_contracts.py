from __future__ import annotations

import re
from datetime import date
from sqlite3 import Row

from .models import ArticleSummaryResult
from .research_preferences import UserPreferenceProfile
from .utils import clean_abstract_text, clean_title_text


ARTICLE_PROMPT_REQUIREMENTS = [
    "1. 只根据提供的标题、来源文本、期刊和主题标签判断。来源文本可能是全文整理稿、网页全文或摘要，不要假设还有别的材料。",
    "2. 中文题目要像研究者笔记里的简明概括，不要直译英文标题。",
    "3. 标签只用简洁名词，优先覆盖研究对象、事件/驱动、仪器/数据、模型/方法或应用/影响，不要写句子。",
    "4. 标签尽量采用便于统计的层级名词写法，外层在前、内层在后，例如 电离层/TEC、仪器/GNSS、极区/对流边界。",
    "5. 标签优先复用项目常用词表里的命名；如果确实没有合适标签，可以新造，但要保持短、稳、可检索。",
    "6. 正文用一段中文说明：作者研究什么、用了什么数据/仪器、怎么做、来源文本明确给出的主要结果。第一句直接点明研究对象，不要先写泛泛背景。",
    "7. 如果来源文本信息不足，明确说证据有限，不要编造。",
    "8. 如果当前只拿到摘要和元数据，没有全文，必须按摘要级别概括；不要外推未明确给出的机制、应用效果或定量改进。",
    "9. 如果来源文本没有直接提到应用场景、业务价值或定量效果，不要主动补写“服务于……”或“可用于……”这类扩展。",
]

REPORT_PROMPT_REQUIREMENTS = [
    "1. 只根据提供的单篇总结、标题、期刊、标签和主题概括，不要编造全文细节。",
    "2. 输出适合科研工作周报，语气简洁、专业。",
    "3. 概览和建议要突出真正值得关注的主题、事件、仪器、方法或趋势。",
    "4. 需要结合当前用户研究偏好，优先提醒热层密度、卫星影响、应用影响、业务化预报，以及不局限于漠河的热层风研究。",
]

DEEP_READ_PROMPT_REQUIREMENTS = [
    "1. 必须体现真正的研究判断，不要把摘要换个说法重复。",
    "2. “关键结果”内部固定使用这四个小标题：硬结论、次级结论、合理推论、需进一步研究讨论的结论。",
    "3. 要说明：为什么做、怎么做、最关键结果、贡献、局限、可复现性、与已有工作的关系。",
    "4. 这类深度解读大多是空间物理论文，但也可能是与空间物理主线研究相关的人工智能或其他支撑学科论文。请先判断论文所属领域，再使用该领域合适的简洁标签。",
    "5. 如果是空间物理论文，标签优先用层级标签，例如 热层/密度、电离层/TEC、仪器/GNSS、其他行星/月球；如果是相关人工智能或交叉学科论文，则使用该领域自然、稳定、便于检索的简洁标签，不要硬套空间物理标签。",
    "6. 如果证据边界明显，要在局限或需要人工复核中明确写出，不要编造。",
    "7. 一句话总述必须直接说明研究目标、关键数据/方法和核心结果，优先用“这篇文章针对……”“这篇文章关注……”或“作者研究的是……”，不要用“不是……而是……”这类对比式开头。",
    "8. 除专有名词、仪器名、模型名、指数名、变量名和期刊名外，正文尽量使用中文，不要大量中英混写。",
    "9. 不要输出文件名、目录归档建议、证据范围、Research question、Core claims、Method summary 等旧版区块名。",
    "10. “为什么做”和“新意与贡献”也不要写“不是……而是……”这类对比式句型，直接陈述研究目标或贡献。",
    "11. 中文语境下如需强调术语，优先使用双引号，不要用单引号。",
    "12. “为什么做”必须紧扣文章直接研究问题，不要主动外推到热层密度、卫星阻力、业务化应用等下游问题，除非论文正文明确把它们作为研究目标。",
    "13. “和我已有工作的关系”只说明与用户研究主线最直接的关系；如果联系是间接的，就明确写“间接相关”，不要主动扩展到业务化风险评估、任务规划或工程影响。",
    "14. 如果“关键结果”“新意与贡献”“局限性”包含多个要点，优先输出为 1. 2. 3. 的分条形式。",
    "15. “为什么做”优先依据 Introduction / 引言 中的研究背景、已有认识不足、争议点和作者要填补的空白来总结，不要只把研究目标压成一句短句。",
    "16. 如果某一段内部需要分点，编号必须单独换行写成 1. 2. 3.，不要把“原因。1.”、“结论。1.”这种连写放在同一行。",
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
    blocks.extend(["", "单篇总结清单："])
    for index, summary in enumerate(summaries, start=1):
        row = summary.row
        blocks.extend(
            [
                f"[{index}] 期刊：{row['source_name']}",
                f"题目：{row['title']}",
                f"中文概括：{summary.chinese_title}",
                f"日期：{row['published_date']}",
                f"主题：{row['topic_labels'].replace(chr(10), ', ')}",
                f"标签：{', '.join(summary.tags)}",
                f"一句话总结：{summary.one_sentence}",
                f"正文总结：{summary.body}",
                f"补充信息：{summary.supplement}",
                "",
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
        "2. tags 用短标签，优先层级名词；没有合适标签时可以谨慎新造。",
        "3. body 直接写研究对象、数据/方法和关键结果，不先写泛泛背景。",
        "4. recommendation 只给与阅读价值直接相关的建议，不扩写到无证据的应用前景。",
    ]
    return "\n".join(lines)


def build_manual_report_prompt(
    report_date: date,
    summaries: list[ArticleSummaryResult],
) -> str:
    lines = [
        "任务：基于下面这批论文生成一份中文科研周报。",
        "你需要优先根据 DOI、网页或题目自行检索论文；不要假设本地还有别的上下文。",
        "如果个别论文拿不到全文，可以结合摘要和公开元数据，但不要编造细节。",
        "",
        f"报告日期：{report_date.isoformat()}",
        f"论文数：{len(summaries)}",
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
                f"    期刊：{row['source_name'] or '未提供'}",
                f"    日期：{row['published_date'] or '未提供'}",
            ]
        )
    lines.extend(
        [
            "",
            "输出要求补充：",
            "1. 周报只根据你实际查到的内容写，不要把单篇不存在的结果扩成趋势。",
            "2. 重点关注真正重复出现的研究主题、事件、仪器、方法和现象。",
            "3. overview_bullets 和 daily_suggestions 用简洁可执行表述。",
        ]
    )
    return "\n".join(lines)


def build_deep_read_prompt(
    metadata: dict[str, str],
    full_text: str,
    related_summary: dict[str, str] | None,
    user_preferences: UserPreferenceProfile,
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
            "全文内容：",
            full_text,
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
    journals = sorted({str(summary.row["source_name"]) for summary in summaries})[:12]
    labels = sorted(
        {label for summary in summaries for label in str(summary.row["topic_labels"]).split("\n") if label}
    )[:12]
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
