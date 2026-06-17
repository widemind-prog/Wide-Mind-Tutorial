document.addEventListener("DOMContentLoaded", async () => {
    const paymentStatusEl = document.getElementById("payment-status");
    const payBtn = document.getElementById("pay-btn");
    const payAmountEl = document.getElementById("pay-amount");
    const coursesList = document.getElementById("courses-main");
    const rerunList = document.getElementById("courses-rerun");
    const rerunSection = document.getElementById("rerun-section");
    const rerunPassesEl = document.getElementById("rerun-passes");
    const toastEl = document.getElementById("toast");
    let isPaid = false;
    let userLevel = null;

    function getQueryParam(p) {
        return new URLSearchParams(window.location.search).get(p);
    }

    function showToast(msg, type = "info") {
        if (!toastEl) return;
        toastEl.textContent = msg;
        toastEl.className = "toast show" + (type === "error" ? " toast-error" : "");
        setTimeout(() => toastEl.className = "toast", 3500);
    }

    async function loadUserInfo() {
        try {
            const res = await fetch("/api/auth/me", { credentials: "same-origin" });
            if (!res.ok) return;
            const user = await res.json();
            userLevel = parseInt(user.level);
            const usernameEl = document.getElementById("username");
            const departmentEl = document.getElementById("department");
            const levelEl = document.getElementById("level");
            const semesterEl = document.getElementById("semester");
            if (usernameEl) usernameEl.textContent = user.name;
            if (departmentEl) departmentEl.textContent = user.department;
            if (levelEl) levelEl.textContent = user.level ? user.level + " Level" : "N/A";
            if (semesterEl) semesterEl.textContent = user.semester == 1 ? "1st Semester" : user.semester == 2 ? "2nd Semester" : "N/A";
        } catch (err) {
            console.error("Failed to load user info:", err);
        }
    }

    async function checkPaymentStatus(showToastOnSuccess = false) {
        if (!paymentStatusEl || !payBtn) return;
        try {
            const res = await fetch("/api/payment/status", { credentials: "same-origin" });
            if (!res.ok) {
                paymentStatusEl.textContent = "UNPAID ❌";
                paymentStatusEl.style.color = "red";
                payBtn.style.display = "inline-block";
                return;
            }
            const payment = await res.json();
            if (payAmountEl && payment.amount_display) {
                payAmountEl.textContent = payment.amount_display;
            }
            if (payment.status === "paid" || payment.status === "admin") {
                isPaid = true;
                paymentStatusEl.textContent = payment.status === "admin" ? "ADMIN ✅" : "PAID ✅";
                paymentStatusEl.classList.add("paid-animate");
                paymentStatusEl.style.color = "green";
                payBtn.style.display = "none";
                if (showToastOnSuccess) showToast("Payment verified ✅");
            } else {
                isPaid = false;
                paymentStatusEl.textContent = "UNPAID ❌";
                paymentStatusEl.style.color = "red";
                payBtn.style.display = "inline-block";
            }
        } catch (err) {
            console.error("Payment status error:", err);
        }
    }

    async function loadCourses() {
        try {
            const res = await fetch("/api/courses/my", { credentials: "same-origin" });
            if (!res.ok) return;
            const data = await res.json();

            // Main courses
            if (coursesList) {
                coursesList.innerHTML = "";
                if (!data.courses || data.courses.length === 0) {
                    coursesList.innerHTML = "<li>No courses available for your level and semester yet.</li>";
                } else {
                    data.courses.forEach(course => {
                        const li = document.createElement("li");
                        const a = document.createElement("a");
                        a.textContent = `${course.code} — ${course.title}`;
                        // Always show the course name; lock clicking if unpaid
                        if (isPaid) {
                            a.href = `/course/${course.id}`;
                        } else {
                            a.href = "#";
                            a.style.opacity = "0.6";
                            a.addEventListener("click", e => {
                                e.preventDefault();
                                showToast("Complete payment to access this course ❌", "error");
                            });
                        }
                        li.appendChild(a);
                        coursesList.appendChild(li);
                    });
                }
            }

            // Rerun courses
            if (rerunList) {
                rerunList.innerHTML = "";
                if (data.rerun_courses && data.rerun_courses.length > 0) {
                    if (rerunSection) rerunSection.style.display = "block";
                    data.rerun_courses.forEach(course => {
                        const li = document.createElement("li");
                        const a = document.createElement("a");
                        a.href = `/course/${course.id}`;
                        a.innerHTML = `🔁 <span style="opacity:0.7;font-size:11px;">${course.rerun_level}L</span> ${course.code} — ${course.title}`;
                        li.appendChild(a);
                        rerunList.appendChild(li);
                    });
                }
            }
        } catch (err) {
            console.error("Failed to load courses:", err);
        }
    }

    async function loadRerunPasses() {
        if (!rerunPassesEl) return;
        // Only show for 400L and 500L students who have paid
        if (!isPaid || !userLevel || userLevel < 400) return;

        try {
            const res = await fetch("/api/payment/rerun/status", { credentials: "same-origin" });
            if (!res.ok) return;
            const data = await res.json();
            if (!data.passes || data.passes.length === 0) return;

            rerunPassesEl.innerHTML = "";
            if (rerunSection) rerunSection.style.display = "block";

            data.passes.forEach(pass => {
                const div = document.createElement("div");
                div.className = "rerun-pass-card";
                const isPurchased = pass.status === "paid";

                div.innerHTML = `
                    <div class="rerun-pass-info">
                        <span class="rerun-pass-label">🔁 ${pass.rerun_level}L Rerun Pass</span>
                        <span class="rerun-pass-status ${isPurchased ? 'purchased' : 'not-purchased'}">
                            ${isPurchased ? "✅ Active" : "Not purchased"}
                        </span>
                    </div>
                    <div class="rerun-pass-footer">
                        <span class="rerun-pass-price">${pass.amount_display}</span>
                        ${!isPurchased ? `<button class="btn-rerun-buy" data-level="${pass.rerun_level}">Buy Pass</button>` : ""}
                    </div>
                    ${isPurchased ? `<p class="rerun-pass-desc">Access all ${pass.rerun_level}L courses this semester</p>` : `<p class="rerun-pass-desc">Unlock all ${pass.rerun_level}L courses for this semester</p>`}
                `;
                rerunPassesEl.appendChild(div);
            });

            // Attach buy handlers
            document.querySelectorAll(".btn-rerun-buy").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const level = btn.getAttribute("data-level");
                    btn.disabled = true;
                    btn.textContent = "Initializing...";
                    try {
                        const res = await fetch("/api/payment/rerun/init", {
                            method: "POST",
                            credentials: "same-origin",
                            headers: {"Content-Type": "application/json"},
                            body: JSON.stringify({ rerun_level: level })
                        });
                        const data = await res.json();
                        if (data.status && data.data && data.data.authorization_url) {
                            window.location.href = data.data.authorization_url;
                        } else {
                            showToast(data.error || "Payment initiation failed ❌", "error");
                            btn.disabled = false;
                            btn.textContent = "Buy Pass";
                        }
                    } catch (err) {
                        showToast("Payment initiation failed ❌", "error");
                        btn.disabled = false;
                        btn.textContent = "Buy Pass";
                    }
                });
            });
        } catch (err) {
            console.error("Failed to load rerun passes:", err);
        }
    }

    if (payBtn) {
        payBtn.addEventListener("click", async () => {
            payBtn.disabled = true;
            payBtn.textContent = "Initializing...";
            try {
                const res = await fetch("/api/payment/init", { method: "POST", credentials: "same-origin" });
                const data = await res.json();
                if (data.status && data.data && data.data.authorization_url) {
                    window.location.href = data.data.authorization_url;
                } else {
                    showToast(data.message || "Payment initialization failed ❌", "error");
                    payBtn.disabled = false;
                    payBtn.innerHTML = 'Pay Now <span id="pay-amount"></span> 💳';
                }
            } catch (err) {
                showToast("Payment initiation failed ❌", "error");
                payBtn.disabled = false;
                payBtn.innerHTML = 'Pay Now <span id="pay-amount"></span> 💳';
            }
        });
    }

    const paymentRedirect = getQueryParam("payment");
    if (paymentRedirect === "callback" || paymentRedirect === "rerun_callback") {
        const url = new URL(window.location);
        url.searchParams.delete("payment");
        window.history.replaceState({}, document.title, url);
        setTimeout(async () => {
            await loadUserInfo();
            await checkPaymentStatus(true);
            await loadCourses();
            await loadRerunPasses();
        }, 700);
    } else {
        await loadUserInfo();
        await checkPaymentStatus(false);
        await loadCourses();
        await loadRerunPasses();
    }

    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => { window.location.href = "/logout"; });
    }
});
