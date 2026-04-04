from __future__ import annotations

import re
from pathlib import Path


DEEP_READ_TEMPLATE_VAR_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
REQUIRED_DEEP_READ_HEADINGS = [
    "# 论文深度阅读报告",
    "## 论文信息",
    "### 一句话总述",
    "## 论文详解",
    "### 为什么做",
    "### 如何做",
    "### 关键结果",
    "### 新意与贡献",
    "### 局限性",
    "### 可复现性",
    "### 与已有工作的关系",
    "## 总结",
    "### 最终结论",
    "### 补充信息",
]
DEEP_READ_TEMPLATE_REQUIRED_VARS = {
    "entry_line",
    "apa_citation",
    "title",
    "authors",
    "journal",
    "year",
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
    "timestamp",
}
LEGACY_DEEP_READ_PATTERNS = [
    (r"^文件名：", "正文顶部不应包含文件名行"),
    (r"^##\s+Research question$", "不应继续使用旧版英文标题 Research question"),
    (r"^##\s+Paper type$", "不应继续使用旧版英文标题 Paper type"),
    (r"^##\s+Core claims$", "不应继续使用旧版英文标题 Core claims"),
    (r"^##\s+Method summary$", "不应继续使用旧版英文标题 Method summary"),
    (r"^##\s+Evidence assessment$", "不应继续使用旧版英文标题 Evidence assessment"),
    (r"^##\s+Reproducibility$", "不应继续使用旧版英文标题 Reproducibility"),
    (r"^##\s+Limitations and Hidden Assumptions$", "不应继续使用旧版英文标题 Limitations and Hidden Assumptions"),
    (r"^##\s+Related Work and Novelty$", "不应继续使用旧版英文标题 Related Work and Novelty"),
    (r"^##\s+Practical Takeaway$", "不应继续使用旧版英文标题 Practical Takeaway"),
    (r"^##\s+Confidence Level$", "不应继续使用旧版英文标题 Confidence Level"),
    (r"^##\s+标签（Tags）$", "不应继续使用旧版标签章节"),
    (r"目录归档建议", "不应继续输出目录归档建议区块"),
    (r"证据范围", "不应继续把证据范围作为正式报告区块"),
]
DEEP_READ_REVIEW_MAX_PASSES = 3

DEEP_READ_TEXT_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bday-to-day thermosphere variability\b", "热层日际变化"),
    (r"\brecurrent geomagnetic disturbances\b", "重复性地磁扰动"),
    (r"\bablation experiments?\b", "消融实验"),
    (r"\bablation\b", "消融"),
    (r"\bcontrolled simulations?\b", "受控实验"),
    (r"\bbenchmark(?:ing)?\b", "基线对照"),
    (r"\bback-of-envelope\b", "量级估算"),
    (r"\bdirect causal evidence\b", "直接因果证据"),
    (r"\boperational\b", "业务化"),
    (r"\bpaper type\b", "论文类型"),
    (r"\bresearch question\b", "研究问题"),
    (r"\bcore claims?\b", "核心主张"),
    (r"\bmethod summary\b", "方法概述"),
    (r"\bsupporting evidence\b", "支撑证据"),
    (r"\bevidence quality\b", "证据强度"),
    (r"\bverdict\b", "判断"),
    (r"\bdata or sample\b", "数据或样本"),
    (r"\bscope claim\b", "外推结论"),
    (r"\bsecondary claims?\b", "次要结论"),
    (r"\bprimary claim\b", "核心结论"),
    (r"\bcomparator\b", "对照"),
    (r"\bevaluation target\b", "评估目标"),
    (r"\bthermosphere-ionosphere dynamical coupling\b", "热层-电离层动力耦合"),
    (r"\bthermospheric wind uplift\b", "热层风抬升"),
    (r"\bdownward plasma transport\b", "向下等离子体输运"),
    (r"\btopside ionosphere\b", "顶侧电离层"),
    (r"\bconjugate hemisphere\b", "共轭半球"),
    (r"\bsummer-to-winter\b", "夏半球到冬半球"),
    (r"\bnear sunset\b", "接近日落"),
    (r"\baround midnight\b", "接近午夜"),
    (r"\boccurrence rate\b", "发生率"),
    (r"\blocal time\b", "地方时"),
    (r"\bduration\b", "持续时间"),
    (r"\bmajor mechanism\b", "主要机制"),
    (r"\bplasma source\b", "等离子体来源"),
    (r"\bfull text\b", "全文"),
    (r"\bthermospheric mass density\b", "热层质量密度"),
    (r"\bthermospheric density\b", "热层密度"),
    (r"\bsatellite drag\b", "卫星阻力"),
    (r"\bdrag environment\b", "阻力环境"),
    (r"\bthis paper\b", "这篇文章"),
    (r"\bthis study\b", "这项研究"),
]


