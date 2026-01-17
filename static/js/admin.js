document.addEventListener("DOMContentLoaded", () => {

    const toast = document.getElementById("admin-toast");

    function showToast(message) {
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 3000);
    }

    /* --------------------
       HANDLE ADMIN ACTIONS VIA AJAX
    -------------------- */
    document.querySelectorAll("form").forEach(form => {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();

            // Determine action URL
            const action = form.getAttribute("action") || (e.submitter && e.submitter.getAttribute("formaction"));
            if (!action) return;

            // Optional confirmation for delete buttons
            if (e.submitter && e.submitter.textContent.toLowerCase().includes("delete")) {
                if (!confirm("Are you sure you want to delete?")) return;
            }

            try {
                const res = await fetch(action, {
                    method: "POST",
                    credentials: "same-origin"
                });
                const data = await res.json();

                if (res.ok && data.message) {
                    showToast(data.message);

                    // Update the UI without full reload
                    // For users page
                    if (action.includes("/users/suspend/") || action.includes("/users/mark-paid/") || action.includes("/users/delete/")) {
                        // Reload users grid
                        setTimeout(() => location.reload(), 600); // slight delay to show toast
                    }

                    // For courses page
                    if (action.includes("/courses/delete/") || action.includes("/courses/material/delete/")) {
                        setTimeout(() => location.reload(), 600);
                    }
                } else {
                    showToast(data.error || "Action failed");
                }
            } catch (err) {
                console.error(err);
                showToast("An error occurred");
            }
        });
    });

});