(function () {
  "use strict";

  /* ---------- Show / hide password ---------- */
  document.querySelectorAll('input[type="password"]').forEach(function (input) {
    var wrap = document.createElement("div");
    wrap.className = "pw-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "pw-toggle";
    button.textContent = "Show";
    button.setAttribute("aria-label", "Show password");
    button.addEventListener("click", function () {
      var hidden = input.type === "password";
      input.type = hidden ? "text" : "password";
      button.textContent = hidden ? "Hide" : "Show";
      button.setAttribute("aria-label", hidden ? "Hide password" : "Show password");
    });
    wrap.appendChild(button);
  });

  /* ---------- Password strength ---------- */
  function scorePassword(value) {
    var score = 0;
    if (value.length >= 10) score += 1;
    if (value.length >= 14) score += 1;
    if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
    if (/\d/.test(value)) score += 1;
    if (/[^A-Za-z0-9]/.test(value)) score += 1;
    if (/^(.)\1+$/.test(value) || /^(password|12345|qwerty)/i.test(value)) score = 0;
    return Math.min(score, 4);
  }

  var LEVELS = [
    { text: "Too weak", color: "#b42318" },
    { text: "Weak", color: "#c2570c" },
    { text: "Okay", color: "#b88a00" },
    { text: "Good", color: "#4c8b3a" },
    { text: "Strong", color: "#1b7f4b" }
  ];

  document.querySelectorAll("input[data-strength]").forEach(function (input) {
    var meter = document.createElement("div");
    meter.className = "meter";
    var bar = document.createElement("div");
    bar.className = "meter-bar";
    meter.appendChild(bar);
    var label = document.createElement("p");
    label.className = "meter-label";
    label.setAttribute("aria-live", "polite");

    var anchor = input.closest(".pw-wrap") || input;
    anchor.parentNode.insertBefore(meter, anchor.nextSibling);
    meter.parentNode.insertBefore(label, meter.nextSibling);

    input.addEventListener("input", function () {
      var value = input.value;
      if (!value) {
        bar.style.width = "0";
        label.textContent = "";
        return;
      }
      var level = scorePassword(value);
      bar.style.width = ((level + 1) * 20) + "%";
      bar.style.background = LEVELS[level].color;
      label.textContent = LEVELS[level].text;
    });
  });

  /* ---------- Live ID card preview on the register page ---------- */
  var form = document.querySelector("[data-register-form]");
  var card = document.querySelector(".id-card.is-placeholder");
  if (form && card) {
    var el = {
      name: card.querySelector("[data-card-name]"),
      initials: card.querySelector("[data-card-initials]"),
      program: card.querySelector("[data-card-program]"),
      year: card.querySelector("[data-card-year]")
    };
    var field = function (key) {
      return form.querySelector('[data-preview="' + key + '"]');
    };
    var first = field("first");
    var last = field("last");
    var program = field("program");
    var year = field("year");

    var DEFAULTS = { name: "Your name", program: "Your program", initials: "?" };

    var update = function () {
      var f = first ? first.value.trim() : "";
      var l = last ? last.value.trim() : "";
      var fullName = (f + " " + l).trim();

      el.name.textContent = fullName || DEFAULTS.name;
      el.initials.textContent = ((f.charAt(0) + l.charAt(0)).toUpperCase()) || DEFAULTS.initials;
      el.program.textContent = (program && program.value) || DEFAULTS.program;
      el.year.textContent = year && year.value ? "Year " + year.value : "";
      card.classList.toggle("has-input", Boolean(fullName || (program && program.value)));
    };

    [first, last, program, year].forEach(function (input) {
      if (input) {
        input.addEventListener("input", update);
        input.addEventListener("change", update);
      }
    });
    update();
  }
})();
