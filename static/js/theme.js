/* ===================== THEME =====================
   Priority order:
   1. User's saved manual choice (localStorage)
   2. Device system preference (prefers-color-scheme)
   3. Default: light
   ================================================= */

// Set theme before first paint to avoid flash of wrong theme
(function () {
    var saved = localStorage.getItem("theme");
    if (saved) {
        document.documentElement.setAttribute("data-theme", saved);
    } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
        document.documentElement.setAttribute("data-theme", "dark");
    }
    // No saved + system is light = no attribute needed (light is default)
})();

// React to live system theme changes only when user has no saved preference
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {
    if (!localStorage.getItem("theme")) {
        if (e.matches) {
            document.documentElement.setAttribute("data-theme", "dark");
        } else {
            document.documentElement.removeAttribute("data-theme");
        }
    }
});

// Manual toggle: saves explicit choice to localStorage, overriding system preference
var toggleTheme = function () {
    var html = document.documentElement;
    var isDark = html.getAttribute("data-theme") === "dark";

    if (isDark) {
        html.removeAttribute("data-theme");
        localStorage.setItem("theme", "light");
    } else {
        html.setAttribute("data-theme", "dark");
        localStorage.setItem("theme", "dark");
    }
};
