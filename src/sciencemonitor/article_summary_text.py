from __future__ import annotations

import re
from pathlib import Path
from sqlite3 import Row

from .article_summary_markdown import clean_text, dedupe
from .article_summary_meta import (
    abbreviate_journal_name,
    build_doi_url,
    build_filename as build_filename_for_title,
    build_filename_from_chinese as build_filename_from_title,
    display_title,
    first_author_label,
    format_authors_apa,
    get_override,
    parse_authors,
    sentence_case_title,
    topic_labels,
)
from .llm import ArticleAnalysis
from .models import ArticleSummaryResult
from .tags import clean_tag_text, group_tags, infer_preferred_tags_from_text, normalize_tags
from .utils import clean_title_text

INVALID_OUTPUT_SNIPPETS = ("oops", "todo", "tbd", "placeholder")
PLACEHOLDER_TITLES = {"文献内容概括待补充", "相关研究"}
GENERIC_SENTENCE_FRAGMENTS = (
    "文章围绕相关空间物理问题",
    "利用相关数据分析了关键物理量的变化特征",
    "适合放入今日重点跟进列表",
    "与当前主题方向相关",
    "摘要显示，该研究给出了与上述问题相关的主要结果和解释",
)
ABSTRACT_ONLY_TAG = "信息来源/仅摘要"
ABSTRACT_ONLY_NOTICE = "当前总结仅基于摘要和元数据生成，未获得全文，结论需按摘要级别理解。"
ABSTRACT_ONLY_RE = re.compile(r"仅基于摘要|仅基于论文题目页|仅基于题目页|仅基于元数据|未获取到可靠的全文|未获得全文")

TOPIC_TO_TAG = {
    "电离层": "电离层",
    "热层": "热层",
    "日地耦合": "日地耦合",
    "低层大气波动上传": "重力波/潮汐",
    "磁层-电离层-热层耦合": "磁层-电离层耦合",
    "行星际环境驱动": "太阳风/高速流",
    "空间天气": "空间天气",
    "行星空间环境": "其他行星/行星综合",
}

TAG_GROUP_IDS = (
    "research_object",
    "event_driver",
    "index_control",
    "instrument_data",
    "model_method",
    "result_feature",
    "application_impact",
    "status",
)

FULL_TEXT_SOURCE_KINDS = {"html_full_text", "local_pdf_full_text"}


def sanitize_generation_text(text: str) -> str:
    cleaned = clean_title_text(str(text or ""))
    cleaned = re.sub(r"(?i)\boops\b.*$", "", cleaned).strip()
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"([。；])\1+", r"\1", cleaned)
    return cleaned.strip()


def sanitize_tag(tag: str) -> str:
    return clean_tag_text(sanitize_generation_text(tag))


def sanitize_tags(
    tags: list[str],
    *,
    root: Path | None = None,
    max_tags: int = 14,
    context: str = "",
    record_candidates: bool = False,
) -> list[str]:
    return normalize_tags(
        tags,
        root=root,
        max_tags=max_tags,
        context=context,
        record_candidates=record_candidates,
    )


def prefer_more_specific_tags(tags: list[str]) -> list[str]:
    refined: list[str] = []
    for tag in tags:
        if any(other != tag and other.startswith(tag + "/") for other in tags):
            continue
        refined.append(tag)
    return refined


def is_placeholder_title(text: str) -> bool:
    cleaned = sanitize_generation_text(text)
    return not cleaned or cleaned in PLACEHOLDER_TITLES


def is_generic_sentence(text: str) -> bool:
    cleaned = sanitize_generation_text(text)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if any(snippet in lowered for snippet in INVALID_OUTPUT_SNIPPETS):
        return True
    return any(fragment in cleaned for fragment in GENERIC_SENTENCE_FRAGMENTS)


