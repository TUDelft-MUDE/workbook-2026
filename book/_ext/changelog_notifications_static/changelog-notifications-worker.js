"use strict";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const bookUrl = new URL("../", self.location.href);
    const target = new URL(event.notification.data.url, bookUrl);
    if (target.origin !== bookUrl.origin || !target.pathname.startsWith(bookUrl.pathname)) {
      throw new Error("Invalid changelog notification URL");
    }

    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const changelog = windows.find((client) => client.url === target.href);
    if (changelog) {
      await changelog.focus();
    } else {
      await self.clients.openWindow(target.href);
    }
  })());
});
