from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .config import project_root
from .config_ui_review import _sample_rendered_html

ALL_CONFIG_UI_VIEWS = ("overview", "weekly-report", "deep-read", "manual-llm", "settings")
VIEW_TITLES = {
    "overview": "总览",
    "weekly-report": "周报",
    "deep-read": "深度解读",
    "manual-llm": "人工中转",
    "settings": "设置",
}
VIEW_ARTIFACTS = {
    "overview": "overview-960.png",
    "weekly-report": "weekly-report-960.png",
    "deep-read": "deep-read-960.png",
    "manual-llm": "manual-llm-960.png",
    "settings": "settings-960.png",
}
GLOBAL_UI_FILES = {
    "src/sciencemonitor/config_ui.py",
    "src/sciencemonitor/config_ui_page.py",
    "src/sciencemonitor/config_ui_page_sections.py",
    "src/sciencemonitor/ui_assets/config_ui.css",
    "src/sciencemonitor/ui_assets/config_ui.js",
}
MULTI_VIEW_UI_FILES = {
    "src/sciencemonitor/config_ui_result_cards.py": ("weekly-report", "deep-read", "manual-llm"),
    "src/sciencemonitor/config_ui_state_summary.py": ("overview", "weekly-report", "deep-read", "manual-llm"),
    "src/sciencemonitor/token_monitor.py": ("overview",),
}


@dataclass(frozen=True)
class ConfigUIVisualReviewIssue:
    category: str
    message: str


@dataclass(frozen=True)
class ConfigUIVisualReviewReport:
    passed: bool
    issues: list[ConfigUIVisualReviewIssue]
    artifacts: list[Path]
    reviewed_views: tuple[str, ...] = field(default_factory=tuple)


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


def infer_visual_review_targets(changed_paths: Iterable[str]) -> tuple[str, ...]:
    inferred: list[str] = []
    for raw_path in changed_paths:
        path = str(raw_path or "").strip().replace("\\", "/")
        if not path:
            continue
        lower = path.lower()
        if path in GLOBAL_UI_FILES:
            return ALL_CONFIG_UI_VIEWS
        explicit = MULTI_VIEW_UI_FILES.get(path)
        if explicit:
            for view in explicit:
                if view not in inferred:
                    inferred.append(view)
            continue
        if "deep" in lower and "config_ui" in lower:
            _append_view(inferred, "deep-read")
            continue
        if "manual" in lower or "chatgpt_web_manual" in lower:
            _append_view(inferred, "manual-llm")
            continue
        if "report" in lower and "config_ui" in lower:
            _append_view(inferred, "weekly-report")
            continue
        if "settings" in lower or ("paths" in lower and "config_ui" in lower):
            _append_view(inferred, "settings")
            continue
        if "token" in lower or "overview" in lower:
            _append_view(inferred, "overview")
    return tuple(inferred)


def resolve_visual_review_targets(
    *,
    targets: Iterable[str] | None = None,
    changed_paths: Iterable[str] | None = None,
) -> tuple[str, ...]:
    normalized_targets = _normalize_targets(targets or ())
    if normalized_targets:
        return normalized_targets
    inferred_targets = infer_visual_review_targets(changed_paths or ())
    if inferred_targets:
        return inferred_targets
    return ALL_CONFIG_UI_VIEWS


