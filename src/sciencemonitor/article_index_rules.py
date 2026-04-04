from __future__ import annotations

import re
import unicodedata
from pathlib import Path


WIKILINK_RE = re.compile(r"(!)?\[\[(.+?)(?:\|([^\]]+))?\]\]")
OTHER_PLANET_TAG_RE = re.compile(r"(?<!\w)#其他行星/[^\s#]+")
DISPLAY_STATUS_SUFFIX_RE = re.compile(r"\s*-\s*(重要|Todo|TODO|待读|待读|待整理|可做)$")

PLANETARY_ROOT_PAGE = "6 - 其他行星"
PLANETARY_FOCUS_PAGES = {"7 - 太阳与日球层", "8 - 波粒相互作用", "9 - 高能粒子与辐射带"}
EARTH_SECTION_PREFIXES = ("1", "2", "3", "4")

INDEX_TREE: list[tuple[str, list]] = [
    ("1 - 空间环境", ["1.1 - 行星际磁场影响", "1.2 - 空间环境指数", "1.3 - 应用"]),
    (
        "2 - 热层电离层耦合系统",
        [
            "2.1 - 综述",
            "2.2 - 热层数据",
            "2.3 - 热层建模",
            "2.4 - 空间天气事件的影响",
            "2.5 - 太阳辐射影响",
            "2.6 - 磁暴",
            "2.7 - TAD与TID",
            "2.8 - 耀斑",
            "2.9 - EMA & ETA",
            ("2.10 - 经度结构", ["2.10.1 - 四波结构", "2.10.2 - 经度差异", "2.10.3 - X-Pattern"]),
            "2.11 - 赤道电场",
            "2.12 - 电动力学",
            "2.13 - 极尖区密度小尺度特征",
            "2.14 - 长期趋势",
            "2.15 - 赤道超旋",
            "2.16 - 极光",
            "2.17 - 南北半球差异",
            "2.18 - Day-to-Day",
            "2.19 - 全球同步响应",
            "2.20 - 极区粒子沉降",
            "2.21 - 伺服理论",
            "2.22 - 潮汐",
            "2.23 - 热层风",
            "2.24 - 极区对流",
            "2.25 - CIR",
            "2.26 - 热层中小尺度结构",
        ],
    ),
    ("3 - 临近空间", ["3.1 - 行星波"]),
    ("4 - 磁层", ["4.1 - 磁尾", "4.2 - 磁重联", "4.3 - 磁层-电离层-热层耦合", "4.4 - 磁层顶"]),
    ("5 - 图书", []),
    (
        PLANETARY_ROOT_PAGE,
        [
            "6.1 - 月球",
            "6.2 - 水星",
            "6.3 - 金星",
            ("6.4 - 火星", ["6.4.1 - 行星际环境的影响"]),
            "6.5 - 木星",
            "6.6 - 土星",
            "6.7 - 天王星",
            "6.8 - 海王星",
            "6.9 - 行星综合",
        ],
    ),
    ("7 - 太阳与日球层", []),
    ("8 - 波粒相互作用", []),
    ("9 - 高能粒子与辐射带", []),
    ("10 - 科学趣闻", []),
]

LEGACY_PAGE_RENAMES = {
    "6 - 火星": "6.4 - 火星",
    "6.1 - 行星际环境的影响": "6.4.1 - 行星际环境的影响",
    "7 - 科学趣闻": "10 - 科学趣闻",
    "太阳与日球层": "7 - 太阳与日球层",
    "波粒相互作用": "8 - 波粒相互作用",
    "高能粒子与辐射带": "9 - 高能粒子与辐射带",
    "行星空间环境": "6.9 - 行星综合",
}

PLANET_PAGE_MAP = {
    "月球": "6.1 - 月球",
    "水星": "6.2 - 水星",
    "金星": "6.3 - 金星",
    "火星": "6.4 - 火星",
    "木星": "6.5 - 木星",
    "土星": "6.6 - 土星",
    "天王星": "6.7 - 天王星",
    "海王星": "6.8 - 海王星",
    "行星综合": "6.9 - 行星综合",
}

PLANET_TAG_MAP = {planet: f"其他行星/{planet}" for planet in PLANET_PAGE_MAP}
PLANETARY_PAGE_NAMES = set(PLANET_PAGE_MAP.values()) | {"6.4.1 - 行星际环境的影响"}

PLANET_KEYWORDS = {
    "月球": ["研究星球/月球", " lunar ", " moon ", "月球", "danuri", "kplo", "chang’e", "chang'e"],
    "水星": ["研究星球/水星", " mercury ", " mercurian ", "水星"],
    "金星": ["研究星球/金星", " venus ", " venusian ", "金星"],
    "火星": ["研究星球/火星", " mars ", " martian ", "火星", "nozomi"],
    "木星": ["研究星球/木星", " jupiter ", " jovian ", "木星", "ganymede", "木卫三", "europa", "木卫二"],
    "土星": ["研究星球/土星", " saturn ", " saturnian ", "土星", "titan", "土卫六", "enceladus", "土卫二"],
    "天王星": ["研究星球/天王星", " uranus ", " uranian ", "天王星"],
    "海王星": ["研究星球/海王星", " neptune ", " neptunian ", "海王星"],
}

