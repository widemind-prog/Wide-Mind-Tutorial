document.addEventListener("DOMContentLoaded", async () => {

    const paymentStatusEl = document.getElementById("payment-status");
    const payBtn = document.getElementById("pay-btn");
    const toast = document.getElementById("toast");
    const coursesList = document.getElementById("courses");

    let isPaid = false;
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
       LOAD COURSES
    -------------------- */
    async function loadCourses() {
        const res = await fetch("/api/courses/my", { credentials: "same-origin" });
        const data = await res.json();
        coursesList.innerHTML = "";

        if (!data.courses || data.courses.length === 0) {
            coursesList.innerHTML = "<li>No courses yet</li>";
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
                a.addEventListener("click", e => {
                    e.preventDefault();
                    alert("Payment required to access this course");
                });
            }
            li.appendChild(a);
            coursesList.appendChild(li);
        });
    }

    /* --------------------
       PAYMENT STATUS
    -------------------- */
    async function checkPaymentStatus() {
        const res = await fetch("/api/payment/status", { credentials: "same-origin" });
        if (!res.ok) return;

        const payment = await res.json();
        if (payment.status === "paid") {
            isPaid = true;
            paymentStatusEl.textContent = "PAID ✅";
            paymentStatusEl.classList.add("paid-animate");
            payBtn.style.display = "none";
            showToastOnce();
        } else {
            isPaid = false;
            paymentStatusEl.textContent = "UNPAID ❌";
            paymentStatusEl.style.color = "red";
            payBtn.style.display = "inline-block";
        }
    }

    /* --------------------
       USER INFO
    -------------------- */
    const meRes = await fetch("/api/auth/me", { credentials: "same-origin" });
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
        const res = await fetch("/api/payment/init", { method: "POST", credentials: "same-origin" });
        const data = await res.json();
        if (data.status) {
            window.location.href = data.data.authorization_url;
        }
    });

    /* --------------------
       INITIAL LOAD
    -------------------- */
    await checkPaymentStatus();   // sets isPaid
    await loadCourses();          // ALWAYS load courses once

    /* --------------------
       LOGOUT
    -------------------- */
    document.getElementById("logout-btn")
        .addEventListener("click", () => window.location.href = "/logout");

});