def run_config_ui_visual_review(
    root: Path | None = None,
    *,
    targets: Iterable[str] | None = None,
    changed_paths: Iterable[str] | None = None,
) -> ConfigUIVisualReviewReport:
    project = root or project_root()
    reviewed_views = resolve_visual_review_targets(targets=targets, changed_paths=changed_paths)
    issues: list[ConfigUIVisualReviewIssue] = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on runtime env
        return ConfigUIVisualReviewReport(
            passed=False,
            issues=[ConfigUIVisualReviewIssue("missing_browser_runtime", f"Playwright 不可用：{exc}")],
            artifacts=[],
            reviewed_views=reviewed_views,
        )
    try:
        metrics, artifacts = _run_visual_browser_session(project, sync_playwright, reviewed_views)
    except Exception as exc:  # pragma: no cover - depends on runtime env
        return ConfigUIVisualReviewReport(
            passed=False,
            issues=[ConfigUIVisualReviewIssue("browser_execution_failed", f"UI 视觉检查执行失败：{exc}")],
            artifacts=[],
            reviewed_views=reviewed_views,
        )
    if "overview" in reviewed_views:
        issues.extend(_evaluate_overview_token_visual_metrics(metrics))
    if "weekly-report" in reviewed_views:
        issues.extend(_evaluate_weekly_report_visual_metrics(metrics))
    if "deep-read" in reviewed_views:
        issues.extend(
            _evaluate_simple_view_metrics(
                metrics,
                prefix="deep_read",
                missing_message="深度解读页缺少视觉检查所需的关键 DOM 元素。",
                required_panels=("deep-read-status", "deep-read-single", "deep-read-folder", "deep-read-stats", "latest-deep-read"),
            )
        )
    if "manual-llm" in reviewed_views:
        issues.extend(
            _evaluate_simple_view_metrics(
                metrics,
                prefix="manual_llm",
                missing_message="人工中转页缺少视觉检查所需的关键 DOM 元素。",
                required_panels=("manual-activity", "manual-create", "manual-import", "latest-manual-result"),
            )
        )
    if "settings" in reviewed_views:
        issues.extend(
            _evaluate_simple_view_metrics(
                metrics,
                prefix="settings",
                missing_message="设置页缺少视觉检查所需的关键 DOM 元素。",
                required_panels=("provider-settings", "path-settings", "tag-management"),
            )
        )
    return ConfigUIVisualReviewReport(
        passed=not issues,
        issues=issues,
        artifacts=artifacts,
        reviewed_views=reviewed_views,
    )


def render_config_ui_visual_review_summary(report: ConfigUIVisualReviewReport) -> str:
    raw_views = getattr(report, "reviewed_views", ())
    if not isinstance(raw_views, (list, tuple)):
        raw_views = ()
    reviewed_views = ", ".join(str(item) for item in raw_views) if raw_views else "none"
    lines = [
        "Config UI visual review summary:",
        f"- reviewed_views={reviewed_views}",
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


def _run_visual_browser_session(project: Path, sync_playwright, reviewed_views: tuple[str, ...]):
    html = _sample_rendered_html(project)
    artifact_dir = _artifact_dir(project)
    collectors = {
        "overview": _collect_overview_token_visual_metrics,
        "weekly-report": _collect_weekly_report_visual_metrics,
        "deep-read": lambda page: _collect_simple_view_metrics(
            page,
            metric_prefix="deep_read",
            view_name="deep-read",
            panels=("deep-read-status", "deep-read-single", "deep-read-folder", "deep-read-stats", "latest-deep-read"),
        ),
        "manual-llm": lambda page: _collect_simple_view_metrics(
            page,
            metric_prefix="manual_llm",
            view_name="manual-llm",
            panels=("manual-activity", "manual-create", "manual-import", "latest-manual-result"),
        ),
        "settings": lambda page: _collect_simple_view_metrics(
            page,
            metric_prefix="settings",
            view_name="settings",
            panels=("provider-settings", "path-settings", "tag-management"),
        ),
    }
    metrics: dict[str, float | bool | str | list[str]] = {}
    artifacts: list[Path] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "config_ui_sample.html"
        html_path.write_text(html, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 1100})
            page.goto(html_path.as_uri())
            page.wait_for_timeout(200)
            for view_name in reviewed_views:
                page.evaluate(_activate_view_script(view_name, VIEW_TITLES[view_name]))
                page.wait_for_timeout(100)
                artifact_path = artifact_dir / VIEW_ARTIFACTS[view_name]
                page.screenshot(path=str(artifact_path), full_page=True)
                metrics.update(collectors[view_name](page))
                artifacts.append(artifact_path)
            browser.close()
    return metrics, artifacts


