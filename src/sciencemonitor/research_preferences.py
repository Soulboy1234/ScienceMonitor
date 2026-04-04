from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class UserPreferenceProfile:
    research_focus: list[str] = field(default_factory=list)
    priority_alerts: list[str] = field(default_factory=list)
    priority_themes: list[str] = field(default_factory=list)
    theme_keywords: dict[str, list[str]] = field(default_factory=dict)


DEFAULT_RESEARCH_PREFERENCES = {
    "research_focus": [
        "热层密度及其变化机制",
        "空间环境对卫星运行、轨道衰减、阻力环境和任务安全的影响",
        "空间天气对人类生产生活的影响",
        "与应用相关的空间环境风险评估、预报和响应",
        "热层风相关研究，但不再局限于漠河区域",
    ],
    "priority_alerts": [
        "热层质量密度异常、长期变化、建模和数据同化",
        "磁暴、亚暴、行星际环境变化对卫星阻力和轨道环境的影响",
        "空间天气导致的卫星故障、通信导航受扰、轨道维持压力增加等应用问题",
        "空间环境对低轨卫星星座、姿轨控和任务规划的影响",
        "面向业务化或准业务化的预报模型、经验模型、机器学习模型",
        "热层风与热层密度、卫星阻力、能量沉降之间的耦合关系",
    ],
    "priority_article_signals": [
        "直接讨论 TMD、satellite drag、orbit decay、thermospheric forcing 的文章",
        "讨论 space weather societal impacts、operational impacts、infrastructure impacts 的文章",
        "讨论上游空间环境信息如何改善卫星环境建模和预报的文章",
    ],
    "monitoring_scope": {
        "monitoring_domain": "space_physics",
        "article_summary_domain": "space_physics",
        "report_domain": "space_physics",
    },
    "deep_read_scope": {
        "primary_domain": "space_physics",
        "allow_related_disciplines": True,
        "preferred_related_disciplines": ["artificial_intelligence"],
    },
}


def load_research_preferences_payload(path: Path) -> dict:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            merged = json.loads(json.dumps(DEFAULT_RESEARCH_PREFERENCES))
            _deep_update_dict(merged, payload)
            return normalize_research_preferences_payload(merged)
    return normalize_research_preferences_payload(json.loads(json.dumps(DEFAULT_RESEARCH_PREFERENCES)))


