from __future__ import annotations

import copy
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .article_summary_markdown import build_tag_line, extract_summary_tags
from .config import (
    article_summaries_root,
    deep_reads_root,
    focus_tags_config_path,
    formal_tags_markdown_path,
    output_root,
    pending_tags_json_path,
    pending_tags_markdown_path,
    project_root,
)
from .tags import normalize_haystack_text


LEGACY_PENDING_TAGS_PATH = Path("data/tag_candidates.json")
FORMAL_TAGS_TITLE = "# 正式标签"
PENDING_TAGS_TITLE = "# 预选标签"
GROUP_SUFFIX = "（分组）"
AI_SUMMARY_SUFFIX = "【AI总结】"
PENDING_COUNT_SUFFIX_RE = re.compile(r"\s*[（(]\s*(?:使用)?\s*\d+\s*次(?:[^）)]*)?[）)]\s*$")
MARKDOWN_BULLET_RE = re.compile(r"^(?P<indent>\s*)-\s+(?:(?P<checkbox>\[[ xX]\])\s+)?(?P<label>.+?)\s*$")
PENDING_REVIEW_BODY_RE = re.compile(
    r"^(?P<label>.+?)\s*[（(]\s*(?P<count>\d+)\s*次(?:[^）)]*)?[）)](?P<tail>.*)$"
)
EXISTING_OUTPUT_TAG_ALIAS_MAP = {
    "仪器/数据": ["数据"],
    "仪器/数据/数据对比": ["数据/数据对比"],
    "太阳风-磁层能量耦合": ["对象/磁层/太阳风耦合"],
    "磁层-电离层耦合": ["对象/磁层/电离层耦合"],
    "Space-X事件": ["事件/SpaceX事件"],
    "模拟研究": ["方法/数值模拟"],
    "模式模拟": ["方法/数值模拟"],
    "建模/经验建模": ["方法/建模/经验模型"],
    "建模/数值模拟": ["方法/数值模拟"],
    "模型/数值模拟": ["方法/数值模拟"],
    "模型/MSIS/修正": ["模型/MSIS"],
    "磁暴/HILDCAAs": ["事件/HILDCAAs"],
    "电离层/EIA/X-Pattern": ["对象/电离层/EIA", "对象/电离层/X-Pattern"],
    "极区/HP": ["指数/HP"],
    "极区/CPCP": ["指数/CPCP"],
    "特征/MTM": ["对象/热层/MTM"],
    "特征/午夜密度最大值": ["对象/热层/MTM"],
    "热层/数据": ["数据"],
    "深度学习": ["方法/建模/机器学习"],
    "Alfvén波": ["对象/Alfven波"],
    "热层/伺服理论": ["对象/热层/风场/伺服理论"],
    "热层/时间延迟": ["对象/热层/响应时延"],
    "热层/加热冷却时延": ["对象/热层/响应时延"],
    "低热层/温度": ["对象/热层/低热层", "对象/热层/温度"],
    "指数/太阳风": ["对象/太阳风"],
    "工具": ["方法/建模"],
    "热层/风": ["对象/热层/风场"],
    "热层/质量密度": ["对象/热层/密度"],
    "重力波/潮汐": ["对象/重力波", "对象/潮汐"],
    "方法/统计分析": ["方法/统计研究"],
    "极区对流/边界": ["对象/极区/对流边界"],
    "卫星/阻力": ["应用/卫星影响"],
    "对象/空间天气/地磁暴": ["事件/磁暴"],
    "对象/物理机制/Joule加热": ["对象/极区/焦耳加热"],
    "对象/行星空间环境": ["对象/行星际环境"],
    "对象/行星空间环境/IMF构型": ["指数/IMF"],
    "对象/行星际环境/IMF构型": ["指数/IMF"],
    "对象/行星空间环境/日冕物质抛射CME": ["事件/磁暴/CME"],
    "对象/行星际环境/日冕物质抛射CME": ["事件/磁暴/CME"],
    "仪器/磁力计": ["仪器/磁强计"],
    "应用/空间天气预报": ["应用/预测"],
    "应用/空间天气/预报": ["应用/预测"],
    "应用/卫星再入/轨迹预测": ["应用/卫星轨道衰减"],
    "模型/深度学习": ["方法/建模/机器学习"],
    "模型/残差网络": ["方法/建模/机器学习"],
    "赤道/质量密度异常": ["对象/热层/EMA"],
    "研究星球/土星": ["对象/其他行星/土星"],
    "研究星球/木星": ["对象/其他行星/木星"],
}
DEFAULT_CATEGORY_PREFIXES = {
    "热层": "research_object",
    "电离层": "research_object",
    "极区": "research_object",
    "磁层": "research_object",
    "日地耦合": "research_object",
    "重力波": "research_object",
    "其他行星": "research_object",
    "低热层": "research_object",
    "火星": "research_object",
    "逃逸层": "research_object",
    "赤道": "research_object",
    "中间层": "research_object",
    "场": "research_object",
    "地磁": "research_object",
    "环电流": "research_object",
    "等离子体层": "research_object",
    "粒子注入": "research_object",
    "磁层顶": "research_object",
    "弓激波": "research_object",
    "周期扰动": "research_object",
    "动力学过程": "research_object",
    "Alfvén波": "research_object",
    "潮汐": "research_object",
    "磁暴": "event_driver",
    "太阳风": "event_driver",
    "行星际激波": "event_driver",
    "SSW": "event_driver",
    "亚暴": "event_driver",
    "磁重联": "event_driver",
    "SEP": "event_driver",
    "Space-X事件": "event_driver",
    "太空台风": "event_driver",
    "仪器": "instrument_data",
    "数据": "instrument_data",
    "卫星": "instrument_data",
    "探测器": "instrument_data",
    "台站": "instrument_data",
    "指数": "index_control",
    "参数": "index_control",
    "模型": "model_method",
    "建模": "model_method",
    "深度学习": "model_method",
    "模拟研究": "model_method",
    "数据同化": "model_method",
    "统计研究": "model_method",
    "误差估计": "model_method",
    "工具": "model_method",
    "可解释模型": "model_method",
    "方法": "model_method",
    "特征": "result_feature",
    "空间天气": "application_impact",
    "卫星影响": "application_impact",
    "业务化预报": "application_impact",
    "卫星轨道衰减": "application_impact",
    "空间天气影响": "application_impact",
    "预测": "application_impact",
    "应用": "application_impact",
    "信息来源": "status",
    "综述": "status",
    "Todo": "status",
    "重要": "status",
    "展望": "status",
    "科学思考": "status",
    "同行评审": "status",
    "摘要缺失": "status",
    "元数据": "status",
    "状态": "status",
}


@dataclass(frozen=True)
class PendingTagEntry:
    tag: str
    category: str
    family: str
    count: int
    first_seen: str
    last_seen: str
    contexts: dict[str, int]
    selected: bool
    note: str
    usage_count: int
    usage_by_kind: dict[str, int]


@dataclass(frozen=True)
class PendingTagPromotionResult:
    promoted_tags: list[str]
    formal_markdown_path: Path
    pending_markdown_path: Path
    protected_files: list[Path]


@dataclass(frozen=True)
class PendingTagReviewDecision:
    family_id: str
    category_id: str
    original_tag: str
    current_tag: str
    selected: bool
    usage_count: int
    note: str


@dataclass(frozen=True)
class PendingTagFamilySpec:
    id: str
    title: str


@dataclass(frozen=True)
class PendingTagNormalizationResult:
    status: str
    tag: str
    category_id: str
    family_id: str
    formal_targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class PendingTagReviewApplyResult:
    protected_files: list[Path]
    rewritten_entries: list[OutputTagRewriteEntry]
    promoted_tags: list[str]


@dataclass(frozen=True)
class OutputTagRewriteEntry:
    path: Path
    changes: list[tuple[str, tuple[str, ...]]]
    remaining_nonformal: tuple[str, ...]


@dataclass(frozen=True)
class OutputTagRewriteResult:
    scanned_files: int
    modified_entries: list[OutputTagRewriteEntry]
    remaining_nonformal_counts: dict[str, int]


class _TreeNode:
    def __init__(self, name: str, full_label: str) -> None:
        self.name = name
        self.full_label = full_label
        self.is_actual = False
        self.count = 0
        self.checked = False
        self.children: dict[str, _TreeNode] = {}


