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
        var storageKey = "audioTime_" + materialId;
        var reportInterval = null;
        var lastReportedTime = 0;

        // Disable right-click, dragging, download, and Picture-in-Picture
        audio.addEventListener("contextmenu", function (e) {
            e.preventDefault();
            showToast("Right-click disabled on audio", true);
        });
        audio.addEventListener("dragstart", function (e) { e.preventDefault(); });
        audio.setAttribute("controlsList", "nodownload");
        audio.setAttribute("disablePictureInPicture", "true");
        audio.title = "Right-click and download disabled";

        // Resume from last position on this device. This is local-only
        // memory for instant resume (works even before metadata round-trips
        // to the server); it's separate from the server-side listened_seconds
        // used for the account page's progress bar and completion tracking.
        var savedTime = null;
        try {
            savedTime = localStorage.getItem(storageKey);
        } catch (e) {}
        if (savedTime) {
            var resumeTo = parseFloat(savedTime);
            if (audio.readyState >= 1) {
                // Metadata already available
                if (resumeTo > 0 && resumeTo < audio.duration) audio.currentTime = resumeTo;
            } else {
                audio.addEventListener("loadedmetadata", function () {
                    if (resumeTo > 0 && resumeTo < audio.duration) audio.currentTime = resumeTo;
                }, { once: true });
            }
        }

        function saveLocalPosition(t) {
            try { localStorage.setItem(storageKey, t); } catch (e) {}
        }
        function clearLocalPosition() {
            try { localStorage.removeItem(storageKey); } catch (e) {}
        }

        // Update the local "last position" continuously while playing, so a
        // refresh/crash mid-playback still resumes close to where you left off.
        audio.addEventListener("timeupdate", function () {
            saveLocalPosition(audio.currentTime);
        });

        audio.addEventListener("play", function () {
            // Report every 10 seconds while playing
            reportInterval = setInterval(function () {
                if (!audio.paused && !audio.ended && audio.duration) {
                    lastReportedTime = audio.currentTime;
                    reportProgress(materialId, audio.currentTime, audio.duration);
                }
            }, 10000);
        });

        audio.addEventListener("pause", function () {
            clearInterval(reportInterval);
            if (audio.duration) {
                lastReportedTime = audio.currentTime;
                reportProgress(materialId, audio.currentTime, audio.duration);
            }
        });

        audio.addEventListener("ended", function () {
            clearInterval(reportInterval);
            if (audio.duration) {
                lastReportedTime = audio.duration;
                reportProgress(materialId, audio.duration, audio.duration);
            }
            // Lesson finished — clear local resume point so it starts from
            // the beginning next time instead of "resuming" at the very end.
            clearLocalPosition();
        });

        // Catches manual scrubbing/skipping (e.g. dragging straight to the
        // end) — "pause"/"ended" don't reliably fire for every seek, so
        // without this a skip-to-end followed by quickly leaving the page
        // could report nothing at all.
        audio.addEventListener("seeked", function () {
            if (audio.duration) {
                lastReportedTime = audio.currentTime;
                reportProgress(materialId, audio.currentTime, audio.duration);
            }
        });

        // Save on page unload. Use the larger of "current playback position"
        // and "last time we already reported" — covers the case where the
        // browser auto-paused the element (so audio.paused is already true)
        // right after a seek-to-end, which would otherwise be skipped here.
        window.addEventListener("beforeunload", function () {
            if (!audio.duration) return;
            var pos = Math.max(audio.currentTime, lastReportedTime);
            if (pos > 0) {
                reportProgress(materialId, pos, audio.duration);
            }
        });

        // Also flush progress when the tab is hidden/backgrounded — mobile
        // browsers often don't reliably fire beforeunload at all.
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "hidden" && audio.duration) {
                var pos = Math.max(audio.currentTime, lastReportedTime);
                if (pos > 0) {
                    lastReportedTime = pos;
                    reportProgress(materialId, pos, audio.duration);
                }
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
