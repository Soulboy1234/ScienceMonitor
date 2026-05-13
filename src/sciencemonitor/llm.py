from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from sqlite3 import Row
from typing import Callable

from .analysis_providers import SUPPORTED_ANALYSIS_PROVIDERS
from .chatgpt_web_manual import (
    ManualResponsePending,
    load_manual_response,
    manual_status_counts,
    prepare_manual_request_bundle,
)
from .config import (
    chatgpt_web_manual_root,
    llm_cache_root,
    llm_tmp_root,
    load_master_plan_preferences,
)
from .llm_api_support import (
    StructuredOutputParseError,
    check_ollama_available,
    _extract_json_object_candidate,
    _ollama_json_repair_candidates,
    _parse_structured_output,
    resolve_api_key,
    resolve_api_key_source,
    resolve_base_url,
    run_ollama_structured,
    run_openai_structured,
    run_openrouter_structured,
)
from .llm_contracts import (
    _prepare_article_source_text_for_prompt,
    build_article_prompt,
    build_article_schema,
    build_deep_read_evidence_prompt,
    build_deep_read_evidence_schema,
    build_deep_read_prompt,
    build_deep_read_schema,
    build_manual_article_prompt,
    build_manual_deep_read_prompt,
    build_manual_report_prompt,
    build_ollama_deep_read_evidence_prompt_v2,
    build_ollama_deep_read_evidence_schema_v2,
    build_ollama_deep_read_final_prompt_v2,
    build_ollama_deep_read_revision_prompt_v2,
    build_report_prompt,
    build_report_schema,
)
from .models import ArticleSummaryResult
from .tag_review import review_generated_tags
from .token_monitor import record_api_usage
from .utils import clean_abstract_text, clean_title_text


SUPPORTED_REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
DEFAULT_CODEX_EXECUTABLE_CANDIDATES = (
    Path("/Applications/Codex.app/Contents/Resources/codex"),
)


DEFAULT_ANALYSIS_CONFIG = {
    "provider": "codex_local",
    "article_summaries": {
        "reasoning_effort": "medium",
    },
    "report": {
        "reasoning_effort": "medium",
    },
    "deep_reads": {
        "reasoning_effort": "high",
    },
    "codex_local": {
        "model": "",
        "executable": "",
        "sandbox": "read-only",
        "timeout_seconds": 180,
    },
    "openai_api": {
        "api_key": "",
        "api_key_env": "SCIENCEMONITOR_OPENAI_API_KEY",
        "model": "gpt-5-mini",
        "base_url": "https://api.openai.com/v1/responses",
        "timeout_seconds": 120,
    },
    "openrouter_api": {
        "api_key": "",
        "api_key_env": "SCIENCEMONITOR_OPENROUTER_API_KEY",
        "model": "openai/gpt-5-mini",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "site_url": "",
        "app_name": "ScienceMonitor",
        "timeout_seconds": 120,
    },
    "ollama_api": {
        "model": "gemma4:26b",
        "base_url": "http://127.0.0.1:11434/api/chat",
        "timeout_seconds": 900,
        "keep_alive": 0,
        "num_ctx": 32768,
        "num_predict": 4096,
        "deep_read_num_predict": 8192,
        "deep_read_quality_mode": True,
        "deep_read_stage_keep_alive": "1m",
        "deep_read_final_max_chars": 16000,
    },
    "chatgpt_web_manual": {},
}

FALLBACK_TAG_NORMALIZATION_RULES = [
    (r"低纬.*电离层|电离层.*低纬|赤道电离层", "电离层/低纬"),
    (r"高纬.*电离层|电离层.*高纬|极区电离层", "电离层/高纬"),
    (r"中纬.*电离层|电离层.*中纬", "电离层/中纬"),
    (r"总电子含量|total electron content|\btec\b", "电离层/TEC"),
    (r"电离层.*不规则体|等离子体泡|赤道等离子体泡", "电离层/不规则体"),
    (r"电离层.*闪烁", "电离层/闪烁"),
    (r"极区对流.*边界|边界.*极区对流|polar convection", "极区/对流边界"),
    (r"磁层状态|磁层活动|磁层/活动", "磁层"),
    (r"热层风场|中性风|thermospheric wind|neutral wind|meridional wind|zonal wind", "热层/风场"),
    (r"热层密度|中性密度|thermospheric mass density|thermospheric density|neutral density|satellite drag|drag environment|drag of leo satellites|leo satellite drag", "热层/密度"),
    (r"热层成分|o/n2|composition|nitric oxide|一氧化氮|atomic oxygen", "热层/成分"),
    (r"热层温度|中性温度|thermospheric temperature|neutral temperature|exospheric temperature", "热层/温度"),
    (r"月球|moon|lunar", "对象/其他行星/月球"),
    (r"火星|mars|martian", "对象/其他行星/火星"),
    (r"金星|venus|venusian", "对象/其他行星/金星"),
    (r"水星|mercury|mercurian", "对象/其他行星/水星"),
    (r"木星|jupiter|jovian", "对象/其他行星/木星"),
    (r"土星|saturn|saturnian", "对象/其他行星/土星"),
    (r"天王星|uranus|uranian", "对象/其他行星/天王星"),
    (r"海王星|neptune|neptunian", "对象/其他行星/海王星"),
    (r"广义线性模型|generalized linear model|\bglm\b", "建模/统计模型/GLM"),
    (r"观测/?射电掩星|射电掩星", "仪器/射电掩星"),
    (r"探测器/?kplo|danuri|kplo", "仪器/KPLO"),
    (r"物理量/?电子密度", "电离层/电子密度"),
]

class AnalysisQuotaExceeded(RuntimeError):
    def __init__(self, provider: str, detail_path: Path, *, retry_after: str = "", phase: str = "analysis") -> None:
        self.provider = provider
        self.detail_path = detail_path
        self.retry_after = retry_after.strip()
        self.phase = phase
        message = f"{provider} {phase} stopped because the account hit its usage limit."
        if self.retry_after:
            message += f" Try again at {self.retry_after}."
        message += f" Details: {detail_path}"
        super().__init__(message)

    def ui_message(self) -> str:
        base = f"{self.provider} 额度已耗尽，本次任务已中止。"
        if self.retry_after:
            base += f" 可在 {self.retry_after} 后重试。"
        return base


class AnalysisProviderTimeout(RuntimeError):
    def __init__(
        self,
        provider: str,
        *,
        timeout_seconds: int,
        request_name: str = "",
        phase: str = "analysis",
    ) -> None:
        self.provider = provider
        self.timeout_seconds = int(timeout_seconds)
        self.request_name = request_name.strip()
        self.phase = phase
        message = f"{provider} {phase} timed out after {self.timeout_seconds}s."
        if self.request_name:
            message += f" Request: {self.request_name}."
        super().__init__(message)

    def ui_message(self) -> str:
        if self.provider == "ollama_api":
            if self.request_name.startswith("deep_read"):
                return (
                    f"Ollama 本地模型单次请求超过 {self.timeout_seconds} 秒，本次深度解读已暂停。"
                    " 已完成的中间结果会保留。"
                )
            return (
                f"Ollama 本地模型单次请求超过 {self.timeout_seconds} 秒，本次周报已暂停。"
                " 已完成的单篇总结会保留。"
            )
        return f"{self.provider} 单次请求超过 {self.timeout_seconds} 秒，本次任务已暂停。"


class AnalysisProviderInvalidOutput(RuntimeError):
    def __init__(
        self,
        provider: str,
        *,
        request_name: str = "",
        detail: str = "",
        raw_preview: str = "",
        detail_path: Path | None = None,
        phase: str = "analysis",
    ) -> None:
        self.provider = provider
        self.request_name = request_name.strip()
        self.detail = detail.strip()
        self.raw_preview = raw_preview.strip()
        self.detail_path = detail_path
        self.phase = phase
        message = f"{provider} {phase} returned invalid structured output."
        if self.request_name:
            message += f" Request: {self.request_name}."
        if self.detail:
            message += f" Detail: {self.detail}"
        if self.detail_path is not None:
            message += f" Details: {self.detail_path}"
        super().__init__(message)

    def ui_message(self) -> str:
        if self.provider == "ollama_api":
            if self.request_name.startswith("deep_read"):
                return "Ollama 本地模型返回的深度解读结构化 JSON 不完整或格式错误。"
            return "Ollama 本地模型返回的结构化 JSON 不完整或格式错误，该篇单篇总结已记录为未完成。"
        return f"{self.provider} 返回的结构化 JSON 不完整或格式错误。"


