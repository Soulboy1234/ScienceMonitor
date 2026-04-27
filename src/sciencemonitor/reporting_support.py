from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import ArticleSummaryResult


THEME_ALLOWED_ROOTS = {"对象", "事件"}
THEME_GENERIC_TAGS = {
    "对象",
    "对象/热层",
    "对象/电离层",
    "对象/极区",
    "对象/磁层",
    "对象/太阳",
    "对象/太阳风",
    "对象/其他行星",
    "对象/高能粒子",
    "对象/重力波",
    "对象/波动",
    "对象/动力学过程",
    "对象/周期扰动",
    "对象/日地耦合",
    "事件",
}
THEME_BLOCKED_PREFIXES = ("对象/日地耦合",)
THEME_BLOCKED_DISPLAYS = {"日地耦合", "数据分析", "统计研究"}
TOPIC_WEAK_OBJECT_DISPLAYS = {
    "地磁",
    "高能粒子/电子",
    "太阳/日球层",
    "磁层/弓激波",
}


@dataclass(frozen=True)
class ReportThemeBucket:
    tag: str
    display: str
    count: int
    journals: tuple[str, ...]
    summaries: tuple[ArticleSummaryResult, ...]


def display_report_theme(tag: str) -> str:
    parts = [part.strip() for part in str(tag or "").split("/") if part.strip()]
    if len(parts) <= 1:
        return str(tag or "").strip()
    if parts[0] not in THEME_ALLOWED_ROOTS:
        return "/".join(parts)
    return "/".join(parts[1:])


def _theme_root(tag: str) -> str:
    return str(tag or "").split("/", 1)[0].strip()


def _theme_depth(tag: str) -> int:
    return len([part for part in str(tag or "").split("/") if part.strip()])


def _is_status_tag(tag: str) -> bool:
    clean = str(tag or "").strip()
    return not clean or clean.startswith("信息来源/") or clean in {"综述", "Todo", "重要", "展望", "科学思考"}


def _is_theme_candidate(tag: str) -> bool:
    clean = str(tag or "").strip()
    if not clean or _is_status_tag(clean):
        return False
    if _theme_root(clean) not in THEME_ALLOWED_ROOTS:
        return False
    if clean in THEME_GENERIC_TAGS:
        return False
    if any(clean == prefix or clean.startswith(prefix + "/") for prefix in THEME_BLOCKED_PREFIXES):
        return False
    display = display_report_theme(clean)
    if display in THEME_BLOCKED_DISPLAYS:
        return False
    return True


def _summary_row_value(summary: ArticleSummaryResult, key: str) -> str:
    try:
        return str(summary.row[key] or "")
    except Exception:
        return ""


def _prefer_more_specific_tags(tags: list[str]) -> list[str]:
    ordered = sorted({tag for tag in tags if tag}, key=lambda item: (_theme_depth(item), len(item)), reverse=True)
    selected: list[str] = []
    for tag in ordered:
        if any(existing.startswith(f"{tag}/") for existing in selected):
            continue
        selected.append(tag)
    return list(reversed(selected))


def theme_tags_for_summary(summary: ArticleSummaryResult) -> list[str]:
    candidates = [tag for tag in summary.tags if _is_theme_candidate(tag)]
    specific = _prefer_more_specific_tags(candidates)
    if specific:
        return specific[:4]
    fallback = [tag for tag in summary.tags if _is_theme_candidate(tag) and _theme_depth(tag) >= 2]
    return _prefer_more_specific_tags(fallback)[:3]


def collect_report_theme_buckets(
    summaries: list[ArticleSummaryResult],
    *,
    min_count: int = 1,
) -> list[ReportThemeBucket]:
    grouped: dict[str, list[ArticleSummaryResult]] = defaultdict(list)
    journal_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for summary in summaries:
        source_name = _summary_row_value(summary, "source_name") or _summary_row_value(summary, "journal_title") or "未知期刊"
        for tag in theme_tags_for_summary(summary):
            grouped[tag].append(summary)
            journal_counts[tag][source_name] += 1

    buckets: list[ReportThemeBucket] = []
    for tag, items in grouped.items():
        unique_map: dict[str, ArticleSummaryResult] = {}
        for item in items:
            doi = ""
            try:
                doi = str(item.row["doi"] or "")
            except Exception:
                doi = ""
            key = str(getattr(item, "output_path", "") or doi or item.note_title or display_report_theme(tag))
            unique_map[key] = item
        unique_items = list(unique_map.values())
        if len(unique_items) < min_count:
            continue
        journals = tuple(journal for journal, _ in journal_counts[tag].most_common())
        buckets.append(
            ReportThemeBucket(
                tag=tag,
                display=display_report_theme(tag),
                count=len(unique_items),
                journals=journals,
                summaries=tuple(unique_items),
            )
        )

    def _bucket_key(bucket: ReportThemeBucket) -> tuple[int, int, int, str]:
        display = bucket.display
        specificity_bonus = 1 if "/" in display else 0
        return (bucket.count, specificity_bonus, _theme_depth(bucket.tag), display)

    return sorted(buckets, key=_bucket_key, reverse=True)


def topic_recommendation_buckets(summaries: list[ArticleSummaryResult]) -> list[ReportThemeBucket]:
    buckets = collect_report_theme_buckets(summaries, min_count=2)
    selected: list[ReportThemeBucket] = []
    for bucket in buckets:
        if bucket.tag.startswith("对象/") and bucket.count < 3 and bucket.display in TOPIC_WEAK_OBJECT_DISPLAYS:
            continue
        selected.append(bucket)
    return selected


def top_theme_labels_for_schema(summaries: list[ArticleSummaryResult], *, limit: int = 8) -> list[str]:
    labels: list[str] = []
    for bucket in collect_report_theme_buckets(summaries, min_count=1):
        if bucket.display not in labels:
            labels.append(bucket.display)
        if len(labels) >= limit:
            break
    return labels
