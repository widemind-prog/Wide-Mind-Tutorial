document.addEventListener("DOMContentLoaded", async () => {
    const paymentStatusEl = document.getElementById("payment-status");
    const payBtn = document.getElementById("pay-btn");
    const coursesList = document.getElementById("courses");
    let isPaid = false;

    function getQueryParam(param) {
        return new URLSearchParams(window.location.search).get(param);
    }

    async function checkPaymentStatus() {
        if (!paymentStatusEl || !payBtn) return;
        try {
            const res = await fetch("/api/payment/status", { credentials: "same-origin" });
            if (!res.ok) return;

            const payment = await res.json();
            isPaid = payment.status === "paid";

            if (isPaid) {
                paymentStatusEl.textContent = "PAID ✅";
                paymentStatusEl.style.color = "green";
                if (payBtn) payBtn.style.display = "none";
            } else {
                paymentStatusEl.textContent = "UNPAID ❌";
                paymentStatusEl.style.color = "red";
                if (payBtn) payBtn.style.display = "inline-block";
            }

            await loadCourses();
        } catch (err) {
            console.error("Payment check failed:", err);
        }
    }

    async function loadCourses() {
        if (!coursesList) return;
        try {
            const res = await fetch("/api/courses", { credentials: "same-origin" });
            if (!res.ok) {
                coursesList.innerHTML = "<li>Failed to load courses</li>";
                return;
            }

            const data = await res.json();
            coursesList.innerHTML = "";

            if (!data.length) {
                coursesList.innerHTML = "<li>No courses yet</li>";
                return;
            }

            data.forEach(entry => {
                const course = entry.course;
                const materials = entry.materials;
                const li = document.createElement("li");
                li.innerHTML = `<strong>${course.course_title}</strong> (${course.course_code})<ul>${materials.map(m => `<li><a href="/stream/${m.file_type}/${m.id}" target="_blank">${m.title}</a></li>`).join("")}</ul>`;
                coursesList.appendChild(li);
            });
        } catch (err) {
            console.error("Failed to load courses:", err);
        }
    }

    if (payBtn) {
        payBtn.addEventListener("click", async () => {
            try {
                const res = await fetch("/api/payment/init", { method: "POST", credentials: "same-origin" });
                const data = await res.json();
                if (data.status && data.data && data.data.authorization_url) {
                    window.location.href = data.data.authorization_url;
                } else {
                    alert("Payment initiation failed");
                }
            } catch (err) {
                console.error(err);
                alert("Payment initiation error");
            }
        });
    }

    if (getQueryParam("payment") === "callback") {
        alert("Payment completed! Refreshing status...");
    }

    await checkPaymentStatus();
});