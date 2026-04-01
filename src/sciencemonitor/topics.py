from __future__ import annotations

from dataclasses import dataclass
import re

from .models import Paper, SourceConfig, TopicProfile
from .utils import normalize_text

AUXILIARY_TOPIC_IDS = {"methods_models"}
SPACE_DOMAIN_KEYWORDS = [
    "ionosphere",
    "ionospheric",
    "thermosphere",
    "thermospheric",
    "magnetosphere",
    "magnetospheric",
    "space weather",
    "solar wind",
    "geomagnetic",
    "geomagnetically",
    "interplanetary",
    "heliosphere",
    "cme",
    "coronal mass ejection",
    "imf",
    "aurora",
    "auroral",
    "total electron content",
    "tec",
    "electron density",
    "plasma bubble",
    "scintillation",
    "field aligned current",
    "field-aligned current",
    "joule heating",
    "neutral density",
    "upper atmosphere",
    "f region",
    "e region",
    "tids",
    "mstid",
    "equatorial ionization anomaly",
    "ring current",
    "radiation belt",
    "plasmasphere",
    "polar cap",
    "substorm",
    "superdarn",
    "fabry-perot",
    "电离层",
    "热层",
    "磁层",
    "空间天气",
    "太阳风",
    "地磁暴",
]

STRONG_SPACE_DOMAIN_KEYWORDS = [
    "ionosphere",
    "ionospheric",
    "thermosphere",
    "thermospheric",
    "neutral density",
    "thermospheric mass density",
    "satellite drag",
    "orbit decay",
    "magnetosphere",
    "magnetospheric",
    "solar wind",
    "geomagnetic",
    "interplanetary",
    "heliosphere",
    "aurora",
    "auroral",
    "total electron content",
    "tec",
    "plasma bubble",
    "scintillation",
    "field aligned current",
    "field-aligned current",
    "joule heating",
    "f region",
    "e region",
    "superdarn",
    "fabry-perot",
    "drag environment",
    "电离层",
    "热层",
    "磁层",
    "空间天气",
    "热层密度",
    "卫星阻力",
    "轨道衰减",
]

NON_SPACE_NOISE_KEYWORDS = [
    "quasar",
    "ultraluminous x-ray source",
    "x-ray source",
    "black hole",
    "neutron star",
    "supernova",
    "galaxy",
    "galaxies",
    "agn",
    "active galactic nucleus",
    "stellar",
    "star formation",
    "exoplanet",
    "cosmology",
    "accretion disk",
    "spark discharge",
    "metamaterial",
]


@dataclass
class ClassificationResult:
    topics: list[str]
    topic_labels: list[str]
    relevance_score: float
    matched_keywords: list[str]
    has_domain_anchor: bool
    has_strong_domain_anchor: bool
    has_noise_conflict: bool


class TopicClassifier:
    def __init__(self, topics: list[TopicProfile]) -> None:
        self.topics = topics

    def classify(self, paper: Paper, source: SourceConfig) -> ClassificationResult:
        haystack = normalize_text(" ".join([paper.title, paper.abstract]))
        matched_topics: list[str] = []
        topic_labels: list[str] = []
        matched_keywords: list[str] = []
        score = 0.0
        has_domain_anchor = self._has_domain_anchor(haystack)
        has_strong_domain_anchor = self._has_strong_domain_anchor(haystack)
        has_noise_conflict = self._has_noise_conflict(haystack)

        for topic in self.topics:
            topic_hits = [keyword for keyword in topic.keywords if self._keyword_matches(haystack, keyword)]
            if topic_hits:
                matched_topics.append(topic.id)
                topic_labels.append(topic.label)
                matched_keywords.extend(topic_hits[:3])
                score += 2.0 + min(2.0, 0.35 * len(topic_hits))

        primary_topics = self._primary_topics(matched_topics)

        score += self._source_score_bonus(source)
        score += min(len(paper.authors), 6) * 0.03
        if paper.abstract:
            score += min(len(paper.abstract) / 400.0, 1.0)

        if source.mode == "full" and not matched_topics:
            score += 1.0
        elif source.mode == "topic_filter" and (not primary_topics or not has_domain_anchor or not has_strong_domain_anchor):
            score -= 2.5
        elif source.mode == "watchlist" and (not primary_topics or not has_domain_anchor or not has_strong_domain_anchor):
            score -= 4.0
        if source.mode in {"topic_filter", "watchlist"} and has_noise_conflict and not has_strong_domain_anchor:
            score -= 5.0

        return ClassificationResult(
            topics=matched_topics,
            topic_labels=topic_labels,
            relevance_score=round(score, 3),
            matched_keywords=matched_keywords,
            has_domain_anchor=has_domain_anchor,
            has_strong_domain_anchor=has_strong_domain_anchor,
            has_noise_conflict=has_noise_conflict,
        )

    def should_keep(self, result: ClassificationResult, source: SourceConfig) -> bool:
        primary_topics = self._primary_topics(result.topics)
        if source.mode == "full":
            return True
        if source.mode == "topic_filter":
            return bool(primary_topics) and result.has_domain_anchor and result.has_strong_domain_anchor
        if source.mode == "watchlist":
            return (
                bool(primary_topics)
                and result.has_domain_anchor
                and result.has_strong_domain_anchor
                and not result.has_noise_conflict
                and result.relevance_score >= 3.0
            )
        return False

    def _source_score_bonus(self, source: SourceConfig) -> float:
        if source.tier == "core":
            return 1.5
        if source.tier == "related":
            return 0.75
        if source.tier == "watchlist":
            return 0.25
        return 0.0

    def _keyword_matches(self, haystack: str, keyword: str) -> bool:
        normalized = normalize_text(keyword)
        if not normalized:
            return False

        # Chinese keywords and mixed strings with CJK characters are stable as substring matches.
        if re.search(r"[\u4e00-\u9fff]", normalized):
            return normalized in haystack

        compact = normalized.replace(" ", "")
        alnum_length = len(re.sub(r"[^a-z0-9]+", "", compact))

        # Short acronyms such as TEC, FAC, Dst should only match as standalone terms.
        if alnum_length <= 4:
            pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
            return re.search(pattern, haystack) is not None

        if " " not in normalized and "-" not in normalized:
            pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
            return re.search(pattern, haystack) is not None

        phrase_parts = [part for part in re.split(r"[\s-]+", normalized) if part]
        if not phrase_parts:
            return False
        phrase_pattern = r"[\s-]+".join(re.escape(part) for part in phrase_parts)
        pattern = rf"(?<![a-z0-9]){phrase_pattern}(?![a-z0-9])"
        return re.search(pattern, haystack) is not None

    def _primary_topics(self, topic_ids: list[str]) -> list[str]:
        return [topic_id for topic_id in topic_ids if topic_id not in AUXILIARY_TOPIC_IDS]

    def _has_domain_anchor(self, haystack: str) -> bool:
        return any(self._keyword_matches(haystack, keyword) for keyword in SPACE_DOMAIN_KEYWORDS)

    def _has_strong_domain_anchor(self, haystack: str) -> bool:
        return any(self._keyword_matches(haystack, keyword) for keyword in STRONG_SPACE_DOMAIN_KEYWORDS)

    def _has_noise_conflict(self, haystack: str) -> bool:
        return any(self._keyword_matches(haystack, keyword) for keyword in NON_SPACE_NOISE_KEYWORDS)
