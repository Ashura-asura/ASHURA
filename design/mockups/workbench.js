/* ASHURA workbench design prototype interactions. Mockup only: no backend. */
(function () {
  "use strict";

  var railItems = Array.prototype.slice.call(document.querySelectorAll("[data-route]"));
  var views = Array.prototype.slice.call(document.querySelectorAll("[data-view]"));
  var title = document.getElementById("topbar-workspace");
  var context = document.getElementById("topbar-context");

  var NAMES = {
    command: "Command Center",
    execution: "Execution Studio",
    knowledge: "Knowledge Studio",
    system: "System Monitor",
    settings: "Settings & Security"
  };

  var CONTEXT = {
    command: "Trace architecture",
    execution: "Turn #121 · arithmetic",
    knowledge: "Deployment window review",
    system: "Runtime and storage",
    settings: "Privacy and access"
  };

  function route(name) {
    views.forEach(function (view) {
      view.classList.toggle("is-active", view.dataset.view === name);
    });
    railItems.forEach(function (item) {
      var active = item.dataset.route === name;
      item.classList.toggle("is-active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    if (title) title.textContent = NAMES[name] || name;
    if (context) context.textContent = CONTEXT[name] || "";
    document.body.classList.remove("nav-open", "sessions-open", "context-open", "evidence-open",
      "operations-open", "memory-open");
    if (scrim) scrim.hidden = true;
    var main = document.getElementById("workspace");
    if (main) main.scrollTop = 0;
  }

  railItems.forEach(function (item) {
    item.addEventListener("click", function () { route(item.dataset.route); });
  });

  // Theme toggle cycles dark -> light -> dark for the mockup.
  var themeToggle = document.getElementById("theme-toggle");
  var themeIcon = document.getElementById("theme-icon");
  var themeOptions = Array.prototype.slice.call(document.querySelectorAll("[data-theme-choice]"));

  function applyTheme(theme, persist) {
    var resolved = theme;
    if (theme === "system") {
      resolved = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    }
    document.documentElement.dataset.theme = resolved;
    if (themeIcon) {
      themeIcon.innerHTML = '<use href="#icon-' + (resolved === "dark" ? "sun" : "moon") + '"/>';
    }
    themeOptions.forEach(function (option) {
      var active = option.dataset.themeChoice === theme || option.dataset.themeChoice === resolved;
      option.classList.toggle("is-active", option.dataset.themeChoice === theme);
      option.setAttribute("aria-checked", String(option.dataset.themeChoice === theme));
    });
    if (persist) {
      try { localStorage.setItem("ashura-theme", theme); } catch (error) { /* storage may be blocked */ }
    }
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true);
    });
  }

  themeOptions.forEach(function (option) {
    option.addEventListener("click", function () {
      applyTheme(option.dataset.themeChoice, true);
    });
  });

  var stored = null;
  try { stored = localStorage.getItem("ashura-theme"); } catch (error) { stored = null; }
  applyTheme(stored || "dark", false);

  // Drawers on small screens.
  var scrim = document.getElementById("scrim");

  function toggleDrawer(cls) {
    var open = document.body.classList.contains(cls);
    ["nav-open", "sessions-open", "context-open", "evidence-open", "operations-open",
      "memory-open"].forEach(function (name) {
      document.body.classList.remove(name);
    });
    if (!open) document.body.classList.add(cls);
    if (scrim) scrim.hidden = !document.body.classList.contains("nav-open") &&
      !document.body.classList.contains("sessions-open") &&
      !document.body.classList.contains("context-open") &&
      !document.body.classList.contains("evidence-open") &&
      !document.body.classList.contains("operations-open") &&
      !document.body.classList.contains("memory-open");
  }

  var menuToggle = document.getElementById("menu-toggle");
  if (menuToggle) menuToggle.addEventListener("click", function () { toggleDrawer("nav-open"); });
  var sessionsToggle = document.getElementById("sessions-toggle");
  if (sessionsToggle) sessionsToggle.addEventListener("click", function () { toggleDrawer("sessions-open"); });
  var contextToggle = document.getElementById("context-toggle");
  if (contextToggle) contextToggle.addEventListener("click", function () { toggleDrawer("context-open"); });
  var evidenceToggle = document.getElementById("evidence-toggle");
  if (evidenceToggle) evidenceToggle.addEventListener("click", function () { toggleDrawer("evidence-open"); });
  var operationsToggle = document.getElementById("operations-toggle");
  if (operationsToggle) operationsToggle.addEventListener("click", function () { toggleDrawer("operations-open"); });
  var memoryToggle = document.getElementById("memory-toggle");
  if (memoryToggle) memoryToggle.addEventListener("click", function () { toggleDrawer("memory-open"); });
  if (scrim) scrim.addEventListener("click", function () {
    ["nav-open", "sessions-open", "context-open", "evidence-open", "operations-open",
      "memory-open"].forEach(function (name) {
      document.body.classList.remove(name);
    });
    scrim.hidden = true;
  });

  // Close buttons inside drawers.
  Array.prototype.slice.call(document.querySelectorAll("[data-close-drawer]")).forEach(function (button) {
    button.addEventListener("click", function () {
      ["nav-open", "sessions-open", "context-open", "evidence-open", "operations-open",
        "memory-open"].forEach(function (name) {
        document.body.classList.remove(name);
      });
      if (scrim) scrim.hidden = true;
    });
  });

  // Inspector tabs.
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".context-tab"));
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      tabs.forEach(function (other) {
        other.classList.toggle("is-active", other === tab);
        other.setAttribute("aria-selected", String(other === tab));
      });
    });
  });

  // Knowledge tabs.
  var knowledgeTabs = Array.prototype.slice.call(document.querySelectorAll(".knowledge-tab"));
  knowledgeTabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      knowledgeTabs.forEach(function (other) {
        other.classList.toggle("is-active", other === tab);
        other.setAttribute("aria-selected", String(other === tab));
      });
    });
  });

  // Selection rows in the mockups.
  function selectRows(selector) {
    var rows = Array.prototype.slice.call(document.querySelectorAll(selector));
    rows.forEach(function (row) {
      row.addEventListener("click", function () {
        rows.forEach(function (other) { other.classList.toggle("is-active", other === row); });
      });
    });
  }
  selectRows(".session-row");
  selectRows(".operation-row");
  selectRows(".memory-row");

  // Raw record disclosure.
  var rawToggle = document.querySelector(".raw-toggle");
  if (rawToggle) {
    rawToggle.addEventListener("click", function () {
      var expanded = rawToggle.getAttribute("aria-expanded") === "true";
      rawToggle.setAttribute("aria-expanded", String(!expanded));
    });
  }

  // Keyboard shortcut hint: Ctrl/Cmd+K focuses the session filter.
  document.addEventListener("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      var target = document.querySelector(".search-input input");
      if (target) target.focus();
    }
  });
})();
