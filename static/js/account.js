document.addEventListener("DOMContentLoaded", async () => {

    const paymentStatusEl = document.getElementById("payment-status");
    const payBtn = document.getElementById("pay-btn");
    const toast = document.getElementById("toast");

    let lastPaymentStatus = null;
    let pollingInterval = null;

    /* --------------------
       TOAST
    -------------------- */
    function showToast() {
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 3000);
    }

    /* --------------------
       FETCH PAYMENT STATUS
    -------------------- */
    async function checkPaymentStatus() {
        const res = await fetch("/api/payment/status", {
            credentials: "same-origin"
        });
        if (!res.ok) return;

        const payment = await res.json();

        // ---- PAID ----
        if (payment.status === "paid") {
            paymentStatusEl.textContent = "PAID ✅";
            paymentStatusEl.classList.add("paid-animate");
            payBtn.style.display = "none";

            // Show toast ONLY once (first time paid)
            if (lastPaymentStatus !== "paid") {
                showToast();
                await loadCourses(true);

                // STOP polling permanently
                if (pollingInterval) {
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                }
            }
        }

        // ---- UNPAID ----
        else {
            paymentStatusEl.textContent = "UNPAID ❌";
            paymentStatusEl.style.color = "red";
            payBtn.style.display = "inline-block";
        }

        lastPaymentStatus = payment.status;
    }

    /* --------------------
       USER INFO
    -------------------- */
    const meRes = await fetch("/api/auth/me", {
        credentials: "same-origin"
    });

    if (!meRes.ok) {
        window.location.href = "/login-page";
        return;
    }

    const user = await meRes.json();
    document.getElementById("username").textContent = user.name;
    document.getElementById("department").textContent = user.department;
    document.getElementById("level").textContent = user.level;

    /* --------------------
       PAY BUTTON
    -------------------- */
    payBtn.addEventListener("click", async () => {
        const res = await fetch("/api/payment/init", {
            method: "POST",
            credentials: "same-origin"
        });

        const data = await res.json();
        if (data.status) {
            window.location.href = data.data.authorization_url;
        }
    });

    /* --------------------
       COURSES
    -------------------- */
    async function loadCourses(isPaid = false) {
        const courseRes = await fetch("/api/courses/my", {
            credentials: "same-origin"
        });

        const data = await courseRes.json();
        const list = document.getElementById("courses");
        list.innerHTML = "";

        if (!data.courses || data.courses.length === 0) {
            list.innerHTML = "<li>No courses yet</li>";
            return;
        }

        data.courses.forEach(course => {
            const li = document.createElement("li");
            const a = document.createElement("a");

            a.textContent = `${course.code} - ${course.title}`;

            if (isPaid) {
                a.href = `/course/${course.id}`;
            } else {
                a.href = "#";
                a.onclick = e => {
                    e.preventDefault();
                    alert("Payment required");
                };
            }

            li.appendChild(a);
            list.appendChild(li);
        });
    }

    /* --------------------
       LOGOUT
    -------------------- */
    document.getElementById("logout-btn")
        .addEventListener("click", () => {
            window.location.href = "/logout";
        });

    /* --------------------
       INITIAL LOAD
    -------------------- */
    await checkPaymentStatus();
    await loadCourses(lastPaymentStatus === "paid");

    /* --------------------
       AUTO POLLING (STOP AFTER PAID)
    -------------------- */
    if (lastPaymentStatus !== "paid") {
        pollingInterval = setInterval(checkPaymentStatus, 5000);
    }

});