def build_safe_one_sentence(row: Row, tags: list[str]) -> str:
    focus = "、".join(tags[:2]) if tags else "空间物理"
    return f"该文主要涉及{focus}，建议结合原标题和摘要确认其最核心的结论与方法。"


def build_safe_recommendation(row: Row, tags: list[str]) -> str:
    focus = "、".join(tags[:2]) if tags else "当前监控主题"
    return f"如果你在跟踪{focus}，这篇文章值得先看摘要、数据来源和方法部分。"


def build_safe_body(row: Row, tags: list[str]) -> str:
    focus = "、".join(tags[:3]) if tags else "相关空间物理问题"
    return f"这篇文章的标题和摘要信息不足以支持更细的中文概括。根据现有元数据，它主要涉及{focus}，建议后续结合全文继续确认具体数据、方法和结论。"


def validate_summary_fields(
    row: Row,
    chinese_title: str,
    tags: list[str],
    body: str,
    supplement: str,
    recommendation: str,
    one_sentence: str,
    *,
    root: Path | None = None,
    candidate_context: str = "",
) -> tuple[str, list[str], str, str, str, str]:
    cleaned_tags = sanitize_tags(tags, root=root, context=candidate_context, record_candidates=bool(root))
    if not cleaned_tags:
        cleaned_tags = sanitize_tags(get_focus_tags(row, analysis=None, root=root), root=root)

    cleaned_title = sanitize_generation_text(chinese_title)
    if is_placeholder_title(cleaned_title):
        cleaned_title = sanitize_generation_text(build_chinese_title(row, analysis=None, root=root))
    if is_placeholder_title(cleaned_title):
        cleaned_title = "标题与摘要信息待补充"

    cleaned_body = sanitize_generation_text(body)
    if is_generic_sentence(cleaned_body):
        cleaned_body = build_safe_body(row, cleaned_tags)

    cleaned_supplement = sanitize_generation_text(supplement)
    if not cleaned_supplement:
        cleaned_supplement = build_supplement_text(row, analysis=None, root=root)
    cleaned_supplement = normalize_summary_supplement(row, cleaned_supplement)
    if supplement_claims_abstract_only(cleaned_supplement):
        cleaned_tags = sanitize_tags(cleaned_tags + [ABSTRACT_ONLY_TAG], root=root, context=candidate_context, record_candidates=bool(root))

    cleaned_recommendation = sanitize_generation_text(recommendation)
    if is_generic_sentence(cleaned_recommendation):
        cleaned_recommendation = build_safe_recommendation(row, cleaned_tags)

    cleaned_one_sentence = sanitize_generation_text(one_sentence)
    if is_generic_sentence(cleaned_one_sentence):
        cleaned_one_sentence = build_safe_one_sentence(row, cleaned_tags)

    return (
        cleaned_title,
        cleaned_tags,
        cleaned_body,
        cleaned_supplement,
        cleaned_recommendation,
        cleaned_one_sentence,
    )


def article_summary_quality_score(summary: ArticleSummaryResult) -> int:
    score = 0
    if not is_placeholder_title(summary.chinese_title):
        score += 1
    if len(sanitize_tags(summary.tags)) >= 3:
        score += 1
    if not is_generic_sentence(summary.body):
        score += 1
    if not is_generic_sentence(summary.one_sentence):
        score += 1
    return score


