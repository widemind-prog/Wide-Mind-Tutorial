document.addEventListener("DOMContentLoaded", function () {
    var paymentStatusEl = document.getElementById("payment-status");
    var payBtn = document.getElementById("pay-btn");
    var payAmountEl = document.getElementById("pay-amount");
    var trialBanner = document.getElementById("trial-banner");
    var trialActiveBanner = document.getElementById("trial-active-banner");
    var trialExpiredBanner = document.getElementById("trial-expired-banner");
    var trialCountdown = document.getElementById("trial-countdown");
    var trialCourseLink = document.getElementById("trial-course-link");
    var progressOverall = document.getElementById("progress-overall");
    var progressEmpty = document.getElementById("progress-empty");
    var overallBar = document.getElementById("overall-bar");
    var overallLabel = document.getElementById("overall-label");
    var overallPct = document.getElementById("overall-pct");
    var overallTime = document.getElementById("overall-time");
    var courseProgressList = document.getElementById("course-progress-list");
    var countdownInterval = null;

    function formatTime(seconds) {
        seconds = Math.max(0, Math.round(seconds || 0));
        var h = Math.floor(seconds / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        var s = seconds % 60;
        if (h > 0) return h + "h " + m + "m";
        if (m > 0) return m + "m";
        return s + "s";
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

    // Renders one card per accessible course, each showing
    // (credited seconds / total course duration) * 100 as a percentage bar.
    // This mirrors exactly how the server computes it in progress.py:
    // audio is capped at its own known duration, a PDF is a one-time flip
    // that either counts its full weight or none of it. Tapping a card goes
    // straight into that course.
    function renderCourseProgress(courses) {
        if (!courseProgressList) return;
        if (!courses.length) {
            courseProgressList.innerHTML = "";
            return;
        }
        courseProgressList.innerHTML = courses.map(function (c) {
            var meta;
            if (c.unconfigured_count > 0) {
                meta = formatTime(c.credited_seconds) + " of " + formatTime(c.total_seconds) +
                    " · " + c.unconfigured_count + " item" + (c.unconfigured_count !== 1 ? "s" : "") +
                    " pending setup";
            } else {
                meta = formatTime(c.credited_seconds) + " of " + formatTime(c.total_seconds);
            }
            return '<a class="course-progress-card" href="/course/' + c.course_id + '">' +
                '<div class="course-progress-head">' +
                    '<div>' +
                        '<div class="course-progress-code">' + escapeHtml(c.course_code) + '</div>' +
                        '<div class="course-progress-title">' + escapeHtml(c.course_title) + '</div>' +
                    '</div>' +
                    '<div class="course-progress-pct">' + c.percent + '%</div>' +
                '</div>' +
                '<div class="course-progress-track">' +
                    '<div class="course-progress-fill" style="width:' + c.percent + '%;"></div>' +
                '</div>' +
                '<div class="course-progress-meta">' + meta + '</div>' +
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

            // Progress: overall summary + per-course cards
            if (d.courses && d.courses.length > 0) {
                if (progressOverall) progressOverall.style.display = "block";
                if (progressEmpty) progressEmpty.style.display = "none";
                if (overallLabel) overallLabel.textContent = "Across " + d.courses.length + " course" + (d.courses.length !== 1 ? "s" : "");
                if (overallPct) overallPct.textContent = d.overall_percent + "%";
                if (overallBar) overallBar.style.width = d.overall_percent + "%";
                if (overallTime) overallTime.textContent = formatTime(d.overall_credited_seconds) + " studied of " + formatTime(d.overall_total_seconds) + " available";
                renderCourseProgress(d.courses);
            } else {
                if (progressOverall) progressOverall.style.display = "none";
                if (progressEmpty) progressEmpty.style.display = "block";
                if (courseProgressList) courseProgressList.innerHTML = "";
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
