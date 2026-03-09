function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, '+')
        .replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

function pushLog(msg) {
    console.log(msg);
    var el = document.getElementById("push-debug");
    if (el) el.innerHTML += msg + "<br>";
}

async function subscribeToPush() {
    pushLog("SW supported: " + ("serviceWorker" in navigator));
    pushLog("Push supported: " + ("PushManager" in window));
    pushLog("VAPID: " + (typeof VAPID_PUBLIC_KEY !== "undefined" && VAPID_PUBLIC_KEY ? "present" : "MISSING"));
    pushLog("Permission: " + Notification.permission);

    if (!("serviceWorker" in navigator)) { pushLog("STOP: no SW"); return; }
    if (!("PushManager" in window)) { pushLog("STOP: no PushManager"); return; }
    if (typeof VAPID_PUBLIC_KEY === "undefined" || !VAPID_PUBLIC_KEY) { pushLog("STOP: no VAPID"); return; }

    try {
        pushLog("Waiting for SW...");
        const registration = await navigator.serviceWorker.ready;
        pushLog("SW ready: " + registration.scope);

        const existing = await registration.pushManager.getSubscription();
        pushLog("Existing sub: " + (existing ? "YES" : "none"));
        if (existing) { pushLog("Already subscribed"); return; }

        pushLog("Requesting permission...");
        const permission = await Notification.requestPermission();
        pushLog("Permission: " + permission);

        if (permission !== "granted") { pushLog("STOP: not granted"); return; }

        pushLog("Subscribing...");
        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
        });
        pushLog("Subscribed: " + subscription.endpoint.substring(0, 40) + "...");

        const res = await fetch("/api/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify(subscription)
        });
        pushLog("Server: " + res.status);

    } catch (err) {
        pushLog("ERROR: " + err.message);
    }
}

window.VAPID_PUBLIC_KEY = typeof VAPID_PUBLIC_KEY !== "undefined" ? VAPID_PUBLIC_KEY : null;
setTimeout(subscribeToPush, 2000);
