// -------------------------
// auth.js
// -------------------------

// Helper to read cookie by name
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
}

document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("login-form");
    if (!loginForm) return;

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const csrfToken = getCookie("csrf_token"); // get CSRF token from cookie

        const res = await fetch("/login", {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken  // 🔥 send CSRF token
            },
            credentials: "include",   // keeps session cookie
            body: JSON.stringify({
                email: loginForm.email.value,
                password: loginForm.password.value
            })
        });

        const data = await res.json();

        if (res.ok && data.redirect) {
            window.location.href = data.redirect;
        } else {
            document.getElementById("login-msg").textContent =
                data.error || "Login failed";
        }
    });
});