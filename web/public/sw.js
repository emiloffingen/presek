self.addEventListener('push', function(event) {
  if (event.data) {
    let payload = {};
    try {
      payload = event.data.json();
    } catch (e) {
      payload = { title: "Пресек", message: event.data.text() };
    }
    
    event.waitUntil(
      self.registration.showNotification(payload.title || "Пресек", {
        body: payload.message || "Ново известување",
        icon: '/img/presek_emblem.png',
        badge: '/img/presek_emblem.png',
        data: { url: payload.click_url || '/' },
        vibrate: [200, 100, 200]
      })
    );
  }
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windowClients => {
      for (let i = 0; i < windowClients.length; i++) {
        let client = windowClients[i];
        if (client.url.includes(event.notification.data.url) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(event.notification.data.url);
      }
    })
  );
});
