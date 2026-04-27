from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .article_summary_markdown import build_tag_line, extract_numbered_line, extract_summary_body, extract_summary_tags
from .config import article_summaries_root, deep_reads_root, formal_tags_markdown_path, project_root
from .tag_governance import (
    OutputTagRewriteEntry,
    OutputTagRewriteResult,
    _infer_pending_family_id,
    formal_tag_labels,
    govern_pending_candidate_tag,
    record_pending_tags,
    refresh_pending_tag_files,
    resolve_existing_output_tag,
)
from .tags import clean_tag_text, load_tag_taxonomy, normalize_haystack_text


FORMAL_ROOTS = ("对象", "事件", "指数", "仪器", "数据", "方法", "模型", "工具", "特征", "应用", "信息来源")
CATEGORY_DEFAULT_ROOT = {
    "research_object": "对象",
    "event_driver": "事件",
    "index_control": "指数",
    "instrument_data": "仪器",
    "model_method": "方法",
    "result_feature": "特征",
    "application_impact": "应用",
    "status": "信息来源",
}
DATA_ROOT_HINTS = (
    "数据",
    "观测",
    "目录",
    "图",
    "谱",
    "剖面",
    "掩星",
    "再分析",
    "TLE",
    "MERRA",
    "OMNI",
    "RH200",
    "JAWARA",
)
TOOL_ROOT_HINTS = ("工具", "软件", "脚本", "代码", "平台", "框架", "库")
MODEL_ROOT_HINTS = (
    "模型",
    "MSIS",
    "DTM",
    "TIEGCM",
    "TIMEGCM",
    "GITM",
    "CMIT",
    "CTIP",
    "WACCM",
    "WAM-IPE",
    "LFM",
    "MIX",
    "AMIE",
    "JB2008",
    "HASDM",
    "WINDMI",
    "PPMLR",
    "TDIM",
    "IPWM",
    "Weimer",
)
METHOD_ROOT_HINTS = (
    "方法",
    "分析",
    "统计",
    "反演",
    "拟合",
    "机器学习",
    "神经网络",
    "扩散",
    "重建",
    "建模",
    "模拟",
    "同化",
    "估计",
    "理论",
    "算法",
)
TAG_REVIEW_CONTEXTS = {"article_summary", "article_summary_review", "deep_read", "deep_read_inferred", "output_rewrite"}
PENDING_LIMIT_BY_CONTEXT = {
    "article_summary": 2,
    "article_summary_review": 2,
    "output_rewrite": 2,
    "output_review": 2,
    "deep_read": 3,
    "deep_read_inferred": 3,
}
PENDING_FAMILY_PRIORITY = {
    "applications_impacts": 60,
    "instruments_missions_observations": 55,
    "models_methods": 52,
    "planetary_environment": 46,
    "magnetosphere_particles": 43,
    "solar_corona_heliosphere": 40,
    "it_coupling_extensions": 36,
    "data_assets": 30,
}
PENDING_DETAIL_PENALTY_KEYWORDS = (
    "变化",
    "响应",
    "结构",
    "观测",
    "统计",
    "调查",
    "位相",
    "峰期",
    "亮温",
    "链路",
    "边界",
    "参数化",
    "参数",
    "驱动",
    "过程",
)