def _collect_overview_token_visual_metrics(page) -> dict[str, float | bool]:
    return page.evaluate(
        """
        () => {
          const tokenRoot = document.querySelector('[data-token-usage-root]');
          const statsStrip = document.querySelector('.run-stats-card .stats-strip');
          const statChips = statsStrip ? Array.from(statsStrip.querySelectorAll('.stat-chip')) : [];
          const statChipTops = statChips.map((node) => node.getBoundingClientRect().top);
          const overviewRoot = document.querySelector('.view[data-view="overview"]');
          const llmCard = overviewRoot ? Array.from(overviewRoot.querySelectorAll('.card')).find((node) => (node.querySelector('h4')?.textContent || '').includes('LLM 状态')) : null;
          const runtimePanel = overviewRoot ? Array.from(overviewRoot.querySelectorAll('.panel')).find((node) => (node.querySelector('h3')?.textContent || '').includes('运行状态检查')) : null;
          const runtimeRows = runtimePanel ? Array.from(runtimePanel.querySelectorAll('.status-check-row')) : [];
          const chart = tokenRoot?.querySelector('.token-chart-days');
          const columns = chart ? Array.from(chart.querySelectorAll('.token-chart-column')) : [];
          const xAxisSlots = tokenRoot ? Array.from(tokenRoot.querySelectorAll('.token-chart-axis-slot.visible')) : [];
          const xAxisLabels = xAxisSlots.map((node) => node.querySelector('.token-chart-axis-label')).filter(Boolean);
          const yTickContainer = tokenRoot?.querySelector('.token-chart-axis-y-ticks');
          const yTicks = yTickContainer ? Array.from(yTickContainer.querySelectorAll('.token-y-tick')) : [];
          const legend = tokenRoot?.querySelector('.token-chart-legend');
          const summary = tokenRoot?.querySelector('.token-usage-summary');
          const yAxis = tokenRoot?.querySelector('.token-chart-axis-y');
          const xAxis = tokenRoot?.querySelector('.token-chart-axis-x');
          const xAxisLabelGrid = tokenRoot?.querySelector('.token-chart-axis-labels');
          const grid = tokenRoot?.querySelector('.token-chart-grid');
          const gridLines = grid ? Array.from(grid.querySelectorAll('.token-grid-line')) : [];
          const tooltip = tokenRoot?.querySelector('[data-token-chart-tooltip]');
          const nonZeroColumns = columns.filter((node) => node.classList.contains('has-value'));
          const chartRect = chart?.getBoundingClientRect();
          const xAxisRect = xAxis?.getBoundingClientRect();
          const labelGridRect = xAxisLabelGrid?.getBoundingClientRect();
          const chartScaleMax = yTicks.length
            ? Math.max(...yTicks.map((node) => Number((node.textContent || '0').replaceAll(',', '')) || 0))
            : 0;
          const yTickCenters = yTicks.map((node) => {
            const rect = node.getBoundingClientRect();
            return rect.top + rect.height / 2;
          });
          const gridLineTops = gridLines.map((node) => node.getBoundingClientRect().top);
          const zeroTickBottomDelta = yTickCenters.length && chartRect
            ? Math.abs(yTickCenters[yTickCenters.length - 1] - chartRect.bottom)
            : 999;
          let maxTickDelta = 999;
          if (yTickCenters.length && yTickCenters.length === gridLineTops.length) {
            maxTickDelta = Math.max(...yTickCenters.map((center, index) => Math.abs(center - gridLineTops[index])));
          }
          const xLabelOverflow = xAxisLabels.some((node) => {
            const rect = node.getBoundingClientRect();
            return !xAxisRect || rect.left < xAxisRect.left - 1 || rect.right > xAxisRect.right + 1;
          });
          const ratioDeltas = nonZeroColumns.map((node) => {
            const totalTokens = Number(node.dataset.tokenTotal || 0);
            const totalHeightPercent = Array.from(node.querySelectorAll('.token-chart-segment'))
              .reduce((sum, seg) => sum + (Number.parseFloat(seg.style.height || '0') || 0), 0);
            const expectedRatio = chartScaleMax > 0 ? totalTokens / chartScaleMax : 0;
            const actualRatio = totalHeightPercent / 100;
            return Math.abs(expectedRatio - actualRatio);
          });
          const pixelRatioDeltas = nonZeroColumns.map((node) => {
            const totalTokens = Number(node.dataset.tokenTotal || 0);
            const totalPixelHeight = Array.from(node.querySelectorAll('.token-chart-segment'))
              .reduce((sum, seg) => sum + seg.getBoundingClientRect().height, 0);
            const expectedRatio = chartScaleMax > 0 ? totalTokens / chartScaleMax : 0;
            const actualRatio = chartRect && chartRect.height > 0 ? totalPixelHeight / chartRect.height : 0;
            return Math.abs(expectedRatio - actualRatio);
          });
          const xSlotCenters = xAxisSlots.map((node) => {
            const rect = node.getBoundingClientRect();
            return rect.left + (rect.width / 2);
          });
          const xSlotSpacings = [];
          for (let index = 0; index < xSlotCenters.length - 1; index += 1) {
            xSlotSpacings.push(xSlotCenters[index + 1] - xSlotCenters[index]);
          }
          const xSlotSpacingVariance = xSlotSpacings.length
            ? Math.max(...xSlotSpacings) - Math.min(...xSlotSpacings)
            : 0;
          const nonZeroColumnOverflow = nonZeroColumns.map((node) => {
            const rect = node.getBoundingClientRect();
            if (!chartRect) return 999;
            return Math.max(0, chartRect.left - rect.left, rect.right - chartRect.right);
          });
          return {
            overviewTokenMissing: !(tokenRoot && chart && summary && xAxisLabelGrid && yTickContainer),
            overviewStatsChipCount: statChips.length,
            overviewStatsTopVariance: statChipTops.length ? Math.max(...statChipTops) - Math.min(...statChipTops) : 999,
            overviewRuntimeRows: runtimeRows.length,
            overviewLlmTop: llmCard ? llmCard.getBoundingClientRect().top : 99999,
            overviewRuntimeTop: runtimePanel ? runtimePanel.getBoundingClientRect().top : 99999,
            overviewColumnCount: columns.length,
            overviewNonZeroColumns: nonZeroColumns.length,
            overviewLegendCount: legend ? legend.children.length : 0,
            overviewChartHeight: chartRect ? chartRect.height : 0,
            overviewSummaryText: summary ? summary.textContent || '' : '',
            overviewXAxisLabelCount: xAxisSlots.length,
            overviewXAxisBelowChart: xAxisRect && chartRect ? xAxisRect.top >= chartRect.bottom - 1 : false,
            overviewYAxisMissing: !yAxis,
            overviewXAxisMissing: !xAxis,
            overviewYAxisTickContainerMissing: !yTickContainer,
            overviewXAxisLabelGridMissing: !xAxisLabelGrid,
            overviewGridCount: gridLines.length,
            overviewYTickCount: yTicks.length,
            overviewYTickMaxDelta: maxTickDelta,
            overviewZeroTickBottomDelta: zeroTickBottomDelta,
            overviewMaxRatioDelta: ratioDeltas.length ? Math.max(...ratioDeltas) : 0,
            overviewMaxPixelRatioDelta: pixelRatioDeltas.length ? Math.max(...pixelRatioDeltas) : 0,
            overviewXLabelOverflow: xLabelOverflow,
            overviewXLabelSpacingVariance: xSlotSpacingVariance,
            overviewNonZeroColumnOverflow: nonZeroColumnOverflow.length ? Math.max(...nonZeroColumnOverflow) : 0,
            overviewTooltipMissing: !tooltip,
          };
        }
        """
    )


