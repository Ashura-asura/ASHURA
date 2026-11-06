/* Theme bootstrap. Classic script so the effective theme is set before first paint.
   The stored value is a preference: "system" follows the OS live. */
(function () {
  "use strict";
  var KEY = "ashura-theme";
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  var preference = "system";
  try {
    var saved = window.localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light" || saved === "system") preference = saved;
  } catch (error) {
    preference = "system";
  }

  function effective(value) {
    if (value === "system") return media && media.matches ? "light" : "dark";
    return value === "light" ? "light" : "dark";
  }

  function paint() {
    root.setAttribute("data-theme", effective(preference));
    root.setAttribute("data-theme-preference", preference);
  }

  paint();
  if (media) {
    var onChange = function () {
      if (preference === "system") paint();
    };
    if (media.addEventListener) media.addEventListener("change", onChange);
    else if (media.addListener) media.addListener(onChange);
  }

  window.ashuraTheme = {
    effective: function () { return effective(preference); },
    preference: function () { return preference; },
    set: function (value) {
      preference = value === "light" || value === "dark" || value === "system" ? value : "system";
      try { window.localStorage.setItem(KEY, preference); } catch (error) { /* storage may be disabled */ }
      paint();
      return effective(preference);
    }
  };
})();
