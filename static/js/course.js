document.addEventListener("DOMContentLoaded", function () {
    var toast = document.getElementById("toast");

    function showToast(message, isError) {
        if (!toast) return;
        toast.textContent = message;
        toast.style.background = isError ? "#a00000" : "#333";
        toast.classList.add("show");
        setTimeout(function () { toast.classList.remove("show"); }, 3000);
    }

    // =====================
    // AUDIO PROGRESS TRACKING
    // =====================
    function reportProgress(materialId, listenedSeconds, durationSeconds) {
        fetch("/api/progress/update", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                material_id: materialId,
                listened_seconds: listenedSeconds,
                duration_seconds: durationSeconds
            })
        }).catch(function () {});
    }

    document.querySelectorAll("audio[data-material-id]").forEach(function (audio) {
        var materialId = parseInt(audio.getAttribute("data-material-id"));
        var reportInterval = null;

        // Disable right-click, dragging, download, and Picture-in-Picture
        audio.addEventListener("contextmenu", function (e) {
            e.preventDefault();
            showToast("Right-click disabled on audio", true);
        });
        audio.addEventListener("dragstart", function (e) { e.preventDefault(); });
        audio.setAttribute("controlsList", "nodownload");
        audio.setAttribute("disablePictureInPicture", "true");
        audio.title = "Right-click and download disabled";

        audio.addEventListener("play", function () {
            // Report every 10 seconds while playing
            reportInterval = setInterval(function () {
                if (!audio.paused && !audio.ended && audio.duration) {
                    reportProgress(materialId, audio.currentTime, audio.duration);
                }
            }, 10000);
        });

        audio.addEventListener("pause", function () {
            clearInterval(reportInterval);
            if (audio.duration) {
                reportProgress(materialId, audio.currentTime, audio.duration);
            }
        });

        audio.addEventListener("ended", function () {
            clearInterval(reportInterval);
            if (audio.duration) {
                reportProgress(materialId, audio.duration, audio.duration);
            }
        });

        // Save on page unload
        window.addEventListener("beforeunload", function () {
            if (!audio.paused && audio.duration) {
                reportProgress(materialId, audio.currentTime, audio.duration);
            }
        });
    });

    // =====================
    // PDF OPEN TRACKING
    // =====================
    document.querySelectorAll("a.pdf-link[data-material-id]").forEach(function (link) {
        link.addEventListener("click", function () {
            var materialId = parseInt(link.getAttribute("data-material-id"));
            fetch("/api/progress/open-pdf", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ material_id: materialId })
            }).catch(function () {});
        });
    });
});
