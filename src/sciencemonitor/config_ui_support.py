from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .article_index import sync_out_library
from .article_summaries import render_article_summary
from .article_summary_markdown import load_article_summary_template
from .article_summary_meta import abbreviate_journal_name
from .article_summary_text import build_note_title
from .chatgpt_web_manual import (
    ManualRequestBundle,
    import_manual_response,
    import_manual_response_from_recommended_file,
    list_manual_requests,
    load_manual_response,
    prepare_manual_request_bundle,
)
from .config import (
    article_summaries_root,
    chatgpt_web_manual_requests_root,
    chatgpt_web_manual_responses_root,
    deep_reads_root,
    load_sources,
    reports_root,
    templates_root,
)
from .deep_read_markdown import _run_deep_read_review_loop, _validate_deep_read_markdown
from .deep_reads import (
    _build_deep_read_output_path,
    _build_knowledge_position_text,
    _find_related_summary,
    _load_deep_read_template,
    _normalize_deep_read_analysis,
    _render_deep_read_markdown,
)
from .llm import AnalysisEngine, ArticleAnalysis, DeepReadAnalysis
from .llm_contracts import build_article_schema, build_deep_read_schema, build_manual_article_prompt, build_manual_deep_read_prompt
from .utils import clean_title_text


def collect_config_ui_state(project: Path) -> dict:
    summary_root = article_summaries_root(project)
    deep_root = deep_reads_root(project)
    report_root = reports_root(project)
    manual_requests = list_manual_requests(project, limit=0)
    manual_response_count = _count_json_files(chatgpt_web_manual_responses_root(project))
    counts = {
        "article_summaries": _count_markdown_files(summary_root),
        "deep_reads": _count_markdown_files(deep_root),
        "reports": _count_markdown_files(report_root),
        "manual_requests": len(manual_requests),
        "manual_responses": manual_response_count,
        "manual_files": _count_manual_files(project),
    }
    return {
        "counts": counts,
        "latest_article_summary": _latest_markdown_file(summary_root),
        "latest_deep_read": _latest_markdown_file(deep_root),
        "latest_report": _latest_markdown_file(report_root),
        "journals": _load_monitored_journal_labels(project),
        "journal_groups": _load_monitored_journal_groups(project),
        "token_usage": _detect_token_usage(project),
        "maintenance_status": _load_latest_maintenance_status(project),
    }


def create_manual_request_from_ui(
    project: Path,
    *,
    request_kind: str,
    title: str,
    doi: str,
    journal: str = "",
    url: str = "",
) -> ManualRequestBundle:
    engine = AnalysisEngine(project)
    engine.provider = "chatgpt_web_manual"
    engine.config["provider"] = "chatgpt_web_manual"
    cleaned_title = clean_title_text(title or "")
    if request_kind == "article_summary":
        row = _manual_article_row(title=cleaned_title, doi=doi, journal=journal, url=url)
        request_id = f"article_{engine._article_cache_key(row)}"
        prompt = build_manual_article_prompt(row)
        schema = build_article_schema()
        context = engine._manual_context_for_article(row)
    elif request_kind == "deep_read":
        metadata = _manual_deep_read_metadata(title=cleaned_title, doi=doi, journal=journal, url=url)
        cache_basis = "|".join(
            [
                "deep_read_template_v5",
                str(metadata.get("doi", "")),
                str(metadata.get("title", "")),
                str(metadata.get("journal", "")),
                "manual_web_search",
                engine._analysis_signature("deep_reads"),
            ]
        )
        request_id = f"deep_read_{hashlib.sha1(cache_basis.encode('utf-8')).hexdigest()}"
        prompt = build_manual_deep_read_prompt(metadata, None)
        schema = build_deep_read_schema()
        context = engine._manual_context_for_deep_read(metadata, "")
    else:
        raise ValueError("manual request kind 只支持 article_summary 或 deep_read。")
    return prepare_manual_request_bundle(
        project,
        request_id=request_id,
        request_kind=request_kind,
        title=cleaned_title or doi or request_id,
        prompt=prompt,
        schema=schema,
        reasoning_effort=engine._analysis_reasoning_effort("article_summaries" if request_kind == "article_summary" else "deep_reads"),
        context=context,
    )


