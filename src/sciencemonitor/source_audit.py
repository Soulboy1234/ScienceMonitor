from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path

from .config import audit_logs_root, load_sources, load_topics, project_root
from .crossref import CrossrefClient
from .http import HTTPClient
from .topics import TopicClassifier


@dataclass
class SourceAuditRow:
    source_id: str
    journal_title: str
    mode: str
    issn: str
    app_fetched_count: int | None
    kept_count: int | None
    exact_online_count: int | None
    exact_pub_count: int | None
    possible_missing: str
    note: str
    app_sample_titles: list[str]
    exact_online_sample_titles: list[str]
    exact_pub_sample_titles: list[str]


def generate_source_audit(
    report_date: date,
    window_days: int = 7,
    max_per_source: int = 100,
    root: Path | None = None,
) -> tuple[Path, Path, list[SourceAuditRow]]:
    root = root or project_root()
    since_date = report_date - timedelta(days=max(window_days - 1, 0))
    sources = load_sources(root / "config" / "sources.json")
    topics = load_topics(root / "config" / "topics.json")
    http = HTTPClient(timeout=10)
    crossref = CrossrefClient(http)
    classifier = TopicClassifier(topics)

    rows: list[SourceAuditRow] = []
    for source in sources:
        app_fetched_count: int | None
        kept_count: int | None
        app_sample_titles: list[str]
        note_parts: list[str] = []

        try:
            app_papers = crossref.fetch_recent_works(
                source=source,
                since_date=since_date,
                until_date=report_date,
                max_rows=max_per_source,
            )
            app_fetched_count = len(app_papers)
            kept_count = 0
            for paper in app_papers:
                result = classifier.classify(paper, source)
                if classifier.should_keep(result, source):
                    kept_count += 1
            app_sample_titles = [paper.title for paper in app_papers[:3]]
        except Exception as exc:
            app_fetched_count = None
            kept_count = None
            app_sample_titles = []
            note_parts.append(f"程序抓取错误: {exc}")

        exact_online_count = None
        exact_pub_count = None
        exact_online_sample_titles: list[str] = []
        exact_pub_sample_titles: list[str] = []

        if source.issn:
            exact_online_count, exact_online_sample_titles, online_error = _crossref_exact_count(
                http=http,
                issn=source.issn,
                since_date=since_date,
                until_date=report_date,
                field="online",
            )
            exact_pub_count, exact_pub_sample_titles, pub_error = _crossref_exact_count(
                http=http,
                issn=source.issn,
                since_date=since_date,
                until_date=report_date,
                field="pub",
            )
            if online_error:
                note_parts.append(f"online核验失败: {online_error}")
            if pub_error:
                note_parts.append(f"pub核验失败: {pub_error}")
        else:
            note_parts.append("未配置ISSN，无法做Crossref精确核验")

        expected_count = exact_online_count if source.crossref_date_field == "online" else exact_pub_count
        possible_missing = _possible_missing(app_fetched_count, expected_count)

        if possible_missing == "是":
            note_parts.append(
                f"程序抓取 {app_fetched_count} 篇，少于 Crossref 精确计数 {expected_count} 篇"
            )
        elif possible_missing == "否":
            if expected_count == 0:
                note_parts.append("Crossref 精确核验显示近7天无记录")
            else:
                note_parts.append("程序抓取数与 Crossref 精确计数一致")
        else:
            if expected_count is None:
                note_parts.append("缺少可用的精确计数，建议官网或RSS复核")
            elif app_fetched_count is not None and app_fetched_count > expected_count:
                note_parts.append("程序抓取数高于精确计数，可能存在模糊匹配或时间字段差异")

        if (
            app_fetched_count is not None
            and kept_count is not None
            and app_fetched_count > 0
            and kept_count == 0
            and source.mode != "full"
        ):
            note_parts.append("有候选文献，但当前过滤规则全部剔除了")

        rows.append(
            SourceAuditRow(
                source_id=source.id,
                journal_title=source.journal_title,
                mode=source.mode,
                issn=source.issn,
                app_fetched_count=app_fetched_count,
                kept_count=kept_count,
                exact_online_count=exact_online_count,
                exact_pub_count=exact_pub_count,
                possible_missing=possible_missing,
                note="；".join(note_parts),
                app_sample_titles=app_sample_titles,
                exact_online_sample_titles=exact_online_sample_titles,
                exact_pub_sample_titles=exact_pub_sample_titles,
            )
        )
        time.sleep(0.15)

    report_dir = audit_logs_root(root)
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / f"source_audit_{report_date.isoformat()}.md"
    json_path = report_dir / f"source_audit_{report_date.isoformat()}.json"
    markdown_path.write_text(_build_markdown(report_date, window_days, rows), encoding="utf-8")
    json_path.write_text(
        json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return markdown_path, json_path, rows


def _crossref_exact_count(
    http: HTTPClient,
    issn: str,
    since_date: date,
    until_date: date,
    field: str,
) -> tuple[int | None, list[str], str | None]:
    if field == "online":
        date_filter = (
            f"issn:{issn},from-online-pub-date:{since_date.isoformat()},"
            f"until-online-pub-date:{until_date.isoformat()}"
        )
    else:
        date_filter = f"issn:{issn},from-pub-date:{since_date.isoformat()},until-pub-date:{until_date.isoformat()}"

    params = {
        "filter": date_filter,
        "rows": "5",
        "sort": "published",
        "order": "desc",
        "select": "DOI,title,container-title,published,published-online,published-print,issued",
    }
    try:
        payload = http.get_json(CrossrefClient.API_URL, params=params)
    except Exception as exc:
        return None, [], str(exc)

    message = payload.get("message", {})
    total = int(message.get("total-results", 0))
    sample_titles = [(item.get("title") or [""])[0] for item in message.get("items", [])[:3]]
    return total, sample_titles, None


def _possible_missing(app_fetched_count: int | None, expected_count: int | None) -> str:
    if app_fetched_count is None or expected_count is None:
        return "待核"
    if app_fetched_count < expected_count:
        return "是"
    if app_fetched_count == expected_count:
        return "否"
    return "待核"


def _build_markdown(report_date: date, window_days: int, rows: list[SourceAuditRow]) -> str:
    lines: list[str] = []
    lines.append("# Source Audit")
    lines.append("")
    lines.append(f"- 日期：{report_date.isoformat()}")
    lines.append(f"- 审计窗口：近 {window_days} 天")
    lines.append(f"- 期刊数：{len(rows)}")
    lines.append(f"- 可能漏抓：{sum(1 for row in rows if row.possible_missing == '是')} 本")
    lines.append(f"- 待进一步核验：{sum(1 for row in rows if row.possible_missing == '待核')} 本")
    lines.append("")
    lines.append("| 期刊 | 模式 | 程序抓到 | 程序保留 | Crossref-online | Crossref-pub | 是否可能漏抓 | 备注 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.journal_title,
                    row.mode,
                    _fmt_count(row.app_fetched_count),
                    _fmt_count(row.kept_count),
                    _fmt_count(row.exact_online_count),
                    _fmt_count(row.exact_pub_count),
                    row.possible_missing,
                    row.note.replace("|", "/"),
                ]
            )
            + " |"
        )

    suspicious_rows = [row for row in rows if row.possible_missing != "否"]
    if suspicious_rows:
        lines.append("")
        lines.append("## 重点复核")
        lines.append("")
        for row in suspicious_rows:
            lines.append(f"### {row.journal_title}")
            lines.append(f"- 模式：{row.mode}")
            lines.append(f"- 抓到 / 保留：{_fmt_count(row.app_fetched_count)} / {_fmt_count(row.kept_count)}")
            lines.append(
                f"- Crossref-online / pub：{_fmt_count(row.exact_online_count)} / {_fmt_count(row.exact_pub_count)}"
            )
            lines.append(f"- 判断：{row.possible_missing}")
            lines.append(f"- 备注：{row.note}")
            if row.app_sample_titles:
                lines.append(f"- 程序样例：{'；'.join(row.app_sample_titles)}")
            if row.exact_online_sample_titles:
                lines.append(f"- online样例：{'；'.join(row.exact_online_sample_titles)}")
            if row.exact_pub_sample_titles:
                lines.append(f"- pub样例：{'；'.join(row.exact_pub_sample_titles)}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _fmt_count(value: int | None) -> str:
    return "-" if value is None else str(value)