PLANETARY_GENERIC_KEYWORDS = ["研究星球/行星综合", "多行星", "multi-planet", "multi planet", "行星比较", "行星综合"]

KEYWORD_PAGE_RULES: list[tuple[str, list[str]]] = [
    ("9 - 高能粒子与辐射带", ["radiation belt", "辐射带", "solar energetic particle", "太阳高能粒子", "gcr", "energetic particle", "高能粒子", "俘获电子", "俘获质子"]),
    ("8 - 波粒相互作用", ["wave-particle", "波粒相互作用", "chorus", "whistler", "ulf wave", "electron conic"]),
    ("7 - 太阳与日球层", ["solar wind", "太阳风", "interplanetary", "行星际", "heliosphere", "日球层", "icme", "cme"]),
    ("2.20 - 极区粒子沉降", ["电子沉降", "粒子沉降", "electron precipitation", "particle precipitation", "nitric oxide", "no cooling"]),
    ("2.16 - 极光", ["极光", "aurora", "auroral oval", "pulsating aurora"]),
    ("2.24 - 极区对流", ["极区对流", "polar convection", "cross polar cap potential", "cpcp", "polar cap convection", "hmb"]),
    ("2.23 - 热层风", ["热层风", "thermospheric wind", "neutral wind", "zonal wind", "meridional wind", "vertical wind"]),
    ("2.22 - 潮汐", ["潮汐", "tide", "tidal"]),
    ("2.7 - TAD与TID", ["tad", "tid", "traveling atmospheric disturbance", "traveling ionospheric disturbance", "mstid"]),
    ("2.9 - EMA & ETA", ["equatorial ionization anomaly", "赤道电离异常", "equatorial mass density anomaly", "equatorial thermosphere anomaly", "赤道质量密度异常", "赤道热层异常", "喷泉", "fountain"]),
    ("2.10.3 - X-Pattern", ["x-pattern"]),
    ("2.10.2 - 经度差异", ["经度", "longitude", "longitudinal", "sector"]),
    ("2.11 - 赤道电场", ["赤道电场", "equatorial electric field", "vertical drift", "prompt penetration", "e×b drift"]),
    ("2.12 - 电动力学", ["电动力学", "electrodynamic", "electric field", "plasma drift", "fac", "field aligned current"]),
    ("2.17 - 南北半球差异", ["南北半球", "hemispheric", "north-south", "asymmetry"]),
    ("2.18 - Day-to-Day", ["day-to-day", "day to day", "quiet-time variability"]),
    ("2.25 - CIR", ["corotating", "cir", "high-speed stream", "coronal hole"]),
    ("2.6 - 磁暴", ["磁暴", "geomagnetic storm", "storm-time", "gannon storm", "superstorm"]),
    ("2.8 - 耀斑", ["solar flare", "耀斑", "soft x-ray flare"]),
    ("2.5 - 太阳辐射影响", ["solar irradiance", "euv", "solar radiation", "eclipse", "x-ray"]),
    ("4.2 - 磁重联", ["磁重联", "reconnection", "parallel electric field", "bbf"]),
    ("4.4 - 磁层顶", ["magnetopause", "磁层顶", "magnetosheath", "bow shock", "kelvin-helmholtz", "kh vortex"]),
    ("4.1 - 磁尾", ["magnetotail", "磁尾", "plasma sheet", "tail current sheet"]),
    ("4.3 - 磁层-电离层-热层耦合", ["磁层-电离层-热层耦合", "substorm current wedge", "field aligned current", "ionosphere-thermosphere coupling"]),
    ("3.1 - 行星波", ["planetary wave", "gravity wave", "secondary gravity wave", "ssw"]),
    ("1.2 - 空间环境指数", ["dst", "sym-h", "kp", "ae", "au", "al"]),
    ("1.3 - 应用", ["satellite drag", "轨道", "operational", "forecast", "prediction", "业务化"]),
    ("1.1 - 行星际磁场影响", ["imf", "solar wind", "interplanetary", "icme", "cme", "heliosphere"]),
]

