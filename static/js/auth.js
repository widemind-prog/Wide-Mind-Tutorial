document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("login-form");
    if (!loginForm) return;

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",   // 🔥 THIS FIXES IT
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
