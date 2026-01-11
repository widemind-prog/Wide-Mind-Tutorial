document.addEventListener("DOMContentLoaded", async () => {

    const paymentStatusEl = document.getElementById("payment-status");
    const payBtn = document.getElementById("pay-btn");
    const toast = document.getElementById("toast");

    let pollingId = null;

    const TOAST_KEY = "paymentToastShown";

    /* --------------------
       TOAST (ONCE EVER)
    -------------------- */
    function showToastOnce() {
        if (localStorage.getItem(TOAST_KEY) === "true") return;

        toast.classList.add("show");
        localStorage.setItem(TOAST_KEY, "true");

        setTimeout(() => toast.classList.remove("show"), 3000);
    }

    /* --------------------
       PAYMENT STATUS
    -------------------- */
    async function checkPaymentStatus() {
        const res = await fetch("/api/payment/status", {
            credentials: "same-origin"
        });
        if (!res.ok) return;

        const payment = await res.json();

        if (payment.status === "paid") {
            paymentStatusEl.textContent = "PAID ✅";
            paymentStatusEl.classList.add("paid-animate");
            payBtn.style.display = "none";

            showToastOnce();
            await loadCourses(true);

            // STOP polling forever
            if (pollingId) {
                clearInterval(pollingId);
                pollingId = null;
            }

        } else {
            paymentStatusEl.textContent = "UNPAID ❌";
            paymentStatusEl.style.color = "red";
            payBtn.style.display = "inline-block";
        }
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
        const res = await fetch("/api/courses/my", {
            credentials: "same-origin"
        });

        const data = await res.json();
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
        .addEventListener("click", () => window.location.href = "/logout");

    /* --------------------
       INITIAL LOAD
    -------------------- */
    await checkPaymentStatus();

    /* --------------------
       POLLING (ONLY IF UNPAID)
    -------------------- */
    if (!localStorage.getItem(TOAST_KEY)) {
        pollingId = setInterval(checkPaymentStatus, 5000);
    }
});