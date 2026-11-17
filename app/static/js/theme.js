// Light/dark toggle. The initial theme is set by the inline script in <head>.
(function () {
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", function () {
    var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("mik-theme", next); } catch (e) {}
  });
})();