def _collect_weekly_report_visual_metrics(page) -> dict[str, float | bool]:
    return page.evaluate(
        """
        () => {
          const form = document.querySelector('.weekly-report-form-card');
          const journals = document.querySelector('.weekly-report-journals-card');
          const main = document.querySelector('.main');
          const formStack = document.querySelector('.weekly-report-form-card .form-stack');
          if (!form || !journals || !main || !formStack) {
            return {weeklyMissing: true};
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
            weeklyMissing: false,
            weeklyFormWidth: formRect.width,
            weeklyJournalsWidth: journalsRect.width,
            weeklySameRowDelta: Math.abs(formRect.top - journalsRect.top),
            weeklyFormStackGap: parseFloat(getComputedStyle(formStack).gap || '0'),
            weeklyGapMin: gaps.length ? Math.min(...gaps) : 0,
            weeklyGapMax: gaps.length ? Math.max(...gaps) : 0,
            weeklyGapVariance: gaps.length ? Math.max(...gaps) - Math.min(...gaps) : 0,
            weeklyMainScrollWidth: main.scrollWidth,
            weeklyMainClientWidth: main.clientWidth,
            weeklyDocumentScrollWidth: document.documentElement.scrollWidth,
            weeklyDocumentClientWidth: document.documentElement.clientWidth,
          };
        }
        """
    )