SATELLITE_SUBJECT_PATTERNS = (
    r"\bsatellite\b",
    r"\bsatellites\b",
    r"\bspacecraft\b",
    r"\bconstellation\b",
    r"\borbit\b",
    r"\borbital\b",
    r"\bleo\b",
    r"\bgeo\b",
    r"\bgso\b",
    r"\bdrag\b",
    r"卫星",
    r"星座",
    r"轨道",
    r"阻力",
    r"姿轨控",
)
SATELLITE_IMPACT_PATTERNS = (
    r"\bsatellite drag\b",
    r"\bdrag environment\b",
    r"\borbit decay\b",
    r"\borbital decay\b",
    r"\boperational impact\b",
    r"\bmission planning\b",
    r"\borbit maintenance\b",
    r"\bfailure\b",
    r"\banomaly\b",
    r"\brisk\b",
    r"\bhazard\b",
    r"卫星阻力",
    r"阻力环境",
    r"轨道衰减",
    r"轨道维持",
    r"任务规划",
    r"任务安全",
    r"运行影响",
    r"卫星故障",
    r"风险评估",
    r"故障",
)
SATELLITE_ENVIRONMENT_PATTERNS = (
    r"\bspace weather\b",
    r"\bspace environment\b",
    r"\bsolar wind\b",
    r"\bcme\b",
    r"\bicme\b",
    r"\bgeomagnetic storm\b",
    r"\bmagnetic storm\b",
    r"\bsubstorm\b",
    r"\bthermospher",
    r"\bupper atmosphere\b",
    r"\bionospher",
    r"\bradiation belt\b",
    r"\bmagnetospher",
    r"\bparticle precipitation\b",
    r"\bthermospheric forcing\b",
    r"空间天气",
    r"空间环境",
    r"太阳风",
    r"磁暴",
    r"亚暴",
    r"热层",
    r"电离层",
    r"辐射带",
    r"磁层",
    r"能量沉降",
)
SATELLITE_IMPACT_NEGATION_PATTERNS = (
    r"不(?:涉及|研究|讨论|直接分析).{0,40}(?:卫星|轨道|阻力|卫星环境|应用影响|业务化预报)",
    r"不直接(?:涉及|研究|讨论|分析).{0,40}(?:卫星|轨道|阻力|卫星环境|应用影响|业务化预报)",
    r"未直接(?:涉及|讨论|给出|展开).{0,40}(?:卫星|轨道|阻力|应用影响|业务化预报)",
    r"不(?:直接|宜).{0,30}(?:对应|外推到).{0,40}(?:卫星|轨道|阻力|应用影响|业务化预报)",
    r"不能(?:进一步)?外推.{0,40}(?:卫星|轨道|阻力|卫星环境|应用影响|业务化预报)",
    r"并不直接对应.{0,40}(?:卫星|轨道|阻力|应用影响|业务化预报)?",
    r"没有直接.{0,30}(?:卫星|轨道|阻力|应用影响|业务化预报)",
    r"未见.{0,30}(?:卫星|轨道|阻力|应用影响|业务化预报)",
    r"不是直接研究.{0,40}(?:卫星|轨道|阻力|应用影响|业务化预报)",
    r"(?:卫星|轨道|阻力|卫星环境|应用影响|业务化预报).{0,40}(?:未展开|无直接联系|未直接讨论|不能(?:进一步)?外推|不宜外推|未量化)",
)
THERMOSPHERE_CONTEXT_PATTERNS = (
    r"\bthermosphere\b",
    r"\bthermospheric\b",
    r"\bupper atmosphere\b",
    r"热层",
)
THERMOSPHERE_DENSITY_POSITIVE_PATTERNS = (
    r"\bthermospheric density\b",
    r"\bthermospheric mass density\b",
    r"\bneutral density\b",
    r"\bmass density\b",
    r"\bdensity response\b",
    r"\bdensity variation(?:s)?\b",
    r"\bdensity oscillation(?:s)?\b",
    r"\bdensity enhancement\b",
    r"\bdensity depletion\b",
    r"\bdrag-derived density\b",
    r"\bdensity from .*tle\b",
    r"热层密度",
    r"热层质量密度",
    r"中性密度",
    r"质量密度",
    r"密度响应",
    r"密度变化",
    r"密度振荡",
)
THERMOSPHERE_DENSITY_NEGATION_PATTERNS = (
    r"不(?:涉及|研究|讨论|直接分析).{0,20}热层(?:质量)?密度",
    r"未(?:展开|涉及|直接涉及|研究|讨论|分析).{0,20}热层(?:质量)?密度",
    r"不是一篇以.{0,40}热层(?:质量)?密度",
    r"不是直接研究.{0,20}热层(?:质量)?密度",
    r"不(?:是|属于).{0,20}热层(?:质量)?密度(?:研究|论文|工作)?",
    r"更偏.{0,40}(?:坐标|模型|框架|方法).{0,40}不(?:是|属于).{0,20}热层(?:质量)?密度",
    r"不应外推.{0,40}热层(?:质量)?密度",
    r"热层(?:质量)?密度.{0,40}(?:未展开|无直接联系|未直接讨论|不能(?:进一步)?外推|不宜外推|未量化)",
    r"does not (?:involve|study|analyze|discuss).{0,20}thermospheric (?:mass )?density",
    r"not (?:about|focused on).{0,20}thermospheric (?:mass )?density",
    r"thermospheric (?:mass )?density.{0,40}(?:not discussed|not analyzed|not expanded|not quantified|not directly linked)",
)
THERMOSPHERE_WIND_POSITIVE_PATTERNS = (
    r"\bthermospheric wind(?:s)?\b",
    r"\bneutral wind(?:s)?\b",
    r"\bzonal wind(?:s)?\b",
    r"\bmeridional wind(?:s)?\b",
    r"\bvertical wind(?:s)?\b",
    r"热层风",
    r"中性风",
    r"纬向风",
    r"经向风",
    r"垂直风",
    r"风场",
)
THERMOSPHERE_WIND_NEGATION_PATTERNS = (
    r"不(?:涉及|研究|讨论|直接分析).{0,20}(?:热层风|中性风|风场)",
    r"未(?:展开|涉及|直接涉及|研究|讨论|分析).{0,20}(?:热层风|中性风|风场)",
    r"不是一篇以.{0,40}(?:热层风|中性风|风场)",
    r"不应外推.{0,40}(?:热层风|中性风|风场)",
    r"does not (?:involve|study|analyze|discuss).{0,20}(?:thermospheric|neutral) wind",
)
IONOSPHERE_CONTEXT_PATTERNS = (
    r"\bionosphere\b",
    r"\bionospheric\b",
    r"\bequatorial ionosphere\b",
    r"\blow latitude ionosphere\b",
    r"\bmid-?latitude ionosphere\b",
    r"\bhigh-?latitude ionosphere\b",
    r"电离层",
    r"赤道电离层",
    r"低纬电离层",
    r"中纬电离层",
    r"高纬电离层",
)
IONOSPHERE_TEC_POSITIVE_PATTERNS = (
    r"\btec\b",
    r"\btotal electron content\b",
    r"\bgnss tec\b",
    r"\bgps tec\b",
    r"总电子含量",
)
IONOSPHERE_ELECTRON_DENSITY_POSITIVE_PATTERNS = (
    r"\bionospheric electron density\b",
    r"\belectron density(?: profile)?\b",
    r"电子密度",
)
POLAR_CONTEXT_PATTERNS = (
    r"\bpolar\b",
    r"\baurora(?:l)?\b",
    r"\bcusp\b",
    r"\bpolar cap\b",
    r"\bhigh-?latitude\b",
    r"极区",
    r"极光",
    r"极盖",
    r"高纬",
)
GEOMAGNETIC_STORM_PATTERNS = (
    r"\bgeomagnetic storm(?:s)?\b",
    r"\bmagnetic storm(?:s)?\b",
    r"\bstorm-?time\b",
    r"磁暴",
)
SUBSTORM_PATTERNS = (
    r"\bsubstorm(?:s)?\b",
    r"亚暴",
)
SOLAR_WIND_PATTERNS = (
    r"\bsolar wind\b",
    r"\binterplanetary\b",
    r"太阳风",
    r"行星际",
)
HIGH_SPEED_FLOW_PATTERNS = (
    r"\bhigh[- ]speed (?:solar wind|stream(?:s)?)\b",
    r"\bhss\b",
    r"\bcorotating interaction region\b",
    r"\bcir\b",
    r"高速流",
    r"高速太阳风",
    r"共转相互作用区",
)
GEOMAGNETIC_STORM_FOCUS_PATTERNS = (
    r"(?:研究|分析|对比|比较|评估|刻画|聚焦|复盘).{0,24}(?:geomagnetic storm|magnetic storm|磁暴)",
    r"(?:geomagnetic storm|magnetic storm|磁暴).{0,24}(?:响应|扰动|恢复|复盘|链路|对比|比较)",
    r"\bstorm response\b",
)
GRAVITY_WAVE_PATTERNS = (
    r"\bgravity wave(?:s)?\b",
    r"\bagw\b",
    r"重力波",
)
EUV_PATTERNS = (
    r"\beuv\b",
    r"\bextreme ultraviolet\b",
    r"极紫外",
    r"EUV",
)
ICON_PATTERNS = (
    r"icon",
    r"\bionospheric connection explorer\b",
    r"mighti",
)
PLANET_PATTERNS_BY_NAME = {
    "火星": (r"\bmars\b", r"\bmartian\b", r"火星"),
    "金星": (r"\bvenus\b", r"\bvenusian\b", r"金星"),
    "土星": (r"\bsaturn\b", r"土星"),
    "木星": (r"\bjupiter\b", r"木星"),
    "水星": (r"\bmercury\b", r"水星"),
    "月球": (r"\bmoon\b", r"\blunar\b", r"月球"),
    "彗星": (r"\bcomet\b", r"彗星"),
}
ESCAPE_PATTERNS = (
    r"\bescape\b",
    r"\bescaping\b",
    r"\boutflow\b",
    r"\bescape rate\b",
    r"逃逸",
    r"外逸",
)
SUN_TO_EARTH_EXPLICIT_PATTERNS = (
    r"\bsun-?to-?earth\b",
    r"\bsolar-?terrestrial\b",
    r"\bsolar wind magnetosphere ionosphere thermosphere\b",
    r"\bsolar wind magnetosphere ionosphere\b",
    r"日地耦合",
    r"太阳-地球耦合",
    r"太阳到地球",
    r"从太阳到地球",
    r"多圈层耦合",
    r"跨圈层耦合",
)
SUN_TO_EARTH_SOLAR_DRIVER_PATTERNS = (
    r"\bsolar wind\b",
    r"\bcme\b",
    r"\bicme\b",
    r"\binterplanetary\b",
    r"\bimf\b",
    r"\bcoronal mass ejection\b",
    r"\bsolar flare\b",
    r"\bsep\b",
    r"\bheliosphere\b",
    r"\bheliospheric\b",
    r"太阳风",
    r"行星际",
    r"日球层",
    r"日冕物质抛射",
    r"CME",
    r"ICME",
    r"太阳耀斑",
)
SUN_TO_EARTH_MAGNETOSPHERE_PATTERNS = (
    r"\bmagnetosphere\b",
    r"\bmagnetospheric\b",
    r"\bmagnetosheath\b",
    r"\bbow shock\b",
    r"\bmagnetopause\b",
    r"\bmagnetotail\b",
    r"\bradiation belt\b",
    r"\bring current\b",
    r"\bplasmasphere\b",
    r"磁层",
    r"磁鞘",
    r"弓激波",
    r"磁层顶",
    r"磁尾",
    r"辐射带",
    r"环电流",
)
SUN_TO_EARTH_IONOSPHERE_PATTERNS = (
    r"\bionosphere\b",
    r"\bionospheric\b",
    r"\btec\b",
    r"\bfof2\b",
    r"\bhmf2\b",
    r"\bspread-?f\b",
    r"\bscintillation\b",
    r"电离层",
    r"TEC",
    r"foF2",
    r"hmF2",
    r"扩展F",
    r"闪烁",
)
SUN_TO_EARTH_THERMOSPHERE_PATTERNS = (
    r"\bthermosphere\b",
    r"\bthermospheric\b",
    r"\bupper atmosphere\b",
    r"\bneutral wind\b",
    r"\bneutral density\b",
    r"\bmass density\b",
    r"热层",
    r"高层大气",
    r"中性风",
    r"中性密度",
    r"质量密度",
    r"热层风",
)
SUN_TO_EARTH_COUPLING_PATTERNS = (
    r"\bcoupl(?:e|ing)\b",
    r"\bchain\b",
    r"\bcascade\b",
    r"\bdriver-response\b",
    r"\benergy transfer\b",
    r"\blinked response\b",
    r"\bconnection\b",
    r"耦合",
    r"链条",
    r"链路",
    r"级联",
    r"传递",
    r"响应链",
)
SUN_TO_EARTH_NEGATION_PATTERNS = (
    r"不(?:涉及|讨论|研究|聚焦|属于).{0,40}(?:日地耦合|太阳-地球耦合|太阳到地球|从太阳到地球|跨圈层耦合|多圈层耦合)",
    r"未(?:涉及|讨论|研究|展开).{0,40}(?:日地耦合|太阳-地球耦合|太阳到地球|从太阳到地球|跨圈层耦合|多圈层耦合)",
    r"不是.{0,40}(?:日地耦合|太阳-地球耦合|跨圈层耦合|多圈层耦合)",
)
NON_EARTH_PLANET_PATTERNS = (
    r"\bmars\b",
    r"\bmartian\b",
    r"\bvenus\b",
    r"\bvenusian\b",
    r"\bsaturn\b",
    r"\bjupiter\b",
    r"\bmercury\b",
    r"\blunar\b",
    r"\bmoon\b",
    r"\bcomet\b",
    r"火星",
    r"金星",
    r"土星",
    r"木星",
    r"水星",
    r"月球",
    r"彗星",
)
BROAD_TAG_DROP_PATTERNS = (
    r"^(?:方法/|对象/)?数据分析$",
)


