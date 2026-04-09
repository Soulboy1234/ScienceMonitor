from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import project_root
from .config_ui_review import _sample_rendered_html


@dataclass(frozen=True)
class ConfigUIVisualReviewIssue:
    category: str
    message: str


@dataclass(frozen=True)
class ConfigUIVisualReviewReport:
    passed: bool
    issues: list[ConfigUIVisualReviewIssue]
    artifacts: list[Path]


def _artifact_dir(project: Path) -> Path:
    path = project / "log" / "ui_visual_review"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _activate_view_script(view_name: str, title: str) -> str:
    return f"""
    (() => {{
      document.querySelectorAll('.view').forEach((node) => node.classList.remove('active'));
      document.querySelectorAll('.nav-link').forEach((node) => node.classList.remove('active'));
      const target = document.querySelector('.view[data-view="{view_name}"]');
      if (target) target.classList.add('active');
      const nav = document.querySelector('.nav-link[data-nav-target="{view_name}"]');
      if (nav) nav.classList.add('active');
      const titleNode = document.querySelector('[data-current-title]');
      if (titleNode) titleNode.textContent = "{title}";
    }})();
    """


def run_config_ui_visual_review(root: Path | None = None) -> ConfigUIVisualReviewReport:
    project = root or project_root()
    issues: list[ConfigUIVisualReviewIssue] = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on runtime env
        return ConfigUIVisualReviewReport(
            passed=False,
            issues=[ConfigUIVisualReviewIssue("missing_browser_runtime", f"Playwright 不可用：{exc}")],
            artifacts=[],
        )
    try:
        metrics, artifacts = _run_visual_browser_session(project, sync_playwright)
    except Exception as exc:  # pragma: no cover - depends on runtime env
        return ConfigUIVisualReviewReport(
            passed=False,
            issues=[ConfigUIVisualReviewIssue("browser_execution_failed", f"UI 视觉检查执行失败：{exc}")],
            artifacts=[],
        )
    issues.extend(_evaluate_weekly_report_visual_metrics(metrics))
    return ConfigUIVisualReviewReport(passed=not issues, issues=issues, artifacts=artifacts)


def render_config_ui_visual_review_summary(report: ConfigUIVisualReviewReport) -> str:
    lines = [
        "Config UI visual review summary:",
        f"- issues={len(report.issues)}",
        f"- screenshots={len(report.artifacts)}",
        f"- overall={'ok' if report.passed else 'failed'}",
    ]
    if report.artifacts:
        lines.append("- artifacts:")
        for item in report.artifacts:
            lines.append(f"  - {item}")
    if report.issues:
        lines.append("- violations:")
        for item in report.issues:
            lines.append(f"  - {item.category}: {item.message}")
    else:
        lines.append("- violations: none")
    return "\n".join(lines)


def _run_visual_browser_session(project: Path, sync_playwright):
    html = _sample_rendered_html(project)
    artifact_dir = _artifact_dir(project)
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "config_ui_sample.html"
        html_path.write_text(html, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 1100})
            page.goto(html_path.as_uri())
            page.wait_for_timeout(200)
            page.evaluate(_activate_view_script("weekly-report", "周报"))
            page.wait_for_timeout(100)
            weekly_artifact = artifact_dir / "weekly-report-960.png"
            page.screenshot(path=str(weekly_artifact), full_page=True)
            metrics = _collect_weekly_report_visual_metrics(page)
            browser.close()
    return metrics, [weekly_artifact]


def _collect_weekly_report_visual_metrics(page) -> dict[str, float | bool]:
    return page.evaluate(
        """
        () => {
          const form = document.querySelector('.weekly-report-form-card');
          const journals = document.querySelector('.weekly-report-journals-card');
          const main = document.querySelector('.main');
          const formStack = document.querySelector('.weekly-report-form-card .form-stack');
          if (!form || !journals || !main || !formStack) {
            return {missing: true};
          }
          const formRect = form.getBoundingClientRect();
          const journalsRect = journals.getBoundingClientRect();
          const stackChildren = Array.from(formStack.children).filter((node) => node.offsetParent !== null);
          const gaps = [];
          for (let index = 0; index < stackChildren.length - 1; index += 1) {
            const currentRect = stackChildren[index].getBoundingClientRect();
            const nextRect = stackChildren[index + 1].getBoundingClientRect();
            gaps.push(nextRect.top - currentRect.bottom);
          }
          return {
            missing: false,
            formWidth: formRect.width,
            journalsWidth: journalsRect.width,
            sameRowDelta: Math.abs(formRect.top - journalsRect.top),
            formStackGap: parseFloat(getComputedStyle(formStack).gap || '0'),
            gapMin: gaps.length ? Math.min(...gaps) : 0,
            gapMax: gaps.length ? Math.max(...gaps) : 0,
            gapVariance: gaps.length ? Math.max(...gaps) - Math.min(...gaps) : 0,
            mainScrollWidth: main.scrollWidth,
            mainClientWidth: main.clientWidth,
            documentScrollWidth: document.documentElement.scrollWidth,
            documentClientWidth: document.documentElement.clientWidth,
          };
        }
        """
    )


def _evaluate_weekly_report_visual_metrics(metrics: dict[str, float | bool]) -> list[ConfigUIVisualReviewIssue]:
    if metrics.get("missing"):
        return [ConfigUIVisualReviewIssue("missing_elements", "周报页缺少视觉检查所需的关键 DOM 元素。")]
    issues: list[ConfigUIVisualReviewIssue] = []
    if metrics["sameRowDelta"] > 24:
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_cards_wrapped",
                f"周报页首行卡片未保持同一行，顶部偏移差为 {metrics['sameRowDelta']:.1f}px。",
            )
        )
    ratio = metrics["formWidth"] / metrics["journalsWidth"] if metrics["journalsWidth"] else 0
    if not (2.4 <= ratio <= 3.6):
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_cards_ratio",
                f"周报页首行卡片宽度比异常，当前约为 {ratio:.2f}:1。",
            )
        )
    if not (10 <= metrics["formStackGap"] <= 14):
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_form_stack_gap",
                f"周报表单主栈 gap 异常，当前为 {metrics['formStackGap']:.1f}px。",
            )
        )
    if metrics["gapVariance"] > 4:
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_form_spacing_variance",
                f"周报表单纵向间距不均匀，最小 {metrics['gapMin']:.1f}px，最大 {metrics['gapMax']:.1f}px。",
            )
        )
    if metrics["mainScrollWidth"] > metrics["mainClientWidth"] + 2:
        issues.append(
            ConfigUIVisualReviewIssue(
                "main_overflow",
                f"主内容区出现横向溢出，scrollWidth={metrics['mainScrollWidth']}，clientWidth={metrics['mainClientWidth']}。",
            )
        )
    if metrics["documentScrollWidth"] > metrics["documentClientWidth"] + 2:
        issues.append(
            ConfigUIVisualReviewIssue(
                "document_overflow",
                f"页面整体出现横向溢出，scrollWidth={metrics['documentScrollWidth']}，clientWidth={metrics['documentClientWidth']}。",
            )
        )
    return issues
