document.addEventListener("click", function (e) {
  var title = e.target.closest(".md-nav--secondary > .md-nav__title");
  if (!title) return;
  var nav = title.parentElement;
  var open = nav.classList.toggle("toc-open");
  title.setAttribute("aria-expanded", open ? "true" : "false");
});

function initToc() {
  document.querySelectorAll(".md-nav--secondary > .md-nav__title").forEach(function (t) {
    t.setAttribute("role", "button");
    t.setAttribute("tabindex", "0");
    t.setAttribute("aria-expanded", t.parentElement.classList.contains("toc-open") ? "true" : "false");
    t.onkeydown = function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); t.click(); }
    };
  });
}
if (window.document$) window.document$.subscribe(initToc);
else document.addEventListener("DOMContentLoaded", initToc);