def _extract_codex_retry_after(stderr_text: str) -> str:
    match = re.search(r"try again at ([^.]+)\.", stderr_text, flags=re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _raise_codex_usage_limit(stderr_text: str, stderr_path: Path, *, phase: str) -> None:
    lowered = stderr_text.lower()
    if "usage limit" in lowered or "purchase more credits" in lowered or "upgrade to pro" in lowered:
        raise AnalysisQuotaExceeded(
            "codex_local",
            stderr_path,
            retry_after=_extract_codex_retry_after(stderr_text),
            phase=phase,
        )


def _summarize_codex_missing_output(stderr_text: str, stderr_path: Path) -> str:
    lowered = stderr_text.lower()
    if "usage limit" in lowered or "purchase more credits" in lowered or "upgrade to pro" in lowered:
        _raise_codex_usage_limit(stderr_text, stderr_path, phase="analysis")
    if "invalid json" in lowered or "schema" in lowered:
        return (
            "codex_local analysis finished without a valid structured response. "
            f"Details: {stderr_path}"
        )
    return (
        "codex_local analysis finished without writing structured output. "
        f"Details: {stderr_path}"
    )


def _summarize_codex_failure(returncode: int, stderr_text: str, stderr_path: Path) -> str:
    lowered = stderr_text.lower()
    if "usage limit" in lowered or "purchase more credits" in lowered or "upgrade to pro" in lowered:
        _raise_codex_usage_limit(stderr_text, stderr_path, phase="analysis")
    return f"codex_local analysis failed with exit code {returncode}. Details: {stderr_path}"


def _emit_analysis_progress(callback: Callable[[dict], None] | None, **payload: object) -> None:
    if callback is None:
        return
    callback(dict(payload))


@dataclass(frozen=True)
class ArticleAnalysis:
    chinese_title: str
    tags: list[str]
    body: str
    supplement: str
    recommendation: str
    one_sentence: str


@dataclass(frozen=True)
class TopicInsight:
    label: str
    summary: str


@dataclass(frozen=True)
class JournalInsight:
    journal: str
    summary: str


@dataclass(frozen=True)
class ReportAnalysis:
    overview_bullets: list[str] = field(default_factory=list)
    daily_suggestions: list[str] = field(default_factory=list)
    preference_overview: str = ""
    work_implication: str = ""
    preference_paper_indices: list[int] = field(default_factory=list)
    work_implication_paper_indices: list[int] = field(default_factory=list)
    topic_insights: list[TopicInsight] = field(default_factory=list)
    journal_insights: list[JournalInsight] = field(default_factory=list)

    def topic_summary(self, label: str) -> str | None:
        for item in self.topic_insights:
            if item.label == label:
                return item.summary
        return None

    def journal_summary(self, journal: str) -> str | None:
        from .reporting_support import normalize_report_journal_name

        normalized = normalize_report_journal_name(journal)
        for item in self.journal_insights:
            if item.journal == journal or normalize_report_journal_name(item.journal) == normalized:
                return item.summary
        return None


@dataclass(frozen=True)
class DeepReadAnalysis:
    chinese_title: str
    tags: list[str]
    paper_type: str
    one_sentence_overview: str
    why: str
    how: str
    key_results: str
    contribution: str
    limitations: str
    reproducibility: str
    relation: str
    final_conclusion: str
    relation_to_my_work: str
    follow_up_questions: str
    needs_manual_review: str
    knowledge_position: str


class AnalysisEngine:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.config = self._load_config(root / "config" / "analysis.json")
        self.user_preferences = load_master_plan_preferences(root)
        self.provider = str(self.config.get("provider", "codex_local") or "codex_local")
        self.cache_root = llm_cache_root(root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.tmp_root = llm_tmp_root(root)
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def article_enabled(self) -> bool:
        return self.provider in SUPPORTED_ANALYSIS_PROVIDERS

    def report_enabled(self) -> bool:
        return self.provider in SUPPORTED_ANALYSIS_PROVIDERS

    def deep_read_enabled(self) -> bool:
        return self.provider in SUPPORTED_ANALYSIS_PROVIDERS

    def analyze_article(self, row: Row, index: int) -> ArticleAnalysis | None:
        if not self.article_enabled():
            return None
        self._ensure_supported_provider()

        cache_key = self._article_cache_key(row)
        cached = self._read_json_cache("articles", cache_key)
        if cached:
            return ArticleAnalysis(
                chinese_title=str(cached["chinese_title"]).strip(),
                tags=self._normalize_tags(cached.get("tags", [])),
                body=str(cached["body"]).strip(),
                supplement=str(cached["supplement"]).strip(),
                recommendation=str(cached["recommendation"]).strip(),
                one_sentence=str(cached["one_sentence"]).strip(),
            )

        prompt = self._build_manual_article_prompt(row) if self.provider == "chatgpt_web_manual" else self._build_article_prompt(row)
        schema = self._article_schema()
        request_name = f"article_{cache_key}"
        try:
            payload = self._run_structured(
                prompt,
                schema,
                request_name,
                reasoning_effort=self._analysis_reasoning_effort("article_summaries"),
                manual_context=self._manual_context_for_article(row),
            )
        except AnalysisProviderInvalidOutput as exc:
            if self.provider != "ollama_api":
                raise
            payload = self._recover_ollama_article_payload(row, prompt, schema, request_name, exc)
        result = ArticleAnalysis(
            chinese_title=str(payload["chinese_title"]).strip(),
            tags=self._normalize_tags([str(item).strip() for item in payload["tags"] if str(item).strip()]),
            body=str(payload["body"]).strip(),
            supplement=str(payload["supplement"]).strip(),
            recommendation=str(payload["recommendation"]).strip(),
            one_sentence=str(payload["one_sentence"]).strip(),
        )
        self._write_json_cache("articles", cache_key, {
            "chinese_title": result.chinese_title,
            "tags": result.tags,
            "body": result.body,
            "supplement": result.supplement,
            "recommendation": result.recommendation,
            "one_sentence": result.one_sentence,
        })
        return result

    def analyze_report(self, report_date: date, summaries: list[ArticleSummaryResult]) -> ReportAnalysis | None:
        if not self.report_enabled() or not summaries:
            return None
        self._ensure_supported_provider()

        selected_summaries = list(summaries)
        summary_signature = "|".join(
            "::".join(
                [
                    str(summary.row["doi"] or summary.row["fingerprint"] or summary.note_title),
                    ",".join(summary.tags),
                    hashlib.sha1(
                        "\n".join(
                            [
                                summary.note_title,
                                summary.body,
                                summary.supplement,
                                summary.recommendation,
                                summary.one_sentence,
                            ]
                        ).encode("utf-8")
                    ).hexdigest()[:12],
                ]
            )
            for summary in selected_summaries
        )
        signature_hash = hashlib.sha1(summary_signature.encode("utf-8")).hexdigest()[:12]
        cache_basis = "|".join(
            [
                "report_v7",
                report_date.isoformat(),
                str(len(selected_summaries)),
                signature_hash,
                self._analysis_signature("report"),
            ]
        )
        cache_key = hashlib.sha1(cache_basis.encode("utf-8")).hexdigest()[:20]
        cached = self._read_json_cache("reports", cache_key)
        if cached:
            return self._report_from_payload(cached)

        prompt = (
            self._build_manual_report_prompt(report_date, selected_summaries)
            if self.provider == "chatgpt_web_manual"
            else self._build_report_prompt(report_date, selected_summaries)
        )
        schema = self._report_schema(selected_summaries)
        payload = self._run_structured(
            prompt,
            schema,
            f"report_{cache_key}",
            reasoning_effort=self._analysis_reasoning_effort("report"),
            manual_context=self._manual_context_for_report(report_date, selected_summaries),
        )
        self._write_json_cache("reports", cache_key, payload)
        return self._report_from_payload(payload)

    def analyze_deep_read(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None = None,
        manual_context: dict | None = None,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> DeepReadAnalysis | None:
        if not self.deep_read_enabled():
            return None
        self._ensure_supported_provider()

        raw_full_text = str(full_text or "").strip()
        normalized_full_text = clean_abstract_text(full_text)
        if self.provider != "chatgpt_web_manual" and not normalized_full_text:
            return None

        cache_basis_parts = [
            "deep_read_template_v6",
            str(metadata.get("doi", "")),
            str(metadata.get("title", "")),
            str(metadata.get("journal", "")),
            hashlib.sha1(normalized_full_text.encode("utf-8")).hexdigest()[:16] if normalized_full_text else "manual_web_search",
            self._analysis_signature("deep_reads"),
        ]
        if self.provider == "ollama_api" and self._ollama_deep_read_quality_mode_enabled():
            cache_basis_parts.append("ollama_deep_read_quality_v3")
        cache_basis = "|".join(cache_basis_parts)
        cache_key = hashlib.sha1(cache_basis.encode("utf-8")).hexdigest()
        cached = self._read_json_cache("deep_reads", cache_key)
        if cached:
            if self.provider == "ollama_api" and self._ollama_deep_read_quality_mode_enabled():
                cached = self._normalize_ollama_deep_read_payload(cached)
            return self._deep_read_from_payload(cached)

        if self.provider == "chatgpt_web_manual":
            prompt = self._build_manual_deep_read_prompt(metadata, related_summary)
        elif self.provider == "ollama_api" and self._ollama_deep_read_quality_mode_enabled():
            payload = self._run_ollama_deep_read_quality_v2(
                metadata,
                self._ollama_deep_read_source_text(raw_full_text, normalized_full_text),
                related_summary,
                cache_key=cache_key,
                progress_callback=progress_callback,
            )
            self._write_json_cache("deep_reads", cache_key, payload)
            return self._deep_read_from_payload(payload)
        else:
            prompt = self._build_deep_read_prompt(metadata, normalized_full_text, related_summary)
        schema = self._deep_read_schema()
        payload = self._run_structured(
            prompt,
            schema,
            f"deep_read_{cache_key}",
            reasoning_effort=self._analysis_reasoning_effort("deep_reads"),
            manual_context=manual_context or self._manual_context_for_deep_read(metadata, normalized_full_text),
        )
        self._write_json_cache("deep_reads", cache_key, payload)
        return self._deep_read_from_payload(payload)

    def _report_from_payload(self, payload: dict) -> ReportAnalysis:
        return ReportAnalysis(
            overview_bullets=self._normalize_text_list(payload.get("overview_bullets", [])),
            daily_suggestions=self._normalize_text_list(payload.get("daily_suggestions", [])),
            preference_overview=str(payload.get("preference_overview", "")).strip(),
            work_implication=str(payload.get("work_implication", "")).strip(),
            preference_paper_indices=self._normalize_index_list(payload.get("preference_paper_indices", [])),
            work_implication_paper_indices=self._normalize_index_list(payload.get("work_implication_paper_indices", [])),
            topic_insights=[
                TopicInsight(label=str(item["label"]).strip(), summary=str(item["summary"]).strip())
                for item in payload.get("topic_insights", [])
                if str(item.get("label", "")).strip() and str(item.get("summary", "")).strip()
            ],
            journal_insights=[
                JournalInsight(journal=str(item["journal"]).strip(), summary=str(item["summary"]).strip())
                for item in payload.get("journal_insights", [])
                if str(item.get("journal", "")).strip() and str(item.get("summary", "")).strip()
            ],
        )

    def _normalize_index_list(self, values: object) -> list[int]:
        if not isinstance(values, list):
            return []
        normalized: list[int] = []
        for item in values:
            try:
                value = int(item)
            except Exception:
                continue
            if value <= 0 or value in normalized:
                continue
            normalized.append(value)
        return normalized[:4]

    def _deep_read_from_payload(self, payload: dict) -> DeepReadAnalysis:
        return DeepReadAnalysis(
            chinese_title=str(payload.get("chinese_title", "")).strip(),
            tags=self._normalize_tags([str(item).strip() for item in payload.get("tags", []) if str(item).strip()]),
            paper_type=str(payload.get("paper_type", "")).strip(),
            one_sentence_overview=str(payload.get("one_sentence_overview", "")).strip(),
            why=str(payload.get("why", "")).strip(),
            how=str(payload.get("how", "")).strip(),
            key_results=str(payload.get("key_results", "")).strip(),
            contribution=str(payload.get("contribution", "")).strip(),
            limitations=str(payload.get("limitations", "")).strip(),
            reproducibility=str(payload.get("reproducibility", "")).strip(),
            relation=str(payload.get("relation", "")).strip(),
            final_conclusion=str(payload.get("final_conclusion", "")).strip(),
            relation_to_my_work=str(payload.get("relation_to_my_work", "")).strip(),
            follow_up_questions=str(payload.get("follow_up_questions", "")).strip(),
            needs_manual_review=str(payload.get("needs_manual_review", "")).strip(),
            knowledge_position=str(payload.get("knowledge_position", "")).strip(),
        )

    def _run_ollama_deep_read_quality_v2(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None,
        *,
        cache_key: str,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        evidence_payload = self._ollama_deep_read_evidence_payload_v2(
            metadata,
            full_text,
            related_summary,
            cache_key=cache_key,
            progress_callback=progress_callback,
        )
        evidence_context = self._format_ollama_deep_read_evidence_context_v2(evidence_payload)
        final_context = self._ollama_deep_read_final_context_v2(full_text)
        _emit_analysis_progress(progress_callback, stage="ollama_final", message="正在基于证据提纲生成最终深度解读。")
        prompt = self._build_ollama_deep_read_final_prompt_v2(
            metadata,
            final_context,
            related_summary,
            evidence_context=evidence_context,
        )
        retry_prompt = self._build_ollama_deep_read_final_retry_prompt_v2(
            metadata,
            final_context,
            related_summary,
            evidence_context=evidence_context,
        )
        payload = self._run_ollama_deep_read_structured_with_repair(
            prompt,
            self._deep_read_schema(),
            f"deep_read_{cache_key}",
            stage="final",
            retry_prompt=retry_prompt,
            progress_callback=progress_callback,
        )
        payload = self._normalize_ollama_deep_read_payload(payload)
        issues = self._ollama_deep_read_quality_issues(payload, evidence_payload)
        if issues:
            _emit_analysis_progress(progress_callback, stage="ollama_revision", message="正在修订深度解读初稿。")
            revision_prompt = self._build_ollama_deep_read_revision_prompt_v2(
                metadata,
                payload,
                issues,
                evidence_context,
            )
            try:
                revised = self._run_ollama_deep_read_structured_with_repair(
                    revision_prompt,
                    self._deep_read_schema(),
                    f"deep_read_revision_{cache_key[:20]}",
                    stage="revision",
                    retry_prompt=self._append_ollama_strict_json_retry_rules(revision_prompt, stage="revision"),
                    progress_callback=progress_callback,
                )
                payload = self._normalize_ollama_deep_read_payload(revised)
            except AnalysisProviderInvalidOutput:
                _emit_analysis_progress(
                    progress_callback,
                    stage="ollama_revision_skipped",
                    message="Ollama 修订阶段 JSON 仍无效，已保留最终初稿并标记人工复核。",
                )
                payload = self._mark_ollama_revision_skipped(payload)
        return self._downgrade_ollama_relation_overreach(payload)

    def _ollama_deep_read_source_text(self, raw_full_text: str, normalized_full_text: str) -> str:
        raw = str(raw_full_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if raw and ("\n" in raw or len(raw) > len(normalized_full_text or "") * 1.15):
            return raw
        return str(normalized_full_text or "").strip()

    def _ollama_deep_read_evidence_payload_v2(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None,
        *,
        cache_key: str,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        evidence_key = hashlib.sha1(f"deep_read_evidence_v3|{cache_key}".encode("utf-8")).hexdigest()
        cached = self._read_json_cache("deep_read_evidence", evidence_key)
        if cached is not None:
            return cached
        _emit_analysis_progress(progress_callback, stage="ollama_evidence", message="正在用全文整理证据边界。")
        evidence_source_text = self._ollama_deep_read_final_context_v2(
            full_text,
            max_chars=self._ollama_deep_read_evidence_context_max_chars(),
        )
        prompt = self._build_ollama_deep_read_evidence_prompt_v2(metadata, evidence_source_text, related_summary)
        retry_prompt = self._build_ollama_deep_read_evidence_retry_prompt_v2(metadata, evidence_source_text, related_summary)
        payload = self._run_ollama_deep_read_structured_with_repair(
            prompt,
            self._ollama_deep_read_evidence_schema_v2(),
            f"deep_read_evidence_v3_{cache_key[:20]}",
            stage="evidence",
            retry_prompt=retry_prompt,
            progress_callback=progress_callback,
        )
        self._write_json_cache("deep_read_evidence", evidence_key, payload)
        return payload

    def _run_ollama_deep_read_structured_with_repair(
        self,
        prompt: str,
        schema: dict,
        name: str,
        *,
        stage: str,
        retry_prompt: str | None = None,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        try:
            return self._run_ollama_structured(prompt, schema, name)
        except AnalysisProviderInvalidOutput as exc:
            repaired = self._repair_ollama_deep_read_payload_from_error(schema, exc)
            if repaired is not None:
                _emit_analysis_progress(
                    progress_callback,
                    stage=f"ollama_{stage}_json_repaired",
                    message=f"Ollama 深度解读{self._ollama_deep_read_stage_label(stage)} JSON 已本地修复。",
                )
                return repaired
            if not retry_prompt:
                raise
            retry_name = f"{name}_json_retry"
            try:
                payload = self._run_ollama_structured(retry_prompt, schema, retry_name)
            except AnalysisProviderInvalidOutput as retry_exc:
                repaired_retry = self._repair_ollama_deep_read_payload_from_error(schema, retry_exc)
                if repaired_retry is not None:
                    _emit_analysis_progress(
                        progress_callback,
                        stage=f"ollama_{stage}_json_repaired_after_retry",
                        message=(
                            f"Ollama 深度解读{self._ollama_deep_read_stage_label(stage)}严格重试 JSON "
                            "已本地修复。"
                        ),
                    )
                    return repaired_retry
                raise retry_exc from exc
            _emit_analysis_progress(
                progress_callback,
                stage=f"ollama_{stage}_json_retried",
                message=f"Ollama 深度解读{self._ollama_deep_read_stage_label(stage)} JSON 已通过严格重试恢复。",
            )
            return payload

    def _repair_ollama_deep_read_payload_from_error(
        self,
        schema: dict,
        exc: AnalysisProviderInvalidOutput,
    ) -> dict | None:
        raw = self._invalid_output_text(exc)
        if not raw:
            return None
        schema_name = str((schema or {}).get("name", "") or "")
        if schema_name not in {"deep_read_analysis", "ollama_deep_read_evidence_v2"}:
            try:
                return _parse_structured_output("ollama_api", raw, schema=schema)
            except StructuredOutputParseError:
                return None
        for candidate in self._ollama_deep_read_json_repair_candidates(raw):
            payload = self._load_ollama_json_candidate(candidate)
            if not isinstance(payload, dict):
                continue
            payload = self._repair_ollama_deep_read_payload_keys(payload, schema)
            if not self._looks_like_ollama_deep_read_payload(payload, schema):
                continue
            completed = self._complete_ollama_deep_read_payload(payload, schema)
            try:
                return _parse_structured_output(
                    "ollama_api",
                    json.dumps(completed, ensure_ascii=False),
                    schema=schema,
                )
            except StructuredOutputParseError:
                continue
        return None

    def _ollama_deep_read_json_repair_candidates(self, raw: str) -> list[str]:
        sources: list[str] = []

        def add(value: str) -> None:
            clean = str(value or "").strip()
            if clean and clean not in sources:
                sources.append(clean)

        stripped = self._strip_ollama_json_fence(raw)
        add(raw)
        add(stripped)
        add(_extract_json_object_candidate(raw))
        add(_extract_json_object_candidate(stripped))
        add(self._slice_first_to_last_json_brace(stripped))

        candidates: list[str] = []
        for source in sources:
            repaired = self._repair_ollama_deep_read_json_text(source)
            for candidate in [source, repaired, *_ollama_json_repair_candidates(repaired)]:
                clean = str(candidate or "").strip()
                if clean and clean not in candidates:
                    candidates.append(clean)
        return candidates

    def _strip_ollama_json_fence(self, value: str) -> str:
        text = str(value or "").strip()
        if not text.startswith("```"):
            return text
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _slice_first_to_last_json_brace(self, value: str) -> str:
        text = str(value or "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return text
        return text[start:end + 1].strip()

    def _repair_ollama_deep_read_json_text(self, value: str) -> str:
        text = self._strip_ollama_json_fence(value)
        text = re.sub(r"(?m)^(\s*)[-*]\s+(?=\"[^\"]+\"\s*:)", r"\1", text)
        text = re.sub(r"(?m)^(\s*)[．。·、，,]+(?=\"[^\"]+\"\s*:)", r"\1", text)
        text = re.sub(r"(?m)^(\s*)[\u4e00-\u9fff]{1,2}(?=\"[^\"\n]+\"\s*[,}\]])", r"\1", text)
        text = re.sub(r'(?m)^(\s*)_([A-Za-z][A-Za-z0-9_]*)"\s*:', r'\1"\2":', text)
        text = re.sub(r'(?m)^(\s*)([A-Za-z_][A-Za-z0-9_]*)"\s*:', r'\1"\2":', text)
        text = re.sub(
            r'(?m)^(\s*)"?(?:_?open_questions|open_question|open_issues)"?\s*:',
            r'\1"open_questions":',
            text,
        )
        text = re.sub(
            r'(?m)^(\s*)"?(?:ers_findings|secondaryfindings|secondary_findings_list)"?\s*:',
            r'\1"secondary_findings":',
            text,
        )
        text = re.sub(r'(?<=[。.!?！？；;\)])""(?=\s*[,}\]])', r'"', text)
        text = re.sub(
            r'(?ms)^(\s*"reproducibility"\s*:\s*"(?:\\.|[^"\\])*")\s*\n\s*}\s*,\s*\n'
            r'(\s*"(?:relation|final_conclusion|relation_to_my_work|follow_up_questions|needs_manual_review|knowledge_position)"\s*:)',
            r"\1,\n\2",
            text,
        )
        evidence_keys = (
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
        )
        for key in evidence_keys:
            text = re.sub(
                rf'(?m)(^\s{{4}}"(?:\\.|[^"\\])*"\s*,?\s*\n)(\s{{2}}"{key}"\s*:)',
                r"\1  ],\n\2",
                text,
            )
        return text

    def _load_ollama_json_candidate(self, candidate: str) -> object | None:
        clean = str(candidate or "").strip()
        if not clean:
            return None
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(clean)
            except Exception:
                return None

    def _repair_ollama_deep_read_payload_keys(self, payload: dict, schema: dict) -> dict:
        schema_name = str((schema or {}).get("name", "") or "")
        repaired = dict(payload or {})
        aliases: dict[str, tuple[str, ...]] = {}
        if schema_name == "ollama_deep_read_evidence_v2":
            aliases = {
                "open_questions": ("_open_questions", "open_question", "open_issues"),
                "secondary_findings": ("ers_findings", "secondaryfindings", "secondary_findings_list"),
            }
        elif schema_name == "deep_read_analysis":
            aliases = {
                "final_conclusion": ("conclusion", "overall_conclusion", "最终结论"),
                "relation_to_my_work": ("my_work_relation", "relation_to_current_work"),
                "follow_up_questions": ("follow_up", "followup_questions", "next_questions"),
                "needs_manual_review": ("manual_review", "need_manual_review"),
            }
        for canonical, candidates in aliases.items():
            if canonical in repaired and repaired.get(canonical) not in (None, ""):
                continue
            for candidate in candidates:
                if candidate not in repaired:
                    continue
                value = repaired.get(candidate)
                if value in (None, ""):
                    continue
                repaired[canonical] = value
                break
        return repaired

    def _looks_like_ollama_deep_read_payload(self, payload: dict, schema: dict) -> bool:
        required = [str(item) for item in (((schema or {}).get("schema") or {}).get("required", []) or [])]
        if not required:
            return False
        present = [key for key in required if key in payload]
        schema_name = str((schema or {}).get("name", "") or "")
        if schema_name == "ollama_deep_read_evidence_v2":
            return (
                len(present) >= len(required) - 2
                and "research_problem" in payload
                and ("method_chain" in payload or "hard_findings" in payload)
            )
        if schema_name == "deep_read_analysis":
            return (
                len(present) >= len(required) - 2
                and "one_sentence_overview" in payload
                and ("key_results" in payload or "how" in payload)
            )
        return False

    def _complete_ollama_deep_read_payload(self, payload: dict, schema: dict) -> dict:
        schema_name = str((schema or {}).get("name", "") or "")
        required = [str(item) for item in (((schema or {}).get("schema") or {}).get("required", []) or [])]
        completed = dict(payload or {})
        missing = [key for key in required if key not in completed]
        if schema_name == "ollama_deep_read_evidence_v2":
            for key in required:
                value = completed.get(key)
                if key not in completed:
                    completed[key] = []
                elif isinstance(value, dict):
                    completed[key] = self._flatten_ollama_deep_read_json_value(value)
                elif isinstance(value, list):
                    completed[key] = [
                        text
                        for item in value
                        for text in self._flatten_ollama_deep_read_json_value(item)
                        if text
                    ]
                else:
                    completed[key] = str(value or "").strip()
            return completed

        if schema_name == "deep_read_analysis":
            for key in required:
                if key == "tags":
                    completed[key] = self._normalize_ollama_tags(completed.get(key, []))
                    continue
                if key == "final_conclusion" and not str(completed.get(key, "") or "").strip():
                    completed[key] = self._fallback_ollama_final_conclusion(completed)
                    continue
                if key not in completed:
                    completed[key] = ""
            if missing:
                note = "Ollama 深度解读结构化输出缺少字段，已本地补齐：{}；需人工复核补齐内容。".format(
                    "、".join(missing)
                )
                existing = str(completed.get("needs_manual_review", "") or "").strip()
                completed["needs_manual_review"] = f"{existing}\n{note}".strip() if existing else note
            return completed
        return completed

    def _flatten_ollama_deep_read_json_value(self, value: object) -> list[str]:
        if isinstance(value, dict):
            parts: list[str] = []
            for raw_key, raw_value in value.items():
                label = str(raw_key).strip()
                flattened = self._flatten_ollama_deep_read_json_value(raw_value)
                if not flattened:
                    continue
                body = "；".join(flattened)
                parts.append(f"{label}：{body}" if label else body)
            return parts
        if isinstance(value, list):
            parts = []
            for item in value:
                parts.extend(self._flatten_ollama_deep_read_json_value(item))
            return parts
        text = str(value or "").strip()
        return [text] if text else []

    def _fallback_ollama_final_conclusion(self, payload: dict) -> str:
        for key in ("one_sentence_overview", "relation", "contribution", "key_results"):
            value = self._stringify_ollama_deep_read_value(payload.get(key, ""), field=key).strip()
            if value:
                return value
        return "Ollama 输出缺少 final_conclusion，需依据正文和关键结果人工复核最终结论。"

    def _build_ollama_deep_read_evidence_retry_prompt_v2(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None,
    ) -> str:
        source_text = self._ollama_deep_read_retry_context(full_text, max_chars=9000)
        prompt = self._build_ollama_deep_read_evidence_prompt_v2(metadata, source_text, related_summary)
        return self._append_ollama_strict_json_retry_rules(prompt, stage="evidence")

    def _build_ollama_deep_read_final_retry_prompt_v2(
        self,
        metadata: dict[str, str],
        final_context: str,
        related_summary: dict[str, str] | None,
        *,
        evidence_context: str,
    ) -> str:
        retry_context = self._ollama_deep_read_retry_context(final_context, max_chars=9000)
        prompt = self._build_ollama_deep_read_final_prompt_v2(
            metadata,
            retry_context,
            related_summary,
            evidence_context=evidence_context,
        )
        return self._append_ollama_strict_json_retry_rules(prompt, stage="final")

    def _ollama_deep_read_retry_context(self, text: str, *, max_chars: int) -> str:
        clean = str(text or "").strip()
        if len(clean) <= max_chars:
            return clean
        return self._ollama_head_mid_tail_context(clean, max_chars=max_chars)

    def _append_ollama_strict_json_retry_rules(self, prompt: str, *, stage: str) -> str:
        field_rule = ""
        if stage in {"final", "revision"}:
            field_rule = (
                "schema 中的字符串字段必须输出字符串，不要输出对象或数组；需要分点时在同一个字符串内写 1. 2. 3.。"
            )
        return "\n".join(
            [
                str(prompt or "").strip(),
                "",
                "上一次 Ollama 深度解读结构化输出不是合法 JSON。本次是恢复重试，必须严格遵守：",
                "1. 只输出一个 JSON 对象，不要代码块、markdown bullet、解释文字或前后缀。",
                "2. 对象 key 必须是双引号字符串；数组元素必须是双引号字符串；不要留下孤立英文残片或尾逗号。",
                "3. LaTeX 或公式里的反斜杠必须写成双反斜杠，或者改成中文变量名描述。",
                "4. required 字段必须全部出现；证据不足时填空字符串或空数组。",
                field_rule,
            ]
        ).strip()

    def _ollama_deep_read_stage_label(self, stage: str) -> str:
        return {
            "evidence": "证据阶段",
            "final": "最终阶段",
            "revision": "修订阶段",
        }.get(str(stage or "").strip(), "阶段")

    def _mark_ollama_revision_skipped(self, payload: dict) -> dict:
        adjusted = dict(payload or {})
        note = "Ollama 修订阶段结构化输出无效，已保留最终初稿；需人工复核修订建议。"
        existing = str(adjusted.get("needs_manual_review", "") or "").strip()
        adjusted["needs_manual_review"] = f"{existing}\n{note}".strip() if existing else note
        return adjusted

    def _format_ollama_deep_read_evidence_context_v2(self, payload: dict) -> str:
        labels = [
            ("research_problem", "研究问题"),
            ("introduction_gap", "引言空白"),
            ("method_chain", "方法与证据链"),
            ("hard_findings", "硬结论证据"),
            ("secondary_findings", "次级结论证据"),
            ("reasonable_inferences", "合理推论证据"),
            ("open_questions", "待验证问题"),
            ("contribution_points", "新意与贡献证据"),
            ("limitations", "局限与证据边界"),
            ("reproducibility_notes", "可复现性线索"),
            ("relation_to_my_work_evidence", "与用户工作的关系证据"),
            ("manual_review_points", "人工复核点"),
        ]
        lines: list[str] = []
        for key, label in labels:
            value = self._format_evidence_value(payload.get(key, ""), numbered=True)
            if value:
                lines.append(f"{label}：\n{value}")
        return "\n\n".join(lines)

    def _ollama_deep_read_evidence_context_max_chars(self) -> int:
        settings = self.config.get("ollama_api", {})
        try:
            final_max_chars = int(settings.get("deep_read_final_max_chars", 16000) or 16000)
        except Exception:
            final_max_chars = 16000
        return max(16000, min(28000, final_max_chars * 2))

    def _ollama_deep_read_final_context_v2(self, full_text: str, *, max_chars: int | None = None) -> str:
        settings = self.config.get("ollama_api", {})
        if max_chars is None:
            max_chars = int(settings.get("deep_read_final_max_chars", 16000) or 16000)
        text = str(full_text or "").strip()
        if not text:
            return ""
        if max_chars <= 0:
            return text

        section_specs = [
            ("摘要/引言", ("abstract", "plain language summary", "key points", "introduction"), 0.24),
            ("方法/数据", ("method", "methods", "data", "observation", "observations", "model", "instrument"), 0.20),
            ("案例/验证", ("case study", "case studies", "validation", "verification", "benchmark", "experiment"), 0.24),
            (
                "结果/讨论",
                ("result", "results", "analysis", "discussion", "recommendation", "engineering consequence"),
                0.20,
            ),
            ("结论/总结", ("conclusion", "conclusions", "summary"), 0.12),
        ]
        section_blocks: list[str] = []
        for label, keywords, fraction in section_specs:
            body = self._extract_ollama_section_excerpt(text, keywords, max_chars=max(900, int(max_chars * fraction)))
            if body:
                section_blocks.append(f"{label}：\n{body}")
        blocks = list(section_blocks)
        target_snippets = self._ollama_deep_read_target_snippets(text, max_chars=max(1600, int(max_chars * 0.65)))
        target_block = ""
        if target_snippets:
            target_block = f"重点案例/建议片段：\n{target_snippets}"
            blocks.append(target_block)
        joined = "\n\n".join(blocks).strip()
        if len(joined) > max_chars:
            if target_block and len(target_block) < max_chars:
                section_budget = max(600, max_chars - len(target_block) - 2)
                section_part = self._trim_ollama_context("\n\n".join(section_blocks), max_chars=section_budget)
                return f"{section_part}\n\n{target_block}".strip()
            return self._trim_ollama_context(joined, max_chars=max_chars)
        if len(joined) >= min(max_chars, 2200) or len(text) <= max_chars:
            return joined or text[:max_chars].strip()
        return self._ollama_head_mid_tail_context(text, max_chars=max_chars)

    def _ollama_deep_read_target_snippets(self, text: str, *, max_chars: int) -> str:
        clean = str(text or "").strip()
        lower = clean.lower()
        if not (
            re.search(r"\bpinns?\b|physics[-\s]+informed|物理(?:信息|约束)神经网络", lower, flags=re.IGNORECASE)
            and re.search(r"\bxai\b|explainab|可解释性?人工智能", lower, flags=re.IGNORECASE)
        ):
            return ""
        keywords = (
            "multiplicative error propagation",
            "multiplicative",
            "false confidence",
            "kirsch",
            "stress concentration",
            "piecewise stiffness",
            "piecewise",
            "varying properties",
            "cantilever",
            "euler-bernoulli",
            "recommendations for engineering practice",
            "recommendations",
            "validation processes",
            "sensitivity analysis",
            "independent engineering review",
            "fail-safe",
            "fail safe",
            "case studies",
            "case study",
        )
        windows: list[tuple[int, int]] = []
        for keyword in keywords:
            index = lower.find(keyword)
            if index < 0:
                continue
            start = max(0, index - 700)
            end = min(len(clean), index + 1500)
            merged = False
            for existing_index, (existing_start, existing_end) in enumerate(windows):
                if start <= existing_end + 250 and end >= existing_start - 250:
                    windows[existing_index] = (min(existing_start, start), max(existing_end, end))
                    merged = True
                    break
            if not merged:
                windows.append((start, end))
        if not windows:
            return ""

        snippets: list[str] = []
        used = 0
        for start, end in windows:
            if used >= max_chars:
                break
            excerpt = clean[start:end].strip()
            excerpt = self._trim_ollama_context(excerpt, max_chars=max_chars - used)
            if not excerpt:
                continue
            snippets.append(excerpt)
            used += len(excerpt)
        return "\n\n".join(snippets).strip()

    def _extract_ollama_section_excerpt(self, text: str, keywords: tuple[str, ...], *, max_chars: int) -> str:
        heading_re = re.compile(
            r"(?im)^(?P<heading>(?:\d+(?:\.\d+)*\.?\s*)?[A-Z][A-Za-z0-9,()\-–/&: ]{2,100})\s*$"
        )
        matches = list(heading_re.finditer(text))
        excerpts: list[str] = []
        remaining = max_chars
        for index, match in enumerate(matches):
            heading = match.group("heading").strip().lower()
            if not any(keyword in heading for keyword in keywords):
                continue
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                excerpt = self._trim_ollama_context(body, max_chars=remaining)
                if excerpt:
                    excerpts.append(excerpt)
                    remaining -= len(excerpt)
                if remaining <= 200:
                    break
        return "\n\n".join(excerpts).strip()

    def _ollama_head_mid_tail_context(self, text: str, *, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        head_chars = max(1000, int(max_chars * 0.45))
        mid_chars = max(800, int(max_chars * 0.25))
        tail_chars = max(800, max_chars - head_chars - mid_chars)
        mid_start = max(0, int((len(text) - mid_chars) / 2))
        head = self._trim_ollama_context(text[:head_chars], max_chars=head_chars)
        middle = self._trim_ollama_context(text[mid_start:mid_start + mid_chars], max_chars=mid_chars)
        tail = self._trim_ollama_context(text[-tail_chars:], max_chars=tail_chars)
        return "\n\n".join(
            [
                "开头材料：\n" + head,
                "中段材料：\n" + middle,
                "结尾材料：\n" + tail,
            ]
        )

    def _trim_ollama_context(self, text: str, *, max_chars: int) -> str:
        clean = str(text or "").strip()
        if len(clean) <= max_chars:
            return clean
        return clean[:max_chars].rsplit(" ", 1)[0].strip()

    def _normalize_ollama_deep_read_payload(self, payload: dict) -> dict:
        normalized = dict(payload or {})
        if "chinese_title" not in normalized and "chinese_und_title" in normalized:
            normalized["chinese_title"] = normalized.get("chinese_und_title")
        required = self._deep_read_schema()["schema"]["required"]
        for key in required:
            if key == "tags":
                normalized[key] = self._normalize_ollama_tags(normalized.get(key, []))
                continue
            text_value = self._stringify_ollama_deep_read_value(normalized.get(key, ""), field=key)
            normalized[key] = self._repair_ollama_deep_read_terms(text_value)
        normalized["why"] = re.sub(r"^[:：\s]+", "", str(normalized.get("why", "") or "").strip())
        normalized["why"] = re.sub(r"^作者要解决的问题是[:：]\s*[:：]\s*", "作者要解决的问题是：", normalized["why"])
        return normalized

    def _normalize_ollama_tags(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        if not text:
            return []
        return [item.strip(" #") for item in re.split(r"[,，;；\s]+", text) if item.strip(" #")]

    def _stringify_ollama_deep_read_value(self, value: object, *, field: str = "") -> str:
        parsed = self._parse_ollama_structured_text(value)
        if parsed is not None and parsed is not value:
            return self._stringify_ollama_deep_read_value(parsed, field=field)
        if isinstance(value, list):
            return self._format_ollama_deep_read_list(value, field=field)
        if isinstance(value, dict):
            return self._format_ollama_deep_read_dict(value, field=field)
        return str(value or "").strip()

    def _parse_ollama_structured_text(self, value: object) -> object | None:
        if isinstance(value, (list, dict)):
            return None
        text = str(value or "").strip()
        if not ((text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}"))):
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return None

    def _format_ollama_deep_read_dict(self, value: dict, *, field: str) -> str:
        key_result_labels = ("硬结论", "次级结论", "合理推论", "需进一步研究讨论的结论")
        if field == "key_results":
            blocks: list[str] = []
            for label in key_result_labels:
                if label not in value:
                    continue
                body = self._format_ollama_deep_read_list(value.get(label), field=field)
                if body:
                    blocks.append(f"{label}：\n{body}")
            if blocks:
                return "\n".join(blocks)

        blocks = []
        for raw_key, raw_value in value.items():
            label = str(raw_key).strip()
            if not label:
                continue
            body = self._stringify_ollama_deep_read_value(raw_value, field=field).strip()
            if not body:
                continue
            blocks.append(f"{label}：\n{body}")
        return "\n".join(blocks)

    def _format_ollama_deep_read_list(self, value: object, *, field: str) -> str:
        if not isinstance(value, list):
            text = str(value or "").strip()
            return text
        items: list[str] = []
        for item in value:
            if isinstance(item, dict):
                item_text = self._format_ollama_deep_read_dict(item, field=field)
            elif isinstance(item, list):
                item_text = self._format_ollama_deep_read_list(item, field=field)
            else:
                item_text = str(item or "").strip()
            item_text = re.sub(r"^\s*\d+[.．、)）]\s*", "", item_text.strip())
            if item_text:
                items.append(item_text)
        return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))

    def _repair_ollama_deep_read_terms(self, value: str) -> str:
        text = str(value or "").strip()
        replacements = [
            (r"太阳[-－—]月球（S-M）", "太阳风-磁层（S-M）"),
            (r"太阳[-－—]月球/S-M", "太阳风-磁层/S-M"),
            (r"太阳[-－—]月球/电离层", "太阳风-磁层/电离层"),
            (r"太阳[-－—]月球发电机", "太阳风-磁层发电机"),
            (r"太阳[-－—]月球动力机", "太阳风-磁层动力机"),
            (r"太阳[-－—]月球", "太阳风-磁层"),
            (r"(?<!耳)焦热", "焦耳热"),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text)
        text = text.replace("这篇文章的目标是本文通过", "这篇文章通过")
        text = re.sub(r"^本文通过", "这篇文章通过", text)
        return text

    def _ollama_deep_read_quality_issues(self, payload: dict, evidence_payload: dict) -> list[str]:
        issues: list[str] = []
        core_length = sum(
            len(str(payload.get(key, "") or ""))
            for key in (
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
            )
        )
        if core_length < 2600:
            issues.append("深度解读正文偏短，整体判断密度不足。")
        key_result_counts = self._ollama_key_result_counts(str(payload.get("key_results", "") or ""))
        sparse_labels = [label for label, count in key_result_counts.items() if count < 2]
        if sparse_labels:
            issues.append(f"关键结果分层不足，以下类别少于 2 条：{'、'.join(sparse_labels)}。")
        if self._ollama_relation_overstates_directness(payload):
            issues.append("“和我已有工作的关系”写成直接相关，但标签和证据没有直接支撑。")
        if self._ollama_payload_contains_list_repr(payload):
            issues.append("存在 Python/JSON 列表字符串，需要改成逐条编号文本。")
        if len(str(payload.get("needs_manual_review", "") or "")) < 35:
            issues.append("需要人工复核的点过短，应明确列出图表、公式、抽取缺损或争议性解释。")
        evidence_text = json.dumps(evidence_payload, ensure_ascii=False)
        if "缺损" in evidence_text and "缺损" not in str(payload.get("needs_manual_review", "")):
            issues.append("证据预分析提到全文抽取缺损，最终报告需要在人工复核点中保留。")
        issues.extend(self._ollama_ai_engineering_deep_read_issues(payload, evidence_payload))
        return issues

    def _ollama_ai_engineering_deep_read_issues(self, payload: dict, evidence_payload: dict) -> list[str]:
        evidence_text = json.dumps(evidence_payload, ensure_ascii=False)
        evidence_lower = evidence_text.lower()
        if not (
            re.search(r"\bpinns?\b|physics[-\s]+informed|物理(?:信息|约束)神经网络", evidence_lower, flags=re.IGNORECASE)
            and re.search(r"\bxai\b|explainab|可解释性?人工智能", evidence_lower, flags=re.IGNORECASE)
        ):
            return []
        report_text = json.dumps(payload, ensure_ascii=False)
        report_lower = report_text.lower()
        issues: list[str] = []
        if not re.search(r"乘法式|误差传播|multiplicative|false confidence|虚假(?:可信|信心|验证)", report_lower, flags=re.IGNORECASE):
            issues.append("PINN/XAI 方法论文缺少对乘法式误差传播或虚假可信度机制的总结。")
        case_requirements = (
            ("Kirsch/圆孔应力集中案例", r"kirsch|圆孔|应力集中"),
            ("悬臂梁 XAI 案例", r"cantilever|悬臂梁"),
            ("分段刚度/材料不连续案例", r"piecewise|分段|材料不连续|刚度"),
        )
        missing_cases = [
            label
            for label, pattern in case_requirements
            if re.search(pattern, evidence_lower, flags=re.IGNORECASE)
            and not re.search(pattern, report_lower, flags=re.IGNORECASE)
        ]
        if missing_cases:
            issues.append(f"PINN/XAI 方法论文遗漏关键案例：{'、'.join(missing_cases)}。")
        if not re.search(r"敏感性分析|独立(?:工程)?审查|fail[-\s]?safe|验证协议|triangulat|不确定性", report_lower, flags=re.IGNORECASE):
            issues.append("PINN/XAI 方法论文缺少作者关于验证、敏感性分析、独立审查或 fail-safe 边界的实践建议。")
        return issues

    def _ollama_key_result_counts(self, value: str) -> dict[str, int]:
        labels = ("硬结论", "次级结论", "合理推论", "需进一步研究讨论的结论")
        text = str(value or "")
        counts: dict[str, int] = {}
        for index, label in enumerate(labels):
            next_labels = labels[index + 1 :]
            if next_labels:
                next_pattern = "|".join(re.escape(item) for item in next_labels)
                pattern = rf"{re.escape(label)}[:：]?\s*(.*?)(?={next_pattern}[:：]?|\Z)"
            else:
                pattern = rf"{re.escape(label)}[:：]?\s*(.*)\Z"
            match = re.search(pattern, text, flags=re.S)
            body = match.group(1).strip() if match else ""
            numbered = re.findall(r"(?m)^\s*(?:\d+[.．、)）]|[-*])\s+", body)
            if numbered:
                counts[label] = len(numbered)
            else:
                sentences = [item for item in re.split(r"[。！？；]\s*", body) if item.strip()]
                counts[label] = len(sentences)
        return counts

    def _ollama_relation_overstates_directness(self, payload: dict) -> bool:
        relation = str(payload.get("relation_to_my_work", "") or "")
        if not re.search(r"直接相关|高度相关|密切相关", relation):
            return False
        tags = [str(item) for item in payload.get("tags", []) if str(item).strip()]
        direct_tag = any(
            tag in {"热层/密度", "热层/风场", "卫星影响", "业务化预报"}
            or tag.startswith("应用/")
            or "卫星阻力" in tag
            or "空间环境风险" in tag
            for tag in tags
        )
        return not direct_tag

    def _downgrade_ollama_relation_overreach(self, payload: dict) -> dict:
        if not self._ollama_relation_overstates_directness(payload):
            return payload
        adjusted = dict(payload)
        adjusted["relation_to_my_work"] = (
            "间接相关。该文可作为空间天气扰动和磁层-电离层耦合的机制背景，"
            "但论文没有直接研究热层密度、热层风、卫星阻力或业务化预报，"
            "因此不宜直接外推到当前应用主线。"
        )
        return adjusted

    def _ollama_payload_contains_list_repr(self, payload: dict) -> bool:
        for value in payload.values():
            if not isinstance(value, str):
                continue
            text = value.strip()
            if text.startswith("[") and text.endswith("]"):
                return True
            if "['" in text or '["' in text:
                return True
        return False

    def _recover_ollama_article_payload(
        self,
        row: Row,
        prompt: str,
        schema: dict,
        request_name: str,
        exc: AnalysisProviderInvalidOutput,
    ) -> dict:
        repaired = self._repair_ollama_article_payload_from_error(row, schema, exc)
        if repaired is not None:
            return repaired

        retry_prompt = "\n".join(
            [
                self._build_article_prompt(self._short_article_retry_row(row)),
                "",
                "上一次输出不是合法的完整 JSON。本次必须只输出一个 JSON 对象，不能输出思考过程、Markdown、代码块或解释文字。",
                "required 字段即使证据不足也要保留；信息不足处用空字符串或空数组，不要省略字段。",
            ]
        )
        try:
            payload = self._run_ollama_structured(retry_prompt, schema, f"{request_name}_json_retry")
        except AnalysisProviderInvalidOutput:
            raise exc
        return self._coerce_article_payload(row, payload)

    def _repair_ollama_article_payload_from_error(
        self,
        row: Row,
        schema: dict,
        exc: AnalysisProviderInvalidOutput,
    ) -> dict | None:
        raw = self._invalid_output_text(exc)
        if not raw:
            return None
        candidates: list[str] = []
        extracted = _extract_json_object_candidate(raw)
        candidates.append(extracted)
        candidates.extend(_ollama_json_repair_candidates(extracted))
        for candidate in candidates:
            clean = str(candidate or "").strip()
            if not clean:
                continue
            payload: object
            try:
                payload = json.loads(clean)
            except json.JSONDecodeError:
                try:
                    payload = ast.literal_eval(clean)
                except Exception:
                    continue
            if not isinstance(payload, dict):
                continue
            if not self._looks_like_article_payload(payload, schema):
                continue
            coerced = self._coerce_article_payload(row, payload)
            if self._article_payload_has_required_keys(coerced, schema):
                return coerced
        return None

    def _invalid_output_text(self, exc: AnalysisProviderInvalidOutput) -> str:
        if exc.detail_path is not None and exc.detail_path.exists():
            text = exc.detail_path.read_text(encoding="utf-8", errors="replace")
            marker = "raw output:"
            if marker in text:
                return text.split(marker, 1)[1].strip()
            return text.strip()
        return exc.raw_preview.strip()

    def _article_payload_has_required_keys(self, payload: dict, schema: dict) -> bool:
        required = list(((schema or {}).get("schema") or {}).get("required", []) or [])
        return all(str(item) in payload for item in required)

    def _looks_like_article_payload(self, payload: dict, schema: dict) -> bool:
        required = {str(item) for item in (((schema or {}).get("schema") or {}).get("required", []) or [])}
        if required.intersection(payload):
            return True
        article_aliases = {"中文题目", "标题", "摘要", "标签", "一句话总结", "one_sentence_summary"}
        if article_aliases.intersection(str(key) for key in payload):
            return True
        provider_wrapper_keys = {"model", "created_at", "message", "done", "done_reason", "total_duration"}
        if provider_wrapper_keys.intersection(payload):
            return False
        return False

    def _coerce_article_payload(self, row: Row, payload: dict) -> dict:
        coerced = dict(payload)
        row_title = str(row["title"] if "title" in row.keys() else "")
        coerced["chinese_title"] = self._coerce_article_string_field(
            coerced.get("chinese_title"),
            fallback=clean_title_text(row_title),
        )
        coerced["tags"] = self._coerce_article_tags(coerced.get("tags"))
        for key in ("body", "supplement", "recommendation", "one_sentence"):
            coerced[key] = self._coerce_article_string_field(coerced.get(key))
        return {
            "chinese_title": coerced["chinese_title"],
            "tags": coerced["tags"],
            "body": coerced["body"],
            "supplement": coerced["supplement"],
            "recommendation": coerced["recommendation"],
            "one_sentence": coerced["one_sentence"],
        }

    def _coerce_article_string_field(self, value: object, *, fallback: str = "") -> str:
        if value is None:
            return fallback
        if isinstance(value, str):
            return clean_abstract_text(value) or fallback
        if isinstance(value, list):
            return clean_abstract_text("；".join(str(item).strip() for item in value if str(item).strip())) or fallback
        if isinstance(value, dict):
            return clean_abstract_text(json.dumps(value, ensure_ascii=False)) or fallback
        return clean_abstract_text(str(value)) or fallback

    def _coerce_article_tags(self, value: object) -> list[str]:
        raw_items: list[object]
        if isinstance(value, list):
            raw_items = value
        elif isinstance(value, str):
            text = value.strip()
            parsed: object | None = None
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    try:
                        parsed = ast.literal_eval(text)
                    except Exception:
                        parsed = None
            if isinstance(parsed, list):
                raw_items = parsed
            else:
                raw_items = re.split(r"[,，;；、\s]+", text)
        elif value is None:
            raw_items = []
        else:
            raw_items = [value]
        tags: list[str] = []
        for item in raw_items:
            clean = re.sub(r"\s+", "", str(item or "").strip().strip("#"))
            if clean and clean not in tags:
                tags.append(clean)
        return tags[:8]

    def _short_article_retry_row(self, row: Row) -> dict:
        short_row = dict(row)
        source_kind = str(short_row.get("summary_source_kind", "") or "").strip().lower()
        preserve_blocks = source_kind in {"html_full_text", "local_pdf_full_text"}
        source_text = _prepare_article_source_text_for_prompt(
            str(short_row.get("abstract", "") or ""),
            preserve_blocks=preserve_blocks,
        )
        max_chars = 2600 if preserve_blocks else 1600
        if len(source_text) > max_chars:
            source_text = source_text[:max_chars].rsplit(" ", 1)[0].strip() + (" ..." if not preserve_blocks else "\n...")
        short_row["abstract"] = source_text
        return short_row

    def _run_structured(
        self,
        prompt: str,
        schema: dict,
        name: str,
        *,
        reasoning_effort: str = "",
        manual_context: dict | None = None,
    ) -> dict:
        if self.provider == "codex_local":
            return self._run_codex_structured(prompt, schema, name, reasoning_effort=reasoning_effort)
        if self.provider == "openai_api":
            return self._run_openai_structured(prompt, schema, name)
        if self.provider == "openrouter_api":
            return self._run_openrouter_structured(prompt, schema, name)
        if self.provider == "ollama_api":
            return self._run_ollama_structured(prompt, schema, name)
        if self.provider == "chatgpt_web_manual":
            return self._run_chatgpt_web_manual_structured(
                prompt,
                schema,
                name,
                reasoning_effort=reasoning_effort,
                manual_context=manual_context,
            )
        raise RuntimeError(f"Unsupported analysis provider: {self.provider}")

    def _run_codex_structured(self, prompt: str, schema: dict, name: str, *, reasoning_effort: str = "") -> dict:
        schema_path = self.tmp_root / f"{name}_schema.json"
        output_path = self.tmp_root / f"{name}_output.json"
        stderr_path = self.tmp_root / f"{name}_codex.stderr.log"
        exec_root = Path(tempfile.mkdtemp(prefix="sciencemonitor_codex_exec_"))
        schema_path.write_text(json.dumps(schema["schema"], ensure_ascii=False), encoding="utf-8")
        if output_path.exists():
            output_path.unlink()
        if stderr_path.exists():
            stderr_path.unlink()

        settings = self.config.get("codex_local", {})
        codex_executable = self._resolve_codex_executable(settings)
        cmd = [
            codex_executable,
            "exec",
            "--sandbox",
            str(settings.get("sandbox", "read-only") or "read-only"),
            "--skip-git-repo-check",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "--cd",
            str(exec_root),
        ]
        model = str(settings.get("model", "") or "").strip()
        if model:
            cmd.extend(["--model", model])
        normalized_effort = self._normalize_reasoning_effort(reasoning_effort)
        if normalized_effort:
            cmd.extend(["-c", f'model_reasoning_effort="{normalized_effort}"'])
        cmd.append(prompt)
        timeout = int(settings.get("timeout_seconds", 180) or 180)
        try:
            with stderr_path.open("w", encoding="utf-8") as stderr_handle:
                try:
                    subprocess.run(
                        cmd,
                        cwd=exec_root,
                        check=True,
                        timeout=timeout,
                        stdout=subprocess.DEVNULL,
                        stderr=stderr_handle,
                        env=self._subprocess_env(),
                    )
                except FileNotFoundError as exc:
                    raise RuntimeError(
                        f"Codex executable not found: {codex_executable}. "
                        "Set codex_local.executable in config/analysis.json or SCIENCEMONITOR_CODEX_BIN."
                    ) from exc
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(
                        f"codex_local analysis timed out after {timeout}s. "
                        f"Details: {stderr_path}"
                    ) from exc
                except subprocess.CalledProcessError as exc:
                    stderr_text = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
                    raise RuntimeError(
                        _summarize_codex_failure(exc.returncode, stderr_text, stderr_path)
                    ) from exc
        finally:
            shutil.rmtree(exec_root, ignore_errors=True)
        if not output_path.exists():
            stderr_text = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
            raise RuntimeError(_summarize_codex_missing_output(stderr_text, stderr_path))
        return json.loads(output_path.read_text(encoding="utf-8"))

    def _run_openai_structured(self, prompt: str, schema: dict, name: str) -> dict:
        settings = self.config.get("openai_api", {})
        result = run_openai_structured(settings, prompt, schema)
        record_api_usage(
            self.root,
            provider="openai_api",
            model=str(settings.get("model", "gpt-5-mini") or "gpt-5-mini"),
            raw_usage=result.usage,
            request_name=name,
        )
        return result.payload

    def _run_openrouter_structured(self, prompt: str, schema: dict, name: str) -> dict:
        settings = self.config.get("openrouter_api", {})
        result = run_openrouter_structured(settings, prompt, schema)
        record_api_usage(
            self.root,
            provider="openrouter_api",
            model=str(settings.get("model", "openai/gpt-5-mini") or "openai/gpt-5-mini"),
            raw_usage=result.usage,
            request_name=name,
        )
        return result.payload

    def _run_ollama_structured(self, prompt: str, schema: dict, name: str) -> dict:
        settings = self._ollama_settings_for_request(name)
        timeout_seconds = int(settings.get("timeout_seconds", 900) or 900)
        try:
            result = run_ollama_structured(settings, prompt, schema, request_name=name)
        except TimeoutError as exc:
            raise AnalysisProviderTimeout(
                "ollama_api",
                timeout_seconds=timeout_seconds,
                request_name=name,
                phase="analysis",
            ) from exc
        except StructuredOutputParseError as exc:
            detail_path = self._write_invalid_provider_output(name, exc)
            raise AnalysisProviderInvalidOutput(
                "ollama_api",
                request_name=name,
                detail=exc.detail,
                raw_preview=exc.output_preview,
                detail_path=detail_path,
                phase="analysis",
            ) from exc
        record_api_usage(
            self.root,
            provider="ollama_api",
            model=str(settings.get("model", "gemma4:26b") or "gemma4:26b"),
            raw_usage=result.usage,
            request_name=name,
        )
        return result.payload

    def _ollama_settings_for_request(self, name: str) -> dict:
        settings = dict(self.config.get("ollama_api", {}) or {})
        settings["think"] = False
        if str(name or "").startswith("deep_read"):
            deep_predict = self._positive_int(settings.get("deep_read_num_predict"))
            if deep_predict > 0:
                settings["num_predict"] = deep_predict
            if self._ollama_keep_alive_is_zero(settings):
                settings["keep_alive"] = str(settings.get("deep_read_stage_keep_alive", "1m") or "1m")
        return settings

    def _ollama_keep_alive_is_zero(self, settings: dict) -> bool:
        value = settings.get("keep_alive")
        if value == 0:
            return True
        if isinstance(value, str) and value.strip() == "0":
            return True
        return False

    def _positive_int(self, value: object) -> int:
        try:
            number = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return number if number > 0 else 0

    def _ollama_deep_read_quality_mode_enabled(self) -> bool:
        settings = self.config.get("ollama_api", {})
        return bool(settings.get("deep_read_quality_mode", True))

    def _ollama_deep_read_final_text(self, full_text: str) -> str:
        settings = self.config.get("ollama_api", {})
        max_chars = int(settings.get("deep_read_final_max_chars", 16000) or 16000)
        text = str(full_text or "").strip()
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        head_chars = max(1000, int(max_chars * 0.65))
        tail_chars = max(800, max_chars - head_chars)
        head = text[:head_chars].rsplit(" ", 1)[0].strip()
        tail = text[-tail_chars:].split(" ", 1)[-1].strip()
        return "\n\n".join(
            [
                head,
                "[Ollama 深度解读说明：完整全文已在第一阶段证据预分析中读取；这里保留开头和结尾作为最终报告核对材料，避免本地模型最终阶段空响应或截断。]",
                tail,
            ]
        )

    def _ollama_deep_read_evidence_context(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None,
        *,
        cache_key: str,
    ) -> str:
        evidence_key = hashlib.sha1(f"deep_read_evidence_v1|{cache_key}".encode("utf-8")).hexdigest()
        cached = self._read_json_cache("deep_read_evidence", evidence_key)
        if cached is None:
            prompt = self._build_deep_read_evidence_prompt(metadata, full_text, related_summary)
            cached = self._run_ollama_structured(
                prompt,
                self._deep_read_evidence_schema(),
                f"deep_read_evidence_{cache_key[:20]}",
            )
            self._write_json_cache("deep_read_evidence", evidence_key, cached)
        return self._format_deep_read_evidence_context(cached)

    def _format_deep_read_evidence_context(self, payload: dict) -> str:
        labels = [
            ("research_problem", "研究问题"),
            ("introduction_gap", "引言空白"),
            ("method_chain", "方法与证据链"),
            ("result_chain", "结果链条"),
            ("evidence_limits", "证据边界"),
            ("relation_context", "与已有工作的关系"),
        ]
        lines: list[str] = []
        for key, label in labels:
            value = self._format_evidence_value(payload.get(key, ""))
            if value:
                lines.append(f"- {label}：{value}")
        return "\n".join(lines)

    def _format_evidence_value(self, value: object, *, numbered: bool = False) -> str:
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            if numbered:
                return "\n".join(f"{index}. {part}" for index, part in enumerate(parts, start=1))
            return "；".join(parts)
        return str(value or "").strip()

    def _write_invalid_provider_output(self, name: str, exc: StructuredOutputParseError) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "analysis")).strip("_") or "analysis"
        path = self.tmp_root / f"{safe_name}_invalid_output.txt"
        path.write_text(
            "\n".join(
                [
                    f"provider: {exc.provider}",
                    f"detail: {exc.detail}",
                    "",
                    "raw output:",
                    exc.output_text,
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _run_chatgpt_web_manual_structured(
        self,
        prompt: str,
        schema: dict,
        name: str,
        *,
        reasoning_effort: str = "",
        manual_context: dict | None = None,
    ) -> dict:
        title = str((manual_context or {}).get("title", "") or name)
        request_kind = str((manual_context or {}).get("request_kind", "") or "analysis")
        bundle = prepare_manual_request_bundle(
            self.root,
            request_id=name,
            request_kind=request_kind,
            title=title,
            prompt=prompt,
            schema=schema,
            reasoning_effort=reasoning_effort,
            context=manual_context,
        )
        payload = load_manual_response(
            self.root,
            request_id=name,
            prompt_signature=bundle.prompt_signature,
            schema=schema,
        )
        if payload is not None:
            return payload
        raise ManualResponsePending(bundle)

    def provider_status(self) -> dict:
        codex_settings = self.config.get("codex_local", {})
        openai_settings = self.config.get("openai_api", {})
        openrouter_settings = self.config.get("openrouter_api", {})
        ollama_settings = self.config.get("ollama_api", {})
        codex_executable = self._resolve_codex_executable(codex_settings, strict=False)
        api_key = self._resolve_openai_api_key(openai_settings)
        openrouter_api_key = self._resolve_openrouter_api_key(openrouter_settings)
        ollama_base_url = resolve_base_url(
            ollama_settings,
            default_url="http://127.0.0.1:11434/api/chat",
            provider_name="ollama_api",
            strict=False,
        )
        manual_counts = manual_status_counts(self.root)
        return {
            "provider": self.provider,
            "provider_supported": self.provider in SUPPORTED_ANALYSIS_PROVIDERS,
            "supported_providers": list(SUPPORTED_ANALYSIS_PROVIDERS),
            "codex_executable": codex_executable,
            "codex_available": bool(codex_executable),
            "codex_model": str(codex_settings.get("model", "") or "").strip(),
            "article_reasoning_effort": self._analysis_reasoning_effort("article_summaries"),
            "report_reasoning_effort": self._analysis_reasoning_effort("report"),
            "deep_read_reasoning_effort": self._analysis_reasoning_effort("deep_reads"),
            "openai_base_url": resolve_base_url(
                openai_settings,
                default_url="https://api.openai.com/v1/responses",
                provider_name="openai_api",
                strict=False,
            ),
            "openai_api_key_present": bool(api_key),
            "openai_api_key_source": resolve_api_key_source(
                openai_settings,
                env_name="SCIENCEMONITOR_OPENAI_API_KEY",
                fallback_env_name="OPENAI_API_KEY",
            ),
            "openai_model": str(openai_settings.get("model", "gpt-5-mini") or "gpt-5-mini"),
            "openrouter_base_url": resolve_base_url(
                openrouter_settings,
                default_url="https://openrouter.ai/api/v1/chat/completions",
                provider_name="openrouter_api",
                strict=False,
            ),
            "openrouter_api_key_present": bool(openrouter_api_key),
            "openrouter_api_key_source": resolve_api_key_source(
                openrouter_settings,
                env_name="SCIENCEMONITOR_OPENROUTER_API_KEY",
                fallback_env_name="OPENROUTER_API_KEY",
            ),
            "openrouter_model": str(openrouter_settings.get("model", "openai/gpt-5-mini") or "openai/gpt-5-mini"),
            "ollama_base_url": ollama_base_url,
            "ollama_model": str(ollama_settings.get("model", "gemma4:26b") or "gemma4:26b"),
            "ollama_available": check_ollama_available(ollama_settings) if self.provider == "ollama_api" else False,
            "chatgpt_web_manual_root": str(chatgpt_web_manual_root(self.root)),
            "chatgpt_web_manual_pending": int(manual_counts.get("pending", 0)),
            "chatgpt_web_manual_ready": int(manual_counts.get("ready", 0)),
            "chatgpt_web_manual_stale": int(manual_counts.get("stale", 0)),
        }

    def _build_article_prompt(self, row: Row) -> str:
        return build_article_prompt(row, self.user_preferences)

    def _build_manual_article_prompt(self, row: Row) -> str:
        return build_manual_article_prompt(row)

    def _build_report_prompt(self, report_date: date, summaries: list[ArticleSummaryResult]) -> str:
        return build_report_prompt(report_date, summaries, self.user_preferences)

    def _build_manual_report_prompt(self, report_date: date, summaries: list[ArticleSummaryResult]) -> str:
        return build_manual_report_prompt(report_date, summaries)

    def _build_deep_read_prompt(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None = None,
        evidence_context: str = "",
    ) -> str:
        return build_deep_read_prompt(metadata, full_text, related_summary, self.user_preferences, evidence_context=evidence_context)

    def _build_deep_read_evidence_prompt(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None = None,
    ) -> str:
        return build_deep_read_evidence_prompt(metadata, full_text, related_summary, self.user_preferences)

    def _build_ollama_deep_read_evidence_prompt_v2(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None = None,
    ) -> str:
        return build_ollama_deep_read_evidence_prompt_v2(metadata, full_text, related_summary, self.user_preferences)

    def _build_ollama_deep_read_final_prompt_v2(
        self,
        metadata: dict[str, str],
        final_context: str,
        related_summary: dict[str, str] | None = None,
        *,
        evidence_context: str,
    ) -> str:
        return build_ollama_deep_read_final_prompt_v2(
            metadata,
            final_context,
            related_summary,
            self.user_preferences,
            evidence_context=evidence_context,
        )

    def _build_ollama_deep_read_revision_prompt_v2(
        self,
        metadata: dict[str, str],
        current_payload: dict,
        issues: list[str],
        evidence_context: str,
    ) -> str:
        return build_ollama_deep_read_revision_prompt_v2(
            metadata,
            current_payload,
            issues,
            evidence_context,
            self.user_preferences,
        )

    def _build_manual_deep_read_prompt(
        self,
        metadata: dict[str, str],
        related_summary: dict[str, str] | None = None,
    ) -> str:
        return build_manual_deep_read_prompt(metadata, related_summary)

    def _deep_read_schema(self) -> dict:
        return build_deep_read_schema()

    def _deep_read_evidence_schema(self) -> dict:
        return build_deep_read_evidence_schema()

    def _ollama_deep_read_evidence_schema_v2(self) -> dict:
        return build_ollama_deep_read_evidence_schema_v2()

    def _article_schema(self) -> dict:
        return build_article_schema()

    def _report_schema(self, summaries: list[ArticleSummaryResult]) -> dict:
        return build_report_schema(summaries)

    def _article_cache_key(self, row: Row) -> str:
        source_kind = str(row["summary_source_kind"]).strip().lower() if "summary_source_kind" in row.keys() else ""
        source_text = _prepare_article_source_text_for_prompt(str(row["abstract"] or ""), preserve_blocks=True)
        source_title = clean_title_text(str(row["title"] if "title" in row.keys() else ""))
        identity = str(row["doi"]).strip().lower() or str(row["fingerprint"])
        basis = "|".join(
            [
                "article_v5",
                identity,
                source_kind,
                hashlib.sha1(source_title.encode("utf-8")).hexdigest()[:12],
                hashlib.sha1(source_text.encode("utf-8")).hexdigest()[:16],
                self._analysis_signature("article_summaries"),
            ]
        )
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:20]

    def _analysis_reasoning_effort(self, section: str) -> str:
        settings = self.config.get(section, {})
        if not isinstance(settings, dict):
            return ""
        return self._normalize_reasoning_effort(str(settings.get("reasoning_effort", "") or ""))

    def _normalize_reasoning_effort(self, value: str) -> str:
        clean = str(value or "").strip().lower()
        if clean in SUPPORTED_REASONING_EFFORTS:
            return clean
        return ""

    def _analysis_signature(self, section: str) -> str:
        if self.provider == "openai_api":
            openai_settings = self.config.get("openai_api", {})
            model = str(openai_settings.get("model", "gpt-5-mini") or "gpt-5-mini").strip() or "gpt-5-mini"
        elif self.provider == "openrouter_api":
            openrouter_settings = self.config.get("openrouter_api", {})
            model = str(openrouter_settings.get("model", "openai/gpt-5-mini") or "openai/gpt-5-mini").strip() or "openai/gpt-5-mini"
        elif self.provider == "ollama_api":
            ollama_settings = self.config.get("ollama_api", {})
            model = str(ollama_settings.get("model", "gemma4:26b") or "gemma4:26b").strip() or "gemma4:26b"
            num_ctx = str(ollama_settings.get("num_ctx", "") or "").strip()
            num_predict = str(ollama_settings.get("num_predict", "") or "").strip()
            if section == "deep_reads":
                deep_num_predict = str(ollama_settings.get("deep_read_num_predict", "") or "").strip()
                final_chars = str(ollama_settings.get("deep_read_final_max_chars", "") or "").strip()
                quality = "quality_v2" if ollama_settings.get("deep_read_quality_mode", True) else "standard"
                model = (
                    f"{model}|ctx={num_ctx or 'default'}|predict={num_predict or 'default'}"
                    f"|deep_predict={deep_num_predict or 'default'}|final_chars={final_chars or 'default'}|deep_read={quality}"
                )
            else:
                quality = "quality" if ollama_settings.get("deep_read_quality_mode", True) else "standard"
                model = f"{model}|ctx={num_ctx or 'default'}|predict={num_predict or 'default'}|deep_read={quality}"
        elif self.provider == "chatgpt_web_manual":
            model = "chatgpt_web_manual"
        else:
            codex_settings = self.config.get("codex_local", {})
            model = str(codex_settings.get("model", "") or "").strip() or "default"
        effort = self._analysis_reasoning_effort(section) or "default"
        return f"{self.provider}|{model}|{effort}"

    def _read_json_cache(self, namespace: str, key: str) -> dict | None:
        path = self.cache_root / namespace / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json_cache(self, namespace: str, key: str, payload: dict) -> None:
        path = self.cache_root / namespace
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{key}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize_text_list(self, items: list) -> list[str]:
        normalized: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            if "',' " in text or '","' in text or "。','" in text or "；','" in text or '。","' in text or '；","' in text:
                splitter = '","' if '","' in text else "','"
                for part in text.split(splitter):
                    clean = part.strip(" '\"")
                    if clean:
                        normalized.append(clean)
                continue
            normalized.append(text)
        return normalized

    def _load_config(self, path: Path) -> dict:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(DEFAULT_ANALYSIS_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
            return json.loads(json.dumps(DEFAULT_ANALYSIS_CONFIG))
        payload = json.loads(path.read_text(encoding="utf-8"))
        merged = json.loads(json.dumps(DEFAULT_ANALYSIS_CONFIG))
        for key, value in payload.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        for section in ("article_summaries", "report", "deep_reads"):
            if isinstance(merged.get(section), dict):
                merged[section].pop("fallback_to_rules", None)
        return merged

    def _ensure_supported_provider(self) -> None:
        if self.provider in SUPPORTED_ANALYSIS_PROVIDERS:
            return
        raise RuntimeError(
            "当前 analysis provider 已不再支持。现在只支持 codex_local、openai_api、openrouter_api、ollama_api 或 chatgpt_web_manual。"
        )

    def _resolve_codex_executable(self, settings: dict, strict: bool = True) -> str:
        candidate = (
            str(settings.get("executable", "") or "").strip()
            or os.environ.get("SCIENCEMONITOR_CODEX_BIN", "").strip()
            or os.environ.get("CODEX_BIN", "").strip()
        )
        if candidate:
            resolved = str(Path(candidate).expanduser()) if "/" in candidate else shutil.which(candidate)
            if resolved:
                return resolved
            if strict:
                raise RuntimeError(f"Configured Codex executable was not found: {candidate}")
            return ""
        resolved = shutil.which("codex")
        if resolved:
            return resolved
        for fallback in DEFAULT_CODEX_EXECUTABLE_CANDIDATES:
            if fallback.exists() and os.access(fallback, os.X_OK):
                return str(fallback)
        if strict:
            raise RuntimeError("codex_local provider requires the codex CLI to be installed and on PATH.")
        return ""

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        venv_bin = str(self.root / ".venv" / "bin")
        path_entries = [item for item in env.get("PATH", "").split(os.pathsep) if item]
        if not path_entries or path_entries[0] != venv_bin:
            env["PATH"] = os.pathsep.join([venv_bin, *[item for item in path_entries if item != venv_bin]])
        env.setdefault("VIRTUAL_ENV", str(self.root / ".venv"))
        env.setdefault("PYTHONNOUSERSITE", "1")
        return env

    def _normalize_tags(self, tags: list[str]) -> list[str]:
        normalized = review_generated_tags(tags, root=self.root, max_tags=8, context="llm_analysis")
        if normalized:
            return normalized

        fallback: list[str] = []
        for tag in tags:
            clean = re.sub(r"\s+", "", str(tag))
            if not clean:
                continue
            canonical = clean
            for pattern, replacement in FALLBACK_TAG_NORMALIZATION_RULES:
                if re.search(pattern, clean, flags=re.IGNORECASE):
                    canonical = replacement
                    break
            if canonical not in fallback:
                fallback.append(canonical)
        return self._prefer_more_specific_tags(fallback)[:8]

    def _resolve_openai_api_key(self, settings: dict) -> str:
        return resolve_api_key(
            settings,
            env_name="SCIENCEMONITOR_OPENAI_API_KEY",
            fallback_env_name="OPENAI_API_KEY",
        )

    def _resolve_openrouter_api_key(self, settings: dict) -> str:
        return resolve_api_key(
            settings,
            env_name="SCIENCEMONITOR_OPENROUTER_API_KEY",
            fallback_env_name="OPENROUTER_API_KEY",
        )

    def _resolve_openai_api_key_source(self, settings: dict) -> str:
        return resolve_api_key_source(
            settings,
            env_name="SCIENCEMONITOR_OPENAI_API_KEY",
            fallback_env_name="OPENAI_API_KEY",
        )

    def _resolve_openrouter_api_key_source(self, settings: dict) -> str:
        return resolve_api_key_source(
            settings,
            env_name="SCIENCEMONITOR_OPENROUTER_API_KEY",
            fallback_env_name="OPENROUTER_API_KEY",
        )

    def _resolve_openai_base_url(self, settings: dict, strict: bool = True) -> str:
        return resolve_base_url(
            settings,
            default_url="https://api.openai.com/v1/responses",
            provider_name="openai_api",
            strict=strict,
        )

    def _resolve_openrouter_base_url(self, settings: dict, strict: bool = True) -> str:
        return resolve_base_url(
            settings,
            default_url="https://openrouter.ai/api/v1/chat/completions",
            provider_name="openrouter_api",
            strict=strict,
        )

    def normalize_tags(self, tags: list[str]) -> list[str]:
        return self._normalize_tags(tags)

    def _prefer_more_specific_tags(self, tags: list[str]) -> list[str]:
        refined: list[str] = []
        for tag in tags:
            if any(other != tag and other.startswith(tag + "/") for other in tags):
                continue
            refined.append(tag)
        return refined

    def _manual_context_for_article(self, row: Row) -> dict:
        title = clean_title_text(str(row["title"] or ""))
        source_kind = str(row["summary_source_kind"] or "").strip() if "summary_source_kind" in row.keys() else ""
        return {
            "request_kind": "article_summary",
            "title": title or str(row["doi"] or row["fingerprint"] or "article"),
            "request_label": self._manual_request_label(
                str(row["doi"] or ""),
                str(row["fingerprint"] or ""),
                title,
            ),
            "resource_hints": {
                "title": title,
                "doi": str(row["doi"] or ""),
                "url": str(row["url"] or ""),
                "journal": str(row["source_name"] or ""),
                "published_date": str(row["published_date"] or ""),
                "authors": str(row["authors"] or "").replace("\n", ", "),
                "topic_labels": str(row["topic_labels"] or "").replace("\n", "、"),
            },
            "source_kind": source_kind,
        }

    def _manual_context_for_report(
        self,
        report_date: date,
        summaries: list[ArticleSummaryResult],
    ) -> dict:
        return {
            "request_kind": "weekly_report",
            "title": f"{report_date.isoformat()} 周报",
            "request_label": f"{report_date.isoformat()}_weekly_report",
            "resource_hints": {
                "report_date": report_date.isoformat(),
                "paper_count": str(len(summaries)),
                "paper_titles": "；".join(clean_title_text(str(item.row["title"] or "")) for item in summaries[:12]),
            },
        }

    def _manual_context_for_deep_read(self, metadata: dict[str, str], full_text: str) -> dict:
        return {
            "request_kind": "deep_read",
            "title": clean_title_text(str(metadata.get("title", "") or "")) or str(metadata.get("doi", "") or "deep_read"),
            "request_label": self._manual_request_label(
                str(metadata.get("doi", "") or ""),
                str(metadata.get("title", "") or ""),
            ),
            "resource_hints": {
                "title": str(metadata.get("title", "") or ""),
                "doi": str(metadata.get("doi", "") or ""),
                "url": str(metadata.get("url", "") or ""),
                "journal": str(metadata.get("journal", "") or ""),
                "published_date": str(metadata.get("published_date", "") or ""),
                "authors": str(metadata.get("authors", "") or ""),
            },
        }

    def _manual_request_label(self, *values: str) -> str:
        for value in values:
            clean = re.sub(r"[^0-9A-Za-z]+", "_", str(value or "").strip().lower()).strip("_")
            if clean:
                return clean[:64]
        return "request"
