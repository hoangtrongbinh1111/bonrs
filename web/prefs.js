// Runs before the first paint: theme and language chosen on this browser (no flash of the wrong theme).
(function () {
  try {
    var t = localStorage.getItem("bonrs.theme"), l = localStorage.getItem("bonrs.lang");
    if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
    document.documentElement.lang = l === "en" ? "en" : "vi";
  } catch (e) { /* storage blocked: system theme, Vietnamese */ }
})();