def validate_research_preferences_payload(payload: object, path_name: str) -> list[str]:
    if not isinstance(payload, dict):
        return [f"{path_name} 顶层必须是对象。"]

    issues: list[str] = []
    for key in ("research_focus", "priority_alerts", "priority_article_signals"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            issues.append(f"{path_name} 中的 {key} 必须是列表。")

    monitoring_scope = payload.get("monitoring_scope", {})
    if not isinstance(monitoring_scope, dict):
        issues.append(f"{path_name} 中的 monitoring_scope 必须是对象。")

    deep_read_scope = payload.get("deep_read_scope", {})
    if not isinstance(deep_read_scope, dict):
        issues.append(f"{path_name} 中的 deep_read_scope 必须是对象。")
    elif "preferred_related_disciplines" in deep_read_scope and not isinstance(
        deep_read_scope.get("preferred_related_disciplines"), list
    ):
        issues.append(f"{path_name} 中的 deep_read_scope.preferred_related_disciplines 必须是列表。")

    return issues


def build_user_preference_profile(payload: dict) -> UserPreferenceProfile:
    focus_items = [str(item).strip() for item in payload.get("research_focus", []) if str(item).strip()]
    alert_items = [str(item).strip() for item in payload.get("priority_alerts", []) if str(item).strip()]
    article_signals = [str(item).strip() for item in payload.get("priority_article_signals", []) if str(item).strip()]
    combined_alerts = alert_items + [item for item in article_signals if item not in alert_items]
    theme_keywords = _derive_theme_keywords(focus_items + combined_alerts)
    return UserPreferenceProfile(
        research_focus=focus_items,
        priority_alerts=combined_alerts,
        priority_themes=list(theme_keywords.keys()),
        theme_keywords=theme_keywords,
    )


def extract_section(text: str, heading: str) -> str:
    pattern = rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def parse_research_preferences_from_project_markdown(text: str) -> dict | None:
    section = extract_section(text, "Sync: config/research_preferences.json")
    if not section:
        return None

    monitoring_lines = _extract_bullets(_extract_subsection(section, "监测范围"))
    deep_read_lines = _extract_bullets(_extract_subsection(section, "深度解读范围"))
    return normalize_research_preferences_payload(
        {
            "research_focus": _extract_bullets(_extract_subsection(section, "当前研究重心")),
            "priority_alerts": _extract_bullets(_extract_subsection(section, "特别提醒策略")),
            "priority_article_signals": _extract_bullets(_extract_subsection(section, "高优先级文章信号")),
            "monitoring_scope": {
                "monitoring_domain": _mapping_value(monitoring_lines, "监测", "space_physics"),
                "article_summary_domain": _mapping_value(monitoring_lines, "单篇总结", "space_physics"),
                "report_domain": _mapping_value(monitoring_lines, "周报", "space_physics"),
            },
            "deep_read_scope": {
                "primary_domain": _mapping_value(deep_read_lines, "主领域", "space_physics"),
                "allow_related_disciplines": _parse_yes_no(
                    _mapping_value(deep_read_lines, "允许相关学科", "是"), default=True
                ),
                "preferred_related_disciplines": _split_inline_list(
                    _mapping_value(deep_read_lines, "优先相关学科", "")
                ),
            },
        }
    )


def normalize_research_preferences_payload(payload: dict) -> dict:
    monitoring_scope = payload.get("monitoring_scope", {})
    if not isinstance(monitoring_scope, dict):
        monitoring_scope = {}
    deep_read_scope = payload.get("deep_read_scope", {})
    if not isinstance(deep_read_scope, dict):
        deep_read_scope = {}
    return {
        "research_focus": _normalize_string_list(payload.get("research_focus", [])),
        "priority_alerts": _normalize_string_list(payload.get("priority_alerts", [])),
        "priority_article_signals": _normalize_string_list(payload.get("priority_article_signals", [])),
        "monitoring_scope": {
            "monitoring_domain": str(monitoring_scope.get("monitoring_domain", "space_physics")).strip() or "space_physics",
            "article_summary_domain": str(monitoring_scope.get("article_summary_domain", "space_physics")).strip()
            or "space_physics",
            "report_domain": str(monitoring_scope.get("report_domain", "space_physics")).strip() or "space_physics",
        },
        "deep_read_scope": {
            "primary_domain": str(deep_read_scope.get("primary_domain", "space_physics")).strip() or "space_physics",
            "allow_related_disciplines": bool(deep_read_scope.get("allow_related_disciplines", True)),
            "preferred_related_disciplines": _normalize_string_list(deep_read_scope.get("preferred_related_disciplines", [])),
        },
    }


def _deep_update_dict(target: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update_dict(target[key], value)
        else:
            target[key] = value


def _extract_subsection(text: str, heading: str) -> str:
    pattern = rf"(?ms)^### {re.escape(heading)}\n(.*?)(?=^### |\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _extract_bullets(section_text: str) -> list[str]:
    return [item.strip() for item in re.findall(r"(?m)^- (.+)$", section_text)]


def _mapping_value(lines: list[str], key: str, default: str = "") -> str:
    for line in lines:
        if "：" in line:
            current_key, current_value = line.split("：", 1)
        elif ":" in line:
            current_key, current_value = line.split(":", 1)
        else:
            continue
        if current_key.strip() == key:
            return current_value.strip()
    return default


def _parse_yes_no(value: str, default: bool = True) -> bool:
    normalized = value.strip().lower()
    if normalized in {"是", "true", "yes", "y", "1"}:
        return True
    if normalized in {"否", "false", "no", "n", "0"}:
        return False
    return default


def _split_inline_list(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned or cleaned == "无":
        return []
    return [item.strip() for item in re.split(r"[，,、]", cleaned) if item.strip()]


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]
    return [str(item).strip() for item in items if str(item).strip()]


def _derive_theme_keywords(lines: list[str]) -> dict[str, list[str]]:
    full_text = "\n".join(lines)
    defaults: dict[str, list[str]] = {
        "热层密度": [
            "热层密度",
            "thermospheric mass density",
            "thermospheric density",
            "neutral density",
            "tmd",
            "drag environment",
            "thermospheric forcing",
        ],
        "卫星影响": [
            "卫星",
            "satellite",
            "leo",
            "drag",
            "satellite drag",
            "orbit decay",
            "orbital decay",
            "轨道衰减",
            "轨道环境",
            "星座",
            "constellation",
        ],
        "应用影响": [
            "生产生活",
            "societal impact",
            "operational impact",
            "infrastructure impact",
            "任务安全",
            "风险评估",
            "response",
            "通信",
            "导航",
            "电网",
        ],
        "热层风": [
            "热层风",
            "thermospheric wind",
            "neutral wind",
        ],
        "业务化与预报": [
            "预报",
            "forecast",
            "forecasting",
            "nowcast",
            "业务化",
            "operational",
            "risk",
        ],
        "行星际驱动": [
            "行星际",
            "interplanetary",
            "solar wind",
            "imf",
            "imf by",
            "上游",
        ],
    }

    theme_keywords: dict[str, list[str]] = {}
    for theme, keywords in defaults.items():
        if any(keyword.lower() in full_text.lower() for keyword in keywords):
            theme_keywords[theme] = keywords

    if not theme_keywords:
        theme_keywords = defaults
    return theme_keywords
