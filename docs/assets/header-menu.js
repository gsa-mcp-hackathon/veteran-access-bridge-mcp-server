(function () {
  var NAV_SVG = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/></svg>';
  var TOC_SVG = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M3 9h14V7H3zm0 4h14v-2H3zm0 4h14v-2H3zm16 0h2v-2h-2zm0-10v2h2V7zm0 6h2v-2h-2z"/></svg>';

  function collect(selector) {
    var out = [];
    document.querySelectorAll(selector + " a.md-nav__link[href]").forEach(function (a) {
      if (selector.indexOf("primary") > -1 && a.closest(".md-nav--secondary")) return;
      var depth = 0, el = a.parentElement;
      while (el && !el.matches(".md-sidebar")) {
        if (el.matches("li.md-nav__item")) depth++;
        el = el.parentElement;
      }
      out.push({ href: a.getAttribute("href"), text: a.textContent.trim(), depth: Math.max(depth - 1, 0), active: a.classList.contains("md-nav__link--active") });
    });
    return out;
  }

  function panel(id, items) {
    var p = document.createElement("nav");
    p.className = "vab-panel";
    p.id = id;
    p.hidden = true;
    var ul = document.createElement("ul");
    items.forEach(function (i) {
      var li = document.createElement("li");
      li.style.paddingLeft = i.depth * 14 + "px";
      var a = document.createElement("a");
      a.href = i.href;
      a.textContent = i.text;
      if (i.active) a.className = "is-active";
      li.appendChild(a);
      ul.appendChild(li);
    });
    p.appendChild(ul);
    return p;
  }

  function closeAll() {
    document.querySelectorAll(".vab-panel").forEach(function (p) { p.hidden = true; });
    document.querySelectorAll(".vab-btn").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
  }

  function button(cls, label, html, panelEl) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "vab-btn " + cls;
    b.setAttribute("aria-label", label);
    b.setAttribute("aria-expanded", "false");
    b.innerHTML = html;
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = panelEl.hidden;
      closeAll();
      panelEl.hidden = !open;
      b.setAttribute("aria-expanded", open ? "true" : "false");
    });
    return b;
  }

  function init() {
    var inner = document.querySelector(".md-header__inner");
    if (!inner || inner.querySelector(".vab-btn")) return;

    if (location.pathname.split("/").includes("developer-guide")) {
      // Use the theme's navigation tree so sections and the current page survive.
      document.body.classList.add("vab-guide");
      var sidebar = document.querySelector(".md-sidebar--primary");
      sidebar.id = "vab-guide-sidebar";
      var toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "vab-btn vab-guide-toggle";
      toggle.innerHTML = NAV_SVG;
      toggle.setAttribute("aria-label", "Developer Guide navigation");
      toggle.setAttribute("aria-controls", sidebar.id);
      var expanded = !document.querySelector(".vab-start");
      function showSidebar(show) {
        document.body.classList.toggle("vab-guide-expanded", show);
        toggle.setAttribute("aria-expanded", String(show));
      }
      showSidebar(expanded);
      toggle.addEventListener("click", function () {
        showSidebar(toggle.getAttribute("aria-expanded") !== "true");
      });
      inner.prepend(toggle);
    } else {
      var navPanel = panel("vab-nav-panel", collect(".md-sidebar--primary"));
      var navBtn = button("vab-nav-btn", "Page navigation", NAV_SVG, navPanel);
      inner.insertBefore(navBtn, inner.firstChild);
      navBtn.after(navPanel);
    }

    var tocItems = collect(".md-sidebar--secondary");
    if (tocItems.length) {
      var tocPanel = panel("vab-toc-panel", tocItems);
      var tocBtn = button("vab-toc-btn", "On this page", TOC_SVG + "<span>On this page</span>", tocPanel);
      var wrap = document.createElement("div");
      wrap.className = "vab-toc-wrap";
      wrap.appendChild(tocBtn);
      wrap.appendChild(tocPanel);
      inner.insertBefore(wrap, inner.querySelector(".md-header__source"));
    }
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".vab-panel") || e.target.closest(".vab-panel a")) closeAll();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeAll(); });

  if (window.document$) window.document$.subscribe(init);
  else document.addEventListener("DOMContentLoaded", init);
})();