def build_note_title(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    return build_note_title_from_chinese(row, build_chinese_title(row, analysis=analysis, root=root))


def build_note_title_from_chinese(row: Row, chinese_title: str) -> str:
    first_author = first_author_label(row["authors"])
    year = str(row["published_date"])[:4]
    journal = abbreviate_journal_name(row["source_name"])
    return f"{first_author} {year} - {journal} - {sanitize_generation_text(chinese_title)}"


def _empty_tag_groups() -> dict[str, list[str]]:
    return {key: [] for key in TAG_GROUP_IDS}


def _tag_phrase_for_sentence(tag: str) -> str:
    parts = [item for item in tag.split("/") if item]
    if not parts:
        return tag
    if parts[0] in {"仪器", "指数", "模型", "建模", "特征", "应用", "状态"} and len(parts) > 1:
        return "/".join(parts[1:])
    if parts[0] == "其他行星" and len(parts) > 1:
        return parts[-1]
    return tag


def _tag_phrase_for_title(tag: str) -> str:
    parts = [item for item in tag.split("/") if item]
    if not parts:
        return tag
    if parts[0] in {"仪器", "指数", "模型", "建模", "特征", "应用", "状态"} and len(parts) > 1:
        return "".join(parts[1:])
    if parts[0] == "其他行星" and len(parts) > 1:
        return parts[-1]
    return "".join(parts)


def _tag_text(tags: list[str], *, title_mode: bool = False) -> str:
    if not tags:
        return ""
    formatter = _tag_phrase_for_title if title_mode else _tag_phrase_for_sentence
    return "、".join(formatter(tag) for tag in tags)


def _prefer_deeper_tags(tags: list[str]) -> list[str]:
    ranked = [(tag.count("/"), index, tag) for index, tag in enumerate(tags)]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked]


def build_chinese_title(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "chinese_title" in override:
        return override["chinese_title"]
    if analysis:
        return analysis.chinese_title

    grouped = get_focus_tags_by_group(row, root=root)
    research_tags = _prefer_deeper_tags(grouped["research_object"])
    driver_tags = grouped["event_driver"]
    if driver_tags and research_tags:
        return f"{_tag_phrase_for_title(driver_tags[0])}背景下{_tag_phrase_for_title(research_tags[0])}特征研究"
    if research_tags:
        return f"{_tag_phrase_for_title(research_tags[0])}特征研究"
    if driver_tags:
        return f"{_tag_phrase_for_title(driver_tags[0])}相关研究"
    return "文献内容概括待补充"


def get_focus_tags(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> list[str]:
    override = get_override(row)
    if override and "tags" in override:
        return sanitize_tags(list(override["tags"]), root=root)
    if analysis:
        inferred = infer_preferred_tags_from_text(
            title_text=display_title(row),
            extra_text="\n".join(filter(None, [clean_text(row["notes"]), "\n".join(topic_labels(row))])),
            root=root,
        )
        source_inferred = infer_preferred_tags_from_text(
            body_text=clean_text(row["abstract"]),
            root=root,
        )
        source_grouped = group_tags(source_inferred, root=root)
        body_driver_tags = source_grouped.get("event_driver", [])
        return sanitize_tags(list(analysis.tags) + inferred + body_driver_tags, root=root)

    grouped = get_focus_tags_by_group(row, root=root)
    tags = (
        grouped["research_object"][:2]
        + grouped["event_driver"][:2]
        + grouped["index_control"][:1]
        + grouped["instrument_data"][:3]
        + grouped["model_method"][:2]
        + grouped["result_feature"][:2]
        + grouped["application_impact"][:1]
        + grouped["status"][:1]
    )
    if not tags:
        tags = fallback_tags_from_topics(row, root=root)
    return sanitize_tags(dedupe(tags), root=root)


def get_focus_tags_by_group(row: Row, root: Path | None = None) -> dict[str, list[str]]:
    inferred = infer_preferred_tags_from_text(
        title_text=display_title(row),
        body_text=clean_text(row["abstract"]),
        extra_text="\n".join(filter(None, [clean_text(row["notes"]), "\n".join(topic_labels(row))])),
        root=root,
    )
    if not inferred:
        inferred = fallback_tags_from_topics(row, root=root)

    groups = _empty_tag_groups()
    grouped = group_tags(inferred, root=root)
    for key in TAG_GROUP_IDS:
        groups[key] = grouped.get(key, [])
    return groups


def infer_tags_from_text(text: str, root: Path | None = None) -> list[str]:
    return infer_preferred_tags_from_text(
        title_text=text,
        body_text=text,
        root=root,
    )


def build_apa_citation(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    override = get_override(row)
    if override and "apa_citation" in override:
        return override["apa_citation"]

    authors = parse_authors(row["authors"])
    authors_text = format_authors_apa(authors)
    year = str(row["published_date"])[:4]
    title = sentence_case_title(row["title"])
    journal = row["source_name"]
    doi_url = build_doi_url(row["doi"], row["url"])
    return f"{authors_text} ({year}). {title}. {journal}. {doi_url}"


def build_body_paragraph(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "body" in override:
        return override["body"]
    if analysis:
        return analysis.body

    grouped = get_focus_tags_by_group(row, root=root)
    science_text = _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2] + grouped["event_driver"][:1]) or "相关空间物理问题"
    instrument_text = _tag_text(grouped["instrument_data"][:3] + grouped["model_method"][:1]) or "题目和摘要提到的相关观测或模拟资料"
    physical_text = _tag_text(grouped["result_feature"][:2] + grouped["application_impact"][:1]) or _tag_text(grouped["research_object"][:2]) or "关键物理过程"
    method_text = infer_method(row)
    conclusion_text = infer_conclusion(row)
    return (
        f"这篇文章主要关注{science_text}。作者使用{instrument_text}，通过{method_text}分析{physical_text}的变化特征。"
        f"{conclusion_text}"
    )


def build_supplement_text(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "supplement" in override:
        return override["supplement"]
    if analysis:
        return normalize_summary_supplement(row, analysis.supplement)

    grouped = get_focus_tags_by_group(row, root=root)
    science_text = _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2] + grouped["event_driver"][:1]) or "该研究主题"
    physical_text = _tag_text(grouped["result_feature"][:2] + grouped["application_impact"][:1]) or _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2]) or "相关物理量"
    return f"后续可继续关注{science_text}与{physical_text}之间的联系，以及是否有更多观测或模型结果支持当前结论。"


