document.addEventListener("DOMContentLoaded", async () => {
    try {
        // --- 1. User info ---
        const meRes = await fetch("/api/auth/me", { credentials: "same-origin" });
        if (!meRes.ok) return window.location.href = "/login-page";
        const user = await meRes.json();
        document.getElementById("username").textContent = user.name;
        document.getElementById("department").textContent = user.department;
        document.getElementById("level").textContent = user.level;

        // --- 2. Payment status ---
        const payRes = await fetch("/api/payment/status", { credentials: "same-origin" });
        let payment = { status: "unpaid", amount: 20000 };
        if (payRes.ok) payment = await payRes.json();

        // --- 3. Payment box ---
        const accountBox = document.querySelector(".account-box");
        const payDiv = document.createElement("div");
        payDiv.classList.add("payment-box");
        payDiv.style = "margin-top:15px;padding:10px;background:#fff8dc;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.1)";
        payDiv.innerHTML = `
            <p>Amount to Pay: ₦${payment.amount}</p>
            <p>Status: <strong>${payment.status.toUpperCase()}</strong></p>
            ${payment.status !== "paid" ? '<button id="pay-btn" class="btn">Pay Now</button>' : ''}
        `;
        accountBox.appendChild(payDiv);

        if (payment.status !== "paid") {
            document.getElementById("pay-btn").addEventListener("click", async () => {
                const res = await fetch("/api/payment/init", { method: "POST", credentials: "same-origin" });
                const data = await res.json();
                if (data.status) window.location.href = data.data.authorization_url;
            });
        }

        // --- 4. Courses ---
        const courseRes = await fetch("/api/courses/my", { credentials: "same-origin" });
        const data = await courseRes.json();
        const list = document.getElementById("courses");
        list.innerHTML = "";

        if (!data.courses || data.courses.length === 0) {
            list.innerHTML = "<li>No courses yet</li>";
        } else {
            data.courses.forEach(course => {
                const li = document.createElement("li");
                const a = document.createElement("a");
                a.textContent = `${course.code} - ${course.title}`;
                a.href = payment.status === "paid" ? `/course/${course.id}` : "#";
                a.onclick = e => {
                    if (payment.status !== "paid") {
                        e.preventDefault();
                        alert("Payment required");
                    }
                };
                li.appendChild(a);
                list.appendChild(li);
            });
        }

        // --- 5. Logout ---
        const logoutBtn = document.getElementById("logout-btn");
        if (logoutBtn) logoutBtn.addEventListener("click", () => window.location.href = "/logout");

    } catch (err) {
        console.error("Account page error:", err);
        window.location.href = "/login-page";
    }
});