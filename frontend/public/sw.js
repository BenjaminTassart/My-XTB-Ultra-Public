// Service worker minimal : l'application s'ouvre meme si le reseau est lent.
// Les appels /api ne sont jamais mis en cache ici (le cache des donnees est cote serveur).
const CACHE = 'xtb-shell-v2'

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith('xtb-shell-') && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  )
})
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api')) return
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone()
          e.waitUntil(caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {}))
        }
        return res
      })
      .catch(() => caches.match(e.request).then((r) => r || (e.request.mode === 'navigate' ? caches.match('/').then(page => page || Response.error()) : Response.error())))
  )
})

self.addEventListener('push', (event) => {
  let data = {}
  try { data = event.data?.json() || {} } catch { /* notification générique */ }
  event.waitUntil(self.registration.showNotification(data.title || 'My XTB Ultra', {
    body: data.body || 'Un seuil de prix a été atteint.', icon: '/icon-192.png',
    tag: data.tag || 'xtb-alert', data: { url: '/?tab=portfolio' },
  }))
})
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(self.clients.openWindow('/?tab=portfolio'))
})
