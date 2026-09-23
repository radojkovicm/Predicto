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

// CSRF — every POST form gets the session's token attached automatically,
// so templates never need a hidden field of their own.
function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

document.addEventListener("submit", function (e) {
  const form = e.target;
  if (form.tagName === "FORM" && form.method.toUpperCase() === "POST" && !form.querySelector('input[name="csrf_token"]')) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "csrf_token";
    input.value = getCsrfToken();
    form.appendChild(input);
  }
});

// Delete confirmation
window.confirmDelete = function (title, actionUrl) {
  if (confirm(title)) {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = actionUrl;
    const csrfInput = document.createElement("input");
    csrfInput.type = "hidden";
    csrfInput.name = "csrf_token";
    csrfInput.value = getCsrfToken();
    form.appendChild(csrfInput);
    document.body.appendChild(form);
    form.submit();
  }
};

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