def import_manual_response_and_generate(
    project: Path,
    *,
    request_id: str,
    response_text: str | None = None,
) -> dict[str, str]:
    if response_text is None:
        import_manual_response_from_recommended_file(project, request_id=request_id)
    else:
        import_manual_response(project, request_id=request_id, response_text=response_text)

    metadata = _load_request_metadata(project, request_id)
    schema = metadata.get("schema", {})
    payload = load_manual_response(
        project,
        request_id=request_id,
        prompt_signature=str(metadata.get("prompt_signature", "") or ""),
        schema=schema if isinstance(schema, dict) else None,
    )
    if not payload:
        raise ValueError(f"导入后仍未找到 request_id={request_id} 的结构化响应。")
    request_kind = str(metadata.get("request_kind", "") or "")
    if request_kind == "article_summary":
        output_path = _generate_manual_article_summary(project, metadata, payload)
        return {
            "title": "人工中转文章总结已生成",
            "message": "已导入响应并生成单篇总结。",
            "path": str(output_path),
            "extra_path": "",
        }
    if request_kind == "deep_read":
        output_path = _generate_manual_deep_read(project, metadata, payload)
        return {
            "title": "人工中转深度解读已生成",
            "message": "已导入响应并生成深度解读。",
            "path": str(output_path),
            "extra_path": "",
        }
    raise ValueError(f"不支持的人工中转类型：{request_kind}")


def resolve_request_id_from_upload(project: Path, *, filename: str, response_text: str, request_id_hint: str = "") -> str:
    if request_id_hint.strip():
        return request_id_hint.strip()
    stripped = response_text.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            wrapped_request_id = str(payload.get("request_id", "") or "").strip()
            if wrapped_request_id:
                return wrapped_request_id
    for item in list_manual_requests(project, limit=0):
        if item.response_filename == filename:
            return item.request_id
    raise ValueError("无法从上传文件自动识别 request_id。请确保文件名与推荐响应文件名一致，或手动填写 request_id。")


def _manual_article_row(*, title: str, doi: str, journal: str, url: str) -> dict:
    return {
        "title": title or doi or "Untitled",
        "doi": doi or "",
        "url": url or (f"https://doi.org/{doi}" if doi else ""),
        "source_name": journal or "",
        "published_date": "",
        "authors": "",
        "topic_labels": "",
        "summary_source_kind": "",
        "fingerprint": hashlib.sha1(f"{doi}|{title}|{journal}|{url}".encode("utf-8")).hexdigest()[:20],
        "abstract": "",
        "notes": "",
    }


def _manual_deep_read_metadata(*, title: str, doi: str, journal: str, url: str) -> dict[str, str]:
    return {
        "title": title or doi or "Untitled",
        "doi": doi or "",
        "url": url or (f"https://doi.org/{doi}" if doi else ""),
        "journal": journal or "",
        "authors": "",
        "published_date": "",
        "raw_authors": "",
    }


def _generate_manual_article_summary(project: Path, metadata: dict, payload: dict) -> Path:
    hints = metadata.get("resource_hints", {})
    if not isinstance(hints, dict):
        hints = {}
    row = _manual_article_row(
        title=str(hints.get("title", "") or metadata.get("title", "") or ""),
        doi=str(hints.get("doi", "") or ""),
        journal=str(hints.get("journal", "") or ""),
        url=str(hints.get("url", "") or ""),
    )
    row["published_date"] = str(hints.get("published_date", "") or "")
    row["authors"] = str(hints.get("authors", "") or "").replace(", ", "\n")
    row["topic_labels"] = str(hints.get("topic_labels", "") or "").replace("、", "\n")
    tags = [str(item).strip() for item in payload.get("tags", []) if str(item).strip()]
    source_kind = "chatgpt_web_manual_search"
    if "信息来源/仅摘要" in tags or "仅基于摘要/元数据整理" in str(payload.get("supplement", "")):
        source_kind = "manual_web_abstract"
    row["summary_source_kind"] = source_kind
    analysis = ArticleAnalysis(
        chinese_title=str(payload.get("chinese_title", "") or "").strip(),
        tags=tags,
        body=str(payload.get("body", "") or "").strip(),
        supplement=str(payload.get("supplement", "") or "").strip(),
        recommendation=str(payload.get("recommendation", "") or "").strip(),
        one_sentence=str(payload.get("one_sentence", "") or "").strip(),
    )
    template_text = load_article_summary_template(templates_root(project) / "article_summary_template.md")
    note_title = build_note_title(row, analysis=analysis, root=project)
    markdown = render_article_summary(
        row,
        template_text,
        analysis=analysis,
        note_title=note_title,
        root=project,
    )
    from .article_summaries import _run_article_summary_review_loop

    markdown, issues = _run_article_summary_review_loop(
        row,
        template_text=template_text,
        note_title=note_title,
        markdown=markdown,
        analysis=analysis,
        root=project,
    )
    if issues:
        raise ValueError("人工中转文章总结未通过审核：" + "；".join(issues))
    output_dir = article_summaries_root(project)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{note_title}.md"
    output_path.write_text(markdown, encoding="utf-8")
    sync_out_library(project)
    return output_path