@dataclass(frozen=True)
class TagReviewAuditIssue:
    path: Path
    current_tags: tuple[str, ...]
    reviewed_tags: tuple[str, ...]


@dataclass(frozen=True)
class TagReviewAuditReport:
    passed: bool
    scanned_files: int
    issues: list[TagReviewAuditIssue]


class TagReviewAgent:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.taxonomy = load_tag_taxonomy(root=root)
        self.formal_labels = formal_tag_labels(root)
        self.category_labels: dict[str, set[str]] = {}
        self.leaf_map: dict[str, set[str]] = {}
        self.suffix_map: dict[str, set[str]] = {}
        for label in self.formal_labels:
            category = self.taxonomy.category_for(label)
            self.category_labels.setdefault(category, set()).add(label)
            parts = [part for part in label.split("/") if part]
            if not parts:
                continue
            self.leaf_map.setdefault(parts[-1], set()).add(label)
            for index in range(len(parts)):
                suffix = "/".join(parts[index:])
                self.suffix_map.setdefault(suffix, set()).add(label)

    def review_tags(
        self,
        tags: list[str],
        *,
        title_text: str = "",
        body_text: str = "",
        extra_text: str = "",
        max_tags: int | None = None,
        context: str = "",
        record_candidates: bool = False,
    ) -> list[str]:
        inferred_context = tuple(
            self.taxonomy.infer_tags_from_text(
                title_text=title_text,
                body_text=body_text,
                extra_text=extra_text,
                max_tags=24,
            )
        )
        context_prefixes = self._infer_context_prefixes(title_text=title_text, body_text=body_text, extra_text=extra_text)
        reviewed: list[str] = []
        for raw in tags:
            reviewed.extend(self._review_single_tag(str(raw or "").strip(), inferred_context, context_prefixes))
        normalized = self.taxonomy.normalize_tags(reviewed, max_tags=max_tags, root=None, context=context, record_candidates=False)
        governed_formal: list[str] = []
        pending_candidates: list[str] = []
        for tag in normalized:
            if tag in self.formal_labels:
                if tag not in governed_formal:
                    governed_formal.append(tag)
                continue
            decision = govern_pending_candidate_tag(
                tag,
                formal_labels=self.formal_labels,
                focus_payload=self.taxonomy.payload,
                context_prefixes=context_prefixes,
            )
            if decision.status == "drop":
                continue
            if decision.status == "formal":
                for item in decision.formal_targets:
                    if item not in governed_formal:
                        governed_formal.append(item)
                continue
            if decision.tag:
                pending_candidates.append(decision.tag)
        selected_pending = self._select_pending_candidates(
            pending_candidates,
            context=context,
            title_text=title_text,
            body_text=body_text,
            extra_text=extra_text,
        )
        normalized_governed = self.taxonomy.normalize_tags(
            governed_formal + selected_pending,
            max_tags=max_tags,
            root=None,
            context=context,
            record_candidates=False,
        )
        selected_pending = [tag for tag in normalized_governed if tag not in self.formal_labels]
        if record_candidates and selected_pending:
            categories = {tag: self.taxonomy.category_for(tag) for tag in selected_pending}
            record_pending_tags(self.root, selected_pending, context=context, categories=categories)
        return normalized_governed

    def _select_pending_candidates(
        self,
        pending_candidates: list[str],
        *,
        context: str,
        title_text: str,
        body_text: str,
        extra_text: str,
    ) -> list[str]:
        if not pending_candidates:
            return []
        unique_pending = self.taxonomy.normalize_tags(
            pending_candidates,
            max_tags=max(len(pending_candidates), 32),
            root=None,
            context=context,
            record_candidates=False,
        )
        unique_pending = [tag for tag in unique_pending if tag not in self.formal_labels]
        limit = PENDING_LIMIT_BY_CONTEXT.get(str(context or "").strip())
        if not limit or len(unique_pending) <= limit:
            return unique_pending

        scored: list[tuple[int, str, str]] = []
        for tag in unique_pending:
            category = self.taxonomy.category_for(tag)
            family = _infer_pending_family_id(tag, category)
            score = PENDING_FAMILY_PRIORITY.get(family, 20)
            depth = max(tag.count("/"), 0)
            score -= depth * 3
            leaf = tag.split("/")[-1]
            if len(leaf) <= 4:
                score += 4
            if any(keyword in tag for keyword in PENDING_DETAIL_PENALTY_KEYWORDS):
                score -= 10
            if tag.startswith(("仪器/", "模型/", "方法/", "应用/", "数据/")):
                score += 8
            if tag.startswith("对象/") and depth <= 2:
                score += 3
            if title_text and leaf.lower() in title_text.lower():
                score += 2
            if extra_text and leaf in extra_text:
                score -= 2
            scored.append((score, family, tag))

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        selected: list[str] = []
        used_families: set[str] = set()
        for score, family, tag in scored:
            if len(selected) >= limit:
                break
            if family in used_families:
                continue
            selected.append(tag)
            used_families.add(family)
        if len(selected) < limit:
            for score, family, tag in scored:
                if len(selected) >= limit:
                    break
                if tag in selected:
                    continue
                selected.append(tag)
        return selected

    def _review_single_tag(self, raw_tag: str, inferred_context: tuple[str, ...], context_prefixes: tuple[str, ...]) -> list[str]:
        phrase_alias = self._resolve_phrase_alias(raw_tag, context_prefixes)
        if phrase_alias is not None:
            return phrase_alias
        clean = clean_tag_text(raw_tag)
        if not clean:
            return []
        if any(re.search(pattern, clean, flags=re.IGNORECASE) for pattern in BROAD_TAG_DROP_PATTERNS):
            return []
        resolved = self._resolve_to_formal(clean, inferred_context, context_prefixes)
        if resolved:
            return resolved
        styled = self._style_unknown_tag(clean)
        if any(re.search(pattern, styled, flags=re.IGNORECASE) for pattern in BROAD_TAG_DROP_PATTERNS):
            return []
        resolved = self._resolve_to_formal(styled, inferred_context, context_prefixes)
        if resolved:
            return resolved
        return [styled]

    def _resolve_to_formal(self, tag: str, inferred_context: tuple[str, ...], context_prefixes: tuple[str, ...]) -> list[str] | None:
        resolved = resolve_existing_output_tag(tag, self.formal_labels)
        if resolved:
            return resolved
        clean = clean_tag_text(tag)
        if not clean:
            return None
        category_hint = self.taxonomy.category_for(clean)
        candidates = self._candidate_matches(clean, category_hint)
        if not candidates:
            return None
        if len(candidates) == 1:
            return [candidates[0]]
        best = self._pick_best_candidate(
            candidates,
            raw_tag=clean,
            inferred_context=inferred_context,
            context_prefixes=context_prefixes,
            category_hint=category_hint,
        )
        return [best] if best else None

    def _candidate_matches(self, clean: str, category_hint: str) -> list[str]:
        candidates: set[str] = set()
        for suffix in self._iter_suffixes(clean):
            candidates.update(self.suffix_map.get(suffix, set()))
        leaf = clean.split("/")[-1]
        candidates.update(self.leaf_map.get(leaf, set()))
        if category_hint:
            category_matched = {item for item in candidates if self.taxonomy.category_for(item) == category_hint}
            if category_matched:
                candidates = category_matched
        return sorted(candidates)

    def _pick_best_candidate(
        self,
        candidates: list[str],
        *,
        raw_tag: str,
        inferred_context: tuple[str, ...],
        context_prefixes: tuple[str, ...],
        category_hint: str,
    ) -> str | None:
        if not candidates:
            return None
        scored: list[tuple[int, str]] = []
        for candidate in candidates:
            score = 0
            if candidate == raw_tag:
                score += 20
            if candidate.endswith(f"/{raw_tag}"):
                score += 8
            if category_hint and self.taxonomy.category_for(candidate) == category_hint:
                score += 8
            if candidate.split("/")[-1] == raw_tag.split("/")[-1]:
                score += 3
            for prefix in context_prefixes:
                if candidate.startswith(prefix + "/") or candidate == prefix:
                    score += 10
            for inferred in inferred_context:
                if candidate == inferred:
                    score += 12
                elif candidate.startswith(inferred + "/"):
                    score += 10
                elif inferred.startswith(candidate + "/"):
                    score += 7
                else:
                    common_depth = self._common_prefix_depth(candidate, inferred)
                    if common_depth >= 2:
                        score += 5
                    elif common_depth == 1:
                        score += 2
            scored.append((score, candidate))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if len(scored) == 1:
            return scored[0][1]
        if scored[0][0] > scored[1][0]:
            return scored[0][1]
        return None

    def _resolve_phrase_alias(self, raw_tag: str, context_prefixes: tuple[str, ...]) -> list[str] | None:
        original = str(raw_tag or "").strip()
        if not original:
            return None
        folded = re.sub(r"[\s_/-]+", " ", original).strip().lower()
        if not folded:
            return None
        if folded in {"earth", "地球"}:
            return []
        mapping = (
            ((r"低纬电离层|low latitude ionosphere|low latitude ionospheric",), ["对象/电离层/低纬"]),
            ((r"磁层状态|magnetosphere state",), ["对象/磁层"]),
            ((r"热层风|thermospheric wind|neutral wind",), ["对象/热层/风场"]),
            ((r"中性密度|neutral density|mass density",), ["对象/热层/密度"]),
            ((r"热层温度|thermospheric temperature",), ["对象/热层/温度"]),
            ((r"o n2|o/n2|composition",), ["对象/热层/成分"]),
            ((r"polar convection boundary|极区对流边界",), ["对象/极区/对流边界"]),
            ((r"polar convection|极区对流|高纬过程 极区对流",), ["对象/极区/等离子体对流"]),
            ((r"电子密度|electron density",), self._electron_density_default(context_prefixes)),
            ((r"月球|moon",), ["对象/其他行星/月球"]),
            ((r"火星|mars|martian",), ["对象/其他行星/火星"]),
            ((r"土星|saturn|saturnian",), ["对象/其他行星/土星"]),
        )
        for patterns, targets in mapping:
            if any(re.search(pattern, folded, flags=re.IGNORECASE) for pattern in patterns):
                return list(targets)
        return None

    @staticmethod
    def _electron_density_default(context_prefixes: tuple[str, ...]) -> list[str]:
        if "对象/极区" in context_prefixes:
            return ["对象/极区/电子密度"]
        return ["对象/电离层/电子密度"]

    def _infer_context_prefixes(self, *, title_text: str, body_text: str, extra_text: str) -> tuple[str, ...]:
        haystack = normalize_haystack_text(" ".join(part for part in (title_text, body_text, extra_text) if part))
        if not haystack:
            return ()
        hints: list[str] = []
        signal_rules = (
            (r"ionosphere|电离层|tec|fof2|hmf2|eia|epb|equatorial", "对象/电离层"),
            (r"polar|极区|aurora|auroral|superdarn|cusp|polarcap", "对象/极区"),
            (r"thermosphere|热层|neutralwind|neutral wind|density", "对象/热层"),
            (r"magnetosphere|磁层|radiation belt|ring current|plasmasphere", "对象/磁层"),
        )
        for pattern, prefix in signal_rules:
            if re.search(pattern, haystack, flags=re.IGNORECASE) and prefix not in hints:
                hints.append(prefix)
        return tuple(hints)

    def _style_unknown_tag(self, clean: str) -> str:
        if any(clean == root or clean.startswith(root + "/") for root in FORMAL_ROOTS):
            return clean
        category_hint = self.taxonomy.category_for(clean)
        if category_hint == "instrument_data":
            root = self._instrument_or_data_root(clean)
        elif category_hint == "model_method":
            root = self._method_model_or_tool_root(clean)
        else:
            root = CATEGORY_DEFAULT_ROOT.get(category_hint, "对象")
        return f"{root}/{clean}" if clean and not clean.startswith(root + "/") else clean

    def _instrument_or_data_root(self, clean: str) -> str:
        if any(clean == prefix or clean.startswith(prefix + "/") for prefix in ("仪器", "数据")):
            return clean.split("/", 1)[0]
        if any(hint.lower() in clean.lower() for hint in DATA_ROOT_HINTS):
            return "数据"
        return "仪器"

    def _method_model_or_tool_root(self, clean: str) -> str:
        if any(clean == prefix or clean.startswith(prefix + "/") for prefix in ("方法", "模型", "工具")):
            return clean.split("/", 1)[0]
        if any(hint.lower() in clean.lower() for hint in TOOL_ROOT_HINTS):
            return "工具"
        if any(hint.lower() in clean.lower() for hint in MODEL_ROOT_HINTS):
            return "模型"
        if any(hint.lower() in clean.lower() for hint in METHOD_ROOT_HINTS):
            return "方法"
        if clean.isascii() and clean.upper() == clean and len(clean) >= 3:
            return "模型"
        return "方法"

    @staticmethod
    def _iter_suffixes(tag: str) -> list[str]:
        parts = [part for part in tag.split("/") if part]
        return ["/".join(parts[index:]) for index in range(len(parts))]

    @staticmethod
    def _common_prefix_depth(left: str, right: str) -> int:
        left_parts = [item for item in left.split("/") if item]
        right_parts = [item for item in right.split("/") if item]
        depth = 0
        for left_part, right_part in zip(left_parts, right_parts):
            if left_part != right_part:
                break
            depth += 1
        return depth


