from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import project_root
from .config_ui_review import _sample_rendered_html


@dataclass(frozen=True)
class ConfigUIFunctionalReviewIssue:
    category: str
    message: str


@dataclass(frozen=True)
class ConfigUIFunctionalReviewReport:
    passed: bool
    issues: list[ConfigUIFunctionalReviewIssue]


def run_config_ui_functional_review(root: Path | None = None) -> ConfigUIFunctionalReviewReport:
    project = root or project_root()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - runtime dependent
        return ConfigUIFunctionalReviewReport(
            passed=False,
            issues=[ConfigUIFunctionalReviewIssue("missing_browser_runtime", f"Playwright 不可用：{exc}")],
        )
    try:
        states = _run_functional_browser_session(project, sync_playwright)
    except Exception as exc:  # pragma: no cover - runtime dependent
        return ConfigUIFunctionalReviewReport(
            passed=False,
            issues=[ConfigUIFunctionalReviewIssue("browser_execution_failed", f"UI 功能检查执行失败：{exc}")],
        )
    issues = _evaluate_functional_states(states)
    return ConfigUIFunctionalReviewReport(passed=not issues, issues=issues)


def _snapshot_ui_state(page) -> dict[str, object]:
    return page.evaluate(
        """
        () => {
          const activeView = document.querySelector('.view.active');
          const activeNav = document.querySelector('.nav-link.active');
          const main = document.querySelector('.main');
          const title = document.querySelector('[data-current-title]');
          return {
            active_view: activeView ? activeView.getAttribute('data-view') : '',
            active_nav: activeNav ? activeNav.getAttribute('data-nav-target') : '',
            title: title ? title.textContent.trim() : '',
            scroll_top: main ? main.scrollTop : -1,
          };
        }
        """
    )


def _provider_visibility_state(page) -> dict[str, bool]:
    return page.evaluate(
        """
        () => {
          const visible = (value) => {
            const node = document.querySelector(`[data-provider-only="${value}"]`);
            if (!node) return false;
            const style = window.getComputedStyle(node);
            return style.display !== 'none' && !node.hasAttribute('hidden');
          };
          return {
            codex_visible: visible('codex_local'),
            openai_visible: visible('openai_api'),
            openrouter_visible: visible('openrouter_api'),
          };
        }
        """
    )


def render_config_ui_functional_review_summary(report: ConfigUIFunctionalReviewReport) -> str:
    lines = [
        "Config UI functional review summary:",
        f"- issues={len(report.issues)}",
        f"- overall={'ok' if report.passed else 'failed'}",
    ]
    if report.issues:
        lines.append("- violations:")
        for item in report.issues:
            lines.append(f"  - {item.category}: {item.message}")
    else:
        lines.append("- violations: none")
    return "\n".join(lines)


def _run_functional_browser_session(project: Path, sync_playwright) -> dict[str, dict[str, object]]:
    html = _sample_rendered_html(project)
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "config_ui_sample.html"
        html_path.write_text(html, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 1100})
            page.goto(html_path.as_uri())
            page.wait_for_timeout(200)
            overview = _snapshot_ui_state(page)
            page.evaluate("() => { const main = document.querySelector('.main'); if (main) main.scrollTop = 480; }")
            page.locator('.nav-link[data-nav-target="deep-read"]').click()
            page.wait_for_timeout(120)
            deep_read = _snapshot_ui_state(page)
            page.locator('.nav-link[data-nav-target="settings"]').click()
            page.wait_for_timeout(120)
            settings = _snapshot_ui_state(page)
            provider_states = _collect_provider_states(page)
            browser.close()
    return {
        "overview": overview,
        "deep_read": deep_read,
        "settings": settings,
        **provider_states,
    }


def _collect_provider_states(page) -> dict[str, dict[str, bool]]:
    states: dict[str, dict[str, bool]] = {}
    for provider in ("codex_local", "openai_api", "openrouter_api"):
        page.select_option("[data-provider-select]", provider)
        page.wait_for_timeout(60)
        states[provider] = _provider_visibility_state(page)
    return states


def _evaluate_functional_states(states: dict[str, dict[str, object]]) -> list[ConfigUIFunctionalReviewIssue]:
    issues: list[ConfigUIFunctionalReviewIssue] = []
    overview = states["overview"]
    deep_read = states["deep_read"]
    settings = states["settings"]
    if overview["title"] != "总览":
        issues.append(ConfigUIFunctionalReviewIssue("overview_title", f"初始总览标题异常：{overview['title']}"))
    if overview["active_view"] != "overview":
        issues.append(ConfigUIFunctionalReviewIssue("overview_view", f"初始 active view 异常：{overview['active_view']}"))
    if deep_read["title"] != "深度解读":
        issues.append(ConfigUIFunctionalReviewIssue("deep_read_title", f"深度解读标题异常：{deep_read['title']}"))
    if deep_read["active_view"] != "deep-read":
        issues.append(ConfigUIFunctionalReviewIssue("deep_read_view", f"深度解读 active view 异常：{deep_read['active_view']}"))
    if deep_read["scroll_top"] > 4:
        issues.append(
            ConfigUIFunctionalReviewIssue(
                "deep_read_scroll_reset",
                f"切换到深度解读后主内容区未回到顶部，scrollTop={deep_read['scroll_top']:.1f}px。",
            )
        )
    if settings["title"] != "设置":
        issues.append(ConfigUIFunctionalReviewIssue("settings_title", f"设置页标题异常：{settings['title']}"))
    if settings["active_view"] != "settings":
        issues.append(ConfigUIFunctionalReviewIssue("settings_view", f"设置页 active view 异常：{settings['active_view']}"))
    issues.extend(_evaluate_provider_state("codex", states["codex_local"], {"codex_visible": True, "openai_visible": False, "openrouter_visible": False}))
    issues.extend(_evaluate_provider_state("openai", states["openai_api"], {"codex_visible": False, "openai_visible": True, "openrouter_visible": False}))
    issues.extend(_evaluate_provider_state("openrouter", states["openrouter_api"], {"codex_visible": False, "openai_visible": False, "openrouter_visible": True}))
    return issues


def _evaluate_provider_state(
    name: str,
    actual: dict[str, object],
    expected: dict[str, bool],
) -> list[ConfigUIFunctionalReviewIssue]:
    if all(actual.get(key) == value for key, value in expected.items()):
        return []
    return [
        ConfigUIFunctionalReviewIssue(
            f"provider_{name}_toggle",
            f"切换到 {name} 后，provider 子面板显隐状态不正确。",
        )
    ]
