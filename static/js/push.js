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

async function subscribeToPush() {
    // Only run if service worker and push are supported
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        console.log("Push not supported");
        return;
    }

    // Only subscribe if VAPID key is available (means user is on a page that has it)
    if (!window.VAPID_PUBLIC_KEY) {
        console.log("No VAPID key, skipping push setup");
        return;
    }

    try {
        const registration = await navigator.serviceWorker.ready;

        // Check existing subscription first
        const existing = await registration.pushManager.getSubscription();
        if (existing) {
            console.log("Already subscribed to push");
            return;
        }

        // Request permission
        const permission = await Notification.requestPermission();
        if (permission !== "granted") {
            console.log("Push permission denied");
            return;
        }

        // Subscribe
        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(window.VAPID_PUBLIC_KEY)
        });

        // Send subscription to server
        const res = await fetch("/api/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify(subscription)
        });

        if (res.ok) {
            console.log("Push subscription saved successfully");
        } else {
            console.log("Failed to save subscription:", res.status);
        }

    } catch (err) {
        console.log("Push subscription error:", err);
    }
}

// Only run if user is logged in (page will have VAPID key set)
if (typeof VAPID_PUBLIC_KEY !== "undefined" && VAPID_PUBLIC_KEY) {
    window.VAPID_PUBLIC_KEY = VAPID_PUBLIC_KEY;
    // Small delay to let service worker register first
    setTimeout(subscribeToPush, 2000);
}
