from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from sqlite3 import Row
from typing import TYPE_CHECKING
from urllib import request
from urllib.parse import urlparse

from .config import llm_cache_root, llm_tmp_root, load_focus_tags, load_master_plan_preferences
from .http import DEFAULT_HEADERS
from .utils import clean_abstract_text, clean_title_text

if TYPE_CHECKING:
    from .article_summaries import ArticleSummaryResult


DEFAULT_ANALYSIS_CONFIG = {
    "provider": "rules",
    "article_summaries": {
        "enabled": True,
        "max_items_per_run": 3,
        "fallback_to_rules": True,
    },
    "report": {
        "enabled": True,
        "max_papers_in_prompt": 25,
        "fallback_to_rules": True,
    },
    "deep_reads": {
        "enabled": True,
        "max_input_chars": 28000,
        "fallback_to_rules": False,
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
}

FALLBACK_TAG_NORMALIZATION_RULES = [
    (r"低纬.*电离层|电离层.*低纬|赤道电离层", "电离层/低纬"),
    (r"高纬.*电离层|电离层.*高纬|极区电离层", "电离层/高纬"),
    (r"中纬.*电离层|电离层.*中纬", "电离层/中纬"),
    (r"电离层.*不规则体|等离子体泡|赤道等离子体泡", "电离层/不规则体"),
    (r"电离层.*闪烁", "电离层/闪烁"),
    (r"月球.*电离层|电离层.*月球", "电离层/月球"),
    (r"极区对流.*边界|边界.*极区对流|polar convection", "极区对流/边界"),
    (r"空间天气.*预报|预报.*空间天气", "空间天气"),
    (r"磁层状态|磁层活动|磁层/活动", "磁层"),
    (r"热层风场|中性风|thermospheric wind|neutral wind|meridional wind|zonal wind", "热层/风"),
    (r"热层密度|中性密度|thermospheric mass density|thermospheric density|neutral density|satellite drag|drag environment|drag of leo satellites|leo satellite drag", "热层/密度"),
    (r"热层成分|o/n2|composition|nitric oxide|一氧化氮|atomic oxygen", "热层/成分"),
    (r"热层温度|中性温度|thermospheric temperature|neutral temperature|exospheric temperature", "热层/温度"),
    (r"地球|earth|terrestrial", "研究星球/地球"),
    (r"月球|moon|lunar", "研究星球/月球"),
    (r"火星|mars|martian", "研究星球/火星"),
    (r"金星|venus|venusian", "研究星球/金星"),
    (r"水星|mercury|mercurian", "研究星球/水星"),
    (r"木星|jupiter|jovian", "研究星球/木星"),
    (r"土星|saturn|saturnian", "研究星球/土星"),
    (r"天王星|uranus|uranian", "研究星球/天王星"),
    (r"海王星|neptune|neptunian", "研究星球/海王星"),
    (r"总电子含量|total electron content|\btec\b", "TEC"),
    (r"广义线性模型|generalized linear model|\bglm\b", "GLM"),
    (r"观测/?射电掩星|射电掩星", "射电掩星"),
    (r"探测器/?kplo|danuri|kplo", "KPLO"),
    (r"物理量/?电子密度", "电子密度"),
]


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
        self.focus_tags = load_focus_tags(root / "config" / "focus_tags.json")
        self.user_preferences = load_master_plan_preferences(root)
        self.provider = str(self.config.get("provider", "rules") or "rules")
        self.cache_root = llm_cache_root(root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.tmp_root = llm_tmp_root(root)
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self.tag_normalization_rules = self._build_tag_normalization_rules()

    def article_enabled(self) -> bool:
        return bool(self.config.get("article_summaries", {}).get("enabled", True))

    def report_enabled(self) -> bool:
        return bool(self.config.get("report", {}).get("enabled", True))

    def deep_read_enabled(self) -> bool:
        return bool(self.config.get("deep_reads", {}).get("enabled", True))

    def article_limit(self) -> int:
        return int(self.config.get("article_summaries", {}).get("max_items_per_run", 5) or 0)

    def report_prompt_limit(self) -> int:
        return int(self.config.get("report", {}).get("max_papers_in_prompt", 25) or 25)

    def deep_read_max_input_chars(self) -> int:
        return int(self.config.get("deep_reads", {}).get("max_input_chars", 28000) or 28000)

    def article_fallback_to_rules(self) -> bool:
        return bool(self.config.get("article_summaries", {}).get("fallback_to_rules", True))

    def report_fallback_to_rules(self) -> bool:
        return bool(self.config.get("report", {}).get("fallback_to_rules", True))

    def deep_read_fallback_to_rules(self) -> bool:
        return bool(self.config.get("deep_reads", {}).get("fallback_to_rules", False))

    def analyze_article(self, row: Row, index: int) -> ArticleAnalysis | None:
        if self.provider == "rules" or not self.article_enabled():
            return None
        limit = self.article_limit()
        if limit > 0 and index >= limit:
            return None

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

        prompt = self._build_article_prompt(row)
        schema = self._article_schema()
        payload = self._run_structured(prompt, schema, f"article_{cache_key}")
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

    def analyze_report(self, report_date: date, summaries: list["ArticleSummaryResult"]) -> ReportAnalysis | None:
        if self.provider == "rules" or not self.report_enabled() or not summaries:
            return None

        selected_summaries = summaries[: max(1, self.report_prompt_limit())]
        summary_signature = "|".join(
            str(summary.row["doi"] or summary.row["fingerprint"] or summary.note_title)
            for summary in selected_summaries
        )
        signature_hash = hashlib.sha1(summary_signature.encode("utf-8")).hexdigest()[:12]
        cache_key = f"{report_date.isoformat()}_{len(selected_summaries)}_{signature_hash}_{self.provider}"
        cached = self._read_json_cache("reports", cache_key)
        if cached:
            return self._report_from_payload(cached)

        prompt = self._build_report_prompt(report_date, selected_summaries)
        schema = self._report_schema(selected_summaries)
        payload = self._run_structured(prompt, schema, f"report_{cache_key}")
        self._write_json_cache("reports", cache_key, payload)
        return self._report_from_payload(payload)

    def analyze_deep_read(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None = None,
    ) -> DeepReadAnalysis | None:
        if self.provider == "rules" or not self.deep_read_enabled():
            return None

        normalized_full_text = clean_abstract_text(full_text)
        if not normalized_full_text:
            return None
        max_chars = max(self.deep_read_max_input_chars(), 4000)
        if len(normalized_full_text) > max_chars:
            normalized_full_text = normalized_full_text[:max_chars].rsplit(" ", 1)[0].strip() + " ..."

        cache_basis = "|".join(
            [
                "deep_read_template_v2",
                str(metadata.get("doi", "")),
                str(metadata.get("title", "")),
                str(metadata.get("journal", "")),
                hashlib.sha1(normalized_full_text.encode("utf-8")).hexdigest()[:16],
                self.provider,
            ]
        )
        cache_key = hashlib.sha1(cache_basis.encode("utf-8")).hexdigest()
        cached = self._read_json_cache("deep_reads", cache_key)
        if cached:
            return self._deep_read_from_payload(cached)

        prompt = self._build_deep_read_prompt(metadata, normalized_full_text, related_summary)
        schema = self._deep_read_schema()
        payload = self._run_structured(prompt, schema, f"deep_read_{cache_key}")
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

    def _run_structured(self, prompt: str, schema: dict, name: str) -> dict:
        if self.provider == "codex_local":
            return self._run_codex_structured(prompt, schema, name)
        if self.provider == "openai_api":
            return self._run_openai_structured(prompt, schema)
        raise RuntimeError(f"Unsupported analysis provider: {self.provider}")

    def _run_codex_structured(self, prompt: str, schema: dict, name: str) -> dict:
        schema_path = self.tmp_root / f"{name}_schema.json"
        output_path = self.tmp_root / f"{name}_output.json"
        stderr_path = self.tmp_root / f"{name}_codex.stderr.log"
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
            str(self.root),
        ]
        model = str(settings.get("model", "") or "").strip()
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)
        timeout = int(settings.get("timeout_seconds", 180) or 180)
        with stderr_path.open("w", encoding="utf-8") as stderr_handle:
            try:
                subprocess.run(
                    cmd,
                    cwd=self.root,
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
                raise RuntimeError(
                    f"codex_local analysis failed with exit code {exc.returncode}. "
                    f"Details: {stderr_path}"
                ) from exc
        return json.loads(output_path.read_text(encoding="utf-8"))

    def _run_openai_structured(self, prompt: str, schema: dict) -> dict:
        settings = self.config.get("openai_api", {})
        api_key = self._resolve_openai_api_key(settings)
        if not api_key:
            raise RuntimeError(
                "openai_api provider requires an API key via config/analysis.json "
                "or environment variable SCIENCEMONITOR_OPENAI_API_KEY."
            )
        base_url = self._resolve_openai_base_url(settings)

        payload = {
            "model": str(settings.get("model", "gpt-5-mini") or "gpt-5-mini"),
            "instructions": "你是 Space Physics 文献分析助手。只根据给定标题、摘要和元数据输出中文分析，不要编造全文细节。",
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema["name"],
                    "schema": schema["schema"],
                    "strict": True,
                }
            },
        }
        req = request.Request(
            base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                **DEFAULT_HEADERS,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=int(settings.get("timeout_seconds", 120) or 120)) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        output_text = data.get("output_text", "")
        if not output_text:
            for item in data.get("output", []):
                if item.get("type") != "message":
                    continue
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        output_text = content.get("text", "")
                        break
                if output_text:
                    break
        if not output_text:
            raise RuntimeError("OpenAI response did not include output_text")
        return json.loads(output_text)

    def provider_status(self) -> dict:
        codex_settings = self.config.get("codex_local", {})
        openai_settings = self.config.get("openai_api", {})
        codex_executable = self._resolve_codex_executable(codex_settings, strict=False)
        api_key = self._resolve_openai_api_key(openai_settings)
        return {
            "provider": self.provider,
            "codex_executable": codex_executable,
            "codex_available": bool(codex_executable),
            "codex_model": str(codex_settings.get("model", "") or "").strip(),
            "openai_base_url": self._resolve_openai_base_url(openai_settings, strict=False),
            "openai_api_key_present": bool(api_key),
            "openai_api_key_source": self._resolve_openai_api_key_source(openai_settings),
            "openai_model": str(openai_settings.get("model", "gpt-5-mini") or "gpt-5-mini"),
        }

    def _build_article_prompt(self, row: Row) -> str:
        cleaned_title = clean_title_text(str(row["title"] or ""))
        cleaned_abstract = clean_abstract_text(str(row["abstract"] or ""))
        if len(cleaned_abstract) > 1800:
            cleaned_abstract = cleaned_abstract[:1800].rsplit(" ", 1)[0].strip() + " ..."
        preference_lines: list[str] = []
        if self.user_preferences.priority_themes:
            preference_lines.append(f"当前用户近期更关注：{'、'.join(self.user_preferences.priority_themes)}。")
        if self.user_preferences.priority_alerts:
            preference_lines.append("以下类型文章应优先提醒：")
            preference_lines.extend(f"- {item}" for item in self.user_preferences.priority_alerts[:6])
        return "\n".join(
            [
                "请为一篇空间物理相关论文生成中文文献卡片字段。",
                "要求：",
                "1. 只根据提供的标题、摘要、期刊和主题标签判断。",
                "2. 中文题目要像研究者笔记里的简明概括，不要直译英文标题。",
                "3. 标签只用简洁名词，优先覆盖 科学问题、仪器/数据、关注物理量，不要写句子。",
                "4. 标签尽量采用便于统计的层级名词写法，外层在前、内层在后，例如 电离层/低纬、电离层/不规则体、极区对流/边界。",
                "5. 标签尽量简单，不要过细，不要写成磁层状态这类过长短语，优先写成磁层这类稳定名词。",
                "6. 正文用一段中文说明：研究问题、数据/仪器、方法、主要结论。",
                "7. 如果摘要信息不足，明确说摘要显示的信息有限，不要编造。",
                "",
                *preference_lines,
                "",
                f"期刊：{row['source_name']}",
                f"日期：{row['published_date']}",
                f"题目：{cleaned_title}",
                f"作者：{row['authors'].replace(chr(10), ', ')}",
                f"主题标签：{row['topic_labels'].replace(chr(10), ', ')}",
                f"摘要：{cleaned_abstract or '摘要缺失'}",
            ]
        )

    def _build_report_prompt(self, report_date: date, summaries: list["ArticleSummaryResult"]) -> str:
        blocks = [
            "请基于下面近7天已经完成的单篇空间物理论文总结，为周报生成中文分析。",
            "要求：",
            "1. 只根据提供的单篇总结、标题、期刊、标签和主题概括，不要编造全文细节。",
            "2. 输出适合科研工作周报，语气简洁、专业。",
            "3. 概览和建议要突出真正值得关注的主题、事件、仪器、方法或趋势。",
            "4. 需要结合当前用户研究偏好，优先提醒热层密度、卫星影响、应用影响、业务化预报，以及不局限于漠河的热层风研究。",
            "",
            f"报告日期：{report_date.isoformat()}",
            f"论文数：{len(summaries)}",
            "",
            "当前用户研究偏好：",
        ]
        if self.user_preferences.research_focus:
            blocks.extend(f"- {item}" for item in self.user_preferences.research_focus[:6])
        if self.user_preferences.priority_alerts:
            blocks.append("特别提醒主题：")
            blocks.extend(f"- {item}" for item in self.user_preferences.priority_alerts[:8])
        blocks.extend(
            [
                "",
            "单篇总结清单：",
            ]
        )
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

    def _build_deep_read_prompt(
        self,
        metadata: dict[str, str],
        full_text: str,
        related_summary: dict[str, str] | None = None,
    ) -> str:
        preference_lines: list[str] = []
        if self.user_preferences.research_focus:
            preference_lines.append("当前用户近期研究重心：")
            preference_lines.extend(f"- {item}" for item in self.user_preferences.research_focus[:6])
        if self.user_preferences.priority_alerts:
            preference_lines.append("优先提醒方向：")
            preference_lines.extend(f"- {item}" for item in self.user_preferences.priority_alerts[:8])

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

        return "\n".join(
            [
                "请基于下面提供的论文全文或全文级长文本，生成一份中文深度阅读结构化结果。",
                "要求：",
                "1. 必须体现真正的研究判断，不要把摘要换个说法重复。",
                "2. 要明确区分：硬结论、次级结论、合理解释、仍需保留的部分。",
                "3. 要说明：为什么做、怎么做、最关键结果、贡献、局限、可复现性、与已有工作的关系。",
                "4. 标签只用简洁名词，优先用层级标签，例如 热层/密度、电离层/低纬、研究星球/地球。",
                "5. 如果证据边界明显，要在局限或需要人工复核中明确写出，不要编造。",
                "6. 一句话总述必须直接说明研究目标、关键数据/方法和核心结果，优先用“这篇文章针对……”“这篇文章关注……”或“作者研究的是……”，不要用“不是……而是……”这类对比式开头。",
                "7. 除专有名词、仪器名、模型名、指数名、变量名和期刊名外，正文尽量使用中文，不要大量中英混写。",
                "8. 不要输出文件名、目录归档建议、证据范围、Research question、Core claims、Method summary 等旧版区块名。",
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

    def _deep_read_schema(self) -> dict:
        return {
            "name": "deep_read_analysis",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
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
                ],
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

    def _article_schema(self) -> dict:
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
                "required": [
                    "chinese_title",
                    "tags",
                    "body",
                    "supplement",
                    "recommendation",
                    "one_sentence",
                ],
                "additionalProperties": False,
            },
        }

    def _report_schema(self, summaries: list["ArticleSummaryResult"]) -> dict:
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
                "required": [
                    "overview_bullets",
                    "daily_suggestions",
                    "topic_insights",
                    "journal_insights",
                ],
                "additionalProperties": False,
            },
        }

    def _article_cache_key(self, row: Row) -> str:
        doi = str(row["doi"]).strip().lower()
        return doi.replace("/", "_") if doi else str(row["fingerprint"])

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
        return merged

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
        if strict:
            raise RuntimeError("codex_local provider requires the codex CLI to be installed and on PATH.")
        return ""

    def _resolve_openai_api_key(self, settings: dict) -> str:
        env_name = str(settings.get("api_key_env", "") or "SCIENCEMONITOR_OPENAI_API_KEY").strip()
        if env_name:
            value = os.environ.get(env_name, "").strip()
            if value:
                return value
        direct = str(settings.get("api_key", "") or "").strip()
        if direct:
            return direct
        fallback = os.environ.get("OPENAI_API_KEY", "").strip()
        return fallback

    def _resolve_openai_api_key_source(self, settings: dict) -> str:
        env_name = str(settings.get("api_key_env", "") or "SCIENCEMONITOR_OPENAI_API_KEY").strip()
        if env_name and os.environ.get(env_name, "").strip():
            return env_name
        if str(settings.get("api_key", "") or "").strip():
            return "config"
        if os.environ.get("OPENAI_API_KEY", "").strip():
            return "OPENAI_API_KEY"
        return ""

    def _resolve_openai_base_url(self, settings: dict, strict: bool = True) -> str:
        base_url = str(settings.get("base_url", "https://api.openai.com/v1/responses") or "https://api.openai.com/v1/responses").strip()
        parsed = urlparse(base_url)
        if parsed.scheme == "https":
            return base_url
        if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
            return base_url
        if strict:
            raise RuntimeError("openai_api.base_url must use https unless it points to localhost.")
        return base_url

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
        normalized: list[str] = []
        for tag in tags:
            clean = re.sub(r"\s+", "", str(tag))
            if not clean:
                continue
            canonical = clean
            for pattern, replacement in self.tag_normalization_rules:
                if re.search(pattern, clean, flags=re.IGNORECASE):
                    canonical = replacement
                    break
            if canonical not in normalized:
                normalized.append(canonical)
        return self._prefer_more_specific_tags(normalized)[:8]

    def normalize_tags(self, tags: list[str]) -> list[str]:
        return self._normalize_tags(tags)

    def _build_tag_normalization_rules(self) -> list[tuple[str, str]]:
        rules: list[tuple[str, str]] = []
        for item in self.focus_tags.get("tags", []):
            label = str(item.get("label", "")).strip()
            if not label:
                continue
            rules.append((re.escape(label), label))
            for pattern in item.get("patterns", []):
                text = str(pattern).strip()
                if text:
                    rules.append((text, label))

        if rules:
            return sorted(rules, key=lambda item: len(item[0]), reverse=True)
        return list(FALLBACK_TAG_NORMALIZATION_RULES)

    def _prefer_more_specific_tags(self, tags: list[str]) -> list[str]:
        refined: list[str] = []
        for tag in tags:
            if any(other != tag and other.startswith(tag + "/") for other in tags):
                continue
            refined.append(tag)
        return refined
