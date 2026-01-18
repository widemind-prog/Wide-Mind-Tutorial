// -------------------------
// admin.js
// -------------------------

// Helper to read cookie by name
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
}

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

    // Allowed extensions for front-end check
    const ALLOWED_EXTENSIONS = {
        pdf: ["pdf"],
        audio: ["mp3", "wav"]
    };

    // -----------------------------
    // File name preview
    // -----------------------------
    document.querySelectorAll('form input[type="file"]').forEach(fileInput => {
        let preview = fileInput.parentElement.querySelector(".file-preview");
        if (!preview) {
            preview = document.createElement("div");
            preview.className = "file-preview";
            preview.style.marginTop = "5px";
            preview.style.fontSize = "0.9em";
            preview.style.color = "#555";
            fileInput.parentElement.insertBefore(preview, fileInput.nextSibling);
        }

        fileInput.addEventListener("change", () => {
            if (fileInput.files.length === 0) {
                preview.textContent = "No file selected";
            } else {
                preview.textContent = `Selected file: ${fileInput.files[0].name}`;
            }
        });
    });

    // -----------------------------
    // Intercept ALL admin forms
    // -----------------------------
    document.querySelectorAll(".admin-dashboard form, .admin-box form").forEach(form => {

        form.addEventListener("submit", async (e) => {

            const fileInput = form.querySelector('input[type="file"]');
            if (fileInput && fileInput.files.length > 0) {
                const file = fileInput.files[0];
                const ext = file.name.split(".").pop().toLowerCase();

                if (fileInput.name === "pdf" && !ALLOWED_EXTENSIONS.pdf.includes(ext)) {
                    e.preventDefault();
                    showToast("Invalid file type! Only PDF files allowed.", true);
                    return;
                }

                if (fileInput.name === "audio" && !ALLOWED_EXTENSIONS.audio.includes(ext)) {
                    e.preventDefault();
                    showToast("Invalid file type! Only MP3 or WAV files allowed.", true);
                    return;
                }
            }

            e.preventDefault(); // stop reload

            const button = e.submitter;
            if (!button || !button.formAction) return;

            // Confirm delete actions
            if (button.textContent.toLowerCase().includes("delete")) {
                if (!confirm("This action is permanent. Continue?")) return;
            }

            try {
                const formData = new FormData(form);

                // 🔥 Append CSRF token to FormData for POST
                const csrfToken = getCookie("csrf_token");
                if (csrfToken) formData.append("_csrf_token", csrfToken);

                const res = await fetch(button.formAction, {
                    method: "POST",
                    credentials: "same-origin",
                    body: formData
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