def normalize_summary_supplement(row: Row, supplement: str) -> str:
    clean_supplement = sanitize_generation_text(supplement)
    clean_supplement = clean_supplement.replace("结果片段", "相关内容")
    clean_supplement = clean_supplement.replace("关键章节", "相关内容")
    if supplement_claims_abstract_only(clean_supplement):
        if ABSTRACT_ONLY_NOTICE in clean_supplement:
            return clean_supplement
        return f"{ABSTRACT_ONLY_NOTICE} {clean_supplement}".strip()
    source_kind = str(row.get("summary_source_kind", "") or "").strip().lower()
    if source_kind not in FULL_TEXT_SOURCE_KINDS:
        return clean_supplement

    normalized_prefix = (
        "程序已读取并缓存全文；当前单篇总结为控制额度，基于从全文抽取的摘要、方法、结果和结论证据整理稿生成。"
    )
    if not clean_supplement:
        return normalized_prefix
    if normalized_prefix in clean_supplement:
        return clean_supplement

    cleaned_remainder = re.sub(
        r"当前材料虽来自全文整理稿，但所给节选主要覆盖[^。]*。\s*",
        "",
        clean_supplement,
    ).strip()
    cleaned_remainder = re.sub(
        r"来源文本为全文整理稿，但当前提供给我的证据[^。]*。\s*",
        "",
        cleaned_remainder,
    ).strip()
    cleaned_remainder = cleaned_remainder.replace("结果片段", "结果证据句")
    cleaned_remainder = cleaned_remainder.replace("关键章节", "证据整理稿")
    if not cleaned_remainder:
        return normalized_prefix
    return f"{normalized_prefix} {cleaned_remainder}"


def supplement_claims_abstract_only(supplement: str) -> bool:
    return bool(ABSTRACT_ONLY_RE.search(sanitize_generation_text(supplement)))


