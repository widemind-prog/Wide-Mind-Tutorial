document.addEventListener("DOMContentLoaded", () => {

    const toast = document.getElementById("admin-toast");

    function showToast(message) {
        toast.textContent = message;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 3000);
    }

    // Handle all admin forms with AJAX
    const forms = document.querySelectorAll(".users-grid form");

    forms.forEach(form => {
        form.addEventListener("submit", async (e) => {
            e.preventDefault(); // ❌ STOP default reload

            const action = form.getAttribute("action") || e.submitter.getAttribute("formaction");
            if (!action) return;

            try {
                const res = await fetch(action, {
                    method: "POST",
                    credentials: "same-origin"
                });
                const data = await res.json();

                if (res.ok && data.message) {
                    showToast(data.message);
                    setTimeout(() => location.reload(), 800); // reload to update status
                } else {
                    showToast("Action failed");
                }
            } catch (err) {
                showToast("Error occurred");
                console.error(err);
            }
        });
    });

});