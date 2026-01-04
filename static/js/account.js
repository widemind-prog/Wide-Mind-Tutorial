document.addEventListener("DOMContentLoaded", async () => {
    try {
        // Fetch user info
        const meRes = await fetch("/api/auth/me", { credentials: "same-origin" });
        if (!meRes.ok) {
            window.location.href = "/login-page";
            return;
        }
        const user = await meRes.json();
        document.getElementById("username").textContent = user.name;
        document.getElementById("department").textContent = user.department;
        document.getElementById("level").textContent = user.level;

        // Fetch payment status
        const payRes = await fetch("/api/payment/status", { credentials: "same-origin" });
        let payment = { status: "unpaid", amount: 20000 };
        if (payRes.ok) {
            payment = await payRes.json();
        }

        // Display payment box
        const accountBox = document.querySelector(".account-box");
        const payDiv = document.createElement("div");
        payDiv.classList.add("payment-box");
        payDiv.style.marginTop = "15px";
        payDiv.style.padding = "10px";
        payDiv.style.background = "#fff8dc";
        payDiv.style.borderRadius = "8px";
        payDiv.style.boxShadow = "0 2px 6px rgba(0,0,0,0.1)";
        payDiv.innerHTML = `
            <p>Amount to Pay: ₦${payment.amount}</p>
            <p>Status: <strong>${payment.status.toUpperCase()}</strong></p>
            ${payment.status !== "paid" ? '<button id="pay-btn" class="btn">Pay Now</button>' : ''}
        `;
        accountBox.appendChild(payDiv);

        if (payment.status !== "paid") {
    const payBtn = document.getElementById("pay-btn");
    payBtn.addEventListener("click", async () => {
        // Fake payment process
        const res = await fetch("/api/payment/mark_paid", { method: "POST", credentials: "same-origin" });
        if (res.ok) {
            alert("Payment successful!");
            window.location.reload(); // Reload so courses unlock
        } else {
            alert("Payment failed. Try again.");
        }
    });
}

        // Fetch courses
        const courseRes = await fetch("/api/courses/my", { credentials: "same-origin" });
        const data = await courseRes.json();
        const list = document.getElementById("courses");
        list.innerHTML = "";

        if (!data.courses || data.courses.length === 0) {
            list.innerHTML = "<li>No courses yet</li>";
        } else {
            data.courses.forEach(course => {
                const a = document.createElement("a");
                a.href = "#";
                a.textContent = `${course.code} - ${course.title}`;

                a.onclick = e => {
                    e.preventDefault();
                    if (payment.status !== "paid") {
                        alert("Payment required");
                        return;
                    }
                    window.location.href = `/course/${course.id}`;
                };

                const li = document.createElement("li");
                li.appendChild(a);
                list.appendChild(li);
            });
        }

        // Logout button
        const logoutBtn = document.getElementById("logout-btn");
        if (logoutBtn) {
            logoutBtn.addEventListener("click", () => {
                window.location.href = "/logout";
            });
        }

    } catch (err) {
        console.error("Account page error:", err);
        window.location.href = "/login-page";
    }
});