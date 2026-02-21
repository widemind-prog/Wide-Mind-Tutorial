const socket = io();

const bell = document.getElementById("notification-bell");
const dropdown = document.getElementById("notification-dropdown");
const notifList = document.getElementById("notif-list");
const notifCount = document.getElementById("notif-count");

bell.onclick = () => {
    dropdown.classList.toggle("active");
};

function loadNotifications() {
    fetch("/api/notifications")
    .then(res => res.json())
    .then(data => {
        notifList.innerHTML = "";
        let unread = 0;

        data.forEach(n => {
            if (!n.is_read) unread++;

            const div = document.createElement("div");
            div.className = "notif-item";
            div.innerHTML = `
                <strong>${n.title}</strong>
                <p>${n.message}</p>
            `;
            div.onclick = () => {
                fetch(`/api/notifications/read/${n.id}`, {method:"POST"});
                window.location = n.link || "#";
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

socket.on("new_notification", (data) => {
    loadNotifications();
});

loadNotifications();

const publicKey = VAPID_PUBLIC_KEY;

async function subscribePush() {
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

document.addEventListener("click", function(event) {
    if (!bell.contains(event.target)) {
        dropdown.classList.remove("active");
    }
});