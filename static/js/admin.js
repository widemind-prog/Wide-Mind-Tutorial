document.addEventListener("DOMContentLoaded", () => {

    const toast = document.getElementById("admin-toast");

    function showAdminToast(message, duration = 3000) {
        toast.textContent = message;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), duration);
    }

    /* --------------------
       AJAX Helper
    -------------------- */
    async function postData(url, data = {}) {
        const res = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        return res.json();
    }

    /* --------------------
       USER ACTIONS
    -------------------- */
    document.querySelectorAll("form button").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            const form = btn.closest("form");
            if (!form) return;

            e.preventDefault();

            const url = form.getAttribute("action");
            if (!url) return;

            // Confirm delete actions
            if (btn.textContent.toLowerCase().includes("delete") &&
                !confirm("This action is permanent. Continue?")) return;

            try {
                const result = await postData(url);
                showAdminToast(result.message || "Action completed ✅");

                // Reload page or re-fetch data
                setTimeout(() => location.reload(), 800);
            } catch (err) {
                console.error(err);
                showAdminToast("Action failed ❌");
            }
        });
    });

    /* --------------------
       FORM SUBMISSIONS (ADD COURSES / MATERIALS)
    -------------------- */
    document.querySelectorAll("form").forEach(form => {
        form.addEventListener("submit", async (e) => {
            if (form.getAttribute("enctype") === "multipart/form-data") {
                // Handle file uploads via FormData
                e.preventDefault();
                const url = form.getAttribute("action");
                const formData = new FormData(form);

                try {
                    const res = await fetch(url, {
                        method: "POST",
                        credentials: "same-origin",
                        body: formData
                    });
                    if (res.ok) {
                        showAdminToast("Uploaded successfully ✅");
                        setTimeout(() => location.reload(), 800);
                    } else {
                        showAdminToast("Upload failed ❌");
                    }
                } catch (err) {
                    console.error(err);
                    showAdminToast("Upload failed ❌");
                }
            }
        });
    });

});