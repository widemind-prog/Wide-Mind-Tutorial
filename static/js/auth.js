document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("login-form");
    if (!loginForm) return;

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        // Read CSRF token directly from hidden input
        const csrfToken = loginForm.querySelector('input[name="_csrf_token"]').value;

        try {
            const res = await fetch("/auth/login", {  // POST to /auth/login
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrfToken  // send CSRF token
                },
                credentials: "include",   // keeps session cookie
                body: JSON.stringify({
                    email: loginForm.email.value,
                    password: loginForm.password.value
                })
            });

            const data = await res.json();

            const msgEl = document.getElementById("login-msg");

            if (res.ok) {
                msgEl.style.color = "green";
                msgEl.textContent = "Login successful! Redirecting...";
                setTimeout(() => window.location.href = data.redirect || "/dashboard", 1000);
            } else {
                msgEl.style.color = "red";
                msgEl.textContent = data.error || "Login failed";
            }
        } catch (err) {
            console.error("Login error:", err);
            const msgEl = document.getElementById("login-msg");
            msgEl.style.color = "red";
            msgEl.textContent = "Network error. Try again.";
        }
    });
});