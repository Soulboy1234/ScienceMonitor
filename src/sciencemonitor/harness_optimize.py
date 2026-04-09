from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from .config import logs_root, project_root
from .harness_audit import HarnessAuditReport, run_harness_audit


@dataclass(frozen=True)
class HarnessOptimizeAction:
    name: str
    applied: bool
    detail: str


@dataclass(frozen=True)
class HarnessOptimizeReport:
    before_audit: HarnessAuditReport
    actions: list[HarnessOptimizeAction]
    after_audit: HarnessAuditReport
    report_path: Path | None = None

    @property
    def improved(self) -> bool:
        return len(self.after_audit.findings) < len(self.before_audit.findings)


def harness_optimize_log_root(root: Path | None = None) -> Path:
    return logs_root(root) / "harness_optimize"


def run_harness_optimize(root: Path | None = None, *, write_report: bool = False) -> HarnessOptimizeReport:
    project = root or project_root()
    before = run_harness_audit(project, write_report=False)
    actions = [
        _ensure_readme_entries(project),
        _ensure_agents_entries(project),
        _ensure_harness_overview_entries(project),
        _ensure_release_checklist_entries(project),
        _ensure_python_module_map_entries(project),
    ]
    after = run_harness_audit(project, write_report=False)
    report = HarnessOptimizeReport(before_audit=before, actions=actions, after_audit=after, report_path=None)
    if not write_report:
        return report
    report_path = write_harness_optimize_report(project, report)
    return HarnessOptimizeReport(before_audit=before, actions=actions, after_audit=after, report_path=report_path)


def render_harness_optimize_summary(report: HarnessOptimizeReport) -> str:
    lines = [
        "Harness optimize summary:",
        f"- findings_before={len(report.before_audit.findings)}",
        f"- findings_after={len(report.after_audit.findings)}",
        f"- improved={'yes' if report.improved else 'no'}",
        f"- overall_after={'ok' if report.after_audit.passed else 'failed'}",
    ]
    if report.actions:
        lines.append("- actions:")
        for action in report.actions:
            lines.append(f"  - {action.name}: {'applied' if action.applied else 'skipped'} ({action.detail})")
    if report.report_path:
        lines.append(f"- report={report.report_path}")
    return "\n".join(lines)


def write_harness_optimize_report(root: Path | None, report: HarnessOptimizeReport) -> Path:
    project = root or project_root()
    log_root = harness_optimize_log_root(project)
    log_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_root / f"{timestamp}_harness_optimize.md"
    latest_path = log_root / "latest.md"
    content = _render_harness_optimize_markdown(report)
    path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    return path


