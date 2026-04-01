from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from .article_summaries import (
    ArticleSummaryResult,
    article_summary_quality_score,
    display_title,
    build_doi_url,
    get_override,
    is_generic_sentence,
    is_placeholder_title,
    obsidian_link,
)
from .config import UserPreferenceProfile, load_master_plan_preferences
from .llm import AnalysisEngine, ReportAnalysis

FOCUS_LABELS = {
    "电离层",
    "热层",
    "日地耦合",
    "太阳与日球层",
    "磁层",
    "波粒相互作用",
    "高能粒子与辐射带",
    "低层大气波动上传",
    "磁层-电离层-热层耦合",
    "行星际环境驱动",
    "空间天气",
    "行星空间环境",
}


def build_report(
    report_date: date,
    summaries: list[ArticleSummaryResult],
    window_days: int = 7,
    analysis_engine: AnalysisEngine | None = None,
) -> tuple[str, dict]:
    preferences = analysis_engine.user_preferences if analysis_engine else load_master_plan_preferences()
    rows = [item.row for item in summaries]
    source_groups: dict[str, list[ArticleSummaryResult]] = defaultdict(list)
    topic_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()

    for summary in summaries:
        row = summary.row
        source_groups[row["source_name"]].append(summary)
        labels = [item for item in row["topic_labels"].split("\n") if item]
        filtered = [label for label in labels if label in FOCUS_LABELS]
        label_counts.update(filtered)
        topic_counts.update(filtered)

    top_labels = label_counts.most_common(6)
    highlight_summaries = select_highlights(summaries, preferences=preferences, limit=4)
    report_analysis = resolve_report_analysis(report_date, summaries, analysis_engine)
    stats = {
        "report_date": report_date.isoformat(),
        "window_days": window_days,
        "paper_count": len(summaries),
        "journal_count": len(source_groups),
        "topic_counts": dict(topic_counts),
        "label_counts": dict(label_counts),
        "highlight_count": len(highlight_summaries),
    }

    lines: list[str] = []
    lines.append("----")
    lines.append(f"标题：Space Physics Daily Report - {report_date.isoformat()}")
    lines.append(f"统计窗口：近 {window_days} 天")
    lines.append(f"监控期刊：{', '.join(sorted(source_groups)) if source_groups else '暂无'}")
    lines.append("")

    lines.append("## 今日概览")
    lines.append(f"- 今日共监控到 {len(rows)} 篇新论文，来自 {len(source_groups)} 本期刊。")
    if report_analysis and report_analysis.overview_bullets:
        for bullet in report_analysis.overview_bullets:
            lines.append(f"- {bullet}")
    elif top_labels:
        hotspot_text = "、".join(f"{label}（{count}篇）" for label, count in top_labels[:4])
        lines.append(f"- 今天的论文主要集中在：{hotspot_text}。")
        lines.append(build_overview_line(summaries, top_labels, preferences))
    else:
        lines.append("- 今天新增论文较少，暂未形成明显的主题聚集。")
        lines.append("- 今天仍建议关注与你研究方向相关的电离层、热层和日地耦合论文。")
    lines.append("")

    lines.append("## 今日搜索的文献的主要关注点分类")
    if top_labels:
        for label, count in top_labels:
            lines.append(f"- {label}：{count} 篇")
    else:
        lines.append("- 暂无明确分类结果。")
    lines.append("")

    lines.append("## 今日建议")
    if report_analysis and report_analysis.daily_suggestions:
        lines.extend(f"- {item}" for item in report_analysis.daily_suggestions)
    else:
        lines.extend(build_daily_suggestions(highlight_summaries, top_labels, preferences))
    lines.append("")

    lines.append("### 今日最值得关注的论文")
    if highlight_summaries:
        for index, summary in enumerate(highlight_summaries, start=1):
            lines.extend(format_highlight_block(index, summary))
    else:
        lines.append("   1. 今日暂无重点推荐论文。")
    lines.append("")

    lines.append("### 按主题聚焦")
    if top_labels:
        for index, (label, _) in enumerate(top_labels[:4], start=1):
            lines.extend(
                format_topic_section(
                    index,
                    label,
                    summaries,
                    report_analysis=report_analysis,
                    preferences=preferences,
                )
            )
    else:
        lines.append("#### 主题 1：暂无")
        lines.append("   - 暂无可汇总主题。")
    lines.append("")

    lines.append("### 按期刊汇总")
    if source_groups:
        for source_name in sorted(source_groups):
            lines.extend(
                format_journal_section(
                    source_name,
                    source_groups[source_name],
                    report_analysis=report_analysis,
                    preferences=preferences,
                )
            )
    else:
        lines.append("#### 暂无期刊")
        lines.append("   - 暂无新增论文。")
    lines.append("")

    lines.append("## 附注")
    lines.append("- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。")
    lines.append(f"- 生成时间：{datetime.utcnow().isoformat(timespec='seconds')} UTC")
    lines.append("")
    lines.append("----")
    lines.append("")
    return "\n".join(lines), stats


