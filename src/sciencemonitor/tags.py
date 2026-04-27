from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import load_focus_tags, project_root


INVALID_OUTPUT_SNIPPETS = ("oops", "todo", "tbd", "placeholder")
TAG_TEXT_RE = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9/+\-_.&]+")
DEFAULT_CATEGORY_PREFIXES = {
    "仪器": "instrument_data",
    "指数": "index_control",
    "模型": "model_method",
    "建模": "model_method",
    "特征": "result_feature",
    "应用": "application_impact",
    "状态": "status",
}


@dataclass(frozen=True)
class InferenceRule:
    label: str
    pattern: str
    scope: str = "any"
    excludes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SuppressionRule:
    general: str
    specific: str


class TagTaxonomy:
    def __init__(self, payload: dict, config_path: Path) -> None:
        self.payload = payload
        self.config_path = config_path
        tag_rules = payload.get("tag_rules", {}) if isinstance(payload, dict) else {}
        unknown_policy = tag_rules.get("unknown_tag_policy", {}) if isinstance(tag_rules, dict) else {}

        self.allow_open_vocabulary = bool(tag_rules.get("open_vocabulary", True))
        self.default_max_tags = int(tag_rules.get("default_max_tags", 14) or 14)
        self.pending_tags_path = str(
            tag_rules.get("pending_tags_path", tag_rules.get("candidate_log_path", "config/pending_tags.json"))
            or "config/pending_tags.json"
        )
        self.max_unknown_length = int(unknown_policy.get("max_length", 24) or 24)
        self.max_unknown_levels = int(unknown_policy.get("max_levels", 4) or 4)
        self.reject_patterns = [
            str(item).strip()
            for item in unknown_policy.get("reject_patterns", [])
            if str(item).strip()
        ]
        self.drop_patterns = [
            str(item).strip()
            for item in tag_rules.get("drop_patterns", [])
            if str(item).strip()
        ]

        self.category_order: dict[str, int] = {}
        for index, item in enumerate(payload.get("categories", []), start=1):
            category_id = str(item.get("id", "")).strip()
            if category_id:
                self.category_order[category_id] = int(item.get("order", index) or index)

        self.preferred_labels: set[str] = set()
        self.category_by_label: dict[str, str] = {}
        self.normalization_rules: list[tuple[str, str]] = []
        self.inference_rules: list[InferenceRule] = []
        for item in payload.get("tags", []):
            label = str(item.get("label", "")).strip()
            category = str(item.get("category", "")).strip()
            if not label:
                continue
            self.preferred_labels.add(label)
            if category:
                self.category_by_label[label] = category
            self.normalization_rules.append((rf"^{re.escape(label)}$", label))

            aliases = [str(alias).strip() for alias in item.get("aliases", []) if str(alias).strip()]
            patterns = [str(pattern).strip() for pattern in item.get("patterns", []) if str(pattern).strip()]
            for alias in aliases:
                self.normalization_rules.append((rf"^{re.escape(alias)}$", label))
            for pattern in patterns:
                self.normalization_rules.append((pattern, label))

            scope = str(item.get("inference_scope", "any") or "any").strip().lower() or "any"
            excludes = tuple(
                str(pattern).strip()
                for pattern in item.get("inference_excludes", [])
                if str(pattern).strip()
            )
            for pattern in patterns + [re.escape(alias) for alias in aliases]:
                self.inference_rules.append(InferenceRule(label=label, pattern=pattern, scope=scope, excludes=excludes))

        self.normalization_rules.sort(key=lambda item: len(item[0]), reverse=True)
        self.suppression_rules = [
            SuppressionRule(
                general=str(item.get("general", "")).strip(),
                specific=str(item.get("specific", "")).strip(),
            )
            for item in payload.get("suppression_rules", [])
            if str(item.get("general", "")).strip() and str(item.get("specific", "")).strip()
        ]

    def normalize_tags(
        self,
        tags: list[str],
        *,
        max_tags: int | None = None,
        root: Path | None = None,
        context: str = "",
        record_candidates: bool = False,
    ) -> list[str]:
        normalized: list[str] = []
        candidates: list[str] = []
        for tag in tags:
            canonical = self.normalize_tag(tag)
            if not canonical:
                continue
            if canonical.startswith("其他行星/") and any(item.startswith("其他行星/") for item in normalized):
                continue
            if canonical.startswith("对象/其他行星/") and any(item.startswith("对象/其他行星/") for item in normalized):
                continue
            if canonical not in normalized:
                normalized.append(canonical)
                if canonical not in self.preferred_labels:
                    candidates.append(canonical)

        normalized = self._apply_suppression(normalized)
        normalized = self._prefer_more_specific_tags(normalized)
        normalized = self._sort_tags(normalized)
        limited = normalized[: max_tags or self.default_max_tags]

        if record_candidates and root and candidates:
            kept_candidates = [tag for tag in limited if tag in candidates]
            self._record_candidates(root, kept_candidates, context)
        return limited

    def normalize_tag(self, tag: str) -> str | None:
        cleaned = clean_tag_text(tag)
        if not cleaned:
            return None
        lowered = cleaned.lower()
        if any(snippet in lowered for snippet in INVALID_OUTPUT_SNIPPETS):
            return None
        for pattern in self.drop_patterns:
            if re.search(pattern, cleaned, flags=re.IGNORECASE):
                return None
        for pattern, label in self.normalization_rules:
            if re.search(pattern, cleaned, flags=re.IGNORECASE):
                return label
        if not self.allow_open_vocabulary:
            return None
        if self._is_reasonable_unknown(cleaned):
            return cleaned
        return None

    def infer_tags_from_text(
        self,
        *,
        title_text: str = "",
        body_text: str = "",
        extra_text: str = "",
        max_tags: int | None = None,
    ) -> list[str]:
        title_haystack = normalize_haystack_text(title_text)
        full_haystack = normalize_haystack_text(" ".join(part for part in [title_text, body_text, extra_text] if part))
        matched: list[str] = []

        for rule in self.inference_rules:
            haystack = title_haystack if rule.scope == "title" else full_haystack
            if not haystack:
                continue
            if rule.excludes and any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in rule.excludes):
                continue
            if re.search(rule.pattern, haystack, flags=re.IGNORECASE) and rule.label not in matched:
                matched.append(rule.label)

        return self.normalize_tags(matched, max_tags=max_tags)

    def group_tags(self, tags: list[str]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {category: [] for category in self.category_order}
        groups.setdefault("uncategorized", [])
        for tag in self._sort_tags(tags):
            category = self.category_for(tag)
            groups.setdefault(category, [])
            groups[category].append(tag)
        return groups

    def category_for(self, tag: str) -> str:
        category = self.category_by_label.get(tag)
        if category:
            return category
        prefix = tag.split("/", 1)[0]
        if prefix in DEFAULT_CATEGORY_PREFIXES:
            return DEFAULT_CATEGORY_PREFIXES[prefix]
        if tag in {"综述", "Todo", "重要", "展望", "可做", "科学思考"}:
            return "status"
        if any(keyword in tag for keyword in ("影响", "预测", "预报", "衰减")):
            return "application_impact"
        return "research_object"

    def _apply_suppression(self, tags: list[str]) -> list[str]:
        refined = list(tags)
        for rule in self.suppression_rules:
            if rule.general in refined and rule.specific in refined:
                refined = [tag for tag in refined if tag != rule.general]
        return refined

    def _prefer_more_specific_tags(self, tags: list[str]) -> list[str]:
        refined: list[str] = []
        for tag in tags:
            if any(other != tag and other.startswith(tag + "/") for other in tags):
                continue
            refined.append(tag)
        return refined

    def _sort_tags(self, tags: list[str]) -> list[str]:
        decorated = [
            (
                self.category_order.get(self.category_for(tag), 999),
                index,
                tag,
            )
            for index, tag in enumerate(tags)
        ]
        decorated.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in decorated]

    def _is_reasonable_unknown(self, tag: str) -> bool:
        if len(tag) > self.max_unknown_length:
            return False
        if tag.count("/") + 1 > self.max_unknown_levels:
            return False
        if any(re.search(pattern, tag, flags=re.IGNORECASE) for pattern in self.reject_patterns):
            return False
        if re.search(r"[。！？；：,，]", tag):
            return False
        return True

    def _record_candidates(self, root: Path, tags: list[str], context: str) -> None:
        if not tags:
            return
        from .tag_governance import record_pending_tags

        categories = {tag: self.category_for(tag) for tag in tags}
        record_pending_tags(root, tags, context=context, categories=categories)


