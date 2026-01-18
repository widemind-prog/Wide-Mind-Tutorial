document.addEventListener("DOMContentLoaded", async () => {

    const paymentStatusEl = document.getElementById("payment-status");
    const payBtn = document.getElementById("pay-btn");
    const coursesList = document.getElementById("courses");
    const logoutBtn = document.getElementById("logout-btn");

    let isPaid = false; // tracks if user has paid

    /* --------------------
       HELPER: GET URL PARAMS
    -------------------- */
    function getQueryParam(param) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(param);
    }

    /* --------------------
       LOAD COURSES
    -------------------- */
 async function loadCourses() {
    if (!coursesList) return;

    try {
        // Fetch JSON from the new API
        const res = await fetch("/api/courses", { credentials: "same-origin" });
        if (!res.ok) {
            coursesList.innerHTML = "<li>Failed to load courses</li>";
            return;
        }

        const courses_with_materials = await res.json();
        coursesList.innerHTML = "";

        if (!courses_with_materials || courses_with_materials.length === 0) {
            coursesList.innerHTML = "<li>No courses yet</li>";
            return;
        }

        courses_with_materials.forEach(item => {
            const course = item.course;
            const li = document.createElement("li");
            const a = document.createElement("a");
            a.textContent = `${course.course_code} - ${course.course_title}`;

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
    } catch (err) {
        console.error("Failed to load courses:", err);
        coursesList.innerHTML = "<li>Error loading courses</li>";
    }
}
    /* --------------------
       CHECK PAYMENT STATUS
    -------------------- */
    async function checkPaymentStatus() {
        if (!paymentStatusEl || !payBtn) return;

        const res = await fetch("api/payment/status", { credentials: "same-origin" });
        if (!res.ok) return;

        const payment = await res.json();

        if (payment.status === "paid") {
            if (!isPaid) {
                isPaid = true;
                paymentStatusEl.textContent = "PAID ✅";
                paymentStatusEl.classList.add("paid-animate");
                payBtn.style.display = "none";
                await loadCourses();
            }
        } else {
            isPaid = false;
            paymentStatusEl.textContent = "UNPAID ❌";
            paymentStatusEl.style.color = "red";
            payBtn.style.display = "inline-block";
            await loadCourses();
        }
    }

    /* --------------------
       LOAD USER INFO
    -------------------- */
    try {
        const meRes = await fetch("/auth/me", { credentials: "same-origin" });
        if (!meRes.ok) {
            window.location.href = "/login";
            return;
        }
        const user = await meRes.json();
        const usernameEl = document.getElementById("username");
        const departmentEl = document.getElementById("department");
        const levelEl = document.getElementById("level");

        if (usernameEl) usernameEl.textContent = user.name;
        if (departmentEl) departmentEl.textContent = user.department;
        if (levelEl) levelEl.textContent = user.level;
    } catch (err) {
        console.error("Failed to load user info:", err);
    }

    /* --------------------
       PAY BUTTON
    -------------------- */
    if (payBtn) {
        payBtn.addEventListener("click", async () => {
            try {
                const res = await fetch("api/payment/init", { method: "POST", credentials: "same-origin" });
                const data = await res.json();
                if (data.status) {
                    // Redirect to Paystack full page
                    window.location.href = data.data.authorization_url;
                } else {
                    alert(data.message || "Payment initialization failed");
                }
            } catch (err) {
                console.error("Payment initiation failed:", err);
                alert("Payment initiation failed. Try again.");
            }
        });
    }

    /* --------------------
       PAYSTACK REDIRECT HANDLING
    -------------------- */
    const paymentRedirect = getQueryParam("payment");
    if (paymentRedirect === "callback") {
        alert("Payment successful ✅");
        // Remove query string so message doesn't repeat on reload
        window.history.replaceState({}, document.title, "/account");
        await checkPaymentStatus();
    }

    /* --------------------
       INITIAL LOAD
    -------------------- */
    await checkPaymentStatus();
    await loadCourses();

    /* --------------------
       LOGOUT
    -------------------- */
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            window.location.href = "/logout";
        });
    }

});