PENDING_FAMILY_SPECS = (
    PendingTagFamilySpec("solar_corona_heliosphere", "A. 上游太阳-日冕-日球层家族"),
    PendingTagFamilySpec("magnetosphere_particles", "B. 磁层-辐射带-高能粒子家族"),
    PendingTagFamilySpec("it_coupling_extensions", "C. 电离层-热层-耦合扩展家族"),
    PendingTagFamilySpec("planetary_environment", "D. 行星空间环境家族"),
    PendingTagFamilySpec("instruments_missions_observations", "E. 仪器-任务-台站-观测方式家族"),
    PendingTagFamilySpec("data_assets", "F. 数据资产家族"),
    PendingTagFamilySpec("models_methods", "G. 模型-方法家族"),
    PendingTagFamilySpec("applications_impacts", "H. 应用-工程影响家族"),
)
PENDING_FAMILY_BY_ID = {item.id: item for item in PENDING_FAMILY_SPECS}
PENDING_FAMILY_TITLES = {item.title: item.id for item in PENDING_FAMILY_SPECS}
PENDING_DROP_PREFIXES = (
    "对象/原行星盘",
    "对象/形成/卵石吸积",
    "对象/恒星",
    "对象/系外行星",
    "对象/脉冲星",
    "对象/同行评审",
    "对象/期刊/编务",
    "对象/区域/",
    "对象/地区/",
    "对象/时间/",
    "对象/学科/",
    "对象/组织/",
    "对象/人群/",
    "对象/观测站/",
    "对象/多点观测/",
    "对象/活动区/",
    "对象/活动指标/",
    "对象/太阳活动周/",
    "对象/太阳周/",
    "对象/参数/",
    "对象/指标/",
    "对象/观测/",
    "对象/探测/",
    "对象/载荷/",
    "对象/介质/",
    "对象/驱动/",
    "对象/通信/",
    "对象/物理机制/",
    "对象/现象/",
    "对象/空间天气/",
    "对象/评估/",
)
PENDING_DROP_EXACT_TAGS = {
    "对象/地方时",
    "对象/预条件",
    "对象/多年统计",
    "对象/时变",
    "对象/时空过程",
    "对象/演化/时空过程",
    "对象/雷达",
    "仪器/Honolulu",
    "对象/辐射/X射线",
    "对象/空间天气",
    "对象/卫星",
    "方法/数据分析",
    "对象/数据分析",
    "模型/物理模型",
    "数据分析",
}
PENDING_DROP_KEYWORDS = ("同行评审", "编务", "原行星盘", "系外行星", "脉冲星", "调查问卷", "早期职业科研人员")
PENDING_DIRECT_REWRITE_MAP = {
    "对象/南北不对称": "特征/南北半球不对称性",
    "事件/平流层突然增温": "事件/SSW",
    "对象/低层大气波动/平流层突然增温": "事件/SSW",
    "对象/轨道数据/TLE": "数据/TLE",
    "对象/太阳与日球层/太阳耀斑": "事件/太阳耀斑",
    "对象/太阳与日球层/太阳质子事件": "事件/SEP",
    "对象/太阳/紫外辐照度": "指数/EUV",
    "对象/太阳活动/耀斑": "事件/太阳耀斑",
    "对象/耀斑/紧凑耀斑": "事件/太阳耀斑",
    "方法/深度神经网络": "方法/建模/机器学习",
    "方法/深度学习": "方法/建模/机器学习",
    "方法/人工神经网络": "方法/建模/机器学习",
    "方法/WideLearning": "方法/建模/机器学习",
    "对象/太阳活动/F10.7": "指数/F107",
    "对象/高能粒子/电子通量": "对象/高能粒子/电子",
    "对象/高能粒子/辐射带电子": "对象/高能粒子/电子",
    "对象/日球层/太阳风参数": "对象/太阳风",
    "对象/太阳风/磁偏折": "对象/太阳风",
    "对象/太阳风/阿尔芬面": "对象/太阳/日球层",
    "对象/行星空间环境": "对象/行星际环境",
    "对象/行星空间环境/IMF构型": "指数/IMF",
    "对象/行星际环境/IMF构型": "指数/IMF",
    "对象/行星空间环境/日冕物质抛射CME": "事件/磁暴/CME",
    "对象/行星际环境/日冕物质抛射CME": "事件/磁暴/CME",
    "对象/行星际环境驱动/低动压": "对象/太阳风/动压",
    "对象/行星际环境驱动/低阿尔芬马赫数太阳风": "对象/太阳风",
    "对象/日地耦合/太阳风-地磁耦合": "对象/磁层/太阳风耦合",
    "对象/日地耦合/前震": "对象/磁层/弓激波",
    "对象/地磁场/地磁扰动": "对象/地磁",
    "对象/磁场/地磁坐标": "对象/地磁",
    "对象/极区/极光带": "对象/极区/极光",
    "对象/热层/白昼气辉": "对象/气辉",
    "对象/平流层/极涡": "对象/中间层",
    "对象/电离层/中纬度": "对象/电离层/中纬",
    "对象/电离层/中高纬": "对象/电离层/高纬",
    "对象/电离层/振幅闪烁": "对象/电离层/闪烁",
    "对象/近地空间/激波": "对象/行星际激波",
    "对象/磁层/外辐射带": "对象/高能粒子/电子",
    "对象/感应电流/GIC指数": "应用/基础设施",
    "对象/事件统计/强度分级": "方法/统计研究",
    "对象/空间天气/地磁暴": "事件/磁暴",
    "对象/物理机制/Joule加热": "对象/极区/焦耳加热",
    "对象/能量转换/Joule加热": "对象/极区/焦耳加热",
    "对象/太阳驱动/EUV通量": "指数/EUV",
    "对象/太阳驱动/EUV辐射": "指数/EUV",
    "对象/太阳活动/F10.7指数": "指数/F107",
    "方法/问卷调查": "方法/统计研究",
    "仪器/MIGHTI": "仪器/ICON",
    "仪器/TIMED-SABER": "仪器/SABER",
    "仪器/RadioSolarNetwork": "仪器/射电",
    "仪器/全天空相机": "仪器/极光图像",
    "仪器/磁力计": "仪器/磁强计",
    "应用/预报/短时预报": "应用/预测",
    "应用/预报/短期预测": "应用/预测",
    "应用/空间天气预报": "应用/预测",
    "应用/空间天气/预报": "应用/预测",
    "应用/预报": "应用/预测",
    "应用/卫星再入/轨迹预测": "应用/卫星轨道衰减",
}


def _pending_family_specs() -> tuple[PendingTagFamilySpec, ...]:
    return PENDING_FAMILY_SPECS


def _pending_family_title(family_id: str) -> str:
    spec = PENDING_FAMILY_BY_ID.get(str(family_id or "").strip())
    return spec.title if spec else "未归类家族"


def _pending_family_id_from_header(label: str) -> str | None:
    clean = str(label or "").strip()
    if not clean:
        return None
    direct = PENDING_FAMILY_TITLES.get(clean)
    if direct:
        return direct
    for spec in _pending_family_specs():
        if clean == spec.id or clean.endswith(spec.title):
            return spec.id
    return None


def _infer_pending_context_prefixes(*, title_text: str = "", body_text: str = "", extra_text: str = "") -> tuple[str, ...]:
    haystack = normalize_haystack_text(" ".join(part for part in (title_text, body_text, extra_text) if part))
    if not haystack:
        return ()
    hints: list[str] = []
    signal_rules = (
        (r"ionosphere|电离层|tec|fof2|hmf2|eia|epb|equatorial|esf|mstid", "对象/电离层"),
        (r"polar|极区|aurora|auroral|superdarn|cusp|polarcap|fac|saps", "对象/极区"),
        (r"thermosphere|热层|neutralwind|neutral wind|density|mass density", "对象/热层"),
        (r"magnetosphere|磁层|radiation belt|ring current|plasmasphere|substorm", "对象/磁层"),
    )
    for pattern, prefix in signal_rules:
        if re.search(pattern, haystack, flags=re.IGNORECASE) and prefix not in hints:
            hints.append(prefix)
    return tuple(hints)


def _rewrite_pending_candidate_tag(tag: str, *, context_prefixes: tuple[str, ...] = ()) -> str:
    clean = _clean_markdown_tag_label(tag)
    if not clean:
        return ""
    direct = PENDING_DIRECT_REWRITE_MAP.get(clean)
    if direct:
        return direct

    if clean in {"对象/电场", "电场"}:
        if "对象/极区" in context_prefixes:
            return "对象/极区/电场"
        return "对象/电离层/赤道/电场"
    if clean in {"对象/电子密度", "电子密度"}:
        if "对象/极区" in context_prefixes:
            return "对象/极区/电子密度"
        return "对象/电离层/电子密度"

    if clean.startswith(("对象/太阳/耀斑", "对象/太阳爆发/耀斑", "对象/太阳爆发/太阳耀斑", "对象/太阳耀斑")):
        return "事件/太阳耀斑"
    if clean.startswith(("对象/太阳与日球层/ICME", "对象/ICME", "事件/ICME")):
        return "事件/ICME"
    if clean.startswith(("对象/日冕物质抛射", "事件/CME", "事件/磁暴/CME")):
        return "事件/磁暴/CME"
    if clean.endswith("/TLE") or clean == "TLE":
        return "数据/TLE"

    prefix_rewrites = (
        ("对象/探测器/", "仪器/"),
        ("对象/卫星/", "仪器/"),
        ("对象/台站/", "仪器/"),
        ("对象/任务/", "仪器/"),
        ("对象/轨道数据/", "数据/"),
        ("对象/反演/", "方法/反演/"),
        ("对象/图像处理/", "方法/图像处理/"),
        ("对象/数据处理/", "方法/数据处理/"),
        ("对象/统计分析/", "方法/统计分析/"),
    )
    for source, target in prefix_rewrites:
        if clean.startswith(source):
            return target + clean[len(source) :]

    if clean.startswith("对象/模拟/"):
        remainder = clean[len("对象/模拟/") :]
        return f"方法/数值模拟/{remainder}".rstrip("/")
    if clean.startswith("对象/数值模拟/"):
        remainder = clean[len("对象/数值模拟/") :]
        return f"方法/数值模拟/{remainder}".rstrip("/")
    if clean.startswith("对象/观测/地基"):
        return "数据/地基观测"
    if clean.startswith("对象/地基观测/"):
        return "数据/地基观测/" + clean[len("对象/地基观测/") :]

    mission_like = re.match(r"^对象/([A-Za-z0-9][A-Za-z0-9.+\-]*(?:/[A-Za-z0-9.+\-]+)*)$", clean)
    if mission_like:
        return "仪器/" + mission_like.group(1)
    mission_with_payload = re.match(r"^对象/([A-Za-z0-9][A-Za-z0-9.+\-]*)/(.+)$", clean)
    if mission_with_payload and any(char.isdigit() for char in mission_with_payload.group(1)):
        return "仪器/" + mission_with_payload.group(1) + "/" + mission_with_payload.group(2)
    return clean


def _should_drop_pending_candidate(tag: str) -> bool:
    clean = _clean_markdown_tag_label(tag)
    if not clean:
        return True
    if clean in PENDING_DROP_EXACT_TAGS:
        return True
    if clean.startswith("事件/") and re.search(r"\d{4}(?:[-/年])|\d{1,2}月|\d{1,2}日", clean):
        return True
    if any(token in clean for token in ("地方时", "预条件", "多年统计", "时变", "时空过程")):
        return True
    if any(clean.startswith(prefix) for prefix in PENDING_DROP_PREFIXES):
        return True
    if clean.startswith("对象/任务设计/"):
        return True
    if any(keyword in clean for keyword in PENDING_DROP_KEYWORDS):
        return True
    return False