@lru_cache(maxsize=16)
def _load_tag_review_agent_cached(root_text: str, focus_mtime_ns: int, formal_mtime_ns: int) -> TagReviewAgent:
    del focus_mtime_ns, formal_mtime_ns
    return TagReviewAgent(Path(root_text))


def load_tag_review_agent(root: Path | None = None) -> TagReviewAgent:
    project = (root or project_root()).resolve()
    focus_path = project / "config" / "focus_tags.json"
    formal_path = formal_tags_markdown_path(project)
    return _load_tag_review_agent_cached(
        str(project),
        focus_path.stat().st_mtime_ns if focus_path.exists() else 0,
        formal_path.stat().st_mtime_ns if formal_path.exists() else 0,
    )


def clear_tag_review_cache() -> None:
    _load_tag_review_agent_cached.cache_clear()


def should_keep_satellite_impact_tag(
    *,
    title_text: str = "",
    body_text: str = "",
    extra_text: str = "",
) -> bool:
    positive_haystack = _primary_focus_haystack(title_text=title_text, body_text=body_text, limit=320)
    full_haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text=extra_text)
    if not positive_haystack:
        return True
    if any(re.search(pattern, full_haystack, flags=re.IGNORECASE) for pattern in SATELLITE_IMPACT_NEGATION_PATTERNS):
        return False
    if not any(re.search(pattern, positive_haystack, flags=re.IGNORECASE) for pattern in SATELLITE_SUBJECT_PATTERNS):
        return False
    if not any(re.search(pattern, positive_haystack, flags=re.IGNORECASE) for pattern in SATELLITE_ENVIRONMENT_PATTERNS):
        return False
    if not any(re.search(pattern, positive_haystack, flags=re.IGNORECASE) for pattern in SATELLITE_IMPACT_PATTERNS):
        return False
    return True