def _collect_simple_view_metrics(page, *, metric_prefix: str, view_name: str, panels: tuple[str, ...]) -> dict[str, float | bool | list[str]]:
    return page.evaluate(
        """
        ({ metricPrefix, viewName, panels }) => {
          const root = document.querySelector(`.view[data-view="${viewName}"]`);
          const main = document.querySelector('.main');
          if (!root || !main) {
            return { [`${metricPrefix}_missing`]: true };
          }
          const missingPanels = panels.filter((panel) => !root.querySelector(`[data-ui-panel="${panel}"]`));
          return {
            [`${metricPrefix}_missing`]: false,
            [`${metricPrefix}_missing_panels`]: missingPanels,
            [`${metricPrefix}_main_scroll_width`]: main.scrollWidth,
            [`${metricPrefix}_main_client_width`]: main.clientWidth,
            [`${metricPrefix}_document_scroll_width`]: document.documentElement.scrollWidth,
            [`${metricPrefix}_document_client_width`]: document.documentElement.clientWidth,
          };
        }
        """,
        {"metricPrefix": metric_prefix, "viewName": view_name, "panels": list(panels)},
    )


def _evaluate_weekly_report_visual_metrics(metrics: dict[str, float | bool]) -> list[ConfigUIVisualReviewIssue]:
    if metrics.get("weeklyMissing"):
        return [ConfigUIVisualReviewIssue("missing_elements", "周报页缺少视觉检查所需的关键 DOM 元素。")]
    issues: list[ConfigUIVisualReviewIssue] = []
    if metrics["weeklySameRowDelta"] > 24:
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_cards_wrapped",
                f"周报页首行卡片未保持同一行，顶部偏移差为 {metrics['weeklySameRowDelta']:.1f}px。",
            )
        )
    ratio = metrics["weeklyFormWidth"] / metrics["weeklyJournalsWidth"] if metrics["weeklyJournalsWidth"] else 0
    if not (2.4 <= ratio <= 3.6):
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_cards_ratio",
                f"周报页首行卡片宽度比异常，当前约为 {ratio:.2f}:1。",
            )
        )
    if not (10 <= metrics["weeklyFormStackGap"] <= 14):
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_form_stack_gap",
                f"周报表单主栈 gap 异常，当前为 {metrics['weeklyFormStackGap']:.1f}px。",
            )
        )
    if metrics["weeklyGapVariance"] > 4:
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_form_spacing_variance",
                f"周报表单纵向间距不均匀，最小 {metrics['weeklyGapMin']:.1f}px，最大 {metrics['weeklyGapMax']:.1f}px。",
            )
        )
    if metrics["weeklyMainScrollWidth"] > metrics["weeklyMainClientWidth"] + 2:
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_main_overflow",
                f"周报页主内容区出现横向溢出，scrollWidth={metrics['weeklyMainScrollWidth']}，clientWidth={metrics['weeklyMainClientWidth']}。",
            )
        )
    if metrics["weeklyDocumentScrollWidth"] > metrics["weeklyDocumentClientWidth"] + 2:
        issues.append(
            ConfigUIVisualReviewIssue(
                "weekly_document_overflow",
                f"周报页整体出现横向溢出，scrollWidth={metrics['weeklyDocumentScrollWidth']}，clientWidth={metrics['weeklyDocumentClientWidth']}。",
            )
        )
    return issues