def _infer_pending_family_id(tag: str, category_id: str) -> str:
    clean = _clean_markdown_tag_label(tag)
    if not clean:
        return "solar_corona_heliosphere"
    if clean.startswith("指数/"):
        leaf = clean.split("/", 1)[1] if "/" in clean else clean
        if leaf in {"F107", "MgII"}:
            return "solar_corona_heliosphere"
        if leaf in {"PCN", "CPCP", "HP"}:
            return "it_coupling_extensions"
        return "magnetosphere_particles"
    if clean.startswith(("应用/", "对象/基础设施/", "对象/电网/", "对象/管道/", "对象/航天器电位", "对象/表面充电", "对象/腐蚀/", "对象/低轨/空间碎片")):
        return "applications_impacts"
    if clean.startswith(("方法/", "模型/", "工具/")):
        return "models_methods"
    if clean.startswith("数据/"):
        return "data_assets"
    if clean.startswith("仪器/"):
        return "instruments_missions_observations"
    if clean.startswith(("对象/其他行星/", "对象/木卫三/", "对象/月球/", "对象/火星/", "对象/金星/", "对象/水星/", "对象/土星/", "对象/木星/", "对象/卫星系统/")):
        return "planetary_environment"
    if clean.startswith(("对象/电离层/", "对象/低层大气/", "对象/低层大气波动/", "对象/大气潮汐/", "对象/重力波/", "对象/极区/", "对象/中低纬/", "对象/中纬度/", "对象/区域/", "事件/SSW", "特征/南北半球不对称性")):
        return "it_coupling_extensions"
    if clean.startswith(("对象/高能粒子", "对象/高能粒子与辐射带", "对象/粒子/", "对象/电子/", "对象/离子/", "对象/波粒相互作用", "对象/波动/", "对象/激波", "对象/等离子体", "对象/速度分布", "对象/相对论电子", "对象/辐射带", "对象/散射/", "对象/扩散/")):
        return "magnetosphere_particles"
    if clean.startswith(("对象/太阳/", "对象/太阳日冕/", "对象/日冕", "对象/日球层", "对象/太阳与日球层", "对象/太阳爆发", "对象/太阳耀斑", "对象/行星际环境", "对象/行星际环境驱动", "事件/太阳耀斑", "事件/CME", "事件/磁暴/CME", "事件/ICME", "对象/宇宙线", "对象/射电爆发", "对象/太阳活动")):
        return "solar_corona_heliosphere"
    if category_id == "instrument_data":
        return "instruments_missions_observations"
    if category_id == "model_method":
        return "models_methods"
    if category_id == "application_impact":
        return "applications_impacts"
    if category_id == "event_driver":
        return "solar_corona_heliosphere"
    return "it_coupling_extensions" if clean.startswith("对象/") else "solar_corona_heliosphere"


def govern_pending_candidate_tag(
    tag: str,
    *,
    formal_labels: set[str],
    focus_payload: dict,
    context_prefixes: tuple[str, ...] = (),
) -> PendingTagNormalizationResult:
    clean = _clean_markdown_tag_label(tag)
    if not clean:
        return PendingTagNormalizationResult("drop", "", "uncategorized", "solar_corona_heliosphere")
    resolved = resolve_existing_output_tag(clean, formal_labels)
    if resolved:
        category_id = _infer_category_id(resolved[0], focus_payload)
        family_id = _infer_pending_family_id(resolved[0], category_id)
        return PendingTagNormalizationResult("formal", clean, category_id, family_id, tuple(resolved))

    rewritten = _rewrite_pending_candidate_tag(clean, context_prefixes=context_prefixes)
    if not rewritten or _should_drop_pending_candidate(rewritten):
        return PendingTagNormalizationResult("drop", rewritten, "uncategorized", "solar_corona_heliosphere")

    resolved = resolve_existing_output_tag(rewritten, formal_labels)
    if resolved:
        category_id = _infer_category_id(resolved[0], focus_payload)
        family_id = _infer_pending_family_id(resolved[0], category_id)
        return PendingTagNormalizationResult("formal", rewritten, category_id, family_id, tuple(resolved))

    category_id = _infer_category_id(rewritten, focus_payload)
    family_id = _infer_pending_family_id(rewritten, category_id)
    return PendingTagNormalizationResult("pending", rewritten, category_id, family_id)


def ensure_tag_governance_files(
    root: Path | None = None,
    *,
    refresh_pending: bool = False,
    allow_refresh_call: bool = True,
) -> None:
    project = root or project_root()
    focus_path = focus_tags_config_path(project)
    if not focus_path.exists():
        return
    formal_path = formal_tags_markdown_path(project)
    if not formal_path.exists():
        payload = _load_json_file(focus_path, default={})
        formal_path.parent.mkdir(parents=True, exist_ok=True)
        formal_path.write_text(render_formal_tags_markdown(payload), encoding="utf-8")

    pending_path = pending_tags_json_path(project)
    if not pending_path.exists():
        migrated = _migrate_legacy_pending_tags(project)
        _write_json_if_changed(pending_path, migrated)
    if allow_refresh_call and (refresh_pending or not pending_tags_markdown_path(project).exists()):
        refresh_pending_tag_files(project)


def collect_manual_output_tag_usage(root: Path | None = None) -> dict[str, int]:
    project = root or project_root()
    manual_root = output_root(project) / "manual"
    counts: dict[str, int] = {}
    if not manual_root.exists():
        return counts
    for path in manual_root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        seen: list[str] = []
        for tag in extract_summary_tags(text):
            if tag and tag not in seen:
                seen.append(tag)
        for tag in seen:
            counts[tag] = int(counts.get(tag, 0) or 0) + 1
    return counts


def merge_manual_output_tags_into_formal(root: Path | None = None) -> list[str]:
    project = root or project_root()
    manual_tags = sorted(collect_manual_output_tag_usage(project))
    if not manual_tags:
        return []
    merged = merge_tags_into_formal(project, manual_tags)
    refresh_pending_tag_files(project)
    return merged


def merge_tags_into_formal(
    root: Path | None,
    tags: list[str],
    *,
    ai_summary_tags: set[str] | None = None,
) -> list[str]:
    project = root or project_root()
    ensure_tag_governance_files(project, refresh_pending=False)
    sync_formal_tags_to_focus_tags_json(project)
    focus_payload = _load_json_file(focus_tags_config_path(project), default={})
    formal_text = formal_tags_markdown_path(project).read_text(encoding="utf-8")
    ai_summary_labels = parse_formal_ai_summary_labels(formal_text, focus_payload)
    formal_labels_by_category = parse_formal_tags_markdown(formal_text, focus_payload)
    pending_payload = _load_json_file(pending_tags_json_path(project), default=_default_pending_payload())
    pending_tags = pending_payload.get("tags", {}) if isinstance(pending_payload, dict) and isinstance(pending_payload.get("tags"), dict) else {}
    formal_labels_by_category = _reassign_formal_labels_by_category(focus_payload, formal_labels_by_category, pending_tags)
    existing = {label for labels in formal_labels_by_category.values() for label in labels}
    merged: list[str] = []
    for tag in tags:
        canonical = str(tag or "").strip()
        if not canonical:
            continue
        category_id = _category_for_formal_tag(canonical, focus_payload, pending_tags)
        labels = formal_labels_by_category.setdefault(category_id, [])
        expanded = _expand_labels_with_ancestors([canonical])
        for label in expanded:
            if label not in labels:
                labels.append(label)
            if label not in existing:
                existing.add(label)
                merged.append(label)
    updated_payload = _sync_focus_tags_payload_from_formal(focus_payload, formal_labels_by_category)
    ai_labels_to_render = set(ai_summary_labels)
    ai_labels_to_render.update(str(item or "").strip() for item in (ai_summary_tags or set()) if str(item or "").strip())
    formal_tags_markdown_path(project).write_text(
        render_formal_tags_markdown_from_labels(
            updated_payload,
            formal_labels_by_category,
            ai_summary_labels=ai_labels_to_render,
        ),
        encoding="utf-8",
    )
    _write_json_if_changed(focus_tags_config_path(project), updated_payload)
    from .tags import clear_tag_taxonomy_cache
    from .tag_review import clear_tag_review_cache

    clear_tag_taxonomy_cache()
    clear_tag_review_cache()
    return merged


def sync_formal_tags_to_focus_tags_json(root: Path | None = None) -> bool:
    project = root or project_root()
    focus_path = focus_tags_config_path(project)
    if not focus_path.exists():
        return False
    formal_path = formal_tags_markdown_path(project)
    payload = _load_json_file(focus_path, default={})
    if not formal_path.exists():
        formal_path.parent.mkdir(parents=True, exist_ok=True)
        formal_path.write_text(render_formal_tags_markdown(payload), encoding="utf-8")
        return False

    parsed = parse_formal_tags_markdown(formal_path.read_text(encoding="utf-8"), payload)
    parsed = _reassign_formal_labels_by_category(payload, parsed, pending_tags={})
    updated = _sync_focus_tags_payload_from_formal(payload, parsed)
    changed = _write_json_if_changed(focus_path, updated)
    if changed:
        from .tags import clear_tag_taxonomy_cache
        from .tag_review import clear_tag_review_cache

        clear_tag_taxonomy_cache()
        clear_tag_review_cache()
    return changed


def sync_formal_tags_to_focus_tags_json_if_markdown_newer(root: Path | None = None) -> bool:
    project = root or project_root()
    focus_path = focus_tags_config_path(project)
    formal_path = formal_tags_markdown_path(project)
    if not focus_path.exists() or not formal_path.exists():
        return False
    try:
        if formal_path.stat().st_mtime_ns <= focus_path.stat().st_mtime_ns:
            return False
    except OSError:
        return False
    return sync_formal_tags_to_focus_tags_json(project)


def formal_tag_labels(root: Path | None = None) -> set[str]:
    project = root or project_root()
    sync_formal_tags_to_focus_tags_json_if_markdown_newer(project)
    payload = _load_json_file(focus_tags_config_path(project), default={})
    return {
        str(item.get("label", "")).strip()
        for item in payload.get("tags", [])
        if isinstance(item, dict) and str(item.get("label", "")).strip()
    }


