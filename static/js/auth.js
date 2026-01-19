document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("login-form");
    if (!loginForm) return;

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const msgEl = document.getElementById("login-msg");
        msgEl.textContent = "";

        const email = loginForm.email.value.trim();
        const password = loginForm.password.value.trim();

        if (!email || !password) {
            msgEl.style.color = "red";
            msgEl.textContent = "Please fill in all fields.";
            return;
        }

        try {
            const csrfTokenInput = loginForm.querySelector('input[name="_csrf_token"]');
            const csrfToken = csrfTokenInput ? csrfTokenInput.value : "";

            const res = await fetch("/auth/login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrfToken // optional, backend ignores JSON CSRF
                },
                credentials: "same-origin",
                body: JSON.stringify({ email, password })
            });

            const data = await res.json();

            if (res.ok) {
                msgEl.style.color = "green";
                msgEl.textContent = "Login successful! Redirecting...";
                setTimeout(() => {
                    window.location.href = data.redirect || "/dashboard";
                }, 1000);
            } else {
                msgEl.style.color = "red";
                msgEl.textContent = data.error || "Login failed";
            }
        } catch (err) {
            console.error("Login error:", err);
            msgEl.style.color = "red";
            msgEl.textContent = "Network error. Try again.";
        }
    });
});