def _evaluate_overview_token_visual_metrics(metrics: dict[str, float | bool]) -> list[ConfigUIVisualReviewIssue]:
    if metrics.get("overviewTokenMissing"):
        return [ConfigUIVisualReviewIssue("missing_token_chart", "总览页缺少 token 图表或其关键 DOM。")]
    issues: list[ConfigUIVisualReviewIssue] = []
    if metrics["overviewStatsChipCount"] != 4:
        issues.append(ConfigUIVisualReviewIssue("overview_stats_count", f"运行统计卡片数量异常，当前为 {metrics['overviewStatsChipCount']}，预期 4。"))
    if metrics["overviewStatsTopVariance"] > 4:
        issues.append(
            ConfigUIVisualReviewIssue(
                "overview_stats_wrapped",
                f"运行统计四卡片没有保持同一行，顶部偏移差为 {metrics['overviewStatsTopVariance']:.1f}px。",
            )
        )
    if metrics["overviewLlmTop"] >= metrics["overviewRuntimeTop"]:
        issues.append(ConfigUIVisualReviewIssue("overview_llm_order", "LLM 状态没有位于运行状态检查之上。"))
    if metrics["overviewRuntimeRows"] != 2:
        issues.append(
            ConfigUIVisualReviewIssue(
                "overview_runtime_rows",
                f"运行状态检查紧凑行数异常，当前为 {metrics['overviewRuntimeRows']}，预期 2。",
            )
        )
    if metrics["overviewColumnCount"] != 30:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_day_count",
                f"总览页 token 图列数异常，当前为 {metrics['overviewColumnCount']}，预期 30。",
            )
        )
    if metrics["overviewLegendCount"] < 1:
        issues.append(ConfigUIVisualReviewIssue("token_chart_legend_missing", "总览页 token 图缺少 provider 图例。"))
    if metrics["overviewChartHeight"] < 180:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_too_short",
                f"总览页 token 图高度过小，当前约 {metrics['overviewChartHeight']:.1f}px。",
            )
        )
    if metrics["overviewYAxisMissing"] or metrics["overviewXAxisMissing"]:
        issues.append(ConfigUIVisualReviewIssue("token_chart_axes_missing", "总览页 token 图缺少横轴或纵轴。"))
    if metrics.get("overviewYAxisTickContainerMissing"):
        issues.append(ConfigUIVisualReviewIssue("token_chart_y_ticks_missing", "总览页 token 图缺少纵轴刻度容器。"))
    if metrics["overviewGridCount"] < 5:
        issues.append(ConfigUIVisualReviewIssue("token_chart_grid_missing", "总览页 token 图缺少足够的网格线。"))
    if not (5 <= int(metrics.get("overviewYTickCount", 0) or 0) <= 8):
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_y_tick_range",
                f"总览页 token 图纵轴刻度数异常，当前为 {metrics['overviewYTickCount']}，应在 5 到 8 之间。",
            )
        )
    if metrics["overviewYTickCount"] != metrics["overviewGridCount"]:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_tick_count_mismatch",
                f"总览页 token 图纵轴刻度数与网格线数不一致，刻度={metrics['overviewYTickCount']}，网格={metrics['overviewGridCount']}。",
            )
        )
    tick_delta = metrics.get("overviewYTickMaxDelta", 999)
    if not isinstance(tick_delta, (int, float)):
        tick_delta = 999
    if float(tick_delta) > 14:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_tick_alignment",
                f"总览页 token 图纵轴刻度和网格线错位，最大偏差约 {float(tick_delta):.1f}px。",
            )
        )
    zero_tick_delta = metrics.get("overviewZeroTickBottomDelta", 999)
    if isinstance(zero_tick_delta, (int, float)) and float(zero_tick_delta) > 3:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_zero_baseline_alignment",
                f"总览页 token 图 0 刻度没有与底部基线重合，偏差约 {float(zero_tick_delta):.1f}px。",
            )
        )
    if metrics["overviewTooltipMissing"]:
        issues.append(ConfigUIVisualReviewIssue("token_chart_tooltip_missing", "总览页 token 图缺少 hover tooltip 容器。"))
    if "今天" not in str(metrics.get("overviewSummaryText", "")) or "本周" not in str(metrics.get("overviewSummaryText", "")):
        issues.append(ConfigUIVisualReviewIssue("token_chart_summary_missing", "总览页 token 图缺少今天/本周/本月摘要文本。"))
    if metrics.get("overviewXAxisLabelGridMissing"):
        issues.append(ConfigUIVisualReviewIssue("token_chart_x_labels_missing", "总览页 token 图缺少横轴日期标签容器。"))
    if int(metrics.get("overviewXAxisLabelCount", 0) or 0) != 6:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_x_labels_count",
                f"总览页 token 图横轴标签数量异常，当前为 {metrics['overviewXAxisLabelCount']}，预期 6。",
            )
        )
    if not metrics.get("overviewXAxisBelowChart"):
        issues.append(ConfigUIVisualReviewIssue("token_chart_x_axis_position", "总览页 token 图日期标签没有位于坐标轴下方。"))
    ratio_delta = metrics.get("overviewMaxRatioDelta", 0)
    if isinstance(ratio_delta, (int, float)) and float(ratio_delta) > 0.03:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_value_mapping",
                f"总览页 token 图柱高和纵轴数值映射不一致，最大比例偏差约 {float(ratio_delta):.3f}。",
            )
        )
    pixel_ratio_delta = metrics.get("overviewMaxPixelRatioDelta", 0)
    if isinstance(pixel_ratio_delta, (int, float)) and float(pixel_ratio_delta) > 0.05:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_pixel_height_mapping",
                f"总览页 token 图的实际像素柱高与纵轴数值不一致，最大比例偏差约 {float(pixel_ratio_delta):.3f}。",
            )
        )
    if metrics.get("overviewXLabelOverflow"):
        issues.append(ConfigUIVisualReviewIssue("token_chart_x_label_overflow", "总览页 token 图横轴日期标签超出了标签面板。"))
    x_label_spacing_variance = metrics.get("overviewXLabelSpacingVariance", 0)
    if isinstance(x_label_spacing_variance, (int, float)) and float(x_label_spacing_variance) > 2:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_x_label_spacing",
                f"总览页 token 图横轴标签槽位没有均匀分布，最大间距差约 {float(x_label_spacing_variance):.1f}px。",
            )
        )
    column_overflow = metrics.get("overviewNonZeroColumnOverflow", 0)
    if isinstance(column_overflow, (int, float)) and float(column_overflow) > 1:
        issues.append(
            ConfigUIVisualReviewIssue(
                "token_chart_column_overflow",
                f"总览页 token 图的非零 bar 超出了图表可视区，最大溢出约 {float(column_overflow):.1f}px。",
            )
        )
    return issues