def should_keep_thermosphere_density_tag(
    *,
    title_text: str = "",
    body_text: str = "",
    extra_text: str = "",
) -> bool:
    positive_haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text="")
    full_haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text=extra_text)
    if not positive_haystack:
        return False
    if _has_any(full_haystack, THERMOSPHERE_DENSITY_NEGATION_PATTERNS):
        return False
    return _has_any(positive_haystack, THERMOSPHERE_CONTEXT_PATTERNS) and _has_any(
        positive_haystack, THERMOSPHERE_DENSITY_POSITIVE_PATTERNS
    )


def should_keep_sun_to_earth_coupling_tag(
    *,
    title_text: str = "",
    body_text: str = "",
    extra_text: str = "",
) -> bool:
    haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text="")
    full_haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text=extra_text)
    if not haystack:
        return False
    if _has_any(full_haystack, SUN_TO_EARTH_NEGATION_PATTERNS):
        return False
    if _has_any(full_haystack, NON_EARTH_PLANET_PATTERNS):
        return False
    if _has_any(haystack, SUN_TO_EARTH_EXPLICIT_PATTERNS):
        return True
    if not _has_any(haystack, SUN_TO_EARTH_SOLAR_DRIVER_PATTERNS):
        return False
    if not _has_any(haystack, SUN_TO_EARTH_COUPLING_PATTERNS):
        return False
    sphere_hits = sum(
        1
        for patterns in (
            SUN_TO_EARTH_MAGNETOSPHERE_PATTERNS,
            SUN_TO_EARTH_IONOSPHERE_PATTERNS,
            SUN_TO_EARTH_THERMOSPHERE_PATTERNS,
        )
        if _has_any(haystack, patterns)
    )
    return sphere_hits >= 3