def _render_harness_optimize_markdown(report: HarnessOptimizeReport) -> str:
    lines = [
        "# Harness Optimize Report",
        "",
        render_harness_optimize_summary(report),
        "",
        "## 优化前",
        "",
        f"- findings={len(report.before_audit.findings)}",
        "",
        "## 执行动作",
        "",
    ]
    for action in report.actions:
        lines.append(f"- {action.name}: {'applied' if action.applied else 'skipped'} ({action.detail})")
    lines.extend(
        [
            "",
            "## 优化后",
            "",
            f"- findings={len(report.after_audit.findings)}",
            f"- overall={'ok' if report.after_audit.passed else 'failed'}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _ensure_readme_entries(project: Path) -> HarnessOptimizeAction:
    path = project / "README.md"
    text = path.read_text(encoding="utf-8")
    original = text
    text = _ensure_contains_line(text, "./scripts/run_science_monitor.sh maintenance-check --auto-repair")
    text = _ensure_contains_line(text, "./scripts/run_science_monitor.sh harness-check")
    text = _insert_after_or_append(
        text,
        "- 代码熵检查：`./scripts/run_science_monitor.sh entropy-check`\n",
        "- Harness 审计：`./scripts/run_science_monitor.sh harness-audit`\n"
        "- Harness 优化：`./scripts/run_science_monitor.sh harness-optimize`\n",
    )
    text = _insert_after_or_append(
        text,
        "- `harness-check` 是本地和 CI 的统一 gate，默认只跑 `doctor` 一致性检查和 `golden eval`\n",
        "- `harness-audit` 负责监督当前 harness 是否覆盖了现有工作流的关键风险点\n"
        "- `harness-optimize` 负责按审计建议做低风险、确定性的治理修补\n",
    )
    return _write_if_changed(path, original, text, "readme_harness_entries")


def _ensure_agents_entries(project: Path) -> HarnessOptimizeAction:
    path = project / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    original = text
    text = _ensure_contains_line(text, "./scripts/run_science_monitor.sh maintenance-check --auto-repair")
    text = _ensure_contains_line(text, "./scripts/run_science_monitor.sh harness-check")
    text = _ensure_contains_line(text, "docs/user_guides/harness_governance_overview.md")
    text = _insert_after_or_append(
        text,
        "- 代码熵检查：`./scripts/run_science_monitor.sh entropy-check`\n",
        "- Harness 审计：`./scripts/run_science_monitor.sh harness-audit`\n"
        "- Harness 优化：`./scripts/run_science_monitor.sh harness-optimize`\n",
    )
    text = _insert_after_or_append(
        text,
        "- Harness 总览：`docs/user_guides/harness_governance_overview.md`\n",
        "- Harness 自监督会通过 `harness-audit` 评估当前治理覆盖面，并用 `harness-optimize` 做低风险修补\n",
    )
    return _write_if_changed(path, original, text, "agents_harness_entries")


def _ensure_harness_overview_entries(project: Path) -> HarnessOptimizeAction:
    path = project / "docs" / "user_guides" / "harness_governance_overview.md"
    text = path.read_text(encoding="utf-8")
    original = text
    if _overview_harness_entries_stable(text):
        return HarnessOptimizeAction(name="overview_harness_entries", applied=False, detail="already in sync")
    audit_block = """
### 2.5 `harness-audit`

命令：

```bash
./scripts/run_science_monitor.sh harness-audit
```

负责：

- 检查当前 harness 是否仍覆盖了项目工作流的关键风险点
- 检查 README / AGENTS / CI / runbook / code map 是否与 harness 规则同步
- 输出结构化 finding 和优化建议

它回答的是：**当前 harness 自身是否还需要增强**。

### 2.6 `harness-optimize`

命令：

```bash
./scripts/run_science_monitor.sh harness-optimize
```

负责：

- 根据 `harness-audit` 的 finding 做低风险、确定性的治理修补
- 修补后重新执行一次 harness 审计
- 输出前后对比报告

它回答的是：**当前 harness 自身是否已经按建议完成基础收敛**。
"""
    text = _sanitize_harness_overview_text(text)
    text = _insert_after_or_append(
        text,
        "它回答的是：**当前项目的治理链路是否整体健康**。\n",
        audit_block,
    )
    text = _ensure_overview_relationship_lines(text)
    return _write_if_changed(path, original, text, "overview_harness_entries")


def _ensure_release_checklist_entries(project: Path) -> HarnessOptimizeAction:
    path = project / "docs" / "user_guides" / "release_checklist.md"
    text = path.read_text(encoding="utf-8")
    original = text
    text = _insert_after(
        text,
        "### Harness gate\n\n```bash\n./scripts/run_science_monitor.sh harness-check\n```\n",
        "### Harness 自监督\n\n```bash\n./scripts/run_science_monitor.sh harness-audit\n```\n\n",
    )
    return _write_if_changed(path, original, text, "release_harness_entries")


def _ensure_python_module_map_entries(project: Path) -> HarnessOptimizeAction:
    path = project / "docs" / "user_guides" / "python_module_map.md"
    text = path.read_text(encoding="utf-8")
    original = text
    text = _insert_after_or_append(
        text,
        "- [harness.py](../../src/sciencemonitor/harness.py)\n  统一 harness gate。负责把 `doctor`、`golden eval` 和可选的 `real eval fixture` 检查收成一个 `harness-check` 入口。\n",
        "\n- [harness_audit.py](../../src/sciencemonitor/harness_audit.py)\n  Harness 自监督层。负责评估当前 harness 是否还覆盖了当前工作流的关键风险点，并输出审计报告。\n"
        "\n- [harness_optimize.py](../../src/sciencemonitor/harness_optimize.py)\n  Harness 优化层。负责按 harness 审计结论做低风险、确定性的治理修补，并生成前后对比报告。\n",
    )
    return _write_if_changed(path, original, text, "module_map_harness_entries")


def _insert_after(text: str, anchor: str, addition: str, *, raw_anchor: bool = False) -> str:
    if addition.strip() in text:
        return text
    target = anchor if raw_anchor else anchor.rstrip("\n")
    index = text.find(target)
    if index < 0:
        return text
    insert_at = index + len(target)
    return text[:insert_at] + ("\n" if not text[insert_at:insert_at + 1].startswith("\n") else "") + addition + text[insert_at:]


def _insert_after_or_append(text: str, anchor: str, addition: str) -> str:
    updated = _insert_after(text, anchor, addition)
    if updated != text:
        return updated
    if addition.strip() in text:
        return text
    suffix = "" if not text or text.endswith("\n") else "\n"
    return f"{text}{suffix}{addition}"


def _ensure_contains_line(text: str, needle: str) -> str:
    if needle in text:
        return text
    suffix = "" if not text or text.endswith("\n") else "\n"
    return f"{text}{suffix}{needle}\n"


def _overview_harness_entries_stable(text: str) -> bool:
    return (
        text.count("### 2.5 `harness-audit`") == 1
        and text.count("### 2.6 `harness-optimize`") == 1
        and "### 7. `harness-audit`" not in text
        and "### 8. `harness-optimize`" not in text
        and text.count("- `harness-audit`：治理链路自身是否还有盲区") == 1
        and text.count("- `harness-optimize`：按审计建议做低风险治理修补，再重新审计") == 1
        and text.count("- `harness-audit` 是治理自监督") == 1
        and text.count("- `harness-optimize` 是治理低风险修补") == 1
    )


def _sanitize_harness_overview_text(text: str) -> str:
    text = re.sub(
        r"\n### 7\. `harness-audit`.*?(?=\n### 3\. `maintenance-check`)",
        "\n",
        text,
        flags=re.S,
    )
    return re.sub(
        r"\n### 2\.5 `harness-audit`.*?(?=\n### 3\. `maintenance-check`)",
        "\n",
        text,
        flags=re.S,
    )


def _ensure_overview_relationship_lines(text: str) -> str:
    line_pairs = (
        ("- `harness-check`：治理链路是否整体健康", "- `harness-audit`：治理链路自身是否还有盲区"),
        ("- `maintenance-check`：把以上内容收成“审核 -> 调整 -> 测试 -> 再审核”", "- `harness-optimize`：按审计建议做低风险治理修补，再重新审计"),
        ("- `harness-check` 是治理 gate", "- `harness-audit` 是治理自监督"),
        ("- `maintenance-check` 是维护循环", "- `harness-optimize` 是治理低风险修补"),
    )
    for anchor_line, insert_line in line_pairs:
        text = _ensure_line_before(text, anchor_line, insert_line)
    for line in (
        "- `harness-audit`：治理链路自身是否还有盲区",
        "- `harness-optimize`：按审计建议做低风险治理修补，再重新审计",
        "- `harness-audit` 是治理自监督",
        "- `harness-optimize` 是治理低风险修补",
    ):
        text = _dedupe_exact_line(text, line)
    return text


def _ensure_line_before(text: str, anchor_line: str, insert_line: str) -> str:
    text = _dedupe_exact_line(text, insert_line)
    if insert_line in text:
        return text
    target = f"{anchor_line}\n"
    replacement = f"{insert_line}\n{anchor_line}\n"
    return text.replace(target, replacement, 1)


def _dedupe_exact_line(text: str, line: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    seen = False
    for item in lines:
        if item == line:
            if seen:
                continue
            seen = True
        kept.append(item)
    return "\n".join(kept) + ("\n" if text.endswith("\n") else "")


def _write_if_changed(path: Path, original: str, updated: str, action_name: str) -> HarnessOptimizeAction:
    if updated == original:
        return HarnessOptimizeAction(name=action_name, applied=False, detail="already in sync")
    path.write_text(updated, encoding="utf-8")
    return HarnessOptimizeAction(name=action_name, applied=True, detail=f"updated {path.name}")