def resolve_existing_output_tag(tag: str, formal_labels: set[str]) -> list[str] | None:
    clean = _clean_markdown_tag_label(tag)
    if not clean:
        return []
    if clean in formal_labels:
        return [clean]

    alias_targets = _existing_output_alias_targets(clean)
    if alias_targets and all(item in formal_labels for item in alias_targets):
        return alias_targets

    suffix_map = _build_formal_suffix_map(formal_labels)
    for suffix in _iter_tag_suffixes(clean):
        matches = sorted(set(suffix_map.get(suffix, [])))
        if len(matches) == 1:
            return matches
    return None


def reconcile_output_markdown_tags(
    base_dir: Path,
    *,
    formal_labels: set[str],
) -> OutputTagRewriteResult:
    scanned_files = 0
    modified_entries: list[OutputTagRewriteEntry] = []
    remaining_nonformal_counts: dict[str, int] = {}
    for path in sorted(base_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        scanned_files += 1
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        changed = False
        changes: list[tuple[str, tuple[str, ...]]] = []
        for index, line in enumerate(lines):
            if not line.startswith("- ") or "#" not in line:
                continue
            original_tags = extract_summary_tags(line)
            if not original_tags:
                continue
            rebuilt_tags: list[str] = []
            seen: set[str] = set()
            line_changed = False
            for original in original_tags:
                resolved = resolve_existing_output_tag(original, formal_labels)
                resolved_tags = resolved if resolved else [original]
                if tuple(resolved_tags) != (original,):
                    changes.append((original, tuple(resolved_tags)))
                    line_changed = True
                for item in resolved_tags:
                    canonical = _clean_markdown_tag_label(item)
                    if canonical and canonical not in seen:
                        seen.add(canonical)
                        rebuilt_tags.append(canonical)
            if line_changed:
                prefix = line.split("#", 1)[0].rstrip()
                tag_line = build_tag_line(rebuilt_tags)
                lines[index] = f"{prefix} {tag_line}".rstrip()
                changed = True
        updated_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        if changed:
            path.write_text(updated_text, encoding="utf-8")
        current_tags = extract_summary_tags(updated_text)
        remaining_nonformal = tuple(tag for tag in current_tags if tag not in formal_labels)
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
    return OutputTagRewriteResult(
        scanned_files=scanned_files,
        modified_entries=modified_entries,
        remaining_nonformal_counts=dict(sorted(remaining_nonformal_counts.items(), key=lambda item: (-item[1], item[0]))),
    )


def reconcile_auto_output_tags(root: Path | None = None) -> OutputTagRewriteResult:
    from .tag_review import reconcile_auto_output_tags_with_review

    return reconcile_auto_output_tags_with_review(root)


def load_pending_tags(root: Path | None = None) -> list[PendingTagEntry]:
    project = root or project_root()
    ensure_tag_governance_files(project)
    refresh_pending_tag_files(project)
    payload = _load_json_file(pending_tags_json_path(project), default=_default_pending_payload())
    raw = payload.get("tags", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        return []
    items: list[PendingTagEntry] = []
    for tag, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        items.append(
            PendingTagEntry(
                tag=str(tag),
                category=str(entry.get("category", "") or "uncategorized"),
                family=str(entry.get("family", "") or _infer_pending_family_id(str(tag), str(entry.get("category", "") or "uncategorized"))),
                count=int(entry.get("count", 0) or 0),
                first_seen=str(entry.get("first_seen", "") or ""),
                last_seen=str(entry.get("last_seen", "") or ""),
                contexts={str(key): int(value or 0) for key, value in (entry.get("contexts", {}) or {}).items()},
                selected=bool(entry.get("selected", False)),
                note=str(entry.get("note", "") or ""),
                usage_count=int(entry.get("usage_count", 0) or 0),
                usage_by_kind={str(key): int(value or 0) for key, value in (entry.get("usage_by_kind", {}) or {}).items()},
            )
        )
    items.sort(key=lambda item: (-item.usage_count, -item.count, item.tag))
    return items


def filter_tag_candidates(root: Path | None = None, *, min_count: int = 2, limit: int = 50) -> list[PendingTagEntry]:
    candidates = [item for item in load_pending_tags(root) if item.usage_count >= min_count or item.count >= min_count]
    if limit > 0:
        return candidates[:limit]
    return candidates


def candidate_log_path(root: Path | None = None) -> Path:
    return pending_tags_json_path(root)


def candidate_review_report_path(root: Path | None = None) -> Path:
    return pending_tags_markdown_path(root)


def render_tag_candidates_report(root: Path | None = None, *, min_count: int = 2, limit: int = 50) -> str:
    project = root or project_root()
    refresh_pending_tag_files(project)
    return pending_tags_markdown_path(project).read_text(encoding="utf-8")


def write_tag_candidates_report(root: Path | None = None, *, min_count: int = 2, limit: int = 50) -> Path:
    del min_count, limit
    project = root or project_root()
    refresh_pending_tag_files(project)
    return pending_tags_markdown_path(project)


def record_pending_tags(
    root: Path | None,
    tags: list[str],
    *,
    context: str = "",
    categories: dict[str, str] | None = None,
) -> None:
    project = root or project_root()
    ensure_tag_governance_files(project)
    focus_payload = _load_json_file(focus_tags_config_path(project), default={})
    formal_labels = {str(item.get("label", "")).strip() for item in focus_payload.get("tags", []) if str(item.get("label", "")).strip()}
    payload = _load_json_file(pending_tags_json_path(project), default=_default_pending_payload())
    payload.setdefault("tags", {})
    raw_tags = payload["tags"]
    if not isinstance(raw_tags, dict):
        raw_tags = {}
        payload["tags"] = raw_tags
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    changed = False
    for tag in tags:
        decision = govern_pending_candidate_tag(
            str(tag or "").strip(),
            formal_labels=formal_labels,
            focus_payload=focus_payload,
        )
        if decision.status != "pending":
            continue
        canonical = decision.tag
        entry = raw_tags.get(canonical)
        if not isinstance(entry, dict):
            entry = {
                "category": decision.category_id,
                "family": decision.family_id,
                "count": 0,
                "first_seen": now,
                "last_seen": now,
                "contexts": {},
                "selected": False,
                "note": "",
                "usage_count": 0,
                "usage_by_kind": {"article_summaries": 0, "deep_reads": 0},
            }
        entry["category"] = str(entry.get("category", "") or decision.category_id or (categories or {}).get(canonical) or _infer_category_id(canonical, focus_payload))
        entry["family"] = str(entry.get("family", "") or decision.family_id or _infer_pending_family_id(canonical, entry["category"]))
        entry["count"] = int(entry.get("count", 0) or 0) + 1
        entry.setdefault("first_seen", now)
        entry["last_seen"] = now
        contexts = entry.get("contexts")
        if not isinstance(contexts, dict):
            contexts = {}
        if context:
            contexts[context] = int(contexts.get(context, 0) or 0) + 1
        entry["contexts"] = contexts
        entry.setdefault("selected", False)
        entry.setdefault("note", "")
        entry.setdefault("usage_count", 0)
        entry.setdefault("usage_by_kind", {"article_summaries": 0, "deep_reads": 0})
        raw_tags[canonical] = entry
        changed = True
    if changed:
        _write_json_if_changed(pending_tags_json_path(project), payload)


def refresh_pending_tag_files(root: Path | None = None) -> Path:
    project = root or project_root()
    ensure_tag_governance_files(project, refresh_pending=False, allow_refresh_call=False)
    sync_formal_tags_to_focus_tags_json(project)
    focus_payload = _load_json_file(focus_tags_config_path(project), default={})
    payload = _load_json_file(pending_tags_json_path(project), default=_default_pending_payload())
    payload["version"] = 2
    payload["description"] = _default_pending_payload()["description"]
    payload.setdefault("tags", {})
    raw_tags = payload["tags"] if isinstance(payload.get("tags"), dict) else {}
    review_state = _parse_pending_tag_review_state(pending_tags_markdown_path(project))
    formal_labels = {str(item.get("label", "")).strip() for item in focus_payload.get("tags", []) if str(item.get("label", "")).strip()}
    usage_counts = collect_pending_tag_usage(project)

    normalized_registry: dict[str, dict] = {}
    for tag, entry in raw_tags.items():
        if not isinstance(entry, dict):
            entry = {}
        decision = govern_pending_candidate_tag(
            str(tag or "").strip(),
            formal_labels=formal_labels,
            focus_payload=focus_payload,
        )
        if decision.status != "pending":
            continue
        canonical = decision.tag
        bucket = normalized_registry.setdefault(
            canonical,
            {
                "category": decision.category_id,
                "family": decision.family_id,
                "count": 0,
                "first_seen": "",
                "last_seen": "",
                "contexts": {},
                "selected": False,
                "note": "",
                "usage_count": 0,
                "usage_by_kind": {"article_summaries": 0, "deep_reads": 0},
            },
        )
        bucket["category"] = decision.category_id
        bucket["family"] = decision.family_id
        bucket["count"] = int(bucket.get("count", 0) or 0) + int(entry.get("count", 0) or 0)
        bucket["first_seen"] = _earlier_timestamp(str(bucket.get("first_seen", "") or ""), str(entry.get("first_seen", "") or ""))
        bucket["last_seen"] = _later_timestamp(str(bucket.get("last_seen", "") or ""), str(entry.get("last_seen", "") or ""))
        bucket["contexts"] = _merge_count_maps(bucket.get("contexts", {}), entry.get("contexts", {}))
        preserved_state = review_state.get(canonical, review_state.get(str(tag or "").strip(), {}))
        bucket["selected"] = bool(preserved_state.get("selected", entry.get("selected", False)) or bucket.get("selected", False))
        bucket["note"] = str(preserved_state.get("note", "") or entry.get("note", "") or bucket.get("note", ""))

    for canonical, usage in usage_counts.items():
        decision = govern_pending_candidate_tag(
            canonical,
            formal_labels=formal_labels,
            focus_payload=focus_payload,
        )
        if decision.status != "pending":
            continue
        bucket = normalized_registry.setdefault(
            decision.tag,
            {
                "category": decision.category_id,
                "family": decision.family_id,
                "count": 0,
                "first_seen": "",
                "last_seen": "",
                "contexts": {},
                "selected": False,
                "note": "",
                "usage_count": 0,
                "usage_by_kind": {"article_summaries": 0, "deep_reads": 0},
            },
        )
        bucket["category"] = decision.category_id
        bucket["family"] = decision.family_id
        preserved_state = review_state.get(decision.tag, {})
        bucket["selected"] = bool(preserved_state.get("selected", bucket.get("selected", False)))
        bucket["note"] = str(preserved_state.get("note", "") or bucket.get("note", ""))
        bucket["usage_count"] = int(usage.get("count", 0) or 0)
        bucket["usage_by_kind"] = {
            "article_summaries": int((usage.get("by_kind", {}) or {}).get("article_summaries", 0) or 0),
            "deep_reads": int((usage.get("by_kind", {}) or {}).get("deep_reads", 0) or 0),
        }

    normalized: dict[str, dict] = {}
    for canonical, entry in normalized_registry.items():
        usage_count = int(entry.get("usage_count", 0) or 0)
        if usage_count <= 0:
            continue
        normalized[canonical] = entry
    payload["tags"] = normalized
    _write_json_if_changed(pending_tags_json_path(project), payload)
    markdown_path = pending_tags_markdown_path(project)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_pending_tags_markdown(payload, focus_payload), encoding="utf-8")
    return markdown_path


def promote_selected_pending_tags(root: Path | None = None) -> PendingTagPromotionResult:
    project = root or project_root()
    ensure_tag_governance_files(project)
    apply_result = apply_pending_tag_review_actions(project)
    refresh_pending_tag_files(project)
    return PendingTagPromotionResult(
        apply_result.promoted_tags,
        formal_tags_markdown_path(project),
        pending_tags_markdown_path(project),
        apply_result.protected_files,
    )


def collect_output_tag_usage(root: Path | None = None) -> dict[str, dict[str, object]]:
    project = root or project_root()
    counts: dict[str, dict[str, object]] = {}
    for kind, base in (
        ("article_summaries", article_summaries_root(project)),
        ("deep_reads", deep_reads_root(project)),
    ):
        if not base.exists():
            continue
        for path in base.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            seen = []
            for tag in extract_summary_tags(text):
                if tag not in seen:
                    seen.append(tag)
            for tag in seen:
                entry = counts.setdefault(tag, {"count": 0, "by_kind": {"article_summaries": 0, "deep_reads": 0}})
                entry["count"] = int(entry.get("count", 0) or 0) + 1
                by_kind = entry.get("by_kind")
                if not isinstance(by_kind, dict):
                    by_kind = {"article_summaries": 0, "deep_reads": 0}
                by_kind[kind] = int(by_kind.get(kind, 0) or 0) + 1
                entry["by_kind"] = by_kind
    return counts


def collect_pending_tag_usage(root: Path | None = None) -> dict[str, dict[str, object]]:
    project = root or project_root()
    focus_payload = _load_json_file(focus_tags_config_path(project), default={})
    formal_labels = formal_tag_labels(project)
    counts: dict[str, dict[str, object]] = {}
    for kind, base in (
        ("article_summaries", article_summaries_root(project)),
        ("deep_reads", deep_reads_root(project)),
    ):
        if not base.exists():
            continue
        for path in base.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            context_prefixes = _infer_pending_context_prefixes(title_text=path.stem, body_text=text)
            seen: set[str] = set()
            for raw_tag in extract_summary_tags(text):
                decision = govern_pending_candidate_tag(
                    raw_tag,
                    formal_labels=formal_labels,
                    focus_payload=focus_payload,
                    context_prefixes=context_prefixes,
                )
                if decision.status != "pending" or not decision.tag or decision.tag in seen:
                    continue
                seen.add(decision.tag)
            for tag in seen:
                entry = counts.setdefault(tag, {"count": 0, "by_kind": {"article_summaries": 0, "deep_reads": 0}})
                entry["count"] = int(entry.get("count", 0) or 0) + 1
                by_kind = entry.get("by_kind")
                if not isinstance(by_kind, dict):
                    by_kind = {"article_summaries": 0, "deep_reads": 0}
                by_kind[kind] = int(by_kind.get(kind, 0) or 0) + 1
                entry["by_kind"] = by_kind
    return counts


def _iter_auto_output_paths(project: Path) -> list[Path]:
    paths: list[Path] = []
    for base in (article_summaries_root(project), deep_reads_root(project)):
        if not base.exists():
            continue
        paths.extend(sorted(path for path in base.rglob("*.md") if not path.name.startswith(".")))
    return paths


def _review_note_requests_delete(note: str) -> bool:
    return str(note or "").strip().startswith("删除")


def _resolve_pending_review_target(decision: PendingTagReviewDecision) -> str:
    note = str(decision.note or "").strip()
    target = str(decision.current_tag or "").strip() or str(decision.original_tag or "").strip()
    if not note:
        return target
    explicit_target = _extract_pending_review_target_from_note(note)
    if explicit_target:
        return explicit_target
    changed_match = re.search(r"改成\s*[:：]?\s*(.+)$", note)
    if changed_match:
        return _clean_markdown_tag_label(changed_match.group(1))
    if "EIA" in note.upper():
        return "对象/电离层/EIA"
    if "电离层" in note and target.endswith("电子密度"):
        return "对象/电离层/电子密度"
    return target


def _apply_pending_review_to_outputs(
    project: Path,
    decisions: list[PendingTagReviewDecision],
) -> tuple[list[Path], list[OutputTagRewriteEntry]]:
    formal_labels = formal_tag_labels(project)
    remove_only_tags = {
        decision.original_tag
        for decision in decisions
        if decision.original_tag and _review_note_requests_delete(decision.note)
    }
    replacements: dict[str, tuple[str, ...]] = {}
    for decision in decisions:
        if not decision.original_tag:
            continue
        if decision.original_tag in remove_only_tags:
            replacements[decision.original_tag] = ()
            continue
        target = _resolve_pending_review_target(decision)
        if target and target != decision.original_tag:
            replacements[decision.original_tag] = (target,)

    protected_files: list[Path] = []
    rewritten_entries: list[OutputTagRewriteEntry] = []
    for path in _iter_auto_output_paths(project):
        text = path.read_text(encoding="utf-8")
        file_tags = extract_summary_tags(text)
        protected_delete_request = any(tag in remove_only_tags for tag in file_tags)
        if protected_delete_request:
            protected_files.append(path)
        lines = text.splitlines()
        changed = False
        changes: list[tuple[str, tuple[str, ...]]] = []
        for index, line in enumerate(lines):
            if not line.startswith("- ") or "#" not in line:
                continue
            original_tags = extract_summary_tags(line)
            if not original_tags:
                continue
            rebuilt_tags: list[str] = []
            seen: set[str] = set()
            line_changed = False
            for original in original_tags:
                replacement_tags = replacements.get(original, (original,))
                if tuple(replacement_tags) != (original,):
                    changes.append((original, tuple(replacement_tags)))
                    line_changed = True
                for item in replacement_tags:
                    canonical = _clean_markdown_tag_label(item)
                    if canonical and canonical not in seen:
                        seen.add(canonical)
                        rebuilt_tags.append(canonical)
            if line_changed:
                prefix = line.split("#", 1)[0].rstrip()
                lines[index] = f"{prefix} {build_tag_line(rebuilt_tags)}".rstrip()
                changed = True
        if changed:
            updated_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            path.write_text(updated_text, encoding="utf-8")
            rewritten_entries.append(
                OutputTagRewriteEntry(
                    path=path,
                    changes=_dedupe_change_pairs(changes),
                    remaining_nonformal=tuple(
                        tag for tag in extract_summary_tags(updated_text) if tag not in formal_labels
                    ),
                )
            )
    return protected_files, rewritten_entries


def apply_pending_tag_review_actions(root: Path | None = None) -> PendingTagReviewApplyResult:
    project = root or project_root()
    ensure_tag_governance_files(project, refresh_pending=False)
    sync_formal_tags_to_focus_tags_json(project)
    decisions = parse_pending_tag_review_decisions(project)
    protected_files, rewritten_entries = _apply_pending_review_to_outputs(project, decisions)
    _drop_pending_tags_after_review(
        project,
        {
            decision.original_tag
            for decision in decisions
            if decision.original_tag
            and (
                decision.selected
                or _review_note_requests_delete(decision.note)
                or _resolve_pending_review_target(decision) != decision.original_tag
            )
        },
    )
    refresh_pending_tag_files(project)
    formal_labels = formal_tag_labels(project)
    promote_targets: list[str] = []
    for decision in decisions:
        if not decision.selected or _review_note_requests_delete(decision.note):
            continue
        target_tag = _resolve_pending_review_target(decision)
        if not target_tag:
            continue
        resolved = resolve_existing_output_tag(target_tag, formal_labels)
        if target_tag in formal_labels or resolved:
            continue
        if target_tag not in promote_targets:
            promote_targets.append(target_tag)
    if promote_targets:
        merge_tags_into_formal(project, promote_targets, ai_summary_tags=set(promote_targets))
    refresh_pending_tag_files(project)
    return PendingTagReviewApplyResult(
        protected_files=protected_files,
        rewritten_entries=rewritten_entries,
        promoted_tags=promote_targets,
    )


def _drop_pending_tags_after_review(project: Path, tags: set[str]) -> None:
    if not tags:
        return
    pending_path = pending_tags_json_path(project)
    payload = _load_json_file(pending_path, default=_default_pending_payload())
    raw_tags = payload.get("tags", {}) if isinstance(payload.get("tags"), dict) else {}
    changed = False
    for tag in sorted(tags):
        if tag in raw_tags:
            raw_tags.pop(tag, None)
            changed = True
    if changed:
        payload["tags"] = raw_tags
        _write_json_if_changed(pending_path, payload)


def render_formal_tags_markdown(focus_payload: dict, *, ai_summary_labels: set[str] | None = None) -> str:
    category_map = _category_map(focus_payload)
    tags_by_category: dict[str, list[str]] = {}
    for item in focus_payload.get("tags", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        category = str(item.get("category", "")).strip() or "uncategorized"
        if label:
            tags_by_category.setdefault(category, []).append(label)
    return render_formal_tags_markdown_from_labels(
        focus_payload,
        tags_by_category,
        ai_summary_labels=ai_summary_labels,
    )


def render_formal_tags_markdown_from_labels(
    focus_payload: dict,
    labels_by_category: dict[str, list[str]],
    *,
    ai_summary_labels: set[str] | None = None,
) -> str:
    category_map = _category_map(focus_payload)
    lines = [
        FORMAL_TAGS_TITLE,
        "",
        "> 这份文件是正式 canonical tag 的人工审阅入口。",
        "> 手动修改这份 Markdown 后，程序会用它同步 `config/focus_tags.json` 中的正式标签集合。",
        "> `aliases`、`patterns`、`suppression_rules` 和 `tag_rules` 等机器规则仍保留在 JSON 中维护。",
        "",
    ]
    for category_id, category_label in category_map.items():
        category_tags = _expand_labels_with_ancestors(labels_by_category.get(category_id, []))
        if not category_tags:
            continue
        lines.append(f"## {category_label}")
        lines.extend(
            _render_tag_tree_lines(
                category_tags,
                checkbox_state={},
                usage_counts={},
                actual_tag_set=set(category_tags),
                ai_summary_labels=ai_summary_labels or set(),
                indent_unit="\t",
            )
        )
        lines.append("")
    if lines[-1] != "":
        lines.append("")
    return "\n".join(lines)


def render_pending_tags_markdown(pending_payload: dict, focus_payload: dict) -> str:
    tags_by_family: dict[str, list[tuple[str, int, int, str]]] = {}
    checkbox_state: dict[str, bool] = {}
    usage_counts: dict[str, int] = {}
    note_state: dict[str, str] = {}
    for tag, entry in (pending_payload.get("tags", {}) or {}).items():
        if not isinstance(entry, dict):
            continue
        canonical = str(tag or "").strip()
        usage_count = int(entry.get("usage_count", 0) or 0)
        runtime_count = int(entry.get("count", 0) or 0)
        family = str(entry.get("family", "") or "").strip() or _infer_pending_family_id(
            canonical,
            str(entry.get("category", "") or "uncategorized"),
        )
        category = str(entry.get("category", "") or "uncategorized")
        tags_by_family.setdefault(family, []).append((canonical, usage_count, runtime_count, category))
        checkbox_state[canonical] = bool(entry.get("selected", False))
        usage_counts[canonical] = usage_count
        note_state[canonical] = str(entry.get("note", "") or "")

    lines = [
        PENDING_TAGS_TITLE,
        "",
        "> 这份文件列出尚未进入正式体系、且仍真实存在于输出库中的预选标签。",
        "> 程序会先做前缀清洗、重复簇归并和低价值条目剔除，再把候选项放入下列审阅家族。",
        "> 勾选条目后，在设置页点击“标签转正”即可转入正式标签；转正完成后会自动从这里剔除。",
        "> 每个标签后的次数，只统计真实输出库中已有的文章总结和深度解读文件。",
        "",
    ]
    rendered_any = False
    for family in _pending_family_specs():
        raw_entries = tags_by_family.get(family.id, [])
        if not raw_entries:
            continue
        rendered_any = True
        category_tags = [item[0] for item in sorted(raw_entries, key=lambda item: (-item[1], -item[2], item[0]))]
        lines.append(f"## {family.title}")
        lines.extend(
            _render_pending_tag_lines(
                category_tags,
                checkbox_state=checkbox_state,
                usage_counts=usage_counts,
                note_state=note_state,
            )
        )
        lines.append("")
    if not rendered_any:
        lines.extend(
            [
                "当前没有待审核的预选标签。",
                "",
            ]
        )
    return "\n".join(lines)


def parse_formal_tags_markdown(markdown: str, focus_payload: dict) -> dict[str, list[str]]:
    category_label_to_id = _category_header_alias_map(focus_payload)
    category_order = [str(item.get("id", "")).strip() for item in focus_payload.get("categories", []) if str(item.get("id", "")).strip()]
    labels_by_category: dict[str, list[str]] = {item: [] for item in category_order}
    current_category: str | None = None
    stack: list[str] = []
    base_depth: int | None = None
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            continue
        if stripped.startswith("## "):
            label = stripped[3:].strip()
            current_category = _resolve_formal_category_header(label, category_label_to_id)
            stack = []
            base_depth = None
            continue
        match = MARKDOWN_BULLET_RE.match(raw_line)
        if not match or current_category is None:
            continue
        depth = _indent_depth(match.group("indent"))
        if base_depth is None:
            base_depth = depth
        relative_depth = max(depth - base_depth, 0)
        parent_depth = relative_depth
        while len(stack) > parent_depth:
            stack.pop()
        label_text = _clean_markdown_tag_label(match.group("label"))
        if label_text.endswith(AI_SUMMARY_SUFFIX):
            label_text = label_text[: -len(AI_SUMMARY_SUFFIX)].rstrip()
        is_group_only = label_text.endswith(GROUP_SUFFIX)
        if is_group_only:
            label_text = label_text[: -len(GROUP_SUFFIX)].rstrip()
        full_label = _resolve_full_label(stack, label_text)
        if full_label:
            if not is_group_only and full_label not in labels_by_category[current_category]:
                labels_by_category[current_category].append(full_label)
            stack.append(full_label)
    return labels_by_category


def parse_formal_ai_summary_labels(markdown: str, focus_payload: dict) -> set[str]:
    category_label_to_id = _category_header_alias_map(focus_payload)
    current_category: str | None = None
    stack: list[str] = []
    base_depth: int | None = None
    ai_labels: set[str] = set()
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        if stripped.startswith("## "):
            label = stripped[3:].strip()
            current_category = _resolve_formal_category_header(label, category_label_to_id)
            stack = []
            base_depth = None
            continue
        match = MARKDOWN_BULLET_RE.match(raw_line)
        if not match or current_category is None:
            continue
        depth = _indent_depth(match.group("indent"))
        if base_depth is None:
            base_depth = depth
        relative_depth = max(depth - base_depth, 0)
        parent_depth = relative_depth
        while len(stack) > parent_depth:
            stack.pop()
        label_text = _clean_markdown_tag_label(match.group("label"))
        is_ai_summary = label_text.endswith(AI_SUMMARY_SUFFIX)
        if is_ai_summary:
            label_text = label_text[: -len(AI_SUMMARY_SUFFIX)].rstrip()
        is_group_only = label_text.endswith(GROUP_SUFFIX)
        if is_group_only:
            label_text = label_text[: -len(GROUP_SUFFIX)].rstrip()
        full_label = _resolve_full_label(stack, label_text)
        if full_label and is_ai_summary and not is_group_only:
            ai_labels.add(full_label)
        if full_label:
            stack.append(full_label)
    return ai_labels


def _sync_focus_tags_payload_from_formal(focus_payload: dict, labels_by_category: dict[str, list[str]]) -> dict:
    payload = copy.deepcopy(focus_payload)
    labels_by_category = {key: _expand_labels_with_ancestors(value) for key, value in labels_by_category.items()}
    existing_tags = {
        str(item.get("label", "")).strip(): copy.deepcopy(item)
        for item in payload.get("tags", [])
        if isinstance(item, dict) and str(item.get("label", "")).strip()
    }
    used_ids = {str(item.get("id", "")).strip() for item in payload.get("tags", []) if isinstance(item, dict)}
    new_tags: list[dict] = []
    ordered_labels: list[str] = []
    for category in payload.get("categories", []):
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("id", "")).strip()
        if not category_id:
            continue
        for label in labels_by_category.get(category_id, []):
            clean_label = str(label or "").strip()
            if not clean_label or clean_label in ordered_labels:
                continue
            entry = existing_tags.get(clean_label)
            if entry is None:
                entry = {
                    "id": _unique_tag_id(clean_label, used_ids),
                    "label": clean_label,
                    "category": category_id,
                }
            entry["label"] = clean_label
            entry["category"] = category_id
            new_tags.append(entry)
            ordered_labels.append(clean_label)
    payload["tags"] = new_tags
    valid_labels = set(ordered_labels)
    suppression_rules = []
    for item in payload.get("suppression_rules", []):
        if not isinstance(item, dict):
            continue
        general = str(item.get("general", "")).strip()
        specific = str(item.get("specific", "")).strip()
        if general in valid_labels and specific in valid_labels:
            suppression_rules.append(item)
    payload["suppression_rules"] = suppression_rules
    tag_rules = payload.setdefault("tag_rules", {})
    if isinstance(tag_rules, dict):
        tag_rules.setdefault("pending_tags_path", "config/pending_tags.json")
        tag_rules.pop("candidate_log_path", None)
    return payload


def _migrate_legacy_pending_tags(project: Path) -> dict:
    focus_payload = _load_json_file(focus_tags_config_path(project), default={})
    formal_labels = formal_tag_labels(project)
    pending_path = project / LEGACY_PENDING_TAGS_PATH
    legacy = _load_json_file(pending_path, default={}) if pending_path.exists() else {}
    raw_candidates = legacy.get("candidates", {}) if isinstance(legacy, dict) else {}
    tags: dict[str, dict] = {}
    if isinstance(raw_candidates, dict):
        for tag, entry in raw_candidates.items():
            if not isinstance(entry, dict):
                continue
            canonical = str(tag or "").strip()
            if not canonical:
                continue
            decision = govern_pending_candidate_tag(canonical, formal_labels=formal_labels, focus_payload=focus_payload)
            if decision.status != "pending":
                continue
            tags[decision.tag] = {
                "category": decision.category_id,
                "family": decision.family_id,
                "count": int(entry.get("count", 0) or 0),
                "first_seen": str(entry.get("first_seen", "") or ""),
                "last_seen": str(entry.get("last_seen", "") or ""),
                "contexts": {str(key): int(value or 0) for key, value in (entry.get("contexts", {}) or {}).items()},
                "selected": False,
                "note": "",
                "usage_count": 0,
                "usage_by_kind": {"article_summaries": 0, "deep_reads": 0},
            }
    return {
        "version": 2,
        "description": "Pending tags normalized into review families after runtime outputs are cleaned and deduplicated.",
        "tags": tags,
    }


def _default_pending_payload() -> dict:
    return {
        "version": 2,
        "description": "Pending tags normalized into review families after runtime outputs are cleaned and deduplicated.",
        "tags": {},
    }


def _parse_pending_tag_review_state(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    checks: dict[str, dict[str, object]] = {}
    for entry in _parse_pending_markdown_entries(text, focus_payload=None):
        checks[str(entry["tag"])] = {
            "selected": bool(entry["selected"]),
            "note": str(entry.get("note", "") or ""),
            "family_id": str(entry.get("family_id", "") or ""),
        }
    return checks


def _parse_pending_review_body(body: str) -> tuple[str, int, str]:
    match = PENDING_REVIEW_BODY_RE.match(str(body or "").strip())
    if not match:
        cleaned = _clean_markdown_tag_label(body)
        return cleaned, 0, ""
    label = _clean_markdown_tag_label(match.group("label"))
    count = int(match.group("count") or 0)
    note = _normalize_pending_review_note(match.group("tail") or "")
    return label, count, note


def _parse_pending_markdown_entries(markdown: str, focus_payload: dict | None) -> list[dict[str, object]]:
    category_aliases = _category_header_alias_map(focus_payload or {"categories": []})
    current_family = ""
    entries: list[dict[str, object]] = []
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        if stripped.startswith("## "):
            label = stripped[3:].strip()
            current_family = _pending_family_id_from_header(label) or _resolve_formal_category_header(label, category_aliases) or ""
            continue
        match = MARKDOWN_BULLET_RE.match(raw_line)
        if not match or not match.group("checkbox"):
            continue
        tag, count, note = _parse_pending_review_body(match.group("label"))
        if not tag:
            continue
        entries.append(
            {
                "family_id": current_family,
                "tag": tag,
                "selected": (match.group("checkbox") or "").lower() == "[x]",
                "usage_count": count,
                "note": note,
            }
        )
    return entries


def _ordered_pending_tags_by_family(pending_payload: dict, focus_payload: dict) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for tag, entry in (pending_payload.get("tags", {}) or {}).items():
        if not isinstance(entry, dict):
            continue
        canonical = str(tag or "").strip()
        if not canonical:
            continue
        category = str(entry.get("category", "")).strip() or "uncategorized"
        family = str(entry.get("family", "")).strip() or _infer_pending_family_id(canonical, category)
        usage_count = int(entry.get("usage_count", 0) or 0)
        runtime_count = int(entry.get("count", 0) or 0)
        grouped.setdefault(family, []).append(
            {
                "tag": canonical,
                "usage_count": usage_count,
                "runtime_count": runtime_count,
                "category_id": category,
            }
        )
    ordered: dict[str, list[tuple[str, int, int]]] = {}
    for family in _pending_family_specs():
        raw_entries = grouped.get(family.id, [])
        if raw_entries:
            ordered[family.id] = sorted(raw_entries, key=lambda item: (-int(item["usage_count"]), -int(item["runtime_count"]), str(item["tag"])))
    for family_id, raw_entries in grouped.items():
        if family_id not in ordered:
            ordered[family_id] = sorted(raw_entries, key=lambda item: (-int(item["usage_count"]), -int(item["runtime_count"]), str(item["tag"])))
    return ordered


def parse_pending_tag_review_decisions(root: Path | None = None) -> list[PendingTagReviewDecision]:
    project = root or project_root()
    ensure_tag_governance_files(project, refresh_pending=False)
    focus_payload = _load_json_file(focus_tags_config_path(project), default={})
    pending_payload = _load_json_file(pending_tags_json_path(project), default=_default_pending_payload())
    formal_labels = formal_tag_labels(project)
    markdown = pending_tags_markdown_path(project).read_text(encoding="utf-8")
    actual_entries = _parse_pending_markdown_entries(markdown, focus_payload)
    expected_by_family = _ordered_pending_tags_by_family(pending_payload, focus_payload)
    actual_by_family: dict[str, list[dict[str, object]]] = {}
    for entry in actual_entries:
        actual_by_family.setdefault(str(entry["family_id"]), []).append(entry)

    decisions: list[PendingTagReviewDecision] = []
    family_ids = list(expected_by_family.keys())
    for family_id in family_ids:
        expected_entries = expected_by_family.get(family_id, [])
        actual_family_entries = actual_by_family.get(family_id, [])
        if len(actual_family_entries) != len(expected_entries):
            raise ValueError(
                f"pending_tags.md 中家族 {family_id} 的条目数与 pending_tags.json 不一致："
                f" markdown={len(actual_family_entries)} json={len(expected_entries)}"
            )
        matched_pairs = _match_pending_review_entries(expected_entries, actual_family_entries, formal_labels)
        for expected, actual in matched_pairs:
            original_tag = str(expected["tag"])
            decisions.append(
                PendingTagReviewDecision(
                    family_id=family_id,
                    category_id=str(expected.get("category_id", "") or "uncategorized"),
                    original_tag=original_tag,
                    current_tag=str(actual["tag"]),
                    selected=bool(actual["selected"]),
                    usage_count=int(actual["usage_count"]),
                    note=str(actual["note"]),
                )
            )
    return decisions


def _match_pending_review_entries(
    expected_entries: list[dict[str, object]],
    actual_entries: list[dict[str, object]],
    formal_labels: set[str],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    remaining_expected = list(expected_entries)
    remaining_actual = list(actual_entries)
    matched: list[tuple[dict[str, object], dict[str, object]]] = []

    def _take_match(predicate) -> None:
        nonlocal remaining_expected, remaining_actual, matched
        kept_actual: list[dict[str, object]] = []
        for actual in remaining_actual:
            candidates = [expected for expected in remaining_expected if predicate(expected, actual)]
            if len(candidates) == 1:
                expected = candidates[0]
                matched.append((expected, actual))
                remaining_expected.remove(expected)
            else:
                kept_actual.append(actual)
        remaining_actual = kept_actual

    _take_match(lambda expected, actual: str(expected["tag"]) == str(actual["tag"]))
    _take_match(lambda expected, actual: _pending_review_tags_related(str(expected["tag"]), str(actual["tag"]), formal_labels))
    _take_match(
        lambda expected, actual: int(expected["usage_count"]) == int(actual["usage_count"])
        and sum(1 for item in remaining_expected if int(item["usage_count"]) == int(actual["usage_count"])) == 1
    )

    for expected, actual in zip(remaining_expected, remaining_actual):
        matched.append((expected, actual))
    return matched


def _pending_review_tags_related(expected_tag: str, actual_tag: str, formal_labels: set[str]) -> bool:
    expected = str(expected_tag or "").strip()
    actual = str(actual_tag or "").strip()
    if not expected or not actual:
        return False
    if expected == actual:
        return True
    if actual.endswith(f"/{expected}") or expected.endswith(f"/{actual}"):
        return True
    if expected.split("/")[-1] == actual.split("/")[-1]:
        return True
    resolved = resolve_existing_output_tag(expected, formal_labels)
    return bool(resolved and actual in resolved)


def _render_pending_tag_lines(
    tags: list[str],
    *,
    checkbox_state: dict[str, bool],
    usage_counts: dict[str, int],
    note_state: dict[str, str],
) -> list[str]:
    lines: list[str] = []
    for tag in tags:
        canonical = str(tag or "").strip()
        if not canonical:
            continue
        checkbox = "[x]" if checkbox_state.get(canonical, False) else "[ ]"
        count = int(usage_counts.get(canonical, 0) or 0)
        note = str(note_state.get(canonical, "") or "").strip()
        note_suffix = f" - {note}" if note else ""
        lines.append(f"- {checkbox} {canonical} （{count}次）{note_suffix}")
    return lines


def _merge_output_rewrite_results(results: list[OutputTagRewriteResult]) -> OutputTagRewriteResult:
    scanned_files = sum(item.scanned_files for item in results)
    modified_entries: list[OutputTagRewriteEntry] = []
    remaining_nonformal_counts: dict[str, int] = {}
    for item in results:
        modified_entries.extend(item.modified_entries)
        for tag, count in item.remaining_nonformal_counts.items():
            remaining_nonformal_counts[tag] = int(remaining_nonformal_counts.get(tag, 0) or 0) + int(count or 0)
    return OutputTagRewriteResult(
        scanned_files=scanned_files,
        modified_entries=modified_entries,
        remaining_nonformal_counts=dict(sorted(remaining_nonformal_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
    )


def _dedupe_change_pairs(changes: list[tuple[str, tuple[str, ...]]]) -> list[tuple[str, tuple[str, ...]]]:
    deduped: list[tuple[str, tuple[str, ...]]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for change in changes:
        if change not in seen:
            seen.add(change)
            deduped.append(change)
    return deduped


def _normalize_pending_review_note(tail: str) -> str:
    note = str(tail or "").strip()
    if not note:
        return ""
    note = re.sub(r"^[\-—–:：\s]+", "", note).strip()
    return note


def _looks_like_tag_target(note: str) -> bool:
    clean = _clean_markdown_tag_label(note)
    if not clean or "/" not in clean:
        return False
    if any(char in clean for char in "？?，。,；;（）()[]"):
        return False
    return bool(re.fullmatch(r"[^/\s]+(?:/[^/\s]+)+", clean))


def _extract_pending_review_target_from_note(note: str) -> str:
    clean = _clean_markdown_tag_label(note)
    if not clean or _review_note_requests_delete(clean):
        return ""
    if _looks_like_tag_target(clean):
        return clean
    return ""


def _merge_count_maps(left: dict | object, right: dict | object) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in (left, right):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            merged[str(key)] = int(merged.get(str(key), 0) or 0) + int(value or 0)
    return merged


def _earlier_timestamp(left: str, right: str) -> str:
    candidates = [item for item in (str(left or "").strip(), str(right or "").strip()) if item]
    if not candidates:
        return ""
    return min(candidates)


def _later_timestamp(left: str, right: str) -> str:
    candidates = [item for item in (str(left or "").strip(), str(right or "").strip()) if item]
    if not candidates:
        return ""
    return max(candidates)


def _existing_output_alias_targets(tag: str) -> list[str] | None:
    clean = _clean_markdown_tag_label(tag)
    if not clean:
        return None
    direct = EXISTING_OUTPUT_TAG_ALIAS_MAP.get(clean)
    if direct:
        return list(direct)
    normalized = unicodedata.normalize("NFKC", clean)
    for key, value in EXISTING_OUTPUT_TAG_ALIAS_MAP.items():
        if unicodedata.normalize("NFKC", key) == normalized:
            return list(value)
    return None


def _build_formal_suffix_map(formal_labels: set[str]) -> dict[str, list[str]]:
    suffix_map: dict[str, set[str]] = {}
    for raw in formal_labels:
        label = _clean_markdown_tag_label(raw)
        if not label:
            continue
        parts = [part for part in label.split("/") if part]
        for start in range(len(parts)):
            suffix = "/".join(parts[start:])
            suffix_map.setdefault(suffix, set()).add(label)
    return {key: sorted(value) for key, value in suffix_map.items()}


def _iter_tag_suffixes(tag: str) -> list[str]:
    clean = _clean_markdown_tag_label(tag)
    if not clean:
        return []
    parts = [part for part in clean.split("/") if part]
    return ["/".join(parts[index:]) for index in range(len(parts))]


def _render_tag_tree_lines(
    tags: list[str],
    *,
    checkbox_state: dict[str, bool],
    usage_counts: dict[str, int],
    actual_tag_set: set[str],
    checkbox_mode: bool = False,
    ai_summary_labels: set[str] | None = None,
    indent_unit: str = "  ",
) -> list[str]:
    roots: dict[str, _TreeNode] = {}
    for tag in tags:
        parts = [part for part in str(tag).split("/") if part]
        if not parts:
            continue
        full = parts[0]
        node = roots.setdefault(parts[0], _TreeNode(parts[0], full))
        if tag == full:
            node.is_actual = True
            node.count = int(usage_counts.get(tag, 0) or 0)
            node.checked = bool(checkbox_state.get(tag, False))
        current = node
        current_full = parts[0]
        for part in parts[1:]:
            current_full = f"{current_full}/{part}"
            child = current.children.setdefault(part, _TreeNode(part, current_full))
            if current_full in actual_tag_set:
                child.is_actual = True
                child.count = int(usage_counts.get(current_full, 0) or 0)
                child.checked = bool(checkbox_state.get(current_full, False))
            current = child
    lines: list[str] = []
    for node in roots.values():
        _append_tree_lines(
            lines,
            node,
            depth=0,
            checkbox_mode=checkbox_mode,
            ai_summary_labels=ai_summary_labels or set(),
            indent_unit=indent_unit,
        )
    return lines


def _append_tree_lines(
    lines: list[str],
    node: _TreeNode,
    *,
    depth: int,
    checkbox_mode: bool,
    ai_summary_labels: set[str],
    indent_unit: str,
) -> None:
    indent = indent_unit * depth
    suffix = AI_SUMMARY_SUFFIX if node.full_label in ai_summary_labels else ""
    if checkbox_mode and node.is_actual:
        count_suffix = f"（{node.count}次）"
        checkbox = "[x]" if node.checked else "[ ]"
        lines.append(f"{indent}- {checkbox} {node.name}{suffix} {count_suffix}")
    elif node.is_actual:
        lines.append(f"{indent}- {node.name}{suffix}")
    else:
        lines.append(f"{indent}- {node.name}{GROUP_SUFFIX}")
    for child in node.children.values():
        _append_tree_lines(
            lines,
            child,
            depth=depth + 1,
            checkbox_mode=checkbox_mode,
            ai_summary_labels=ai_summary_labels,
            indent_unit=indent_unit,
        )


def _resolve_full_label(stack: list[str], label_text: str) -> str:
    cleaned = str(label_text or "").strip().strip("`")
    if not cleaned:
        return ""
    if "/" in cleaned or not stack:
        return cleaned
    return f"{stack[-1]}/{cleaned}"


def _indent_depth(indent: str) -> int:
    raw = str(indent or "")
    if not raw:
        return 0
    if "\t" in raw:
        return max(0, len(raw.expandtabs(4)) // 4)
    width = len(raw)
    return width // 2


def _clean_markdown_tag_label(label: str) -> str:
    text = str(label or "").strip().strip("`")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _expand_labels_with_ancestors(labels: list[str]) -> list[str]:
    ordered: list[str] = []
    for raw in labels:
        label = str(raw or "").strip()
        if not label:
            continue
        parts = [part for part in label.split("/") if part]
        prefix: list[str] = []
        for part in parts:
            prefix.append(part)
            current = "/".join(prefix)
            if current not in ordered:
                ordered.append(current)
    return ordered


def _category_for_formal_tag(tag: str, focus_payload: dict, pending_tags: dict[str, dict]) -> str:
    if "/" in tag:
        parts = [part for part in tag.split("/") if part]
        for index in range(len(parts) - 1, 0, -1):
            parent = "/".join(parts[:index])
            parent_category = _infer_category_id(parent, focus_payload)
            if parent_category:
                return parent_category
    entry = pending_tags.get(tag)
    if isinstance(entry, dict):
        category = str(entry.get("category", "") or "").strip()
        if category:
            return category
    return _infer_category_id(tag, focus_payload)


def _category_map(focus_payload: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in focus_payload.get("categories", []):
        if not isinstance(item, dict):
            continue
        category_id = str(item.get("id", "")).strip()
        label = str(item.get("label", "")).strip()
        if category_id and label:
            mapping[category_id] = label
    mapping.setdefault("uncategorized", "未分类")
    return mapping


def _category_header_alias_map(focus_payload: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in focus_payload.get("categories", []):
        if not isinstance(item, dict):
            continue
        category_id = str(item.get("id", "")).strip()
        label = str(item.get("label", "")).strip()
        if not category_id or not label:
            continue
        aliases = {
            label,
            label.replace(" / ", "/"),
            label.replace("/", " / "),
        }
        if " / " in label:
            aliases.add(label.split(" / ", 1)[0].strip())
        elif "/" in label:
            aliases.add(label.split("/", 1)[0].strip())
        for alias in aliases:
            clean = str(alias or "").strip()
            if clean:
                mapping[clean] = category_id
    return mapping


def _resolve_formal_category_header(label: str, alias_map: dict[str, str]) -> str | None:
    clean = str(label or "").strip()
    if not clean:
        return None
    direct = alias_map.get(clean)
    if direct:
        return direct
    stripped = re.sub(r"标签$", "", clean).strip()
    if stripped and stripped != clean:
        direct = alias_map.get(stripped)
        if direct:
            return direct
    for separator in ("与", "和", "、"):
        if separator not in clean:
            continue
        parts = [part.strip() for part in clean.split(separator) if part.strip()]
        for part in parts:
            direct = alias_map.get(part)
            if direct:
                return direct
            simplified = re.sub(r"标签$", "", part).strip()
            if simplified and simplified != part:
                direct = alias_map.get(simplified)
                if direct:
                    return direct
    return None


def _infer_category_id(tag: str, focus_payload: dict) -> str:
    prefix = tag.split("/", 1)[0]
    if prefix in DEFAULT_CATEGORY_PREFIXES:
        return DEFAULT_CATEGORY_PREFIXES[prefix]
    for item in focus_payload.get("tags", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("label", "")).strip() == tag:
            return str(item.get("category", "")).strip() or "research_object"
    if tag in {"综述", "Todo", "重要", "展望", "可做", "科学思考"}:
        return "status"
    if any(keyword in tag for keyword in ("仪器", "卫星", "探测器", "台站", "雷达", "气辉仪", "磁强计", "GNSS", "FPI", "SuperDARN")):
        return "instrument_data"
    if any(keyword in tag for keyword in ("模型", "建模", "模拟", "统计", "学习", "分析", "反演", "方法", "算法", "数据同化", "误差", "工具")):
        return "model_method"
    if any(keyword in tag for keyword in ("磁暴", "亚暴", "激波", "SSW", "太阳风", "CME", "ICME", "SEP", "耀斑", "射电暴", "太空台风", "Space-X")):
        return "event_driver"
    if any(keyword in tag for keyword in ("指数", "IMF", "Dst", "SYM-H", "AE", "AL", "AU", "Ap", "F107", "ROTI", "PCN", "MgII")):
        return "index_control"
    if any(keyword in tag for keyword in ("影响", "预测", "预报", "衰减")):
        return "application_impact"
    return "research_object"


def _reassign_formal_labels_by_category(
    focus_payload: dict,
    labels_by_category: dict[str, list[str]],
    pending_tags: dict[str, dict],
) -> dict[str, list[str]]:
    reassigned: dict[str, list[str]] = {}
    seen: set[str] = set()
    for labels in labels_by_category.values():
        for label in labels:
            canonical = str(label or "").strip()
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            category_id = _category_for_formal_tag(canonical, focus_payload, pending_tags)
            reassigned.setdefault(category_id, []).append(canonical)
    return reassigned


def _unique_tag_id(label: str, used_ids: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", str(label).strip().lower())
    base = base.strip("_") or "tag"
    candidate = base
    index = 2
    while candidate in used_ids:
        candidate = f"{base}_{index}"
        index += 1
    used_ids.add(candidate)
    return candidate


def _load_json_file(path: Path, *, default):
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(default)


def _write_json_if_changed(path: Path, payload: dict) -> bool:
    normalized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == normalized:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalized, encoding="utf-8")
    return True
