from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import re

from .article_summary_markdown import build_tag_line, obsidian_link
from .article_summary_meta import build_doi_url, display_title, get_override, row_value
from .article_summary_text import article_summary_quality_score, build_apa_citation
from .chatgpt_web_manual import ManualResponsePending
from .config import UserPreferenceProfile, can_delete_output_path, load_master_plan_preferences, project_root, reports_root, templates_root
from .llm import AnalysisEngine, AnalysisQuotaExceeded, ReportAnalysis
from .models import ArticleSummaryResult, SkippedArticleSummary
from .reporting_support import (
    ReportThemeBucket,
    collect_report_theme_buckets,
    display_report_journal_name,
    display_report_theme,
    normalize_report_journal_name,
    theme_tags_for_summary,
    topic_recommendation_buckets,
)
from .reporting_template import (
    join_report_lines,
    load_report_template,
    render_report_template,
    run_report_review_loop as _run_report_review_loop,
    validate_report_markdown,
)

REPORT_DIRECT_THEME_RULES: dict[str, dict[str, tuple[str, ...] | set[str]]] = {
    "热层密度": {
        "tags": {"对象/热层/密度"},
        "phrases": (
            "热层密度",
            "thermospheric density",
            "thermospheric mass density",
            "neutral density",
        ),
        "negative_phrases": (
            "不是直接研究热层密度",
            "未直接展开其对热层密度",
            "未讨论热层密度",
        ),
    },
    "热层风": {
        "tags": {"对象/热层/风场", "对象/热层/风场/垂直风"},
        "phrases": (
            "热层风",
            "风场",
            "thermospheric wind",
            "neutral wind",
        ),
    },
    "卫星影响": {
        "tags": {"应用/卫星影响"},
        "phrases": (
            "satellite drag",
            "orbit decay",
            "orbital decay",
            "轨道衰减",
            "卫星阻力",
            "卫星运行",
            "轨道环境",
        ),
        "required_any": (
            "卫星",
            "satellite",
            "轨道",
            "orbit",
            "drag",
        ),
    },
    "业务化与预报": {
        "tags": {"应用/预测"},
        "phrases": (
            "预报",
            "forecast",
            "forecasting",
            "prediction",
            "nowcast",
            "业务化",
            "operational",
        ),
    },
    "应用影响": {
        "tags": set(),
        "phrases": (
            "通信",
            "导航",
            "电网",
            "任务安全",
            "风险评估",
            "业务系统",
        ),
    },
}
LOW_QUALITY_TOPIC_PATTERNS = (
    r"^该文主要涉及",
    r"建议结合原标题和摘要确认",
    r"^本主题主要涉及",
)
LOW_QUALITY_PREFERENCE_PATTERNS = (
    r"如果你在跟踪",
    r"建议结合原标题和摘要确认",
    r"值得先看摘要",
    r"与当前工作相关的内容很多",
    r"assistant to=final",
    r"codex_output_schema",
    r"##errmsg##",
    r"json invalid",
    r"let'?s fix",
    r"oops need proper final",
)
REPORT_TERM_NORMALIZATIONS = {
    "thermospheric forcing": "热层外部强迫",
    "热层外部强迫外部驱动": "热层外部强迫",
}
REPORT_WORDCLOUD_FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)
REPORT_WORDCLOUD_COLORS = (
    "#173F5F",
    "#20639B",
    "#3CAEA3",
    "#F6D55C",
    "#ED553B",
    "#8C1C13",
)
REPORT_WORDCLOUD_EXCLUDED_PREFIXES = (
    "信息来源/",
    "方法/",
    "对象/物理机制",
    "对象/现象",
    "对象/空间天气",
    "对象/评估",
    "对象/卫星",
)
REPORT_WORDCLOUD_EMBED_RE = re.compile(r"!\[\[research_reports/assets/(?P<name>[^|\]]+ 标签词云\.png)(?:\|[^\]]+)?\]\]")
REPORT_WORDCLOUD_WIDTH = 1400
REPORT_WORDCLOUD_HEIGHT = 980
REPORT_WORDCLOUD_MIN_FONT = 22
REPORT_WORDCLOUD_MAX_FONT = 76
REPORT_RECOMMENDATION_PRIMARY_ASPECT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("预测", "预报", "forecast", "prediction", "nowcast"), "输入变量、建模设定和评价方式"),
    (("机器学习", "深度学习", "neural network", "resnet"), "特征选择、训练设定和泛化表现"),
    (("模型", "建模", "simulation", "simulat", "diffusion", "扩散率"), "模型设定、关键参数和结果边界"),
    (("统计", "定量"), "样本分组、响应差异和统计结论"),
    (("观测", "联合观测", "多星", "遥感", "maven", "saber", "vlf", "icon", "gnss", "雷达", "成像"), "观测组合、数据来源和关键响应特征"),
    (("磁暴", "storm", "耀斑", "flare", "cme", "icme", "sep"), "事件背景、过程演化和关键响应"),
    (("比较", "对比", "差异", "different", "difference"), "对比条件和结论边界"),
    (("风场", "wind", "密度", "density", "tec", "电子密度"), "关键物理量的变化特征和解释"),
)
REPORT_RECOMMENDATION_SECONDARY_ASPECT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("边界", "boundary", "激波", "shock", "磁鞘"), "边界结构与动力学判据"),
    (("比较", "对比", "差异", "different", "difference"), "对比条件和结论边界"),
)


