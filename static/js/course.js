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

    // A normal fetch() started inside a pagehide/beforeunload/visibilitychange
    // handler can be silently cancelled mid-flight once the page starts
    // tearing down — this is the #1 reason "I listened for 2 minutes, went
    // back to /account, and progress shows 0" happens. navigator.sendBeacon
    // is purpose-built to survive that: the browser guarantees the request
    // is queued before the page unloads, even on a same-site link click.
    function reportProgressOnExit(materialId, listenedSeconds, durationSeconds) {
        var payload = JSON.stringify({
            material_id: materialId,
            listened_seconds: listenedSeconds,
            duration_seconds: durationSeconds
        });
        if (navigator.sendBeacon) {
            var blob = new Blob([payload], { type: "application/json" });
            var ok = navigator.sendBeacon("/api/progress/update", blob);
            if (ok) return;
        }
        // Fallback for browsers without sendBeacon support
        reportProgress(materialId, listenedSeconds, durationSeconds);
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
            // Report immediately so even a very short listen (under one
            // interval tick) still registers something, then keep reporting
            // every 5 seconds while playback continues.
            if (audio.duration) {
                lastReportedTime = audio.currentTime;
                reportProgress(materialId, audio.currentTime, audio.duration);
            }
            reportInterval = setInterval(function () {
                if (!audio.paused && !audio.ended && audio.duration) {
                    lastReportedTime = audio.currentTime;
                    reportProgress(materialId, audio.currentTime, audio.duration);
                }
            }, 5000);
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

        // Flush progress on every exit path. "pagehide" is the one that
        // actually fires reliably for normal same-site link navigation
        // (e.g. tapping the Account tab in the bottom nav) across both
        // desktop and mobile browsers, including iOS Safari — beforeunload
        // is unreliable on mobile and visibilitychange's "hidden" state is
        // never reached during an in-app navigation (the document stays
        // visible right up until it's replaced). All three are wired here
        // so backgrounding, tab-close, and link-navigation are all covered.
        function flushOnExit() {
            if (!audio.duration) return;
            var pos = Math.max(audio.currentTime, lastReportedTime);
            if (pos > 0) {
                lastReportedTime = pos;
                reportProgressOnExit(materialId, pos, audio.duration);
            }
        }
        window.addEventListener("pagehide", flushOnExit);
        window.addEventListener("beforeunload", flushOnExit);
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "hidden") flushOnExit();
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
