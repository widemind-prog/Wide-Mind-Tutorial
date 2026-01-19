document.addEventListener("DOMContentLoaded", () => {
    const registerForm = document.getElementById("register-form");
    if (!registerForm) return;

    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const csrfToken = registerForm.querySelector('input[name="_csrf_token"]').value;

        // Use FormData instead of JSON
        const formData = new FormData(registerForm);
        formData.append("_csrf_token", csrfToken);

        try {
            const res = await fetch("/register", {
                method: "POST",
                credentials: "same-origin",
                body: formData, // ✅ send as form data
            });

            if (res.redirected) {
                window.location.href = res.url; // Flask redirects to /login
                return;
            }

            const text = await res.text(); // For error messages
            alert("Registration failed: " + text);

        } catch (err) {
            console.error("Registration error:", err);
            alert("Network error. Try again.");
        }
    });
});