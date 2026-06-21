document.addEventListener("DOMContentLoaded", function () {
    var paymentStatusEl = document.getElementById("payment-status");
    var payBtn = document.getElementById("pay-btn");
    var payAmountEl = document.getElementById("pay-amount");
    var trialBanner = document.getElementById("trial-banner");
    var trialActiveBanner = document.getElementById("trial-active-banner");
    var trialExpiredBanner = document.getElementById("trial-expired-banner");
    var trialCountdown = document.getElementById("trial-countdown");
    var trialCourseLink = document.getElementById("trial-course-link");
    var progressCard = document.getElementById("progress-card");
    var progressEmpty = document.getElementById("progress-empty");
    var progressBar = document.getElementById("progress-bar");
    var progressLabel = document.getElementById("progress-label");
    var progressPct = document.getElementById("progress-pct");
    var statCompleted = document.getElementById("stat-completed");
    var statTime = document.getElementById("stat-time");
    var statPending = document.getElementById("stat-pending");
    var lessonsListEl = document.getElementById("lessons-list");
    var countdownInterval = null;

    function formatTime(seconds) {
        var h = Math.floor(seconds / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        if (h > 0) return h + "h " + m + "m";
        if (m > 0) return m + "m";
        return Math.floor(seconds) + "s";
    }

    function startTrialCountdown(secondsRemaining) {
        function tick() {
            if (secondsRemaining <= 0) {
                clearInterval(countdownInterval);
                trialActiveBanner.style.display = "none";
                trialExpiredBanner.style.display = "block";
                return;
            }
            if (trialCountdown) trialCountdown.textContent = formatTime(secondsRemaining);
            secondsRemaining--;
        }
        tick();
        countdownInterval = setInterval(tick, 1000);
    }

    async function loadUserInfo() {
        try {
            var res = await fetch("/api/auth/me", { credentials: "same-origin" });
            if (!res.ok) return;
            var u = await res.json();
            var nameEl = document.getElementById("username");
            var deptEl = document.getElementById("department");
            var levelEl = document.getElementById("level");
            var semEl = document.getElementById("semester");
            if (nameEl) nameEl.textContent = u.name;
            if (deptEl) deptEl.textContent = u.department;
            if (levelEl) levelEl.textContent = u.level ? u.level + " Level" : "N/A";
            if (semEl) semEl.textContent = u.semester == 1 ? "1st Semester" : "2nd Semester";
        } catch (e) {}
    }

    function escapeHtml(s) {
        var div = document.createElement("div");
        div.textContent = s == null ? "" : String(s);
        return div.innerHTML;
    }

    // Renders the exact list of lessons the numbers on the progress card are
    // counting — this is what makes "0 of 4 completed" accountable instead
    // of an opaque aggregate: every lesson, its course, how long it was
    // listened to, and a tap-through straight to where it left off.
    function renderLessonsList(lessons) {
        if (!lessonsListEl) return;
        if (!lessons.length) {
            lessonsListEl.innerHTML = "";
            return;
        }
        lessonsListEl.innerHTML = lessons.map(function (l) {
            var icon = l.completed
                ? '<i class="fa-solid fa-circle-check lesson-row-icon" style="color:green;"></i>'
                : (l.listened_seconds > 0
                    ? '<i class="fa-solid fa-circle-play lesson-row-icon" style="color:#8B7500;"></i>'
                    : '<i class="fa-regular fa-circle lesson-row-icon" style="color:#ccc;"></i>');
            var timeLabel = l.completed
                ? "Completed"
                : (l.listened_seconds > 0 ? formatTime(l.listened_seconds) + " in" : "Not started");
            return '<a class="lesson-row" href="/course/' + l.course_id + '">' +
                icon +
                '<div class="lesson-row-text">' +
                    '<div class="lesson-row-title">' + escapeHtml(l.title) + '</div>' +
                    '<div class="lesson-row-meta">' + escapeHtml(l.course_code) + '</div>' +
                '</div>' +
                '<div class="lesson-row-time">' + timeLabel + '</div>' +
            '</a>';
        }).join("");
    }

    async function loadProgress() {
        try {
            var res = await fetch("/api/progress/summary", {
                credentials: "same-origin",
                cache: "no-store"
            });
            if (!res.ok) return;
            var d = await res.json();

            // Payment status display
            if (d.is_paid) {
                if (paymentStatusEl) {
                    paymentStatusEl.textContent = "PAID";
                    paymentStatusEl.style.color = "green";
                    paymentStatusEl.classList.add("paid-animate");
                }
                if (payBtn) payBtn.style.display = "none";
            } else {
                if (paymentStatusEl) {
                    paymentStatusEl.textContent = "UNPAID";
                    paymentStatusEl.style.color = "crimson";
                }
                if (payBtn) payBtn.style.display = "block";
                if (payAmountEl && d.amount_display) {
                    payAmountEl.textContent = " " + d.amount_display;
                }
            }

            // Trial banner — active / expired, with a direct link to the
            // course flagged as the trial course for this student's level+semester
            if (!d.is_paid && trialBanner) {
                if (d.trial_active) {
                    trialBanner.style.display = "block";
                    trialActiveBanner.style.display = "block";
                    startTrialCountdown(d.trial_seconds_remaining);
                    if (trialCourseLink) {
                        if (d.trial_course && d.trial_course.id) {
                            trialCourseLink.href = "/course/" + d.trial_course.id;
                            trialCourseLink.style.display = "inline-flex";
                            var labelEl = trialCourseLink.querySelector(".trial-course-label");
                            if (labelEl) labelEl.textContent = "Open sample course: " + d.trial_course.code;
                        } else {
                            // No trial course configured yet for this level/semester
                            trialCourseLink.style.display = "none";
                        }
                    }
                } else if (d.trial_expired) {
                    trialBanner.style.display = "block";
                    trialExpiredBanner.style.display = "block";
                }
            }

            // Progress card
            if (d.total_audios > 0) {
                if (progressCard) progressCard.style.display = "block";
                if (progressEmpty) progressEmpty.style.display = "none";
                var pct = d.total_audios > 0
                    ? Math.round((d.completed_count / d.total_audios) * 100)
                    : 0;
                if (progressBar) progressBar.style.width = pct + "%";
                if (progressLabel) progressLabel.textContent = d.completed_count + " of " + d.total_audios + " lessons completed";
                if (progressPct) progressPct.textContent = pct + "%";
                if (statCompleted) statCompleted.textContent = d.completed_count + " lesson" + (d.completed_count !== 1 ? "s" : "");
                if (statTime) statTime.textContent = formatTime(d.total_listened_seconds);
                if (statPending) statPending.textContent = d.pending_count + " lesson" + (d.pending_count !== 1 ? "s" : "");
                renderLessonsList(d.lessons || []);
            } else {
                if (progressCard) progressCard.style.display = "none";
                if (progressEmpty) progressEmpty.style.display = "block";
            }
        } catch (e) {
            console.error("Progress load failed:", e);
        }
    }

    // Pay button
    if (payBtn) {
        payBtn.addEventListener("click", async function () {
            payBtn.disabled = true;
            payBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right:8px;"></i>Initializing...';
            try {
                var res = await fetch("/api/payment/init", {
                    method: "POST", credentials: "same-origin"
                });
                var data = await res.json();
                if (data.status && data.data && data.data.authorization_url) {
                    window.location.href = data.data.authorization_url;
                } else {
                    payBtn.disabled = false;
                    payBtn.innerHTML = '<i class="fa-solid fa-credit-card" style="margin-right:8px;"></i>Pay Now <span id="pay-amount">' + (payAmountEl ? payAmountEl.textContent : "") + "</span>";
                }
            } catch (e) {
                payBtn.disabled = false;
            }
        });
    }

    // Handle payment callback redirect — strip the query param either way
    var params = new URLSearchParams(window.location.search);
    if (params.get("payment") === "callback" || params.get("payment") === "rerun_callback") {
        var url = new URL(window.location);
        url.searchParams.delete("payment");
        window.history.replaceState({}, document.title, url);
    }

    // Init
    loadUserInfo();
    loadProgress();
});