def _generate_manual_deep_read(project: Path, metadata: dict, payload: dict) -> Path:
    hints = metadata.get("resource_hints", {})
    if not isinstance(hints, dict):
        hints = {}
    normalized_metadata = _manual_deep_read_metadata(
        title=str(hints.get("title", "") or metadata.get("title", "") or ""),
        doi=str(hints.get("doi", "") or ""),
        journal=str(hints.get("journal", "") or ""),
        url=str(hints.get("url", "") or ""),
    )
    normalized_metadata["published_date"] = str(hints.get("published_date", "") or "")
    normalized_metadata["authors"] = str(hints.get("authors", "") or "")
    normalized_metadata["raw_authors"] = normalized_metadata["authors"].replace(", ", "\n")
    analysis = DeepReadAnalysis(
        chinese_title=str(payload.get("chinese_title", "") or "").strip(),
        tags=[str(item).strip() for item in payload.get("tags", []) if str(item).strip()],
        paper_type=str(payload.get("paper_type", "") or "").strip(),
        one_sentence_overview=str(payload.get("one_sentence_overview", "") or "").strip(),
        why=str(payload.get("why", "") or "").strip(),
        how=str(payload.get("how", "") or "").strip(),
        key_results=str(payload.get("key_results", "") or "").strip(),
        contribution=str(payload.get("contribution", "") or "").strip(),
        limitations=str(payload.get("limitations", "") or "").strip(),
        reproducibility=str(payload.get("reproducibility", "") or "").strip(),
        relation=str(payload.get("relation", "") or "").strip(),
        final_conclusion=str(payload.get("final_conclusion", "") or "").strip(),
        relation_to_my_work=str(payload.get("relation_to_my_work", "") or "").strip(),
        follow_up_questions=str(payload.get("follow_up_questions", "") or "").strip(),
        needs_manual_review=str(payload.get("needs_manual_review", "") or "").strip(),
        knowledge_position=str(payload.get("knowledge_position", "") or "").strip(),
    )
    analysis = _normalize_deep_read_analysis(
        project,
        analysis,
        metadata_title=str(normalized_metadata.get("title", "") or ""),
        full_text="",
        related_summary=_find_related_summary(project, str(normalized_metadata.get("doi", "") or "")),
    )
    template_text = _load_deep_read_template(templates_root(project) / "deep_reading_report_template.md")
    output_dir = deep_reads_root(project)
    output_dir.mkdir(parents=True, exist_ok=True)
    related_summary = _find_related_summary(project, str(normalized_metadata.get("doi", "") or ""))
    note_path = _build_deep_read_output_path(project, output_dir, normalized_metadata, analysis, related_summary)
    markdown = _render_deep_read_markdown(
        project=project,
        template_text=template_text,
        metadata=normalized_metadata,
        analysis=analysis,
        related_summary=related_summary,
        note_path=note_path,
        pdf_path=None,
        source_kind="chatgpt_web_manual_search",
        source_url=str(normalized_metadata.get("url", "") or ""),
        knowledge_position_text=_build_knowledge_position_text(project, note_path, sync_library=False),
    )
    markdown, review_issues = _run_deep_read_review_loop(markdown, tags=analysis.tags)
    validation_issues = review_issues + _validate_deep_read_markdown(markdown, is_output_note=True)
    if validation_issues:
        raise ValueError("人工中转深度解读未通过审核：" + "；".join(validation_issues))
    note_path.write_text(markdown, encoding="utf-8")
    sync_out_library(project)
    refreshed_markdown = _render_deep_read_markdown(
        project=project,
        template_text=template_text,
        metadata=normalized_metadata,
        analysis=analysis,
        related_summary=related_summary,
        note_path=note_path,
        pdf_path=None,
        source_kind="chatgpt_web_manual_search",
        source_url=str(normalized_metadata.get("url", "") or ""),
        knowledge_position_text=_build_knowledge_position_text(project, note_path, sync_library=True),
    )
    refreshed_markdown, review_issues = _run_deep_read_review_loop(refreshed_markdown, tags=analysis.tags)
    validation_issues = review_issues + _validate_deep_read_markdown(refreshed_markdown, is_output_note=True)
    if validation_issues:
        raise ValueError("人工中转深度解读未通过审核：" + "；".join(validation_issues))
    if refreshed_markdown != markdown:
        note_path.write_text(refreshed_markdown, encoding="utf-8")
    return note_path


