document.addEventListener("DOMContentLoaded", () => {

    const toast = document.getElementById("admin-toast");

    // ------------------------
    // Global toast
    // ------------------------
    window.showToast = function(message, isError = false) {
        if (!toast) return;
        toast.textContent = message;
        toast.style.background = isError ? "#a00000" : "#333";
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 1500);
    };

    // ------------------------
    // Mark as read
    // ------------------------
    document.querySelectorAll(".btn-mark-read").forEach(btn => {
        btn.addEventListener("click", () => {
            showToast("Message marked as read");
            setTimeout(() => btn.closest("form").submit(), 800);
        });
    });

    // ------------------------
    // Mark as unread
    // ------------------------
    document.querySelectorAll(".btn-mark-unread").forEach(btn => {
        btn.addEventListener("click", () => {
            showToast("Message marked as unread");
            setTimeout(() => btn.closest("form").submit(), 800);
        });
    });

});