def build_report(
    report_date: date,
    summaries: list[ArticleSummaryResult],
    missing_source_rows: list | None = None,
    skipped_summary_rows: list[SkippedArticleSummary] | None = None,
    window_days: int = 7,
    analysis_engine: AnalysisEngine | None = None,
    root: Path | None = None,
    require_analysis: bool = True,
) -> tuple[str, dict]:
    project = root or getattr(analysis_engine, "root", None) or project_root()
    template_text = load_report_template(templates_root(project) / "daily_report_template.md")
    preferences = analysis_engine.user_preferences if analysis_engine else load_master_plan_preferences()
    missing_source_rows = missing_source_rows or []
    skipped_summary_rows = skipped_summary_rows or []
    rows = [item.row for item in summaries] + list(missing_source_rows) + [item.row for item in skipped_summary_rows]
    report_analysis = resolve_report_analysis(report_date, summaries, analysis_engine)
    if require_analysis and summaries:
        if analysis_engine is None:
            raise RuntimeError("周报生成已不再支持规则法。请提供可用的 LLM 分析后端。")
        if not analysis_engine.report_enabled():
            raise RuntimeError("当前分析后端不可用，周报生成无法继续。请先在设置里切换到可用的 LLM 后端。")
        if report_analysis is None:
            raise RuntimeError("周报生成需要有效的 LLM 分析结果，但当前未成功返回结果。请检查 provider 配置、模型可用性或额度。")

    journal_counts = build_journal_counts(rows)
    theme_buckets = collect_report_theme_buckets(summaries, min_count=1)
    topic_buckets = topic_recommendation_buckets(summaries)
    highlight_summaries = select_highlights(summaries, preferences=preferences, limit=4)
    all_source_names = [journal for journal, _ in journal_counts]
    tag_wordcloud_block = build_tag_wordcloud_block(report_date, window_days, summaries, project)

    stats = {
        "report_date": report_date.isoformat(),
        "window_days": window_days,
        "paper_count": len(rows),
        "summarized_count": len(summaries),
        "missing_source_count": len(missing_source_rows),
        "skipped_summary_count": len(skipped_summary_rows),
        "journal_count": len(journal_counts),
        "theme_count": len(theme_buckets),
        "topic_recommendation_count": len(topic_buckets),
        "highlight_count": len(highlight_summaries),
    }

    report_info_lines = build_report_info_section(
        report_date,
        window_days,
        journal_counts,
        summarized_count=len(summaries),
        missing_source_count=len(missing_source_rows),
        skipped_summary_count=len(skipped_summary_rows),
    )
    overview_table_lines = build_overview_table_section(theme_buckets)
    objective_overview_lines = build_objective_overview_section(
        summaries,
        theme_buckets,
        journal_counts,
        report_analysis=report_analysis,
    )
    preference_overview_lines = build_preference_overview_section(
        summaries,
        preferences,
        report_analysis=report_analysis,
    )
    recommended_papers_lines = build_recommended_papers_section(highlight_summaries)
    recommended_process_lines = build_recommended_processes_section(
        highlight_summaries,
        theme_buckets,
        report_analysis=report_analysis,
    )
    work_implications_lines = build_work_implications_section(
        summaries,
        preferences,
        report_analysis=report_analysis,
    )
    topic_lines = build_topic_recommendations_section(
        topic_buckets,
        report_analysis=report_analysis,
        preferences=preferences,
    )
    journal_roundup_lines = build_journal_roundup_section(
        summaries,
        journal_counts,
        report_analysis=report_analysis,
        preferences=preferences,
    )
    missing_source_lines = format_missing_source_section(missing_source_rows, skipped_summary_rows)

    markdown = render_report_template(
        template_text,
        {
            "report_date": report_date.isoformat(),
            "window_days": str(window_days),
            "journals": "、".join(all_source_names) if all_source_names else "暂无",
            "report_info_block": join_report_lines(report_info_lines),
            "tag_wordcloud_block": tag_wordcloud_block,
            "overview_table_block": join_report_lines(overview_table_lines),
            "objective_overview_block": join_report_lines(objective_overview_lines),
            "preference_overview_block": join_report_lines(preference_overview_lines),
            "recommended_papers_block": join_report_lines(recommended_papers_lines),
            "recommended_processes_block": join_report_lines(recommended_process_lines),
            "work_implications_block": join_report_lines(work_implications_lines),
            "theme_recommendations_block": join_report_lines(topic_lines),
            "journal_roundup_block": join_report_lines(journal_roundup_lines),
            "missing_sources_block": join_report_lines(missing_source_lines),
            "generated_at": f"{datetime.utcnow().isoformat(timespec='seconds')} UTC",
        },
    )
    markdown, review_issues = _run_report_review_loop(markdown)
    validation_issues = review_issues + validate_report_markdown(markdown)
    if validation_issues:
        raise ValueError("Report output failed template validation: " + "；".join(validation_issues))
    return markdown, stats


def build_tag_wordcloud_block(
    report_date: date,
    window_days: int,
    summaries: list[ArticleSummaryResult],
    project: Path,
) -> str:
    asset_root = reports_root(project) / "assets"
    asset_root.mkdir(parents=True, exist_ok=True)
    asset_name = f"{report_date.isoformat()} 标签词云.png"
    asset_path = asset_root / asset_name
    frequencies = collect_report_tag_frequencies(summaries)
    if not frequencies:
        return "- 本周暂无可视化标签。"
    render_report_tag_wordcloud(
        asset_path,
        frequencies,
        date_range_label=build_report_date_range_label(report_date, window_days),
        seed=report_date.toordinal(),
    )
    return f"![[research_reports/assets/{asset_name}|960]]"


