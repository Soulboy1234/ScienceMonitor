from __future__ import annotations

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
    resolve_api_key,
    resolve_api_key_source,
    resolve_base_url,
    run_openai_structured,
    run_openrouter_structured,
)
from .llm_contracts import (
    _prepare_article_source_text_for_prompt,
    build_article_prompt,
    build_article_schema,
    build_deep_read_prompt,
    build_deep_read_schema,
    build_manual_article_prompt,
    build_manual_deep_read_prompt,
    build_manual_report_prompt,
    build_report_prompt,
    build_report_schema,
)
from .models import ArticleSummaryResult
from .tags import normalize_tags as normalize_project_tags
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
    (r"月球|moon|lunar", "其他行星/月球"),
    (r"火星|mars|martian", "其他行星/火星"),
    (r"金星|venus|venusian", "其他行星/金星"),
    (r"水星|mercury|mercurian", "其他行星/水星"),
    (r"木星|jupiter|jovian", "其他行星/木星"),
    (r"土星|saturn|saturnian", "其他行星/土星"),
    (r"天王星|uranus|uranian", "其他行星/天王星"),
    (r"海王星|neptune|neptunian", "其他行星/海王星"),
    (r"广义线性模型|generalized linear model|\bglm\b", "建模/统计模型/GLM"),
    (r"观测/?射电掩星|射电掩星", "仪器/射电掩星"),
    (r"探测器/?kplo|danuri|kplo", "仪器/KPLO"),
    (r"物理量/?电子密度", "电离层/电子密度"),
]
def _summarize_codex_missing_output(stderr_text: str, stderr_path: Path) -> str:
    lowered = stderr_text.lower()
    if "usage limit" in lowered or "purchase more credits" in lowered or "upgrade to pro" in lowered:
        return (
            "codex_local analysis did not produce structured output because the account hit its usage limit. "
            f"Details: {stderr_path}"
        )
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
        return (
            "codex_local analysis stopped because the account hit its usage limit. "
            f"Details: {stderr_path}"
        )
    return f"codex_local analysis failed with exit code {returncode}. Details: {stderr_path}"

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
    topic_insights: list[TopicInsight] = field(default_factory=list)
    journal_insights: list[JournalInsight] = field(default_factory=list)

    def topic_summary(self, label: str) -> str | None:
        for item in self.topic_insights:
            if item.label == label:
                return item.summary
        return None

    def journal_summary(self, journal: str) -> str | None:
        for item in self.journal_insights:
            if item.journal == journal:
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
        payload = self._run_structured(
            prompt,
            schema,
            f"article_{cache_key}",
            reasoning_effort=self._analysis_reasoning_effort("article_summaries"),
            manual_context=self._manual_context_for_article(row),
        )
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
            str(summary.row["doi"] or summary.row["fingerprint"] or summary.note_title)
            for summary in selected_summaries
        )
        signature_hash = hashlib.sha1(summary_signature.encode("utf-8")).hexdigest()[:12]
        cache_basis = "|".join(
            [
                "report_v2",
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
    ) -> DeepReadAnalysis | None:
        if not self.deep_read_enabled():
            return None
        self._ensure_supported_provider()

        normalized_full_text = clean_abstract_text(full_text)
        if self.provider != "chatgpt_web_manual" and not normalized_full_text:
            return None

        cache_basis = "|".join(
            [
                "deep_read_template_v5",
                str(metadata.get("doi", "")),
                str(metadata.get("title", "")),
                str(metadata.get("journal", "")),
                hashlib.sha1(normalized_full_text.encode("utf-8")).hexdigest()[:16] if normalized_full_text else "manual_web_search",
                self._analysis_signature("deep_reads"),
            ]
        )
        cache_key = hashlib.sha1(cache_basis.encode("utf-8")).hexdigest()
        cached = self._read_json_cache("deep_reads", cache_key)
        if cached:
            return self._deep_read_from_payload(cached)

        prompt = (
            self._build_manual_deep_read_prompt(metadata, related_summary)
            if self.provider == "chatgpt_web_manual"
            else self._build_deep_read_prompt(metadata, normalized_full_text, related_summary)
        )
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
            return self._run_openai_structured(prompt, schema)
        if self.provider == "openrouter_api":
            return self._run_openrouter_structured(prompt, schema)
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

    def _run_openai_structured(self, prompt: str, schema: dict) -> dict:
        return run_openai_structured(self.config.get("openai_api", {}), prompt, schema)

    def _run_openrouter_structured(self, prompt: str, schema: dict) -> dict:
        return run_openrouter_structured(self.config.get("openrouter_api", {}), prompt, schema)

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
        codex_executable = self._resolve_codex_executable(codex_settings, strict=False)
        api_key = self._resolve_openai_api_key(openai_settings)
        openrouter_api_key = self._resolve_openrouter_api_key(openrouter_settings)
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
    ) -> str:
        return build_deep_read_prompt(metadata, full_text, related_summary, self.user_preferences)

    def _build_manual_deep_read_prompt(
        self,
        metadata: dict[str, str],
        related_summary: dict[str, str] | None = None,
    ) -> str:
        return build_manual_deep_read_prompt(metadata, related_summary)

    def _deep_read_schema(self) -> dict:
        return build_deep_read_schema()

    def _article_schema(self) -> dict:
        return build_article_schema()

    def _report_schema(self, summaries: list[ArticleSummaryResult]) -> dict:
        return build_report_schema(summaries)

    def _article_cache_key(self, row: Row) -> str:
        source_kind = str(row["summary_source_kind"]).strip().lower() if "summary_source_kind" in row.keys() else ""
        source_text = _prepare_article_source_text_for_prompt(str(row["abstract"] or ""), preserve_blocks=True)
        identity = str(row["doi"]).strip().lower() or str(row["fingerprint"])
        basis = "|".join(
            [
                "article_v5",
                identity,
                source_kind,
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
            "当前 analysis provider 已不再支持。现在只支持 codex_local、openai_api、openrouter_api 或 chatgpt_web_manual。"
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
        normalized = normalize_project_tags(tags, root=self.root, max_tags=8)
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