def _support_haystack(*, title_text: str = "", body_text: str = "", extra_text: str = "") -> str:
    return normalize_haystack_text(" ".join(part for part in (title_text, _strip_tag_lines(body_text), extra_text) if part))


def _primary_focus_haystack(*, title_text: str = "", body_text: str = "", limit: int = 240) -> str:
    body = _strip_tag_lines(body_text)
    return normalize_haystack_text(" ".join(part for part in (title_text, body[:limit]) if part))


def _has_any(haystack: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in patterns)


def _match_count(haystack: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, haystack, flags=re.IGNORECASE))


def should_keep_solar_wind_tag(
    *,
    title_text: str = "",
    body_text: str = "",
) -> bool:
    positive_haystack = _primary_focus_haystack(title_text=title_text, body_text=body_text, limit=260)
    if not positive_haystack:
        return True
    return _has_any(positive_haystack, SOLAR_WIND_PATTERNS)


def should_keep_high_speed_flow_tag(
    *,
    title_text: str = "",
    body_text: str = "",
) -> bool:
    positive_haystack = _primary_focus_haystack(title_text=title_text, body_text=body_text, limit=260)
    if not positive_haystack:
        return True
    return _has_any(positive_haystack, HIGH_SPEED_FLOW_PATTERNS)


def should_keep_geomagnetic_storm_tag(
    *,
    title_text: str = "",
    body_text: str = "",
    extra_text: str = "",
) -> bool:
    title_haystack = normalize_haystack_text(title_text)
    extra_haystack = normalize_haystack_text(extra_text)
    positive_haystack = _primary_focus_haystack(title_text="", body_text=body_text, limit=260)
    if not title_haystack and not positive_haystack and not extra_haystack:
        return True
    if _has_any(title_haystack, GEOMAGNETIC_STORM_PATTERNS):
        return True
    if "related_summary_tags:" in str(extra_text or "").lower() and _has_any(extra_haystack, GEOMAGNETIC_STORM_PATTERNS):
        return True
    return _has_any(positive_haystack, GEOMAGNETIC_STORM_FOCUS_PATTERNS)