def collect_report_tag_frequencies(summaries: list[ArticleSummaryResult]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for summary in summaries:
        for tag in summary.tags:
            clean = str(tag or "").strip()
            if clean and should_include_report_wordcloud_tag(clean):
                counter[clean] += 1
    return counter


def build_report_wordcloud_display_labels(frequencies: Counter[str]) -> list[tuple[str, int, str]]:
    tags = list(frequencies.keys())
    segments_map = {tag: [segment for segment in tag.split("/") if segment] for tag in tags}
    chosen: dict[str, str] = {}
    for tag in tags:
        segments = segments_map[tag]
        for depth in range(1, len(segments) + 1):
            candidate = "/".join(segments[-depth:])
            if sum(1 for other, other_segments in segments_map.items() if "/".join(other_segments[-depth:]) == candidate) == 1:
                chosen[tag] = candidate
                break
        else:
            chosen[tag] = tag
    return sorted(((display, frequencies[tag], tag) for tag, display in chosen.items()), key=lambda item: (-item[1], item[0], item[2]))


def should_include_report_wordcloud_tag(tag: str) -> bool:
    clean = str(tag or "").strip()
    if not clean:
        return False
    return not any(clean.startswith(prefix) for prefix in REPORT_WORDCLOUD_EXCLUDED_PREFIXES)


def build_report_date_range_label(report_date: date, window_days: int) -> str:
    start_date = report_date - timedelta(days=max(window_days - 1, 0))
    return f"统计范围：{start_date.isoformat()} 至 {report_date.isoformat()}"


def render_report_tag_wordcloud(
    asset_path: Path,
    frequencies: Counter[str],
    *,
    date_range_label: str,
    seed: int,
) -> None:
    from PIL import Image, ImageDraw

    width, height = REPORT_WORDCLOUD_WIDTH, REPORT_WORDCLOUD_HEIGHT
    image = Image.new("RGB", (width, height), "#FBFAF7")
    draw = ImageDraw.Draw(image)
    header_font = load_report_wordcloud_font(28)
    subheader_font = load_report_wordcloud_font(18)
    draw.text((32, 20), "周报标签词云", fill="#173F5F", font=header_font)
    draw.text((32, 58), date_range_label, fill="#56667A", font=subheader_font)
    draw.line((28, 96, width - 28, 96), fill="#D9D6CF", width=2)
    items = build_report_wordcloud_display_labels(frequencies)
    placements = layout_report_wordcloud_items(draw, items, width=width, height=height, seed=seed)
    for label, count, font, x, y in placements:
        color = REPORT_WORDCLOUD_COLORS[(len(label) + count) % len(REPORT_WORDCLOUD_COLORS)]
        draw.text((x, y), label, fill=color, font=font)
    image.save(asset_path)


def cleanup_unused_report_tag_wordclouds(project: Path, *, keep_names: set[str] | None = None) -> None:
    asset_root = reports_root(project) / "assets"
    if not asset_root.exists():
        return
    referenced = referenced_report_tag_wordcloud_names(project) | set(keep_names or set())
    for candidate in asset_root.glob("* 标签词云.png"):
        if candidate.name in referenced:
            continue
        if can_delete_output_path(candidate, project):
            candidate.unlink(missing_ok=True)


def referenced_report_tag_wordcloud_names(project: Path) -> set[str]:
    report_root = reports_root(project)
    names: set[str] = set()
    for markdown_path in report_root.glob("*.md"):
        text = markdown_path.read_text(encoding="utf-8")
        for match in REPORT_WORDCLOUD_EMBED_RE.finditer(text):
            names.add(str(match.group("name") or "").strip())
    return names


def load_report_wordcloud_font(size: int):
    from PIL import ImageFont

    for candidate in REPORT_WORDCLOUD_FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def layout_report_wordcloud_items(
    draw,
    items: list[tuple[str, int, str]],
    *,
    width: int,
    height: int,
    seed: int,
) -> list[tuple[str, int, object, int, int]]:
    max_count = max(count for _, count, _ in items)
    min_count = min(count for _, count, _ in items)
    spread = max(max_count - min_count, 1)
    cloud_top = 116
    cloud_bottom = height - 28
    available_width = width - 64
    available_height = cloud_bottom - cloud_top
    font_cache: dict[int, object] = {}

    rows: list[list[tuple[str, int, object, int, int]]] = []
    current_row: list[tuple[str, int, object, int, int]] = []
    current_width = 0
    current_height = 0
    gap = 26
    max_row_width = available_width

    for label, count, _ in items:
        size = int(
            REPORT_WORDCLOUD_MIN_FONT
            + ((count - min_count) / spread) * (REPORT_WORDCLOUD_MAX_FONT - REPORT_WORDCLOUD_MIN_FONT)
        )
        font = font_cache.get(size)
        if font is None:
            font = load_report_wordcloud_font(size)
            font_cache[size] = font
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        projected = text_width if not current_row else current_width + gap + text_width
        if current_row and projected > max_row_width:
            rows.append(current_row)
            current_row = []
            current_width = 0
            current_height = 0
        current_row.append((label, count, font, text_width, text_height))
        current_width = text_width if len(current_row) == 1 else current_width + gap + text_width
        current_height = max(current_height, text_height)
    if current_row:
        rows.append(current_row)

    if not rows:
        return []

    row_heights = [max(item[4] for item in row) for row in rows]
    total_height = sum(row_heights) + max(len(rows) - 1, 0) * 14
    if total_height > available_height:
        return fallback_grid_wordcloud_layout(draw, items, width=width, height=height)

    placements: list[tuple[str, int, object, int, int]] = []
    y = cloud_top + max((available_height - total_height) // 2, 0)
    for row_index, row in enumerate(rows):
        row_height = row_heights[row_index]
        row_width = sum(item[3] for item in row) + max(len(row) - 1, 0) * gap
        x = 32 + max((available_width - row_width) // 2, 0)
        for label, count, font, text_width, text_height in row:
            y_offset = (row_height - text_height) // 2
            placements.append((label, count, font, x, y + y_offset))
            x += text_width + gap
        y += row_height + 14
    return placements


def fallback_grid_wordcloud_layout(
    draw,
    items: list[tuple[str, int, str]],
    *,
    width: int,
    height: int,
) -> list[tuple[str, int, object, int, int]]:
    font_cache: dict[int, object] = {}
    placements: list[tuple[str, int, object, int, int]] = []
    columns = 4
    left = 32
    top = 116
    available_width = width - 2 * left
    column_width = max(available_width // columns, 1)
    row_y = top
    max_row_height = 0
    col = 0
    for label, count, _ in items:
        size = REPORT_WORDCLOUD_MIN_FONT
        font = font_cache.get(size)
        if font is None:
            font = load_report_wordcloud_font(size)
            font_cache[size] = font
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        if col >= columns:
            col = 0
            row_y += max_row_height + 12
            max_row_height = 0
        x = left + col * column_width + max((column_width - text_width) // 2, 0)
        y = row_y
        placements.append((label, count, font, x, y))
        max_row_height = max(max_row_height, text_height)
        col += 1
    return placements


def build_journal_counts(rows: list) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for row in rows:
        journal = normalize_report_journal_name(row_value(row, "source_name", "") or row_value(row, "journal_title", "") or "未知期刊")
        counts[journal] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def build_report_info_section(
    report_date: date,
    window_days: int,
    journal_counts: list[tuple[str, int]],
    *,
    summarized_count: int,
    missing_source_count: int,
    skipped_summary_count: int,
) -> list[str]:
    start_date = report_date - timedelta(days=max(window_days - 1, 0))
    lines = [
        f"- 调研时间：{start_date.isoformat()} 至 {report_date.isoformat()}。",
        (
            f"- 本周共纳入 {summarized_count} 篇已生成单篇总结的论文，"
            f"另有 {skipped_summary_count} 篇单篇总结未完成、{missing_source_count} 篇未获取摘要或全文的条目。"
        ),
        "",
        "| 期刊 | 新增文章数 |",
        "| --- | ---: |",
    ]
    if not journal_counts:
        lines.append("| 暂无 | 0 |")
        return lines
    for journal, count in journal_counts:
        lines.append(f"| {escape_table_cell(journal)} | {count} |")
    return lines


def build_overview_table_section(theme_buckets: list[ReportThemeBucket]) -> list[str]:
    lines = [
        "| 重点方向 | 文章数 | 重点期刊 |",
        "| --- | ---: | --- |",
    ]
    if not theme_buckets:
        lines.append("| 暂无明显方向 | 0 | 暂无 |")
        return lines
    for bucket in theme_buckets[:6]:
        journal_text = "、".join(bucket.journals[:3]) if bucket.journals else "暂无"
        lines.append(f"| {escape_table_cell(bucket.display)} | {bucket.count} | {escape_table_cell(journal_text)} |")
    return lines


def build_objective_overview_section(
    summaries: list[ArticleSummaryResult],
    theme_buckets: list[ReportThemeBucket],
    journal_counts: list[tuple[str, int]],
    *,
    report_analysis: ReportAnalysis | None = None,
) -> list[str]:
    if not summaries:
        return ["- 本周暂无已生成单篇总结的论文，暂不形成客观概览。"]
    top_themes = "、".join(f"{bucket.display}（{bucket.count}篇）" for bucket in theme_buckets[:4]) or "暂无明显聚集方向"
    top_journals = "、".join(f"{journal}（{count}篇）" for journal, count in journal_counts[:3]) or "暂无明显集中期刊"
    lines = [
        f"- 本周新论文主要分布在 {top_themes}，重点集中于 {top_journals}。"
    ]
    if report_analysis and report_analysis.overview_bullets:
        for bullet in report_analysis.overview_bullets[:2]:
            lines.append(f"- {bullet}")
    else:
        novelty = summarize_cross_theme_signal(theme_buckets)
        lines.append(f"- 值得注意的是，本周最突出的共同点在于 {novelty}。")
    return lines


def summarize_cross_theme_signal(theme_buckets: list[ReportThemeBucket]) -> str:
    if len(theme_buckets) >= 2:
        return f"{theme_buckets[0].display} 与 {theme_buckets[1].display} 两类问题出现频率较高，并且在部分期刊中形成交叉关注"
    if theme_buckets:
        return f"{theme_buckets[0].display} 是最明确的聚焦方向"
    return "当前样本尚未形成稳定的共同主题"


def build_preference_overview_section(
    summaries: list[ArticleSummaryResult],
    preferences: UserPreferenceProfile,
    *,
    report_analysis: ReportAnalysis | None = None,
) -> list[str]:
    relevant_pool = select_preference_hits(summaries, preferences, limit=8)
    if not relevant_pool:
        return ["- 本周与当前研究主线直接重合的内容不多，尚未出现明显聚焦于热层密度、热层风、卫星环境或业务化预报的问题链条。"]
    preferred = relevant_pool[:4]
    linked_summaries = select_supervised_llm_preference_links(
        report_analysis.preference_paper_indices if report_analysis else [],
        summaries,
        preferences,
        limit=3,
    ) or preferred[:3]
    title_text = "；".join(linked_paper_title(summary) for summary in linked_summaries)
    llm_line = supervise_preference_section_text(
        report_analysis.preference_overview if report_analysis else "",
        relevant_pool,
        preferences,
        section="preference_overview",
    )
    if llm_line:
        return [f"- {llm_line}对应论文包括：{title_text}。"]
    theme_text = "、".join(preference_themes_for_summaries(preferred, preferences)) or "热层密度、热层风、卫星环境等方向"
    return [f"- 与当前工作最贴近的内容主要落在 {theme_text}，对应论文包括：{title_text}。"]


def build_recommended_papers_section(highlight_summaries: list[ArticleSummaryResult]) -> list[str]:
    if not highlight_summaries:
        return ["1. 本周暂无满足推荐阈值的重点论文。"]
    lines: list[str] = []
    for index, summary in enumerate(highlight_summaries, start=1):
        lines.extend(format_highlight_block(index, summary))
    return lines


def build_recommended_processes_section(
    highlight_summaries: list[ArticleSummaryResult],
    theme_buckets: list[ReportThemeBucket],
    *,
    report_analysis: ReportAnalysis | None = None,
) -> list[str]:
    lines: list[str] = []
    if report_analysis and report_analysis.daily_suggestions:
        for item in report_analysis.daily_suggestions[:4]:
            lines.append(f"- {normalize_report_phrase(item)}")
        return lines
    process_labels = top_process_labels(highlight_summaries, theme_buckets)
    if not process_labels:
        return ["- 本周暂无明确需要额外跟踪的共同事件或物理过程。"]
    for label in process_labels:
        lines.append(f"- {label}")
    return lines


def top_process_labels(highlight_summaries: list[ArticleSummaryResult], theme_buckets: list[ReportThemeBucket]) -> list[str]:
    labels: list[str] = []
    for bucket in theme_buckets[:6]:
        if bucket.display not in labels:
            labels.append(bucket.display)
    for summary in highlight_summaries:
        for tag in theme_tags_for_summary(summary):
            display = display_report_theme(tag)
            if display not in labels:
                labels.append(display)
            if len(labels) >= 4:
                return labels
    return labels[:4]


def build_work_implications_section(
    highlight_summaries: list[ArticleSummaryResult],
    preferences: UserPreferenceProfile,
    *,
    report_analysis: ReportAnalysis | None = None,
) -> list[str]:
    relevant_pool = select_preference_hits(highlight_summaries, preferences, limit=8)
    if not relevant_pool:
        return ["- 本周暂未看到足以直接推进当前主线工作的集中证据；后续仍可优先跟踪热层密度、热层风、卫星环境和预报建模四类条目。"]
    preferred = relevant_pool[:3]
    linked_summaries = select_supervised_llm_preference_links(
        report_analysis.work_implication_paper_indices if report_analysis else [],
        highlight_summaries,
        preferences,
        limit=2,
    ) or preferred[:2]
    title_text = "；".join(linked_paper_title(summary) for summary in linked_summaries)
    llm_line = supervise_preference_section_text(
        report_analysis.work_implication if report_analysis else "",
        relevant_pool,
        preferences,
        section="work_implication",
    )
    if llm_line:
        return [f"- {llm_line}可优先细读：{title_text}。"]
    theme_text = "、".join(preference_themes_for_summaries(preferred, preferences)) or "当前研究主线"
    return [f"- 这批论文对当前工作的启发主要落在 {theme_text}，可优先从 {title_text} 对应的问题设置、观测/数据组合和结果组织方式继续细读。"]


def format_highlight_block(index: int, summary: ArticleSummaryResult) -> list[str]:
    row = summary.row
    tags = build_tag_line(summary.tags)
    recommendation_reason = build_report_recommendation_reason(summary)
    return [
        f"{index}. 英文题目：{linked_paper_title(summary)}",
        f"   - 所在期刊：{normalize_report_journal_name(row['source_name'] or row['journal_title'])}",
        f"   - 中文题目：{summary.chinese_title}",
        f"   - 推荐理由：{recommendation_reason}",
        f"   - 标签： {tags}",
        f"   - 网址：{build_doi_url(row['doi'], row['url'])}",
    ]


def build_report_recommendation_reason(summary: ArticleSummaryResult) -> str:
    focus = build_report_focus_clause(summary)
    value = build_report_value_clause(summary)
    if focus and value:
        return f"{focus}，{value}。"
    if focus:
        return f"{focus}。"
    fallback = normalize_report_phrase(str(summary.recommendation or "").strip()).rstrip("。；;，, ")
    if fallback and "如果你在跟踪" not in fallback and "值得先看摘要" not in fallback:
        return fallback + "。"
    return "适合先看其研究对象界定、方法路径和核心结论。"


def build_report_focus_clause(summary: ArticleSummaryResult) -> str:
    title = normalize_report_phrase(str(summary.chinese_title or "").strip()).rstrip("。；;，, ")
    if not title:
        title = normalize_report_phrase(display_title(summary.row)).rstrip("。；;，, ")
    if not title:
        return ""
    return f"围绕“{title}”展开"


def build_report_value_clause(summary: ArticleSummaryResult) -> str:
    primary_haystack, secondary_haystack = build_report_reason_haystacks(summary)
    aspects = collect_report_recommendation_aspects(primary_haystack, secondary_haystack)
    if not aspects:
        return "适合先看其研究对象界定、方法路径和核心结论"
    if len(aspects) == 1:
        return f"适合先看其{aspects[0]}"
    if len(aspects) == 2:
        return f"适合先看其{aspects[0]}，以及{aspects[1]}"
    return f"适合先看其{aspects[0]}、{aspects[1]}和{aspects[2]}"


def build_report_reason_haystacks(summary: ArticleSummaryResult) -> tuple[str, str]:
    primary_parts = [
        str(summary.chinese_title or ""),
        " ".join(str(tag or "") for tag in summary.tags),
    ]
    secondary_parts = [
        str(summary.one_sentence or ""),
        str(summary.body or ""),
    ]
    primary = normalize_report_phrase(" ".join(primary_parts).lower())
    secondary = normalize_report_phrase(" ".join(secondary_parts).lower())
    return primary, secondary


def collect_report_recommendation_aspects(primary_haystack: str, secondary_haystack: str) -> list[str]:
    aspects: list[str] = []
    for phrases, aspect in REPORT_RECOMMENDATION_PRIMARY_ASPECT_RULES:
        if any(phrase.lower() in primary_haystack for phrase in phrases):
            if aspect not in aspects:
                aspects.append(aspect)
        if len(aspects) >= 2:
            break
    if len(aspects) < 2:
        for phrases, aspect in REPORT_RECOMMENDATION_SECONDARY_ASPECT_RULES:
            if any(phrase.lower() in secondary_haystack for phrase in phrases):
                if aspect not in aspects:
                    aspects.append(aspect)
            if len(aspects) >= 2:
                break
    return aspects


def build_topic_recommendations_section(
    buckets: list[ReportThemeBucket],
    *,
    report_analysis: ReportAnalysis | None = None,
    preferences: UserPreferenceProfile,
) -> list[str]:
    if not buckets:
        return ["- 无共同主题。当前收录论文尚未在同一具体科学问题下形成多篇聚类。"]
    lines: list[str] = []
    for index, bucket in enumerate(buckets[:4], start=1):
        lines.extend(format_topic_section(index, bucket, report_analysis=report_analysis, preferences=preferences))
    return lines


def format_topic_section(
    index: int,
    bucket: ReportThemeBucket,
    *,
    report_analysis: ReportAnalysis | None = None,
    preferences: UserPreferenceProfile,
) -> list[str]:
    related_summaries = rank_section_summaries(list(bucket.summaries), preferences)[:4]
    linked_titles = "；".join(linked_paper_title(summary) for summary in related_summaries) if related_summaries else "暂无相关文章"
    llm_summary = report_analysis.topic_summary(bucket.display) if report_analysis else None
    journals = "、".join(bucket.journals[:3]) if bucket.journals else "暂无"
    summary_line = summarize_topic_summary(bucket, llm_summary)
    return [
        f"### 主题 {index}：{bucket.display}",
        f"- 推荐理由：本周有 {bucket.count} 篇文章围绕这一问题展开，重点分布在 {journals}。",
        f"- 主题分析：{summary_line}",
        f"- 相关文章：{linked_titles}。",
    ]


def summarize_theme_bucket(bucket: ReportThemeBucket) -> str:
    one_sentences = [summary.one_sentence for summary in bucket.summaries[:3] if summary.one_sentence]
    if one_sentences:
        return "相关文章分别指出：" + "；".join(one_sentences[:2])
    return f"{bucket.display} 是本周多篇文章共同涉及的具体问题。"


def build_journal_roundup_section(
    summaries: list[ArticleSummaryResult],
    journal_counts: list[tuple[str, int]],
    *,
    report_analysis: ReportAnalysis | None = None,
    preferences: UserPreferenceProfile,
) -> list[str]:
    source_groups: dict[str, list[ArticleSummaryResult]] = defaultdict(list)
    source_display_names: dict[str, str] = {}
    for summary in summaries:
        raw_source_name = summary.row["source_name"] or summary.row["journal_title"]
        source_key = normalize_report_journal_name(raw_source_name)
        source_groups[source_key].append(summary)
        source_display_names.setdefault(source_key, display_report_journal_name(raw_source_name))
    lines: list[str] = []
    if not source_groups:
        return ["### 暂无期刊", "- 本周暂无可汇总的期刊内容。"]
    sorted_journals = [journal for journal, _ in journal_counts if journal in source_groups]
    for journal in sorted_journals:
        lines.extend(
            format_journal_section(
                source_display_names.get(journal, display_report_journal_name(journal)),
                source_groups[journal],
                report_analysis=report_analysis,
                preferences=preferences,
                journal_key=journal,
            )
        )
    return lines


def format_journal_section(
    source_name: str,
    summaries: list[ArticleSummaryResult],
    *,
    report_analysis: ReportAnalysis | None = None,
    preferences: UserPreferenceProfile,
    journal_key: str | None = None,
) -> list[str]:
    theme_counts: Counter[str] = Counter()
    theme_examples: dict[str, list[ArticleSummaryResult]] = defaultdict(list)
    for summary in summaries:
        for tag in theme_tags_for_summary(summary):
            display = display_report_theme(tag)
            theme_counts[display] += 1
            theme_examples[display].append(summary)
    focus_directions = [label for label, _ in theme_counts.most_common(3)]
    detail_lines: list[str] = []
    for label, count in theme_counts.most_common(3):
        examples = "；".join(summary.one_sentence for summary in theme_examples[label][:2] if summary.one_sentence)
        detail_lines.append(f"{count} 篇关注 {label}，{examples or '相关内容在单篇总结中已有说明'}")
    llm_summary = report_analysis.journal_summary(journal_key or source_name) if report_analysis else None
    top_summaries = rank_section_summaries(summaries, preferences)[:3]
    lines = [
        f"### {source_name}",
        f"- 今日新增文章数：{len(summaries)}",
        f"- 重点方向：{'、'.join(focus_directions) if focus_directions else '暂无明显聚焦方向'}",
        f"- 分析：{llm_summary or '；'.join(detail_lines) or '本期刊本周样本较少，暂未形成稳定聚类。'}",
    ]
    if top_summaries:
        lines.append("- 具体论文推荐：")
        for index, summary in enumerate(top_summaries, start=1):
            lines.append(f"  {index}. {linked_paper_title(summary)}")
            lines.append(f"     - 中文概括：{summary.body}")
    else:
        lines.append("- 具体论文推荐：暂无。")
    return lines


def format_missing_source_section(rows: list, skipped_summary_rows: list[SkippedArticleSummary] | None = None) -> list[str]:
    skipped_summary_rows = skipped_summary_rows or []
    if not rows and not skipped_summary_rows:
        return ["- 无。"]
    lines: list[str] = []
    if skipped_summary_rows:
        lines.append("#### 未完成单篇总结的文献（LLM 输出失败）")
        for index, item in enumerate(skipped_summary_rows, start=1):
            citation = build_report_apa_citation(item.row)
            reason = item.reason or item.error or "单篇总结生成未完成。"
            lines.append(f"{index}. {citation}")
            lines.append(f"   - 原因：{reason}")
    if rows:
        if lines:
            lines.append("")
        lines.append("#### 未获取摘要/全文的文献（来源材料缺失）")
        for index, row in enumerate(rows, start=1):
            citation = build_report_apa_citation(row)
            lines.append(f"{index}. {citation}")
            diagnostics = _missing_source_diagnostics(row)
            if diagnostics:
                lines.append(f"   - 来源诊断：{'；'.join(diagnostics)}")
            manual_links = _missing_source_manual_links(row)
            if manual_links:
                lines.append(f"   - 人工检索：{' / '.join(manual_links)}")
    return lines


def _missing_source_diagnostics(row) -> list[str]:
    values: list[str] = []
    for key in ("summary_source_diagnostics", "summary_source_error"):
        raw = str(row_value(row, key, "") or "")
        for item in raw.splitlines():
            clean = re.sub(r"\s+", " ", item).strip()
            if clean and clean not in values:
                values.append(clean)
    return values[:8]


def _missing_source_manual_links(row) -> list[str]:
    raw_urls = str(row_value(row, "summary_manual_search_urls", "") or "")
    urls = [item.strip() for item in raw_urls.splitlines() if item.strip()]
    if not urls:
        doi = str(row_value(row, "doi", "") or "").strip()
        url = str(row_value(row, "url", "") or "").strip()
        if doi:
            urls.append(build_doi_url(doi))
        if url and url not in urls:
            urls.append(url)
    links: list[str] = []
    seen_labels: set[str] = set()
    for url in urls:
        label = _manual_search_label(url)
        if label in seen_labels and label not in {"DOI", "ScienceDirect"}:
            continue
        seen_labels.add(label)
        links.append(f"[{label}]({url})")
        if len(links) >= 5:
            break
    return links


def _manual_search_label(url: str) -> str:
    lowered = str(url or "").lower()
    if "doi.org/" in lowered:
        return "DOI"
    if "sciencedirect.com" in lowered:
        return "ScienceDirect"
    if "scholar.google" in lowered:
        return "Google Scholar"
    if "researchgate.net" in lowered:
        return "ResearchGate"
    if "google.com/search" in lowered:
        return "Google"
    match = re.search(r"https?://([^/]+)", str(url or ""))
    return match.group(1) if match else "链接"


def build_report_apa_citation(row) -> str:
    citation = build_apa_citation(row)
    raw_journal = str(row_value(row, "source_name", "") or row_value(row, "journal_title", "") or "")
    normalized_journal = normalize_report_journal_name(raw_journal)
    if raw_journal and normalized_journal != raw_journal:
        citation = citation.replace(f". {raw_journal}. ", f". {normalized_journal}. ")
    return citation


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
    tags = {str(tag or "").strip() for tag in summary.tags if str(tag or "").strip()}
    allowed_themes = set(preferences.priority_themes or REPORT_DIRECT_THEME_RULES.keys())
    matched: list[str] = []
    for theme, rule in REPORT_DIRECT_THEME_RULES.items():
        if theme not in allowed_themes:
            continue
        positive_tags = set(rule.get("tags", set()))
        if positive_tags and tags.intersection(positive_tags):
            matched.append(theme)
            continue
        phrases = [item.lower() for item in rule.get("phrases", ())]
        if not any(phrase in text for phrase in phrases):
            continue
        required_any = [item.lower() for item in rule.get("required_any", ())]
        if required_any and not any(item in text for item in required_any):
            continue
        negative_phrases = [item.lower() for item in rule.get("negative_phrases", ())]
        if negative_phrases and any(item in text for item in negative_phrases):
            continue
        if has_negated_preference_match(text, phrases):
            continue
        matched.append(theme)
    return matched


def preference_match_score(summary: ArticleSummaryResult, preferences: UserPreferenceProfile) -> int:
    return len(matched_preference_themes(summary, preferences))


def build_summary_match_text(summary: ArticleSummaryResult) -> str:
    return " ".join(
        [
            display_title(summary.row).lower(),
            summary.chinese_title.lower(),
            summary.one_sentence.lower(),
            summary.body.lower(),
        ]
    )


def has_negated_preference_match(text: str, phrases: list[str]) -> bool:
    for phrase in phrases:
        escaped = re.escape(phrase)
        if re.search(rf"(未直接展开|未讨论|不涉及|不直接研究|不能外推(?:到)?|未展开).{{0,16}}{escaped}", text):
            return True
        if re.search(rf"{escaped}.{{0,8}}(并非重点|未直接展开|未讨论|不涉及|不直接研究)", text):
            return True
    return False


def summarize_topic_summary(bucket: ReportThemeBucket, llm_summary: str | None) -> str:
    summary = normalize_report_phrase(str(llm_summary or "").strip())
    if summary and not is_low_quality_topic_summary(summary):
        return summary
    return summarize_theme_bucket(bucket)


def is_low_quality_topic_summary(text: str) -> bool:
    clean = normalize_report_phrase(text).strip()
    if not clean:
        return True
    if any(re.search(pattern, clean) for pattern in LOW_QUALITY_TOPIC_PATTERNS):
        return True
    if clean.count("对象/") + clean.count("事件/") + clean.count("方法/") >= 2:
        return True
    return False


def normalize_report_phrase(text: str) -> str:
    clean = str(text or "").strip()
    for source, target in REPORT_TERM_NORMALIZATIONS.items():
        clean = clean.replace(source, target)
    return clean


def supervise_preference_section_text(
    text: str,
    preferred: list[ArticleSummaryResult],
    preferences: UserPreferenceProfile,
    *,
    section: str,
) -> str | None:
    clean = normalize_report_phrase(text).strip()
    if not clean:
        return None
    lowered = clean.lower()
    if any(pattern in lowered for pattern in LOW_QUALITY_PREFERENCE_PATTERNS):
        return None
    if "[[" in clean or "]]" in clean:
        return None
    if "{" in clean or "}" in clean:
        return None
    if len(clean) < 18:
        return None
    allowed_themes = set(preference_themes_for_summaries(preferred, preferences))
    if not allowed_themes:
        return None
    if mentions_disallowed_preference_themes(clean, allowed_themes):
        return None
    if section == "work_implication" and not has_work_implication_signal(clean):
        return None
    if section == "preference_overview" and "直接" not in clean and "相关" not in clean and "贴近" not in clean:
        clean = f"与当前工作直接相关的内容主要体现在{clean.rstrip('。')}"
    return clean.rstrip("。；;，, ") + "。"


def mentions_disallowed_preference_themes(text: str, allowed_themes: set[str]) -> bool:
    for theme in REPORT_DIRECT_THEME_RULES:
        if theme in text and theme not in allowed_themes:
            return True
    return False


def has_work_implication_signal(text: str) -> bool:
    signals = ("启发", "借鉴", "可用于", "可优先", "值得继续", "可作为", "可帮助", "建议")
    return any(signal in text for signal in signals)


def select_supervised_llm_preference_links(
    indices: list[int],
    summaries: list[ArticleSummaryResult],
    preferences: UserPreferenceProfile,
    *,
    limit: int,
) -> list[ArticleSummaryResult]:
    selected: list[ArticleSummaryResult] = []
    seen: set[str] = set()
    for idx in indices:
        if idx < 1 or idx > len(summaries):
            continue
        summary = summaries[idx - 1]
        if preference_match_score(summary, preferences) <= 0:
            continue
        key = str(summary.row["doi"] or summary.note_title)
        if key in seen:
            continue
        selected.append(summary)
        seen.add(key)
        if len(selected) >= limit:
            break
    return selected


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
    limit: int = 4,
) -> list[ArticleSummaryResult]:
    ranked = sorted(summaries, key=lambda item: highlight_priority(item, preferences), reverse=True)
    selected: list[ArticleSummaryResult] = []
    seen_theme_tags: set[str] = set()

    for summary in ranked:
        if article_summary_quality_score(summary) <= 1:
            continue
        preferred_tags = set(theme_tags_for_summary(summary))
        if preferred_tags and preferred_tags.isdisjoint(seen_theme_tags):
            selected.append(summary)
            seen_theme_tags.update(preferred_tags)
        elif len(selected) < 2:
            selected.append(summary)
            seen_theme_tags.update(preferred_tags)
        if len(selected) >= limit:
            break
    return selected[:limit]


def highlight_priority(summary: ArticleSummaryResult, preferences: UserPreferenceProfile) -> tuple[float, float, float, str]:
    row = summary.row
    specificity_bonus = len(theme_tags_for_summary(summary)) * 5
    override_bonus = 5 if get_override(row) else 0
    relevance = float(row["relevance_score"])
    preference_bonus = preference_match_score(summary, preferences) * 8
    quality_bonus = article_summary_quality_score(summary) * 4
    return (specificity_bonus + override_bonus + preference_bonus + quality_bonus + relevance, quality_bonus, relevance, row["published_date"])


def escape_table_cell(text: str) -> str:
    return str(text or "").replace("|", "\\|")


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
    except ManualResponsePending:
        raise
    except AnalysisQuotaExceeded:
        raise
    except Exception:
        return None
