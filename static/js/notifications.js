const socket = io();

const bell = document.getElementById("notification-bell");
const dropdown = document.getElementById("notif-dropdown");
const notifList = document.getElementById("notif-list");
const notifCount = document.getElementById("notif-count");

if (bell) {

    // Toggle dropdown
    bell.addEventListener("click", (e) => {
        e.stopPropagation();
        dropdown.classList.toggle("active");
    });

    // Close when clicking outside
    document.addEventListener("click", (event) => {
        if (!dropdown.contains(event.target) && !bell.contains(event.target)) {
            dropdown.classList.remove("active");
        }
    });

    function formatDateTime(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString();
    }

    function loadNotifications() {
        fetch("/api/notifications")
        .then(res => res.json())
        .then(data => {
            notifList.innerHTML = "";
            let unread = 0;

            if (data.length === 0) {
                notifList.innerHTML = "<p style='padding:15px;'>No notifications yet.</p>";
            }

            data.forEach(n => {

                if (!n.is_read) unread++;

                const div = document.createElement("div");
                div.className = `notif-item ${n.is_read ? "" : "unread"}`;

                div.innerHTML = `
                    <h4>${n.title}</h4>
                    <p>${n.message}</p>
                    <small>${formatDateTime(n.created_at)}</small>
                `;

                div.onclick = () => {
                    fetch(`/api/notifications/read/${n.id}`, {
                        method: "POST"
                    }).then(() => {
                        window.location = n.link || "#";
                    });
                };

                notifList.appendChild(div);
            });

            if (unread > 0) {
                notifCount.textContent = unread;
                notifCount.style.display = "inline-block";
            } else {
                notifCount.style.display = "none";
            }
        });
    }

    // Real-time updates
    socket.on("new_notification", () => {
        loadNotifications();
    });

    loadNotifications();
}

/* ---------------- PUSH SUBSCRIPTION ---------------- */

const publicKey = typeof VAPID_PUBLIC_KEY !== "undefined" ? VAPID_PUBLIC_KEY : null;

async function subscribePush() {

    if (!publicKey) return;

    const registration = await navigator.serviceWorker.ready;

    const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey)
    });

    await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(subscription)
    });
}

function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, "+")
        .replace(/_/g, "/");

    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
}