def build_overview_line(
    summaries: list[ArticleSummaryResult],
    top_labels: list[tuple[str, int]],
    preferences: UserPreferenceProfile,
) -> str:
    journals = sorted({item.row["source_name"] for item in summaries})
    journal_text = "、".join(journals[:3]) if journals else "当前监控期刊"
    theme_text = "、".join(label for label, _ in top_labels[:3])
    preferred = select_preference_hits(summaries, preferences, limit=3)
    if preferred:
        preference_text = "、".join(preference_themes_for_summaries(preferred, preferences))
        return f"- 结合今天的结果看，{journal_text} 上的新论文主要围绕 {theme_text} 展开，其中更值得特别提醒的是 {preference_text} 相关工作。"
    return f"- 结合今天的结果看，{journal_text} 上的新论文主要围绕 {theme_text} 展开，其中与你当前关注方向最贴近的是上层大气、电离层和日地耦合相关研究。"


def build_daily_suggestions(
    highlight_summaries: list[ArticleSummaryResult],
    top_labels: list[tuple[str, int]],
    preferences: UserPreferenceProfile,
) -> list[str]:
    lines: list[str] = []
    if highlight_summaries:
        focus_titles = "；".join(display_title(item.row) for item in highlight_summaries[:2])
        lines.append(f"- 建议优先细读：{focus_titles}。")
    else:
        lines.append("- 建议优先细读：今天暂无高优先级论文。")
    if top_labels:
        lines.append(f"- 建议持续追踪：{'、'.join(label for label, _ in top_labels[:3])}。")
    else:
        lines.append("- 建议持续追踪：今天暂无明显聚焦主题。")
    if highlight_summaries:
        lines.append(f"- 今天值得特别留意的新现象或新数据包括：{build_special_attention(highlight_summaries, preferences)}。")
    else:
        lines.append("- 今天值得特别留意的新现象或新数据：暂无。")
    preferred = select_preference_hits(highlight_summaries, preferences, limit=3)
    if preferred:
        lines.append(f"- 按当前研究偏好，建议额外关注：{preference_focus_line(preferred, preferences)}。")
    return lines


def build_special_attention(summaries: list[ArticleSummaryResult], preferences: UserPreferenceProfile) -> str:
    preferred = select_preference_hits(summaries, preferences, limit=4)
    if preferred:
        themes = preference_themes_for_summaries(preferred, preferences)
        if themes:
            return "、".join(themes)
    tags: list[str] = []
    for summary in summaries:
        tags.extend(summary.tags)
    unique = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            unique.append(tag)
            seen.add(tag)
        if len(unique) >= 4:
            break
    return "、".join(unique) if unique else "当前重点论文中的关键物理过程"


