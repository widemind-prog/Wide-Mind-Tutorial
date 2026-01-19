document.addEventListener("DOMContentLoaded", () => {

    const toast = document.getElementById("admin-toast");

    function showToast(message, isError = false) {
        if (!toast) return;

        toast.textContent = message;
        toast.style.background = isError ? "#a00000" : "#333";
        toast.classList.add("show");

        setTimeout(() => {
            toast.classList.remove("show");
        }, 3000);
    }

    // Intercept ALL admin forms
    document.querySelectorAll(".admin-dashboard form").forEach(form => {

        form.addEventListener("submit", async (e) => {
            e.preventDefault(); // ⛔ stop reload

            const button = e.submitter;
            if (!button || !button.formAction) return;

            // Confirm delete
            if (button.textContent.toLowerCase().includes("delete")) {
                if (!confirm("This action is permanent. Continue?")) return;
            }

            try {
                const res = await fetch(button.formAction, {
                    method: "POST",
                    credentials: "same-origin"
                });

                if (!res.ok) {
                    showToast("Action failed", true);
                    return;
                }

                showToast("Action successful");

                // Refresh once after short delay
                setTimeout(() => {
                    window.location.reload();
                }, 800);

            } catch (err) {
                console.error(err);
                showToast("Server error", true);
            }
        });

    });

});