def _evaluate_simple_view_metrics(
    metrics: dict[str, float | bool | list[str]],
    *,
    prefix: str,
    missing_message: str,
    required_panels: tuple[str, ...],
) -> list[ConfigUIVisualReviewIssue]:
    metrics_prefix = prefix.replace("-", "_")
    if metrics.get(f"{metrics_prefix}_missing"):
        return [ConfigUIVisualReviewIssue(f"{metrics_prefix}_missing", missing_message)]
    issues: list[ConfigUIVisualReviewIssue] = []
    missing_panels = metrics.get(f"{metrics_prefix}_missing_panels", [])
    if isinstance(missing_panels, list) and missing_panels:
        issues.append(
            ConfigUIVisualReviewIssue(
                f"{metrics_prefix}_missing_panels",
                f"{VIEW_TITLES[prefix.replace('_', '-')]} 页缺少关键面板 hook：{', '.join(str(item) for item in missing_panels)}。",
            )
        )
    main_scroll = float(metrics.get(f"{metrics_prefix}_main_scroll_width", 0) or 0)
    main_client = float(metrics.get(f"{metrics_prefix}_main_client_width", 0) or 0)
    doc_scroll = float(metrics.get(f"{metrics_prefix}_document_scroll_width", 0) or 0)
    doc_client = float(metrics.get(f"{metrics_prefix}_document_client_width", 0) or 0)
    if main_scroll > main_client + 2:
        issues.append(
            ConfigUIVisualReviewIssue(
                f"{metrics_prefix}_main_overflow",
                f"{VIEW_TITLES[prefix.replace('_', '-')]} 页主内容区出现横向溢出，scrollWidth={main_scroll:.0f}，clientWidth={main_client:.0f}。",
            )
        )
    if doc_scroll > doc_client + 2:
        issues.append(
            ConfigUIVisualReviewIssue(
                f"{metrics_prefix}_document_overflow",
                f"{VIEW_TITLES[prefix.replace('_', '-')]} 页整体出现横向溢出，scrollWidth={doc_scroll:.0f}，clientWidth={doc_client:.0f}。",
            )
        )
    return issues


def _normalize_targets(targets: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in targets:
        target = str(raw or "").strip()
        if target in ALL_CONFIG_UI_VIEWS and target not in normalized:
            normalized.append(target)
    return tuple(normalized)


def _append_view(targets: list[str], view: str) -> None:
    if view in ALL_CONFIG_UI_VIEWS and view not in targets:
        targets.append(view)
