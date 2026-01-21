document.addEventListener("DOMContentLoaded", async () => {

    const paymentStatusEl = document.getElementById("payment-status");
    const payBtn = document.getElementById("pay-btn");
    const coursesList = document.getElementById("courses");
    const logoutBtn = document.getElementById("logout-btn");

    let isPaid = false; // tracks if user has paid

    /* -------------------- HELPER: GET URL PARAMS -------------------- */
    function getQueryParam(param) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(param);
    }

    /* -------------------- TOAST FUNCTION -------------------- */
    function showToast(message) {
        let toast = document.getElementById("toast");
        if (!toast) {
            toast = document.createElement("div");
            toast.id = "toast";
            toast.className = "toast";
            document.body.appendChild(toast);
        }

        toast.textContent = message;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 3000);
    }

    /* -------------------- LOAD COURSES -------------------- */
    async function loadCourses() {
        if (!coursesList) return;

        try {
            const res = await fetch("/api/courses/my", { credentials: "same-origin" });
            if (!res.ok) throw new Error("Failed to fetch courses");
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
        } catch (err) {
            console.error("Failed to load courses:", err);
            coursesList.innerHTML = "<li>Error loading courses</li>";
        }
    }

    /* -------------------- CHECK PAYMENT STATUS -------------------- */
    async function checkPaymentStatus() {
        if (!paymentStatusEl || !payBtn) return;

        try {
            const res = await fetch("/api/payment/status", { credentials: "same-origin" });
            if (!res.ok) {
                if (res.status === 401) {
                    console.warn("User not authenticated, skipping payment check");
                    paymentStatusEl.textContent = "UNPAID ❌";
                    paymentStatusEl.style.color = "red";
                    payBtn.style.display = "inline-block";
                    return;
                }
                throw new Error("Failed to fetch payment status");
            }

            const payment = await res.json();

            if (payment.status === "paid") {
                if (!isPaid) {
                    isPaid = true;
                    paymentStatusEl.textContent = "PAID ✅";
                    paymentStatusEl.classList.add("paid-animate");
                    paymentStatusEl.style.color = "green";
                    payBtn.style.display = "none";
                    await loadCourses();
                    showToast("Payment verified ✅");
                }
            } else {
                isPaid = false;
                paymentStatusEl.textContent = "UNPAID ❌";
                paymentStatusEl.style.color = "red";
                payBtn.style.display = "inline-block";
                await loadCourses();
            }
        } catch (err) {
            console.error("Error checking payment status:", err);
            paymentStatusEl.textContent = "UNKNOWN ❌";
            paymentStatusEl.style.color = "gray";
        }
    }

    /* -------------------- LOAD USER INFO -------------------- */
    async function loadUserInfo() {
        try {
            const meRes = await fetch("/api/auth/me", { credentials: "same-origin" });
            if (!meRes.ok) {
                console.warn("Not authenticated, redirecting to login");
                return; // Don't force reload
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
            showToast("Failed to load user info");
        }
    }

    /* -------------------- PAY BUTTON -------------------- */
    if (payBtn) {
        payBtn.addEventListener("click", async () => {
            payBtn.disabled = true;
            payBtn.textContent = "Initializing...";

            try {
                const res = await fetch("/api/payment/init", {
                    method: "POST",
                    credentials: "same-origin",
                });
                const data = await res.json();

                if (data.status && data.data && data.data.authorization_url) {
                    window.location.href = data.data.authorization_url;
                } else {
                    alert(data.message || "Payment initialization failed");
                    payBtn.disabled = false;
                    payBtn.textContent = "Pay Now 💳";
                }
            } catch (err) {
                console.error("Payment initiation failed:", err);
                alert("Payment initiation failed. Try again.");
                payBtn.disabled = false;
                payBtn.textContent = "Pay Now 💳";
            }
        });
    }

    /* -------------------- PAYSTACK REDIRECT HANDLING -------------------- */
    const paymentRedirect = getQueryParam("payment");
    if (paymentRedirect === "callback") {
        showToast("Payment successful ✅");

        // Remove query param to avoid loop
        const url = new URL(window.location);
        url.searchParams.delete("payment");
        window.history.replaceState({}, document.title, url);

        // Delay the payment status check to allow cookies/session to settle
        setTimeout(async () => {
            await checkPaymentStatus();
        }, 500);
    }

    /* -------------------- LOGOUT -------------------- */
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            window.location.href = "/logout";
        });
    }

    /* -------------------- INITIAL LOAD -------------------- */
    await loadUserInfo();
    await checkPaymentStatus();
    await loadCourses();

});