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

    // Intercept ONLY forms with buttons that have class "btn-ajax"
    document.querySelectorAll(".admin-dashboard form").forEach(form => {

        // Look for buttons inside the form that need fetch
        const ajaxButtons = form.querySelectorAll(".btn-ajax");

        if (ajaxButtons.length === 0) return; // normal form, do nothing

        form.addEventListener("submit", async (e) => {
            e.preventDefault();

            const button = e.submitter;
            if (!button) return;

            const url = button.formAction || form.action;
            if (!url) {
                showToast("No action URL defined for this form.", true);
                return;
            }

            // Confirm delete
            if (button.textContent.toLowerCase().includes("delete")) {
                if (!confirm("This action is permanent. Continue?")) return;
            }

            try {
                const formData = new FormData(form);

                const res = await fetch(url, {
                    method: "POST",
                    body: formData,
                    credentials: "same-origin"
                });

                if (!res.ok) {
                    const text = await res.text();
                    showToast(text || "Action failed", true);
                    return;
                }

                showToast("Action successful");

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