def format_highlight_block(index: int, summary: ArticleSummaryResult) -> list[str]:
    row = summary.row
    tags = " ".join("#" + tag.replace(" ", "") for tag in summary.tags)
    return [
        f"   {index}. 英文题目：{linked_paper_title(summary)}",
        f"      中文题目：{summary.chinese_title}",
        f"      中文概括：{summary.one_sentence}",
        f"      标签： {tags}",
        f"      推荐理由：{summary.recommendation}",
        f"      网址：{build_doi_url(row['doi'], row['url'])}",
    ]


def format_topic_section(
    index: int,
    label: str,
    summaries: list[ArticleSummaryResult],
    report_analysis: ReportAnalysis | None = None,
    preferences: UserPreferenceProfile | None = None,
) -> list[str]:
    related_summaries = [
        summary
        for summary in summaries
        if label in [item for item in summary.row["topic_labels"].split("\n") if item]
    ]
    related_summaries = rank_section_summaries(related_summaries, preferences or UserPreferenceProfile())[:5]
    titles = "；".join(linked_paper_title(summary) for summary in related_summaries) if related_summaries else "暂无代表性论文"
    one_sentences = "；".join(summary.one_sentence for summary in related_summaries[:3]) if related_summaries else "暂无可概括内容"
    llm_summary = report_analysis.topic_summary(label) if report_analysis else None
    return [
        f"#### 主题 {index}：{label}",
        f"   - 今日这一主题下的代表性论文包括：{titles}。",
        f"   - 这些论文主要围绕：{llm_summary or one_sentences}。",
        f"   - 今天这一主题显示出较高活跃度，说明 {label} 仍是当前监控窗口里的重要方向。",
    ]


def format_journal_section(
    source_name: str,
    summaries: list[ArticleSummaryResult],
    report_analysis: ReportAnalysis | None = None,
    preferences: UserPreferenceProfile | None = None,
) -> list[str]:
    top_topics = Counter()
    for summary in summaries:
        top_topics.update(item for item in summary.row["topic_labels"].split("\n") if item in FOCUS_LABELS)
    direction_text = "、".join(label for label, _ in top_topics.most_common(3)) if top_topics else "暂无明显方向"
    top_summaries = rank_section_summaries(summaries, preferences or UserPreferenceProfile())[:4]
    llm_summary = report_analysis.journal_summary(source_name) if report_analysis else None
    lines = [
        f"#### {source_name}",
        f"   - 今日新增：{len(summaries)} 篇",
        f"   - 重点方向：{direction_text}",
    ]
    if llm_summary:
        lines.append(f"   - LLM分析：{llm_summary}")
    lines.extend([
        "   - 重点论文：",
    ])
    for index, summary in enumerate(top_summaries, start=1):
        lines.append(f"     {index}. {linked_paper_title(summary)}")
        lines.append(f"        中文概括：{summary.one_sentence}")
    return lines


def linked_paper_title(summary: ArticleSummaryResult) -> str:
    return obsidian_link(summary.output_path, display_title(summary.row))


def select_preference_hits(
    summaries: list[ArticleSummaryResult],
    preferences: UserPreferenceProfile,
    limit: int = 3,
) -> list[ArticleSummaryResult]:
    ranked = [summary for summary in summaries if preference_match_score(summary, preferences) > 0]
    ranked.sort(key=lambda item: (preference_match_score(item, preferences), article_summary_quality_score(item)), reverse=True)
    return ranked[:limit]


def preference_focus_line(summaries: list[ArticleSummaryResult], preferences: UserPreferenceProfile) -> str:
    themes = preference_themes_for_summaries(summaries, preferences)
    titles = "；".join(display_title(item.row) for item in summaries[:2])
    if themes:
        return f"{'、'.join(themes)}，对应论文包括 {titles}"
    return titles


def preference_themes_for_summaries(
    summaries: list[ArticleSummaryResult],
    preferences: UserPreferenceProfile,
) -> list[str]:
    themes: list[str] = []
    for summary in summaries:
        matched = matched_preference_themes(summary, preferences)
        for item in matched:
            if item not in themes:
                themes.append(item)
    return themes[:4]


