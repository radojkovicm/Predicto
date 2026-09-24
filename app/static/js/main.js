// Theme toggle — the icon swap is pure CSS keyed off [data-theme]
(function () {
  const html = document.documentElement;
  let saved = "dark";
  try { saved = localStorage.getItem("predicto-theme") || "dark"; } catch (e) {}
  html.setAttribute("data-theme", saved);

  document.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("#theme-toggle")) return;
    const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", next);
    try { localStorage.setItem("predicto-theme", next); } catch (e) {}
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

// Mobile menu — opened from the header hamburger or the tab bar's "More"
(function () {
  document.addEventListener("click", function (e) {
    const menu = document.getElementById("mobile-menu");
    if (!menu) return;
    const toggle = e.target.closest && e.target.closest("#hamburger, #hamburger-tab");
    if (toggle) {
      menu.classList.toggle("open");
    } else if (!menu.contains(e.target)) {
      menu.classList.remove("open");
    }
  });
})();

// Score steppers: big +/- buttons so a tip is two taps, no keyboard needed
(function () {
  document.addEventListener("click", function (e) {
    const btn = e.target.closest && e.target.closest(".step-btn");
    if (!btn) return;
    const input = document.getElementById(btn.dataset.target);
    if (!input) return;
    // An empty box counts as 0, so the first "+" lands on 1 and "-" on 0.
    const current = parseInt(input.value, 10) || 0;
    input.value = Math.min(99, Math.max(0, current + parseInt(btn.dataset.step, 10)));
    input.classList.add("bump");
    setTimeout(function () { input.classList.remove("bump"); }, 120);
  });

  // Selecting the whole value on focus makes typing a new score one keystroke.
  document.addEventListener("focusin", function (e) {
    if (e.target.classList && e.target.classList.contains("goals-input")) e.target.select();
  });
})();

// Kickoff countdown on the match page
(function () {
  const els = document.querySelectorAll(".countdown[data-kickoff]");
  if (!els.length) return;

  function fmt(ms) {
    const mins = Math.floor(ms / 60000);
    const d = Math.floor(mins / 1440), h = Math.floor((mins % 1440) / 60), m = mins % 60;
    if (d > 0) return d + "d " + h + "h";
    if (h > 0) return h + "h " + m + "m";
    return m + "m";
  }

  function tick() {
    els.forEach(function (el) {
      const ms = new Date(el.dataset.kickoff) - new Date();
      el.textContent = ms > 0 ? "Kicks off in " + fmt(ms) : "Kicked off";
    });
  }
  tick();
  setInterval(tick, 30000);
})();

// Day headers on the match list: say "Today" / "Tomorrow" in the viewer's calendar
(function () {
  const labels = document.querySelectorAll(".day-label[data-date]");
  if (!labels.length) return;
  function iso(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  const now = new Date();
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  const names = {};
  names[iso(now)] = "Today";
  names[iso(tomorrow)] = "Tomorrow";
  names[iso(yesterday)] = "Yesterday";
  labels.forEach(function (el) {
    const name = names[el.dataset.date];
    if (name) {
      el.textContent = name + " · " + el.textContent;
      if (name === "Today") el.classList.add("is-today");
    }
  });
})();

// Demo login: tapping a sample account fills the form in
document.addEventListener("click", function (e) {
  const btn = e.target.closest && e.target.closest(".demo-cred");
  if (!btn) return;
  const user = document.getElementById("username");
  const pass = document.getElementById("password");
  if (user && pass) {
    user.value = btn.dataset.user;
    pass.value = btn.dataset.pass;
    pass.focus();
  }
});

// Auto-dismiss flash messages after 5 s
(function () {
  setTimeout(function () {
    document.querySelectorAll(".flash:not(.flash-sticky)").forEach(function (el) {
      el.style.transition = "opacity .5s";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 500);
    });
  }, 5000);
})();