def _load_request_metadata(project: Path, request_id: str) -> dict:
    path = project / "data" / "chatgpt_web_manual" / "requests" / request_id / "metadata.json"
    if not path.exists():
        raise ValueError(f"未找到 request_id={request_id} 的 metadata 文件。")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _count_markdown_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len(list(directory.glob("*.md")))


def _count_json_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len(list(directory.glob("*.json")))


def _latest_markdown_file(directory: Path) -> str:
    if not directory.exists():
        return ""
    paths = [path for path in directory.glob("*.md") if path.is_file()]
    if not paths:
        return ""
    latest = max(paths, key=lambda path: path.stat().st_mtime)
    return str(latest)


def _load_monitored_journal_labels(project: Path) -> list[str]:
    return sorted({abbreviate_journal_name(source.journal_title) for source in load_sources(project / "config" / "sources.json")})


def _load_monitored_journal_groups(project: Path) -> list[dict[str, object]]:
    tier_order = {"core": 0, "related": 1, "watchlist": 2}
    tier_labels = {"core": "核心监测", "related": "相关扩展", "watchlist": "观察列表"}
    grouped: dict[str, list[str]] = {"core": [], "related": [], "watchlist": []}
    sources = sorted(
        load_sources(project / "config" / "sources.json"),
        key=lambda source: (tier_order.get(source.tier, 99), source.priority, abbreviate_journal_name(source.journal_title)),
    )
    for source in sources:
        grouped.setdefault(source.tier, [])
        grouped[source.tier].append(abbreviate_journal_name(source.journal_title))
    return [
        {"label": tier_labels.get(tier, tier), "items": items}
        for tier, items in grouped.items()
        if items
    ]


def _detect_token_usage(project: Path) -> str:
    token_logs = sorted(project.glob("log/**/*token*usage*.md"))
    if not token_logs:
        return "未记录"
    latest = max(token_logs, key=lambda path: path.stat().st_mtime)
    text = latest.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"total_tokens[^0-9]*(\d+)", text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)}（最近记录）"
    return f"已记录：{latest.name}"


def _count_manual_files(project: Path) -> int:
    requests = chatgpt_web_manual_requests_root(project)
    responses = chatgpt_web_manual_responses_root(project)
    request_files = len(list(requests.glob("*/prompt.md"))) if requests.exists() else 0
    response_files = len(list(responses.glob("*.json"))) if responses.exists() else 0
    return request_files + response_files


def _load_latest_maintenance_status(project: Path) -> dict[str, str]:
    latest_path = project / "log" / "maintenance" / "latest.md"
    if not latest_path.exists():
        return {"overall": "unknown", "path": "", "doctor": "", "pytest": "", "harness": "", "entropy": ""}
    text = latest_path.read_text(encoding="utf-8", errors="ignore")

    def _extract(name: str) -> str:
        match = re.search(rf"^- {re.escape(name)}=(\w+)", text, flags=re.MULTILINE)
        return match.group(1) if match else ""

    overall = _extract("overall")
    doctor = _extract("doctor")
    pytest = _extract("pytest")
    harness = _extract("harness")
    entropy = _extract("entropy")
    return {
        "overall": overall or "unknown",
        "path": str(latest_path),
        "doctor": doctor or "",
        "pytest": pytest or "",
        "harness": harness or "",
        "entropy": entropy or "",
    }
