document.addEventListener("DOMContentLoaded", function () {
    var toast = document.getElementById("toast");

    function showToast(message, isError) {
        if (!toast) return;
        toast.textContent = message;
        toast.style.background = isError ? "#a00000" : "#333";
        toast.classList.add("show");
        setTimeout(function () { toast.classList.remove("show"); }, 3000);
    }

    // Standard fetch-based progress report — used for all in-session events
    // (play start, 5s interval, pause, end, seek). Reliable because the
    // page is still alive and credentials are always sent.
    function reportProgress(materialId, listenedSeconds) {
        fetch("/api/progress/update", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                material_id: materialId,
                listened_seconds: listenedSeconds
            })
        }).catch(function () {});
    }

    // Beacon-based flush — used ONLY as a last-resort backup on page exit.
    // navigator.sendBeacon survives page teardown but doesn't guarantee
    // session cookies on all Android browsers. Because regular fetch handles
    // all in-session reports (play, pause, interval, seek), the beacon is
    // just a safety net for uncaught exit scenarios — if it fails silently,
    // the last fetch-based report (max 5s ago) was already written.
    function reportProgressBeacon(materialId, listenedSeconds) {
        var payload = JSON.stringify({
            material_id: materialId,
            listened_seconds: listenedSeconds
        });
        if (navigator.sendBeacon) {
            var blob = new Blob([payload], { type: "application/json" });
            navigator.sendBeacon("/api/progress/update", blob);
        } else {
            reportProgress(materialId, listenedSeconds);
        }
    }

    document.querySelectorAll("audio[data-material-id]").forEach(function (audio) {
        var materialId = parseInt(audio.getAttribute("data-material-id"));
        var storageKey = "audioTime_" + materialId;
        var reportInterval = null;
        var lastReportedTime = 0;

        // ---- ANTI-PIRACY ----
        audio.addEventListener("contextmenu", function (e) {
            e.preventDefault();
            showToast("Right-click disabled", true);
        });
        audio.addEventListener("dragstart", function (e) { e.preventDefault(); });
        audio.setAttribute("controlsList", "nodownload");
        audio.setAttribute("disablePictureInPicture", "true");
        audio.title = "Download disabled";

        // ---- LOCAL RESUME (localStorage, device-only) ----
        var savedTime = null;
        try { savedTime = localStorage.getItem(storageKey); } catch (e) {}
        if (savedTime) {
            var resumeTo = parseFloat(savedTime);
            if (audio.readyState >= 1) {
                if (resumeTo > 0 && resumeTo < audio.duration) audio.currentTime = resumeTo;
            } else {
                audio.addEventListener("loadedmetadata", function () {
                    if (resumeTo > 0 && resumeTo < audio.duration) audio.currentTime = resumeTo;
                }, { once: true });
            }
        }
        function saveLocal(t) { try { localStorage.setItem(storageKey, t); } catch (e) {} }
        function clearLocal() { try { localStorage.removeItem(storageKey); } catch (e) {} }

        audio.addEventListener("timeupdate", function () {
            saveLocal(audio.currentTime);
        });

        // ---- PROGRESS REPORTING ----
        audio.addEventListener("play", function () {
            // Report immediately on play so even a sub-5s listen registers
            if (audio.currentTime > 0) {
                lastReportedTime = audio.currentTime;
                reportProgress(materialId, audio.currentTime);
            }
            clearInterval(reportInterval);
            reportInterval = setInterval(function () {
                if (!audio.paused && !audio.ended) {
                    lastReportedTime = audio.currentTime;
                    reportProgress(materialId, audio.currentTime);
                }
            }, 5000);
        });

        audio.addEventListener("pause", function () {
            clearInterval(reportInterval);
            lastReportedTime = audio.currentTime;
            reportProgress(materialId, audio.currentTime);
        });

        audio.addEventListener("ended", function () {
            clearInterval(reportInterval);
            lastReportedTime = audio.currentTime;
            reportProgress(materialId, audio.currentTime);
            clearLocal();
        });

        // Scrubbing/skipping — report immediately on every seek
        audio.addEventListener("seeked", function () {
            lastReportedTime = audio.currentTime;
            reportProgress(materialId, audio.currentTime);
        });

        // ---- EXIT FLUSH (belt-and-braces backup) ----
        // The 5s interval + pause/seek already write regularly via fetch.
        // These handlers catch the case where the user navigates away without
        // pausing first. The beacon is a secondary safety net only.
        function flushOnExit() {
            var pos = Math.max(audio.currentTime, lastReportedTime);
            if (pos > 0) {
                reportProgressBeacon(materialId, pos);
            }
        }
        window.addEventListener("pagehide", flushOnExit);
        window.addEventListener("beforeunload", flushOnExit);
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "hidden") flushOnExit();
        });
    });

    // ---- PDF OPEN TRACKING ----
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