def build_recommendation(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "recommendation" in override:
        return override["recommendation"]
    if analysis:
        return analysis.recommendation

    grouped = get_focus_tags_by_group(row, root=root)
    science_text = _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2] + grouped["event_driver"][:1]) or "当前主题"
    return f"这篇文章与{science_text}方向相关，适合放入今日重点跟进列表。"


def build_one_sentence_summary(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "one_sentence" in override:
        return override["one_sentence"]
    if analysis:
        return analysis.one_sentence

    grouped = get_focus_tags_by_group(row, root=root)
    science_text = _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2] + grouped["event_driver"][:1]) or "相关空间物理问题"
    instrument_text = _tag_text(grouped["instrument_data"][:2]) or "相关数据"
    physical_text = _tag_text(grouped["result_feature"][:2] + grouped["application_impact"][:1]) or _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2]) or "关键物理量"
    return f"文章围绕{science_text}，利用{instrument_text}分析了{physical_text}的变化特征。"


def infer_method(row: Row) -> str:
    text = normalize_haystack(row)
    methods: list[str] = []
    if any(keyword in text for keyword in ["observation", "observations", "measured", "measurement", "satellite", "radar"]):
        methods.append("观测分析")
    if any(keyword in text for keyword in ["deep learning", "machine learning", "neural network", "resnet", "机器学习", "深度学习"]):
        methods.append("机器学习建模")
    if any(
        keyword in text
        for keyword in [
            "first-principles",
            "first principles",
            "physics-based",
            "general circulation model",
            "mhd model",
            "gitm",
            "tie-gcm",
            "waccm-x",
            "ctipe",
            "swmf",
            "sami2",
            "sami3",
            "gaia",
            "bats-r-us",
        ]
    ):
        methods.append("理论数值模式")
    if any(keyword in text for keyword in ["empirical model", "hasdm", "nrlmsise", "msis", "hwm", "jb2008", "iri"]):
        methods.append("经验模型对比")
    if any(keyword in text for keyword in ["statistical", "statistics", "global", "climatology", "trend"]):
        methods.append("统计分析")
    if any(keyword in text for keyword in ["case study", "event", "storm", "substorm"]):
        methods.append("个例研究")
    if not methods:
        methods.append("标题和摘要信息提炼")
    return "、".join(dedupe(methods))


def infer_conclusion(row: Row) -> str:
    abstract = clean_text(row["abstract"])
    if not abstract:
        return "摘要信息有限，建议结合全文进一步确认具体结论。"

    title = display_title(row).lower()
    if "response" in title or "responses" in title:
        return "摘要显示，该研究重点比较了不同条件下的响应差异，并给出了对应的物理解释。"
    if "observation" in title or "observations" in title:
        return "摘要显示，该研究报道了新的观测结果，并对相关过程给出了现象学解释。"
    if "effects" in title:
        return "摘要显示，该研究评估了不同驱动条件的影响，并讨论了可能的控制机制。"
    if "investigation" in title or "study" in title:
        return "摘要显示，该研究系统分析了相关现象，并总结了关键特征和可能成因。"
    return "摘要显示，该研究给出了与上述问题相关的主要结果和解释，值得结合全文继续细读。"


def normalize_haystack(row: Row) -> str:
    return f" {display_title(row).lower()} {clean_text(row['abstract']).lower()} "


def fallback_tags_from_topics(row: Row, root: Path | None = None) -> list[str]:
    tags: list[str] = []
    for label in topic_labels(row):
        mapped = TOPIC_TO_TAG.get(label)
        if mapped:
            tags.append(mapped)
    return sanitize_tags(tags, root=root)


def build_filename(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    return build_filename_for_title(
        row,
        build_chinese_title(row, analysis=analysis),
        sanitize_generation_text=sanitize_generation_text,
    )


def build_filename_from_chinese(row: Row, chinese_title: str) -> str:
    return build_filename_from_title(
        row,
        chinese_title,
        sanitize_generation_text=sanitize_generation_text,
    )