def clean_tag_text(tag: str) -> str:
    text = str(tag or "").lstrip("#").strip()
    text = re.sub(r"\s+", "", text)
    text = TAG_TEXT_RE.sub("", text)
    return text.strip("./-_")


def normalize_haystack_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    return f" {cleaned} " if cleaned else ""


@lru_cache(maxsize=16)
def _load_taxonomy_cached(config_path: str, mtime_ns: int) -> TagTaxonomy:
    del mtime_ns
    path = Path(config_path)
    payload = load_focus_tags(path)
    return TagTaxonomy(payload, path)


def load_tag_taxonomy(root: Path | None = None, focus_tags_path: Path | None = None) -> TagTaxonomy:
    path = focus_tags_path or (root or project_root()) / "config" / "focus_tags.json"
    resolved = path.resolve()
    return _load_taxonomy_cached(str(resolved), resolved.stat().st_mtime_ns)


def clear_tag_taxonomy_cache() -> None:
    _load_taxonomy_cached.cache_clear()


def normalize_tags(
    tags: list[str],
    *,
    root: Path | None = None,
    focus_tags_path: Path | None = None,
    max_tags: int | None = None,
    context: str = "",
    record_candidates: bool = False,
) -> list[str]:
    taxonomy = load_tag_taxonomy(root=root, focus_tags_path=focus_tags_path)
    return taxonomy.normalize_tags(
        tags,
        max_tags=max_tags,
        root=root,
        context=context,
        record_candidates=record_candidates,
    )


def infer_preferred_tags_from_text(
    *,
    title_text: str = "",
    body_text: str = "",
    extra_text: str = "",
    root: Path | None = None,
    focus_tags_path: Path | None = None,
    max_tags: int | None = None,
) -> list[str]:
    taxonomy = load_tag_taxonomy(root=root, focus_tags_path=focus_tags_path)
    return taxonomy.infer_tags_from_text(
        title_text=title_text,
        body_text=body_text,
        extra_text=extra_text,
        max_tags=max_tags,
    )


def group_tags(
    tags: list[str],
    *,
    root: Path | None = None,
    focus_tags_path: Path | None = None,
) -> dict[str, list[str]]:
    taxonomy = load_tag_taxonomy(root=root, focus_tags_path=focus_tags_path)
    return taxonomy.group_tags(tags)
