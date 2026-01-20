document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("contact-form");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const data = {
            name: form.name.value,
            email: form.email.value,
            subject: form.subject.value,
            message: form.message.value
        };

        try {
            const res = await fetch("/api/contact", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify(data)
            });

            const json = await res.json();

            // Logged out → redirect
            if (json.redirect) {
                window.location.href = json.redirect;
                return;
            }

            // Admin or validation error → show toast
            if (json.error) {
                showToast(json.error, true);
                return;
            }

            // Success
            showToast(json.message);
            form.reset();

        } catch (err) {
            console.error(err);
            showToast("Server error", true);
        }
    });
});