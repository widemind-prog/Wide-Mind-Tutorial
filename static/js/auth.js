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

<script>
document.addEventListener("DOMContentLoaded", () => {
    const toggleIcon = document.querySelector(".toggle-password-icon");
    const passwordInput = document.getElementById("password");

    toggleIcon.addEventListener("click", () => {
        if (passwordInput.type === "password") {
            passwordInput.type = "text";
            // Optional: swap icon to an "eye-open" variant
            toggleIcon.src = "/static/icons/eye-skeleton-open.png";
        } else {
            passwordInput.type = "password";
            toggleIcon.src = "/static/icons/eye-skeleton.png";
        }
    });
});
</script>