TOPIC_FALLBACK_PAGES = {
    "行星际环境驱动": "1.1 - 行星际磁场影响",
    "空间天气": "2.4 - 空间天气事件的影响",
    "电离层": "2 - 热层电离层耦合系统",
    "热层": "2 - 热层电离层耦合系统",
    "低层大气波动上传": "3 - 临近空间",
    "磁层": "4 - 磁层",
    "磁层-电离层-热层耦合": "4.3 - 磁层-电离层-热层耦合",
    "太阳与日球层": "7 - 太阳与日球层",
    "波粒相互作用": "8 - 波粒相互作用",
    "高能粒子与辐射带": "9 - 高能粒子与辐射带",
    "行星空间环境": "6.9 - 行星综合",
}

PARENT_PAGE_RULES = {
    "2 - 热层电离层耦合系统": "2.",
    "4 - 磁层": "4.",
    "3 - 临近空间": "3.",
    PLANETARY_ROOT_PAGE: "6.",
    "6.4 - 火星": "6.4.",
}


def detect_other_planet(note_title: str, text: str) -> str | None:
    haystack = build_planet_detection_haystack(note_title, text)
    matches = []
    for planet, keywords in PLANET_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            matches.append(planet)
    matches = dedupe(matches)
    if len(matches) > 1:
        return "行星综合"
    if len(matches) == 1:
        return matches[0]
    if any(keyword.lower() in haystack for keyword in PLANETARY_GENERIC_KEYWORDS):
        return "行星综合"
    return None


def infer_planetary_pages(note_title: str, text: str, planet: str) -> list[str]:
    haystack = normalize_haystack(f"{note_title}\n{text}")
    pages = [PLANET_PAGE_MAP[planet]]

    if planet == "火星" and any(keyword in haystack for keyword in ["interplanetary", "行星际", "solar wind", "太阳风"]):
        pages.append("6.4.1 - 行星际环境的影响")
    if any(keyword.lower() in haystack for keyword in ["radiation belt", "辐射带", "solar energetic particle", "太阳高能粒子", "gcr", "高能粒子"]):
        pages.append("9 - 高能粒子与辐射带")
    if any(keyword.lower() in haystack for keyword in ["wave-particle", "波粒相互作用", "chorus", "whistler", "ulf wave", "electron conic"]):
        pages.append("8 - 波粒相互作用")
    if any(keyword.lower() in haystack for keyword in ["solar wind", "太阳风", "interplanetary", "行星际", "heliosphere", "日球层", "icme", "cme"]):
        pages.append("7 - 太阳与日球层")
    if planet == "行星综合":
        pages.append("6.9 - 行星综合")

    return dedupe(pages)[:3]


def prune_parent_pages(page_names: list[str]) -> list[str]:
    refined = list(page_names)
    for parent, prefix in PARENT_PAGE_RULES.items():
        if parent in refined and any(item != parent and item.startswith(prefix) for item in refined):
            refined.remove(parent)
    return refined


def is_earth_specific_page(page_name: str) -> bool:
    return page_name.split(" - ", 1)[0].split(".", 1)[0] in EARTH_SECTION_PREFIXES


def build_display_alias(target: str, alias: str | None) -> str | None:
    if "/" not in target and alias is None:
        return None
    label = alias or link_stem(target)
    return prettify_display_label(label)


def prettify_display_label(label: str) -> str:
    cleaned = DISPLAY_STATUS_SUFFIX_RE.sub("", label.strip())
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def build_planet_detection_haystack(note_title: str, text: str) -> str:
    selected = [note_title]
    kept = 0
    for raw_line in text.replace("\x00", "").splitlines():
        line = raw_line.strip()
        if not line or line == "----":
            continue
        if line.startswith("记录时间戳"):
            break
        if "「补充信息」" in line:
            break
        line = OTHER_PLANET_TAG_RE.sub("", line)
        line = re.sub(r"\[\[[^\]]+\]\]", " ", line)
        selected.append(line)
        kept += 1
        if kept >= 4:
            break
    return normalize_haystack("\n".join(selected))


def normalize_haystack(text: str) -> str:
    compact = re.sub(r"\s+", " ", text or "")
    return f" {compact.lower()} "


def normalize_asset_lookup_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").lower()
    normalized = (
        normalized.replace("–", "-")
        .replace("—", "-")
        .replace("‐", "-")
        .replace("‑", "-")
        .replace("−", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("‘", "'")
        .replace("[r-qucik]", "[r-quick]")
        .replace("_withmarginnotes", "")
        .replace("withmarginnotes", "")
        .replace("[", "")
        .replace("]", "")
    )
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s+\.", ".", normalized)
    return normalized.strip()


def normalize_doi(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower().rstrip(").,;")


def extract_year(text: str) -> int:
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return int(match.group(0)) if match else 9999


def extract_year_from_link(link: str) -> int:
    match = WIKILINK_RE.search(link)
    if not match:
        return 9999
    alias = match.group(3) or link_stem(match.group(2))
    return extract_year(alias)


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item and item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def link_stem(target: str) -> str:
    name = Path(target).name
    return name[:-3] if name.lower().endswith(".md") else name
