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

  function menuList(source) {
    var list = document.createElement("ul");
    for (var item of source.children) {
      var section = item.querySelector(":scope > nav:not(.md-nav--secondary) > ul");
      var original = item.querySelector(":scope > a.md-nav__link, :scope > .md-nav__container > a");
      var row = document.createElement("li");
      var contents = row;
      if (section) {
        var details = document.createElement("details");
        var summary = document.createElement("summary");
        summary.textContent = section.parentElement.querySelector(".md-nav__title").textContent.trim();
        details.open = item.classList.contains("md-nav__item--active");
        details.appendChild(summary);
        row.appendChild(details);
        contents = details;
      }
      if (original) {
        var link = document.createElement("a");
        link.href = original.href;
        link.textContent = section ? "Overview" : original.textContent.trim();
        if (original.href.split("#")[0] === location.href.split(/[?#]/)[0] || original.classList.contains("md-nav__link--active")) {
          link.className = "is-active";
          link.setAttribute("aria-current", "page");
        }
        contents.appendChild(link);
      }
      if (section) contents.appendChild(menuList(section));
      list.appendChild(row);
    }
    return list;
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
    b.setAttribute("aria-controls", panelEl.id);
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

    var tree = document.querySelector(".md-sidebar--primary .md-nav--primary > ul");
    if (!tree) return;
    var navPanel = document.createElement("nav");
    navPanel.id = "vab-nav-panel";
    navPanel.className = "vab-panel";
    navPanel.hidden = true;
    navPanel.setAttribute("aria-label", "Site navigation");
    navPanel.appendChild(menuList(tree));
    var navBtn = button("vab-nav-btn", "Site navigation", NAV_SVG, navPanel);
    inner.prepend(navBtn);
    navBtn.after(navPanel);

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
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") {
    var trigger = document.querySelector('.vab-btn[aria-expanded="true"]');
    if (trigger) { closeAll(); trigger.focus(); }
  } });

  if (window.document$) window.document$.subscribe(init);
  else document.addEventListener("DOMContentLoaded", init);
})();