def should_keep_gravity_wave_tag(
    *,
    title_text: str = "",
    body_text: str = "",
) -> bool:
    title_haystack = normalize_haystack_text(title_text)
    positive_haystack = _primary_focus_haystack(title_text="", body_text=body_text, limit=180)
    if not title_haystack and not positive_haystack:
        return True
    if _has_any(title_haystack, GRAVITY_WAVE_PATTERNS):
        return True
    return _match_count(positive_haystack, GRAVITY_WAVE_PATTERNS) >= 2


def should_keep_euv_tag(
    *,
    title_text: str = "",
    body_text: str = "",
) -> bool:
    positive_haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text="")
    if not positive_haystack:
        return True
    return _has_any(positive_haystack, EUV_PATTERNS)


def should_keep_icon_tag(
    *,
    title_text: str = "",
    body_text: str = "",
) -> bool:
    positive_haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text="")
    if not positive_haystack:
        return True
    return _has_any(positive_haystack, ICON_PATTERNS)


def should_keep_other_planet_tag(
    tag: str,
    *,
    title_text: str = "",
    body_text: str = "",
) -> bool:
    positive_haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text="")
    if not positive_haystack:
        return True
    parts = [part for part in clean_tag_text(tag).split("/") if part]
    if len(parts) < 3 or parts[0] != "对象" or parts[1] != "其他行星":
        return True
    planet = parts[2]
    planet_patterns = PLANET_PATTERNS_BY_NAME.get(planet)
    if planet_patterns and not _has_any(positive_haystack, planet_patterns):
        return False
    if parts[-1] == "逃逸":
        return _has_any(positive_haystack, ESCAPE_PATTERNS)
    return True


def should_keep_formal_tag(
    tag: str,
    *,
    title_text: str = "",
    body_text: str = "",
    extra_text: str = "",
) -> bool:
    clean = clean_tag_text(tag)
    if not clean:
        return False
    if clean == "应用/卫星影响":
        return should_keep_satellite_impact_tag(title_text=title_text, body_text=body_text, extra_text=extra_text)
    if clean == "对象/日地耦合" or clean.startswith("对象/日地耦合/"):
        return should_keep_sun_to_earth_coupling_tag(title_text=title_text, body_text=body_text, extra_text=extra_text)
    if clean == "对象/太阳风":
        return should_keep_solar_wind_tag(title_text=title_text, body_text=body_text)
    if clean == "对象/太阳风/高速流":
        return should_keep_high_speed_flow_tag(title_text=title_text, body_text=body_text)
    if clean.startswith("对象/其他行星/"):
        return should_keep_other_planet_tag(clean, title_text=title_text, body_text=body_text)
    haystack = _support_haystack(title_text=title_text, body_text=body_text, extra_text=extra_text)
    if not haystack:
        return True

    if clean == "对象/热层/密度":
        return should_keep_thermosphere_density_tag(title_text=title_text, body_text=body_text, extra_text=extra_text)

    if clean == "对象/重力波":
        return should_keep_gravity_wave_tag(title_text=title_text, body_text=body_text)

    if clean.startswith("对象/热层/风场"):
        if _has_any(haystack, THERMOSPHERE_WIND_NEGATION_PATTERNS):
            return False
        return _has_any(haystack, THERMOSPHERE_WIND_POSITIVE_PATTERNS)

    if clean == "对象/电离层/TEC":
        return _has_any(haystack, IONOSPHERE_TEC_POSITIVE_PATTERNS) and _has_any(haystack, IONOSPHERE_CONTEXT_PATTERNS)

    if clean == "对象/电离层/电子密度":
        return _has_any(haystack, IONOSPHERE_ELECTRON_DENSITY_POSITIVE_PATTERNS) and _has_any(haystack, IONOSPHERE_CONTEXT_PATTERNS)

    if clean == "对象/极区/电子密度":
        return _has_any(haystack, IONOSPHERE_ELECTRON_DENSITY_POSITIVE_PATTERNS) and _has_any(haystack, POLAR_CONTEXT_PATTERNS)

    if clean == "事件/亚暴":
        return _has_any(haystack, SUBSTORM_PATTERNS)

    if clean == "事件/磁暴" or clean.startswith("事件/磁暴/"):
        return should_keep_geomagnetic_storm_tag(title_text=title_text, body_text=body_text, extra_text=extra_text)

    if clean == "指数/EUV":
        return should_keep_euv_tag(title_text=title_text, body_text=body_text)

    if clean == "仪器/ICON":
        return should_keep_icon_tag(title_text=title_text, body_text=body_text)

    return True


def prune_unsupported_formal_tags(
    tags: list[str],
    *,
    title_text: str = "",
    body_text: str = "",
    extra_text: str = "",
) -> list[str]:
    kept: list[str] = []
    for tag in tags:
        clean = clean_tag_text(tag)
        if clean == "对象/太阳风/高速流":
            if should_keep_formal_tag(clean, title_text=title_text, body_text=body_text, extra_text=extra_text):
                kept.append(clean)
            elif should_keep_formal_tag("对象/太阳风", title_text=title_text, body_text=body_text, extra_text=extra_text):
                kept.append("对象/太阳风")
            continue
        if should_keep_formal_tag(clean, title_text=title_text, body_text=body_text, extra_text=extra_text):
            kept.append(clean)
    deduped: list[str] = []
    for tag in kept:
        if tag not in deduped:
            deduped.append(tag)
    return deduped


