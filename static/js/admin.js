document.addEventListener("DOMContentLoaded", () => {

    const toast = document.getElementById("admin-toast");

    // ------------------------
    // Show toast
    // ------------------------
    window.showToast = function(message, isError = false) {
        if (!toast) return;
        toast.textContent = message;
        toast.style.background = isError ? "#a00000" : "#333";
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 1500);
    };

    // ------------------------
    // Suspend / Unsuspend
    // ------------------------
    document.querySelectorAll(".btn-suspend").forEach(btn => {
        btn.addEventListener("click", () => {
            showToast("Toggling suspension...");
            setTimeout(() => {
                const form = btn.closest("form");
                form.action = btn.dataset.url;
                form.submit();
            }, 800);
        });
    });

    // ------------------------
    // Toggle Payment
    // ------------------------
    document.querySelectorAll(".btn-payment").forEach(btn => {
        btn.addEventListener("click", () => {
            showToast("Updating payment status...");
            setTimeout(() => {
                const form = btn.closest("form");
                form.action = btn.dataset.url;
                form.submit();
            }, 800);
        });
    });

    // ------------------------
    // Delete User
    // ------------------------
    document.querySelectorAll(".btn-delete").forEach(btn => {
        btn.addEventListener("click", () => {
            if (!confirm("This action is permanent. Continue?")) return;
            showToast("Deleting user...", true);
            setTimeout(() => {
                const form = btn.closest("form");
                form.action = btn.dataset.url;
                form.submit();
            }, 800);
        });
    });

});