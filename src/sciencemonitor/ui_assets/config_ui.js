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
  const deepReadStatusRoot = document.querySelector("[data-deep-read-status-root]");
  const activeTaskTextRoot = document.querySelector("[data-active-task-text]");
  const activeTaskDetailRoot = document.querySelector("[data-active-task-detail]");
  const tokenUsageRoot = document.querySelector("[data-token-usage-root]");
  const taskTriggerButtons = Array.from(document.querySelectorAll("[data-task-trigger]"));
  const latestResultBodies = Array.from(document.querySelectorAll("[data-latest-result-body]"));
  const uiToken = (document.querySelector('meta[name="sciencemonitor-ui-token"]') || {}).content || "";
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

  function withToken(path) {
    if (!uiToken) return path;
    const separator = path.includes("?") ? "&" : "?";
    return `${path}${separator}token=${encodeURIComponent(uiToken)}`;
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
      : (reportJob.status === "paused_quota" || reportJob.status === "paused_timeout")
        ? "status-check-item ok"
      : reportJob.status === "error"
        ? "status-check-item error"
        : "status-check-item";
    const lines = [];
    const elapsed = formatDuration(reportJob.elapsed_seconds);
    const estimated = formatDuration(reportJob.estimated_total_seconds);
    if (elapsed) lines.push(`运行时长：${elapsed}`);
    if (reportJob.status === "paused_quota") lines.push("状态：等待额度恢复后继续");
    if (reportJob.status === "paused_timeout") lines.push("状态：本地模型超时，可调整超时后继续");
    if (estimated) lines.push(`预计总时长：${estimated}`);
    if (Number(reportJob.fetched_count || 0) > 0) lines.push(`已抓取：${reportJob.fetched_count}`);
    if (Number(reportJob.kept_count || 0) > 0) lines.push(`已保留：${reportJob.kept_count}`);
    if (Number(reportJob.paper_count || 0) > 0) lines.push(`周报论文：${reportJob.paper_count}`);
    if (Number(reportJob.journal_count || 0) > 0) lines.push(`期刊数：${reportJob.journal_count}`);
    if (Number(reportJob.source_total || 0) > 0) lines.push(`来源进度：${reportJob.source_index || 0}/${reportJob.source_total}`);
    if (Number(reportJob.summary_total || 0) > 0) lines.push(`单篇总结：${reportJob.summary_completed || 0}/${reportJob.summary_total}`);
    if (Number(reportJob.summary_skipped || 0) > 0) lines.push(`未完成单篇：${reportJob.summary_skipped}`);
    if (reportJob.summary_model) lines.push(`模型：${reportJob.summary_model}`);
    else if (reportJob.summary_provider) lines.push(`后端：${reportJob.summary_provider}`);
    if (reportJob.summary_provider === "codex_local" && reportJob.summary_reasoning_effort) lines.push(`推理强度：${reportJob.summary_reasoning_effort}`);
    if (Number(reportJob.summary_avg_tokens || 0) > 0) lines.push(`平均单篇 token：${reportJob.summary_avg_tokens}`);
    else if (["codex_local", "openai_api", "openrouter_api", "ollama_api"].includes(reportJob.summary_provider) && Number(reportJob.summary_total || 0) > 0 && Number(reportJob.summary_token_samples || 0) === 0) lines.push("平均单篇 token：本次未新调用");
    const currentSourceHtml = reportJob.stage === "fetching" && reportJob.current_source
      ? `<p>当前来源：<span class="mono">${escapeHtml(reportJob.current_source)}</span></p>`
      : "";
    const titleAlreadyHasJournal = reportJob.summary_current_journal
      && reportJob.summary_current_title
      && reportJob.summary_current_title.startsWith(`${reportJob.summary_current_journal} · `);
    const currentSummaryLabel = titleAlreadyHasJournal
      ? reportJob.summary_current_title
      : reportJob.summary_current_journal && reportJob.summary_current_title
      ? `${reportJob.summary_current_journal} · ${reportJob.summary_current_title}`
      : (reportJob.summary_current_title || "");
    const currentSummaryHtml = currentSummaryLabel
      ? `<p>当前单篇：${escapeHtml(currentSummaryLabel)}</p>`
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

  function renderDeepReadStatus(deepReadJob) {
    if (!deepReadStatusRoot) return;
    const list = deepReadStatusRoot.querySelector(".status-check-list");
    if (!list) return;
    if (!deepReadJob || Object.keys(deepReadJob).length === 0) {
      list.innerHTML = '<div class="status-check-item" data-deep-read-status-body><strong>未运行</strong><p>当前没有正在执行的深度解读任务。</p></div>';
      return;
    }
    const statusClass = deepReadJob.status === "success"
      ? "status-check-item ok"
      : (deepReadJob.status === "paused_quota" || deepReadJob.status === "paused_timeout")
        ? "status-check-item ok"
      : deepReadJob.status === "error"
        ? "status-check-item error"
        : "status-check-item";
    const lines = [];
    const elapsed = formatDuration(deepReadJob.elapsed_seconds);
    const estimated = formatDuration(deepReadJob.estimated_total_seconds);
    const total = Number(deepReadJob.total || 0);
    const completed = Number(deepReadJob.completed || 0);
    const successCount = Number(deepReadJob.success_count || 0);
    const failureCount = Number(deepReadJob.failure_count || 0);
    if (elapsed) lines.push(`运行时长：${elapsed}`);
    if (estimated) lines.push(`预计总时长：${estimated}`);
    if (total > 1) lines.push(`批量进度：${completed}/${total}`);
    if (total > 1 || successCount || failureCount) {
      lines.push(`成功：${successCount}`);
      lines.push(`失败：${failureCount}`);
    }
    if (deepReadJob.source_kind) lines.push(`全文来源：${deepReadJob.source_kind}`);
    if (deepReadJob.output_path) {
      const name = String(deepReadJob.output_path).split(/[\\/]/).pop();
      if (name) lines.push(`最新输出：${name}`);
    }
    const currentPdfHtml = deepReadJob.current_pdf
      ? `<p>当前 PDF：${escapeHtml(deepReadJob.current_pdf)}</p>`
      : "";
    list.innerHTML = `
      <div class="${statusClass}" data-deep-read-status-body>
        <strong>${escapeHtml(deepReadJob.step || "处理中")}</strong>
        <p>${escapeHtml(deepReadJob.message || "暂无状态信息。")}</p>
        ${lines.length ? `<p>${escapeHtml(lines.join(" · "))}</p>` : ""}
        ${currentPdfHtml}
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
      if (!button.dataset.originalLabel) button.dataset.originalLabel = button.textContent || "";
      if (hasRunningTask) {
        button.setAttribute("title", "当前已有任务正在运行，请等待结束后再启动新的任务。");
      } else if (button.dataset.submitting === "true") {
        button.textContent = button.dataset.originalLabel || button.textContent;
        button.dataset.submitting = "false";
      }
    });
  }

  function bindTaskSubmitFeedback() {
    const labels = {
      "weekly-report": "周报任务",
      "deep-read": "深度解读",
      "deep-read-folder": "批量深度解读",
      "manual-create": "人工中转请求",
      "manual-import": "人工中转导入"
    };
    document.querySelectorAll("form").forEach((form) => {
      form.addEventListener("submit", (event) => {
        const submitter = event.submitter;
        if (!submitter || !submitter.dataset || !submitter.dataset.taskTrigger) return;
        const label = labels[submitter.dataset.taskTrigger] || "任务";
        if (!submitter.dataset.originalLabel) submitter.dataset.originalLabel = submitter.textContent || "";
        submitter.dataset.submitting = "true";
        submitter.disabled = true;
        submitter.textContent = "已提交，处理中...";
        if (activeTaskTextRoot) activeTaskTextRoot.textContent = `${label} · 已提交`;
        if (activeTaskDetailRoot) activeTaskDetailRoot.textContent = "请求已发送，等待后端返回结果。";
      });
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
      const response = await window.fetch(withToken(`/latest-result?kind=${encodeURIComponent(kind)}`), { cache: "no-store" });
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
      const response = await window.fetch(withToken("/ui-status"), { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json();
      const reportJob = payload.report_job || {};
      const deepReadJob = payload.deep_read_job || {};
      const activeTask = payload.active_task || {};
      renderActiveTask(activeTask, payload.manual_pending || 0);
      updateTaskButtons(activeTask);
      renderWeeklyReportStatus(reportJob);
      renderDeepReadStatus(deepReadJob);
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

  function updateFolderPickerStatus(input, picker, files) {
    const status = picker.querySelector("[data-folder-status]");
    const pathTargetId = input.dataset.folderPathTarget || "";
    const pathInput = pathTargetId ? document.getElementById(pathTargetId) : null;
    const pdfFiles = Array.from(files || []).filter((file) => String(file.name || "").toLowerCase().endsWith(".pdf"));
    if (status) {
      status.textContent = pdfFiles.length
        ? `已选择 ${pdfFiles.length} 个 PDF`
        : "未选择 PDF";
    }
    const first = pdfFiles[0];
    if (first && pathInput && first.path && String(first.path).startsWith("/")) {
      pathInput.value = String(first.path).replace(/[\\/][^\\/]*$/, "");
    }
  }

  function readAllDirectoryEntries(reader) {
    return new Promise((resolve) => {
      const entries = [];
      const readBatch = () => {
        reader.readEntries((batch) => {
          if (!batch.length) {
            resolve(entries);
            return;
          }
          entries.push(...batch);
          readBatch();
        });
      };
      readBatch();
    });
  }

  function entryToFiles(entry) {
    if (!entry) return Promise.resolve([]);
    if (entry.isFile) {
      return new Promise((resolve) => entry.file((file) => resolve([file]), () => resolve([])));
    }
    if (entry.isDirectory) {
      return readAllDirectoryEntries(entry.createReader())
        .then((entries) => Promise.all(entries.map(entryToFiles)))
        .then((groups) => groups.flat());
    }
    return Promise.resolve([]);
  }

  async function filesFromDrop(event) {
    const items = Array.from((event.dataTransfer && event.dataTransfer.items) || []);
    if (items.length && typeof items[0].webkitGetAsEntry === "function") {
      const groups = await Promise.all(items.map((item) => entryToFiles(item.webkitGetAsEntry())));
      return groups.flat();
    }
    return Array.from((event.dataTransfer && event.dataTransfer.files) || []);
  }

  function bindFolderPickers() {
    document.querySelectorAll("[data-folder-picker]").forEach((picker) => {
      const input = picker.querySelector("[data-folder-input]");
      if (!input) return;
      input.addEventListener("change", () => updateFolderPickerStatus(input, picker, input.files));
      picker.addEventListener("dragover", (event) => {
        event.preventDefault();
        picker.classList.add("drag-over");
      });
      picker.addEventListener("dragleave", () => picker.classList.remove("drag-over"));
      picker.addEventListener("drop", async (event) => {
        event.preventDefault();
        picker.classList.remove("drag-over");
        const files = (await filesFromDrop(event)).filter((file) => String(file.name || "").toLowerCase().endsWith(".pdf"));
        if (files.length && typeof window.DataTransfer === "function") {
          const transfer = new window.DataTransfer();
          files.forEach((file) => transfer.items.add(file));
          input.files = transfer.files;
        }
        updateFolderPickerStatus(input, picker, files);
      });
    });
  }

  if (weeklyReportStatusRoot || deepReadStatusRoot) {
    pollUiStatus();
    pollTimer = window.setInterval(pollUiStatus, 3000);
    window.addEventListener("beforeunload", stopPolling);
  }
  if (activeTaskTextRoot) {
    renderActiveTask({}, 0);
  }
  if (taskTriggerButtons.length) {
    updateTaskButtons({});
    bindTaskSubmitFeedback();
  }
  if (tokenUsageRoot) {
    tokenUsageRoot.addEventListener("pointermove", handleTokenChartPointer);
    tokenUsageRoot.addEventListener("pointerleave", hideTokenTooltip);
  }
  bindFolderPickers();
})();