def _strip_tag_lines(text: str) -> str:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- 标签：") or stripped.startswith("- 标签:"):
            continue
        if stripped.startswith("- [DOI]") and "#" in stripped:
            continue
        if stripped.startswith("- [PDF]") and "#" in stripped:
            continue
        lines.append(raw_line)
    return "\n".join(lines)


def _output_review_evidence(project: Path, path: Path, text: str) -> tuple[str, str]:
    try:
        path.relative_to(article_summaries_root(project))
        body = extract_summary_body(text) or _strip_tag_lines(text)
        supplement = extract_numbered_line(text, "- 「补充信息」")
        return body, supplement
    except Exception:
        return _strip_tag_lines(text), ""


def review_generated_tags(
    tags: list[str],
    *,
    root: Path | None = None,
    title_text: str = "",
    body_text: str = "",
    extra_text: str = "",
    max_tags: int | None = None,
    context: str = "",
    record_candidates: bool = False,
) -> list[str]:
    project = root or project_root()
    agent = load_tag_review_agent(project)
    reviewed = agent.review_tags(
        tags,
        title_text=title_text,
        body_text=body_text,
        extra_text=extra_text,
        max_tags=max_tags,
        context=context,
        record_candidates=record_candidates,
    )
    return prune_unsupported_formal_tags(
        reviewed,
        title_text=title_text,
        body_text=body_text,
        extra_text=extra_text,
    )


def reconcile_auto_output_tags_with_review(root: Path | None = None) -> OutputTagRewriteResult:
    project = root or project_root()
    formal = formal_tag_labels(project)
    modified_entries: list[OutputTagRewriteEntry] = []
    remaining_nonformal_counts: dict[str, int] = {}
    scanned_files = 0
    for base in (article_summaries_root(project), deep_reads_root(project)):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            if path.name.startswith("."):
                continue
            scanned_files += 1
            text = path.read_text(encoding="utf-8")
            body_text, extra_text = _output_review_evidence(project, path, text)
            lines = text.splitlines()
            changed = False
            changes: list[tuple[str, tuple[str, ...]]] = []
            for index, line in enumerate(lines):
                if not line.startswith("- ") or "#" not in line:
                    continue
                current_tags = extract_summary_tags(line)
                if not current_tags:
                    continue
                reviewed_tags = review_generated_tags(
                    current_tags,
                    root=project,
                    title_text=path.stem,
                    body_text=body_text,
                    extra_text=extra_text,
                    max_tags=max(len(current_tags), 14),
                    context="output_rewrite",
                    record_candidates=False,
                )
                if tuple(reviewed_tags) == tuple(current_tags):
                    continue
                prefix = line.split("#", 1)[0].rstrip()
                lines[index] = f"{prefix} {build_tag_line(reviewed_tags)}".rstrip()
                changed = True
                changes.extend((tag, tuple(reviewed_tags)) for tag in current_tags if tag not in reviewed_tags)
            updated_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            if changed:
                path.write_text(updated_text, encoding="utf-8")
            final_tags = extract_summary_tags(updated_text)
            remaining_nonformal = tuple(tag for tag in final_tags if tag not in formal)
            if changed:
                modified_entries.append(
                    OutputTagRewriteEntry(
                        path=path,
                        changes=_dedupe_change_pairs(changes),
                        remaining_nonformal=remaining_nonformal,
                    )
                )
            for tag in remaining_nonformal:
                remaining_nonformal_counts[tag] = int(remaining_nonformal_counts.get(tag, 0) or 0) + 1
    refresh_pending_tag_files(project)
    return OutputTagRewriteResult(
        scanned_files=scanned_files,
        modified_entries=modified_entries,
        remaining_nonformal_counts=dict(sorted(remaining_nonformal_counts.items(), key=lambda item: (-item[1], item[0]))),
    )


def run_tag_output_review(root: Path | None = None) -> TagReviewAuditReport:
    project = root or project_root()
    issues: list[TagReviewAuditIssue] = []
    scanned_files = 0
    for base in (article_summaries_root(project), deep_reads_root(project)):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            if path.name.startswith("."):
                continue
            scanned_files += 1
            text = path.read_text(encoding="utf-8")
            body_text, extra_text = _output_review_evidence(project, path, text)
            current_tags = extract_summary_tags(text)
            if not current_tags:
                continue
            reviewed_tags = review_generated_tags(
                current_tags,
                root=project,
                title_text=path.stem,
                body_text=body_text,
                extra_text=extra_text,
                max_tags=max(len(current_tags), 14),
                context="output_review",
                record_candidates=False,
            )
            if tuple(reviewed_tags) != tuple(current_tags):
                issues.append(
                    TagReviewAuditIssue(
                        path=path,
                        current_tags=tuple(current_tags),
                        reviewed_tags=tuple(reviewed_tags),
                    )
                )
    return TagReviewAuditReport(passed=not issues, scanned_files=scanned_files, issues=issues)


def render_tag_output_review_summary(report: TagReviewAuditReport) -> str:
    lines = [
        "Tag output review summary:",
        f"- scanned_files={report.scanned_files}",
        f"- issues={len(report.issues)}",
        f"- overall={'ok' if report.passed else 'failed'}",
    ]
    if not report.issues:
        lines.append("- violations: none")
        return "\n".join(lines)
    lines.append("- violations:")
    for issue in report.issues[:10]:
        lines.append(
            "  - "
            + f"{issue.path}: current={list(issue.current_tags)} -> reviewed={list(issue.reviewed_tags)}"
        )
    if len(report.issues) > 10:
        lines.append(f"  - ... 另外还有 {len(report.issues) - 10} 个文件")
    return "\n".join(lines)


def _dedupe_change_pairs(changes: list[tuple[str, tuple[str, ...]]]) -> list[tuple[str, tuple[str, ...]]]:
    deduped: list[tuple[str, tuple[str, ...]]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for change in changes:
        if change not in seen:
            seen.add(change)
            deduped.append(change)
    return deduped