def _normalize_deep_read_text(value: str) -> str:
    text = (value or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"([A-Za-z\u4e00-\u9fff])\s*\n-\s*([A-Za-z0-9\u4e00-\u9fff])", r"\1-\2", text)
    text = re.sub(r"(?<=\d)\s*\n\s*(?=\d)", "", text)
    text = re.sub(r"([A-Za-z]{2,})\s*\n\s*([A-Za-z]{2,})", r"\1 \2", text)
    text = re.sub(r"[ \t]+", " ", text)
    for pattern, replacement in DEEP_READ_TEXT_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace("消融 实验", "消融实验")
    text = text.replace("这个文章", "这篇文章")
    text = text.replace("This paper", "这篇文章")
    text = text.replace("This study", "这项研究")
    text = text.replace("‘", "“").replace("’", "”")
    text = re.sub(r"'([^'\n]{1,80})'", r"“\1”", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_one_sentence_overview(value: str) -> str:
    text = _normalize_deep_read_text(value)
    if text.startswith("这篇文章真正想回答的，不是") and "而是" in text:
        after = text.split("而是", 1)[1].strip()
        after = re.sub(r"^(更[^：]{0,10}[：:])", "", after)
        after = after.lstrip("：:，, ")
        text = f"这篇文章的目标是{after}"
    elif text.startswith("这篇文章想回答的，不是") and "而是" in text:
        after = text.split("而是", 1)[1].strip()
        after = after.lstrip("：:，, ")
        text = f"这篇文章的目标是{after}"
    elif text.startswith("这个文章真正想回答的，不是") and "而是" in text:
        after = text.split("而是", 1)[1].strip()
        after = after.lstrip("：:，, ")
        text = f"这篇文章的目标是{after}"
    elif re.match(r"^这篇文章[^。！？\n]{0,80}不是[^。！？\n]{0,120}而是", text):
        text = re.sub(r"^这篇文章[^。！？\n]{0,80}?而是", "这篇文章的目标是", text, count=1)
    text = text.replace("这篇文章的目标是更尖锐的一步：", "这篇文章的目标是")
    text = text.replace("这篇文章的目标是更进一步：", "这篇文章的目标是")
    if text and not re.match(r"^(这篇文章|作者)", text):
        text = f"这篇文章的目标是{text}"
    return text.strip()


def _normalize_goal_text(value: str, *, tags: list[str]) -> str:
    text = _normalize_structured_deep_read_text(value)
    if text:
        first_line, separator, remainder = text.partition("\n")
        normalized_first_line = first_line.strip()
        normalized_first_line = re.sub(r"^(作者研究的目标是|这篇文章的目标是)\s*", "", normalized_first_line)
        direct_target_match = re.search(
            r"(?:作者真正要解决的是|真正要解决的是|要解决的问题是)[:：]?\s*(.+)$",
            normalized_first_line,
        )
        if direct_target_match:
            normalized_first_line = f"作者要解决的问题是：{direct_target_match.group(1).strip()}"
        elif re.search(r"不是", normalized_first_line) and "而是" in normalized_first_line:
            after = normalized_first_line.split("而是", 1)[1].strip().lstrip("：:，, ")
            normalized_first_line = f"作者要解决的问题是：{after}"
        elif normalized_first_line and not normalized_first_line.startswith("作者要解决的问题是"):
            normalized_first_line = f"作者要解决的问题是：{normalized_first_line.lstrip('：:，, ')}"
        normalized_first_line = re.sub(
            r"^作者要解决的问题是：(?:作者|这篇文章)(?:希望|想|试图)?回答(?:的)?(?:问题)?[:：]?\s*",
            "作者要解决的问题是：",
            normalized_first_line,
        )
        text = normalized_first_line if not separator else f"{normalized_first_line}\n{remainder.strip()}"
    if not _supports_downstream_application(tags):
        text = _drop_downstream_sentences(text)
    return text.strip()


def _normalize_key_results_text(value: str) -> str:
    text = _normalize_structured_deep_read_text(value)
    lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        heading_candidate = re.sub(r"^#+\s*", "", stripped)
        if re.fullmatch(r"(硬结论|次级结论|合理推论|需进一步研究讨论的结论)[:：]?", heading_candidate):
            label = heading_candidate.rstrip("：:")
            lines.append(f"#### {label}")
            continue
        lines.append(stripped)
    return "\n".join(line for line in lines if line).strip()


def _normalize_contribution_text(value: str) -> str:
    text = _normalize_structured_deep_read_text(value)
    if "不是" in text and "而是" in text and re.match(r"^(这篇文章|文章|作者)[^。！？\n]{0,100}", text):
        after = text.split("而是", 1)[1].strip().lstrip("：:，, ")
        text = f"这篇文章的新意与贡献在于{after}"
    return text.strip()


def _normalize_structured_deep_read_text(value: str) -> str:
    text = _normalize_deep_read_text(value)
    for index, chinese in enumerate("一二三四五六七八九十", start=1):
        text = re.sub(rf"(?:(?<=^)|(?<=[。；]))\s*第{chinese}[，、]\s*", f"\n{index}. ", text)
    text = text.replace("合理解释：", "合理推论：")
    text = text.replace("合理解释:", "合理推论：")
    text = text.replace("需要进一步讨论/证明：", "需进一步研究讨论的结论：")
    text = text.replace("需要进一步讨论/证明:", "需进一步研究讨论的结论：")
    text = text.replace("仍需保留的部分：", "需进一步研究讨论的结论：")
    text = text.replace("仍需保留的部分:", "需进一步研究讨论的结论：")
    text = re.sub(r"(?<=[。；])(?=(?:硬结论|次级结论|合理推论|需进一步研究讨论的结论)[:：])", "\n", text)
    text = re.sub(r"(?<=[。！？；：])(?=(?:\d+[.．、)](?:\s+|$)))", "\n", text)
    text = re.sub(r"([。；：])\s+(?=(?:\d+[.．、)]|[-*])\s+)", r"\1\n", text)
    text = re.sub(r"(?:(?<=^)|(?<=\n))(\d+[.．、)])(?=\S)", r"\1 ", text)
    text = re.sub(r"(?<=[。！？；])(?=(?:整体看|总体看))", "\n", text)
    lines = [line.rstrip() for line in text.splitlines()]
    normalized_lines: list[str] = []
    previous_was_list = False
    for line in lines:
        stripped = line.strip()
        is_list_item = bool(re.match(r"^(?:\d+[.．、)]\s+|[-*]\s+)", stripped))
        if not stripped:
            continue
        if not is_list_item and previous_was_list and normalized_lines and normalized_lines[-1] != "":
            normalized_lines.append("")
        normalized_lines.append(stripped)
        previous_was_list = is_list_item
    text = "\n".join(normalized_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_relation_to_my_work_text(value: str, *, tags: list[str]) -> str:
    text = _normalize_structured_deep_read_text(value)
    if _supports_downstream_application(tags):
        return text
    numbered_items = _extract_numbered_items(text)
    kept_items = [item for item in numbered_items if not _contains_downstream_keywords(item)]
    kept_paragraphs = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and not re.match(r"^\d+[.、)]\s+", line.strip())
        and not _contains_downstream_keywords(line.strip())
        and not re.search(r"([一二三四五六七八九十两\d]+个)?重要方向", line.strip())
    ]
    closing = "这项工作更适合作为边界区动力学个例和机制对照，不宜直接外推到业务化或定量应用。"
    if kept_items:
        intro = "\n".join(kept_paragraphs) if kept_paragraphs else "它和当前主线的直接关系主要体现在以下几点。"
        lead_block = f"{intro}\n{_render_numbered_items(kept_items)}"
    elif kept_paragraphs:
        lead_block = "\n\n".join(kept_paragraphs)
    else:
        lead_block = _default_relation_to_my_work_lead(tags)
    if lead_block.rstrip() == closing:
        return lead_block.strip()
    return f"{lead_block.strip()}\n\n{closing}".strip()


def _supports_downstream_application(tags: list[str]) -> bool:
    return any(
        tag in {"热层/密度", "卫星影响", "业务化预报"} or tag.startswith("应用/")
        for tag in tags
    )


def _drop_downstream_sentences(text: str) -> str:
    downstream_keywords = (
        "热层密度",
        "卫星阻力",
        "业务化",
        "风险评估",
        "轨道维持",
        "轨道环境",
        "姿轨控",
        "再入预报",
        "星座任务",
        "工程影响",
    )
    lines = text.splitlines()
    kept_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if kept_lines and kept_lines[-1] != "":
                kept_lines.append("")
            continue
        prefix_match = re.match(r"^(\d+[.．、)]\s+|[-*]\s+)", stripped)
        prefix = prefix_match.group(1) if prefix_match else ""
        body = stripped[len(prefix):] if prefix else stripped
        pieces = re.split(r"(?<=[。！？])\s*", body)
        kept_pieces = [
            piece.strip()
            for piece in pieces
            if piece.strip() and not any(keyword in piece for keyword in downstream_keywords)
        ]
        if not kept_pieces:
            continue
        rebuilt = "".join(kept_pieces).strip()
        if prefix:
            rebuilt = prefix + rebuilt
        kept_lines.append(rebuilt)
    while kept_lines and kept_lines[-1] == "":
        kept_lines.pop()
    if not kept_lines:
        return text
    return "\n".join(kept_lines)


def _contains_downstream_keywords(text: str) -> bool:
    downstream_keywords = (
        "热层密度",
        "密度模型",
        "卫星阻力",
        "阻力预报",
        "业务化",
        "风险评估",
        "轨道维持",
        "轨道环境",
        "姿轨控",
        "再入预报",
        "星座任务",
        "工程影响",
    )
    return any(keyword in text for keyword in downstream_keywords)


def _extract_numbered_items(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if re.match(r"^\d+[.、)]\s+", stripped):
            if current:
                items.append(" ".join(current).strip())
            current = [re.sub(r"^\d+[.、)]\s+", "", stripped, count=1).strip()]
            continue
        if current:
            current.append(stripped)
    if current:
        items.append(" ".join(current).strip())
    return items


def _render_numbered_items(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _default_relation_to_my_work_lead(tags: list[str]) -> str:
    if "热层/风场" in tags and any(tag.startswith("极区/") for tag in tags):
        return "它和当前主线的直接关系在于：这是一篇东亚中纬边界区受极区过程直接控制的高质量个例，可用于后续热层风异常事件筛选和机制对照。"
    if "热层/密度" in tags:
        return "它和当前主线的直接关系在于：可作为热层密度异常识别与驱动归因的参考个例。"
    return "它与当前主线是间接相关的，可作为相关机制背景和个例对照。"


def _validate_deep_read_markdown(markdown: str, *, is_output_note: bool) -> list[str]:
    issues: list[str] = []
    lines = markdown.splitlines()
    if lines and lines[0].startswith("文件名："):
        issues.append("正文顶部不应包含文件名行")
    for heading in REQUIRED_DEEP_READ_HEADINGS:
        if heading not in markdown:
            issues.append(f"缺少模板要求的区块：{heading}")
    for pattern, message in LEGACY_DEEP_READ_PATTERNS:
        if re.search(pattern, markdown, flags=re.MULTILINE):
            issues.append(message)
    if re.search(r"### 一句话总述\s*\n[^\n]*不是[^\n]*而是", markdown):
        issues.append("一句话总述仍包含“不是……而是……”式开头")
    if re.search(r"### 为什么做\s*\n[^\n]*不是[^\n]*而是", markdown):
        issues.append("“为什么做”仍包含“不是……而是……”式表述")
    if not is_output_note and re.search(r"\[\[log/real_case_eval/.*\|(PDF|单篇总结)\]\]", markdown):
        issues.append("评测输出仍使用了生产态 Obsidian 链接")
    return issues


def _run_deep_read_review_loop(markdown: str, *, tags: list[str]) -> tuple[str, list[str]]:
    reviewed = markdown
    for _ in range(DEEP_READ_REVIEW_MAX_PASSES):
        fixed = _autofix_deep_read_markdown(reviewed, tags=tags)
        issues = _audit_deep_read_markdown(fixed, tags=tags)
        if not issues:
            return fixed, []
        if fixed == reviewed:
            return fixed, issues
        reviewed = fixed
    return reviewed, _audit_deep_read_markdown(reviewed, tags=tags)


def _autofix_deep_read_markdown(markdown: str, *, tags: list[str]) -> str:
    fixed = markdown
    fixed = _rewrite_section_body(fixed, "### 一句话总述", _normalize_one_sentence_overview)
    fixed = _rewrite_section_body(fixed, "### 为什么做", lambda body: _normalize_goal_text(body, tags=tags))
    fixed = _rewrite_section_body(fixed, "### 如何做", _normalize_structured_deep_read_text)
    fixed = _rewrite_section_body(
        fixed,
        "### 关键结果",
        _normalize_key_results_text,
        next_heading="### 新意与贡献",
    )
    fixed = _rewrite_section_body(fixed, "### 新意与贡献", _normalize_contribution_text)
    fixed = _rewrite_section_body(fixed, "### 局限性", _normalize_structured_deep_read_text)
    fixed = _rewrite_section_body(fixed, "### 可复现性", _normalize_structured_deep_read_text)
    fixed = _rewrite_section_body(fixed, "### 与已有工作的关系", _normalize_structured_deep_read_text)
    fixed = _rewrite_section_body(fixed, "### 最终结论", _normalize_structured_deep_read_text)
    fixed = _rewrite_bullet_value(
        fixed,
        "- 和我已有工作的关系：",
        lambda body: _normalize_relation_to_my_work_text(body, tags=tags),
    )
    fixed = _rewrite_bullet_value(fixed, "- 后续值得追踪的问题：", _normalize_structured_deep_read_text)
    fixed = _rewrite_bullet_value(fixed, "- 需要人工复核的点：", _normalize_structured_deep_read_text)
    fixed = _rewrite_bullet_value(fixed, "- Obsidian 索引挂接：", lambda body: body.strip())
    return fixed.strip() + "\n"


def _audit_deep_read_markdown(markdown: str, *, tags: list[str]) -> list[str]:
    issues: list[str] = []
    why = _extract_section_body(markdown, "### 为什么做")
    if why:
        if "不是" in why and "而是" in why:
            issues.append("“为什么做”仍包含“不是……而是……”式表述")
        if re.search(r"[。；：](?=\d+[.．、)])", why):
            issues.append("“为什么做”中的编号列表未换行")
        if not why.startswith("作者要解决的问题是："):
            issues.append("“为什么做”没有用直接问题陈述开头")
    key_results = _extract_section_body(markdown, "### 关键结果", next_heading="### 新意与贡献")
    if key_results and re.search(r"(?m)^###\s+(硬结论|次级结论|合理推论|需进一步研究讨论的结论)\s*$", key_results):
        issues.append("“关键结果”中的次级标题层级仍然过高")
    return issues


def _extract_section_body(markdown: str, heading: str, *, next_heading: str | None = None) -> str:
    if next_heading:
        pattern = re.compile(rf"(?ms)^{re.escape(heading)}\n(.*?)(?=^{re.escape(next_heading)}\n|^----\s*$|\Z)")
    else:
        pattern = re.compile(rf"(?ms)^{re.escape(heading)}\n(.*?)(?=^###\s|^##\s|^----\s*$|\Z)")
    match = pattern.search(markdown)
    if not match:
        return ""
    return match.group(1).strip()


def _rewrite_section_body(markdown: str, heading: str, transform, *, next_heading: str | None = None) -> str:
    if next_heading:
        pattern = re.compile(rf"(?ms)^({re.escape(heading)}\n)(.*?)(?=^{re.escape(next_heading)}\n|^----\s*$|\Z)")
    else:
        pattern = re.compile(rf"(?ms)^({re.escape(heading)}\n)(.*?)(?=^###\s|^##\s|^----\s*$|\Z)")
    match = pattern.search(markdown)
    if not match:
        return markdown
    replacement = match.group(1) + transform(match.group(2).strip()).strip() + "\n\n"
    return markdown[: match.start()] + replacement + markdown[match.end() :]


def _rewrite_bullet_value(markdown: str, bullet_heading: str, transform) -> str:
    pattern = re.compile(rf"(?ms)^({re.escape(bullet_heading)}\n)(.*?)(?=^- [^\n]+：\n|^----\s*$|\Z)")
    match = pattern.search(markdown)
    if not match:
        return markdown
    replacement = match.group(1) + transform(match.group(2).strip()).strip() + "\n\n"
    return markdown[: match.start()] + replacement + markdown[match.end() :]


def _load_deep_read_template(template_path: Path) -> str:
    template_text = template_path.read_text(encoding="utf-8")
    _validate_deep_read_template(template_text, template_path)
    return template_text


def _validate_deep_read_template(template_text: str, template_path: Path) -> None:
    missing_markers = [marker for marker in REQUIRED_DEEP_READ_HEADINGS if marker not in template_text]
    if "记录时间戳:" not in template_text:
        missing_markers.append("记录时间戳:")
    if missing_markers:
        joined = "、".join(missing_markers)
        raise ValueError(f"Deep read template missing required markers in {template_path}: {joined}")

    found_vars = set(DEEP_READ_TEMPLATE_VAR_RE.findall(template_text))
    missing_vars = sorted(DEEP_READ_TEMPLATE_REQUIRED_VARS - found_vars)
    if missing_vars:
        joined = ", ".join(missing_vars)
        raise ValueError(f"Deep read template missing required placeholders in {template_path}: {joined}")


def _render_deep_read_template(template_text: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise ValueError(f"Deep read template placeholder has no context value: {key}")
        return str(context[key])

    rendered = DEEP_READ_TEMPLATE_VAR_RE.sub(replace, template_text)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered
