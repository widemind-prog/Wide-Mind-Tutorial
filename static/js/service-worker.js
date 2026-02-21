self.addEventListener("push", function(event) {
    const data = event.data.json();

    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.message,
            icon: "/static/images/logo.png",
            data: {
                url: data.link
            }
        })
    );
});

self.addEventListener("notificationclick", function(event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});