def matched_preference_themes(
    summary: ArticleSummaryResult,
    preferences: UserPreferenceProfile,
) -> list[str]:
    text = build_summary_match_text(summary)
    matched: list[str] = []
    for theme, keywords in preferences.theme_keywords.items():
        if any(keyword.lower() in text for keyword in keywords):
            matched.append(theme)
    return matched


def preference_match_score(summary: ArticleSummaryResult, preferences: UserPreferenceProfile) -> int:
    if not preferences.theme_keywords:
        return 0
    text = build_summary_match_text(summary)
    score = 0
    for keywords in preferences.theme_keywords.values():
        if any(keyword.lower() in text for keyword in keywords):
            score += 1
    return score


def build_summary_match_text(summary: ArticleSummaryResult) -> str:
    return " ".join(
        [
            display_title(summary.row).lower(),
            summary.chinese_title.lower(),
            summary.one_sentence.lower(),
            summary.body.lower(),
            " ".join(tag.lower() for tag in summary.tags),
        ]
    )


def rank_section_summaries(
    summaries: list[ArticleSummaryResult],
    preferences: UserPreferenceProfile,
) -> list[ArticleSummaryResult]:
    def key(summary: ArticleSummaryResult) -> tuple[int, int, float]:
        return (
            preference_match_score(summary, preferences),
            article_summary_quality_score(summary),
            float(summary.row["relevance_score"]),
        )

    return sorted(summaries, key=key, reverse=True)


def select_highlights(
    summaries: list[ArticleSummaryResult],
    preferences: UserPreferenceProfile,
    limit: int = 3,
) -> list[ArticleSummaryResult]:
    ranked = sorted(summaries, key=lambda item: highlight_priority(item, preferences), reverse=True)
    selected: list[ArticleSummaryResult] = []
    seen_topics: set[str] = set()

    for summary in ranked:
        row = summary.row
        if article_summary_quality_score(summary) <= 1:
            continue
        if not get_override(row):
            continue
        selected.append(summary)
        seen_topics.update(item for item in row["topic_labels"].split("\n") if item)
        if len(selected) >= limit:
            return selected

    for summary in ranked:
        row = summary.row
        if summary in selected:
            continue
        if article_summary_quality_score(summary) <= 1:
            continue
        topics = tuple(item for item in row["topic_labels"].split("\n") if item)
        if topics and not seen_topics.intersection(topics):
            selected.append(summary)
            seen_topics.update(topics)
        elif len(selected) < max(2, limit // 2):
            selected.append(summary)
        if len(selected) >= limit:
            break
    return selected[:limit]


def highlight_priority(summary: ArticleSummaryResult, preferences: UserPreferenceProfile) -> tuple[float, float, float, str]:
    row = summary.row
    labels = [item for item in row["topic_labels"].split("\n") if item in FOCUS_LABELS]
    overlap = len(labels)
    override_bonus = 5 if get_override(row) else 0
    relevance = float(row["relevance_score"])
    preference_bonus = preference_match_score(summary, preferences) * 8
    quality_bonus = article_summary_quality_score(summary) * 4
    return (overlap * 10 + override_bonus + preference_bonus + quality_bonus + relevance, quality_bonus, relevance, row["published_date"])


def write_report(report_root: Path, report_date: date, markdown: str) -> Path:
    report_root.mkdir(parents=True, exist_ok=True)
    dated_path = report_root / f"{report_date.isoformat()} 周报.md"
    latest_path = report_root / "latest.md"
    dated_path.write_text(markdown, encoding="utf-8")
    latest_path.write_text(markdown, encoding="utf-8")
    return dated_path


def resolve_report_analysis(
    report_date: date,
    summaries: list[ArticleSummaryResult],
    analysis_engine: AnalysisEngine | None,
) -> ReportAnalysis | None:
    if analysis_engine is None:
        return None
    try:
        return analysis_engine.analyze_report(report_date, summaries)
    except Exception:
        return None
