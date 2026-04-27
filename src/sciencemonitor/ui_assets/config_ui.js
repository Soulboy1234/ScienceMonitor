(function () {
  const validViews = ["overview", "weekly-report", "deep-read", "manual-llm", "settings"];
  const links = Array.from(document.querySelectorAll("[data-nav-target]"));
  const views = Array.from(document.querySelectorAll("[data-view]"));
  const titleEl = document.querySelector("[data-current-title]");
  const resizer = document.querySelector("[data-sidebar-resizer]");
  const mainEl = document.querySelector(".main");
  const root = document.documentElement;
  const providerSelect = document.querySelector("[data-provider-select]");
  const weeklyReportStatusRoot = document.querySelector("[data-weekly-report-status-root]");
  const activeTaskTextRoot = document.querySelector("[data-active-task-text]");
  const activeTaskDetailRoot = document.querySelector("[data-active-task-detail]");
  const tokenUsageRoot = document.querySelector("[data-token-usage-root]");
  const taskTriggerButtons = Array.from(document.querySelectorAll("[data-task-trigger]"));
  const latestResultBodies = Array.from(document.querySelectorAll("[data-latest-result-body]"));
  let pollTimer = null;
  const meta = {
    "overview": { title: "总览" },
    "weekly-report": { title: "周报" },
    "deep-read": { title: "深度解读" },
    "manual-llm": { title: "人工中转" },
    "settings": { title: "设置" }
  };
  function activate(viewId) {
    const current = validViews.includes(viewId) ? viewId : "overview";
    views.forEach((view) => view.classList.toggle("active", view.dataset.view === current));
    links.forEach((link) => link.classList.toggle("active", link.dataset.navTarget === current));
    if (titleEl && meta[current]) titleEl.textContent = meta[current].title;
    if (mainEl) {
      if (typeof mainEl.scrollTo === "function") {
        mainEl.scrollTo({ top: 0, left: 0, behavior: "auto" });
      } else {
        mainEl.scrollTop = 0;
        mainEl.scrollLeft = 0;
      }
    }
  }
  links.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = link.dataset.navTarget || "overview";
      window.location.hash = target;
      activate(target);
    });
  });
  window.addEventListener("hashchange", () => activate(window.location.hash.replace(/^#/, "")));
  activate(window.location.hash.replace(/^#/, ""));

  const widthKey = "sciencemonitor.sidebar.width";
  const minWidth = 230;
  const maxWidth = 460;
  const savedWidth = parseInt(window.localStorage.getItem(widthKey) || "", 10);
  if (!Number.isNaN(savedWidth)) {
    root.style.setProperty("--sidebar-width", `${Math.min(maxWidth, Math.max(minWidth, savedWidth))}px`);
  }

  function applySidebarWidth(clientX) {
    const width = Math.min(maxWidth, Math.max(minWidth, clientX));
    root.style.setProperty("--sidebar-width", `${width}px`);
    window.localStorage.setItem(widthKey, String(width));
  }

  if (resizer) {
    const stop = () => {
      resizer.classList.remove("dragging");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", stop);
    };
    const onMove = (event) => {
      applySidebarWidth(event.clientX);
    };
    resizer.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      resizer.classList.add("dragging");
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", stop);
    });
  }

  function updateProviderPanels() {
    if (!providerSelect) return;
    const provider = providerSelect.value || "codex_local";
    document.querySelectorAll("[data-provider-only]").forEach((node) => {
      node.classList.toggle("active", node.getAttribute("data-provider-only") === provider);
    });
  }

  if (providerSelect) {
    providerSelect.addEventListener("change", updateProviderPanels);
    updateProviderPanels();
  }

  function formatDuration(value) {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric) || numeric <= 0) return "";
    const rounded = Math.round(numeric);
    const minutes = Math.floor(rounded / 60);
    const seconds = rounded % 60;
    if (minutes >= 60) {
      const hours = Math.floor(minutes / 60);
      const remainMinutes = minutes % 60;
      return `${hours}h ${remainMinutes}m`;
    }
    if (minutes > 0) return `${minutes}m ${seconds}s`;
    return `${seconds}s`;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function renderWeeklyReportStatus(reportJob) {
    if (!weeklyReportStatusRoot) return;
    const list = weeklyReportStatusRoot.querySelector(".status-check-list");
    if (!list) return;
    if (!reportJob || Object.keys(reportJob).length === 0) {
      list.innerHTML = '<div class="status-check-item" data-weekly-report-status-body><strong>未运行</strong><p>当前没有正在执行的周报任务。</p></div>';
      return;
    }
    const statusClass = reportJob.status === "success"
      ? "status-check-item ok"
      : reportJob.status === "paused_quota"
        ? "status-check-item ok"
      : reportJob.status === "error"
        ? "status-check-item error"
        : "status-check-item";
    const lines = [];
    const elapsed = formatDuration(reportJob.elapsed_seconds);
    const estimated = formatDuration(reportJob.estimated_total_seconds);
    if (elapsed) lines.push(`运行时长：${elapsed}`);
    if (reportJob.status === "paused_quota") lines.push("状态：等待额度恢复后继续");
    if (estimated) lines.push(`预计总时长：${estimated}`);
    if (Number(reportJob.fetched_count || 0) > 0) lines.push(`已抓取：${reportJob.fetched_count}`);
    if (Number(reportJob.kept_count || 0) > 0) lines.push(`已保留：${reportJob.kept_count}`);
    if (Number(reportJob.paper_count || 0) > 0) lines.push(`周报论文：${reportJob.paper_count}`);
    if (Number(reportJob.journal_count || 0) > 0) lines.push(`期刊数：${reportJob.journal_count}`);
    if (Number(reportJob.source_total || 0) > 0) lines.push(`来源进度：${reportJob.source_index || 0}/${reportJob.source_total}`);
    if (Number(reportJob.summary_total || 0) > 0) lines.push(`单篇总结：${reportJob.summary_completed || 0}/${reportJob.summary_total}`);
    if (reportJob.summary_model) lines.push(`模型：${reportJob.summary_model}`);
    else if (reportJob.summary_provider) lines.push(`后端：${reportJob.summary_provider}`);
    if (reportJob.summary_provider === "codex_local" && reportJob.summary_reasoning_effort) lines.push(`推理强度：${reportJob.summary_reasoning_effort}`);
    if (reportJob.summary_provider === "codex_local" && Number(reportJob.summary_avg_tokens || 0) > 0) lines.push(`平均单篇 token：${reportJob.summary_avg_tokens}`);
    else if (reportJob.summary_provider === "codex_local" && Number(reportJob.summary_total || 0) > 0 && Number(reportJob.summary_token_samples || 0) === 0) lines.push("平均单篇 token：本次未新调用");
    const currentSourceHtml = reportJob.current_source
      ? `<p>当前来源：<span class="mono">${escapeHtml(reportJob.current_source)}</span></p>`
      : "";
    const currentSummaryHtml = reportJob.summary_current_title
      ? `<p>当前单篇：${escapeHtml(reportJob.summary_current_title)}</p>`
      : "";
    list.innerHTML = `
      <div class="${statusClass}" data-weekly-report-status-body>
        <strong>${escapeHtml(reportJob.step || "处理中")}</strong>
        <p>${escapeHtml(reportJob.message || "暂无状态信息。")}</p>
        ${lines.length ? `<p>${escapeHtml(lines.join(" · "))}</p>` : ""}
        ${currentSourceHtml}
        ${currentSummaryHtml}
      </div>`;
  }

  function renderActiveTask(activeTask, manualPending) {
    if (!activeTaskTextRoot) return;
    if (!activeTask || Object.keys(activeTask).length === 0) {
      if (Number(manualPending || 0) > 0) {
        activeTaskTextRoot.textContent = "人工中转待处理";
        if (activeTaskDetailRoot) activeTaskDetailRoot.textContent = `当前有 ${manualPending} 个请求等待响应。`;
      } else {
        activeTaskTextRoot.textContent = "当前无运行任务";
        if (activeTaskDetailRoot) activeTaskDetailRoot.textContent = "没有正在执行的后台任务。";
      }
      return;
    }
    const label = activeTask.label || "任务";
    const step = activeTask.step || "";
    const message = activeTask.message || "任务正在运行中。";
    activeTaskTextRoot.textContent = step ? `${label} · ${step}` : label;
    if (activeTaskDetailRoot) activeTaskDetailRoot.textContent = message;
  }

  function updateTaskButtons(activeTask) {
    const hasRunningTask = !!(activeTask && Object.keys(activeTask).length);
    taskTriggerButtons.forEach((button) => {
      button.disabled = hasRunningTask;
      if (hasRunningTask) {
        button.setAttribute("title", "当前已有任务正在运行，请等待结束后再启动新的任务。");
      }
    });
  }

  function hideTokenTooltip() {
    if (!tokenUsageRoot) return;
    const tooltip = tokenUsageRoot.querySelector("[data-token-chart-tooltip]");
    if (!tooltip) return;
    tooltip.hidden = true;
    tooltip.textContent = "";
  }

  function handleTokenChartPointer(event) {
    if (!tokenUsageRoot) return;
    const column = event.target.closest(".token-chart-column");
    const frame = tokenUsageRoot.querySelector("[data-token-chart-frame]");
    const tooltip = tokenUsageRoot.querySelector("[data-token-chart-tooltip]");
    if (!frame || !tooltip || !column || !tokenUsageRoot.contains(column)) {
      hideTokenTooltip();
      return;
    }
    const frameRect = frame.getBoundingClientRect();
    const columnRect = column.getBoundingClientRect();
    const dateText = column.dataset.tokenDate || "";
    const totalTokens = Number(column.dataset.tokenTotal || 0);
    const runCount = Number(column.dataset.tokenRuns || 0);
    tooltip.innerHTML = `${escapeHtml(dateText)}<br>${escapeHtml(totalTokens.toLocaleString("en-US"))} tokens${runCount > 0 ? ` / ${escapeHtml(String(runCount))} 次` : ""}`;
    tooltip.style.left = `${columnRect.left - frameRect.left + (columnRect.width / 2)}px`;
    tooltip.style.top = `${columnRect.top - frameRect.top - 8}px`;
    tooltip.hidden = false;
  }

  async function refreshLatestResult(kind) {
    const target = latestResultBodies.find((node) => node.dataset.latestResultBody === kind);
    if (!target) return;
    try {
      const response = await window.fetch(`/latest-result?kind=${encodeURIComponent(kind)}`, { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json();
      target.innerHTML = payload.html || "";
      target.dataset.latestResultPath = payload.path || "";
      target.dataset.latestResultRevision = payload.revision || "";
    } catch (_error) {
      // Ignore transient polling failures.
    }
  }

  function refreshChangedResults(latestResults) {
    if (!latestResults) return;
    latestResultBodies.forEach((node) => {
      const kind = node.dataset.latestResultBody || "";
      const incoming = latestResults[kind] || {};
      const incomingRevision = incoming.revision || "";
      const incomingPath = incoming.path || "";
      if (incomingRevision !== (node.dataset.latestResultRevision || "") || incomingPath !== (node.dataset.latestResultPath || "")) {
        refreshLatestResult(kind);
      }
    });
  }

  async function pollUiStatus() {
    try {
      const response = await window.fetch("/ui-status", { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json();
      const reportJob = payload.report_job || {};
      const activeTask = payload.active_task || {};
      renderActiveTask(activeTask, payload.manual_pending || 0);
      updateTaskButtons(activeTask);
      renderWeeklyReportStatus(reportJob);
      if (tokenUsageRoot && typeof payload.token_usage_html === "string" && payload.token_usage_html) {
        tokenUsageRoot.innerHTML = payload.token_usage_html;
        hideTokenTooltip();
      }
      refreshChangedResults(payload.latest_results || {});
    } catch (_error) {
      // Ignore transient polling failures.
    }
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  if (weeklyReportStatusRoot) {
    pollUiStatus();
    pollTimer = window.setInterval(pollUiStatus, 3000);
    window.addEventListener("beforeunload", stopPolling);
  }
  if (activeTaskTextRoot) {
    renderActiveTask({}, 0);
  }
  if (taskTriggerButtons.length) {
    updateTaskButtons({});
  }
  if (tokenUsageRoot) {
    tokenUsageRoot.addEventListener("pointermove", handleTokenChartPointer);
    tokenUsageRoot.addEventListener("pointerleave", hideTokenTooltip);
  }
})();
