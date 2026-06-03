// Theme toggle
(function () {
  const html = document.documentElement;
  const saved = localStorage.getItem("predicto-theme") || "dark";
  html.setAttribute("data-theme", saved);

  function setToggleLabel(theme) {
    document.querySelectorAll("#theme-toggle").forEach((btn) => {
      btn.textContent = theme === "dark" ? "☀️" : "🌙";
    });
  }

  setToggleLabel(saved);

  document.addEventListener("click", function (e) {
    if (e.target && e.target.id === "theme-toggle") {
      const current = html.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      html.setAttribute("data-theme", next);
      localStorage.setItem("predicto-theme", next);
      setToggleLabel(next);
    }
  });
})();

// Mobile hamburger menu
(function () {
  document.addEventListener("click", function (e) {
    if (e.target && e.target.id === "hamburger") {
      const menu = document.getElementById("mobile-menu");
      if (menu) menu.classList.toggle("open");
    }
  });
})();

// Auto-dismiss flash messages after 5 s
(function () {
  setTimeout(function () {
    document.querySelectorAll(".flash").forEach(function (el) {
      el.style.transition = "opacity .5s";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 500);
    });
  }, 5000);
})();
