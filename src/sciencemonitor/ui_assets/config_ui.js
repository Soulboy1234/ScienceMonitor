(function () {
  const validViews = ["overview", "weekly-report", "deep-read", "manual-llm", "settings"];
  const links = Array.from(document.querySelectorAll("[data-nav-target]"));
  const views = Array.from(document.querySelectorAll("[data-view]"));
  const titleEl = document.querySelector("[data-current-title]");
  const resizer = document.querySelector("[data-sidebar-resizer]");
  const mainEl = document.querySelector(".main");
  const root = document.documentElement;
  const providerSelect = document.querySelector("[data-provider-select]");
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
})();
