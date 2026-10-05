const CACHE_NAME = 'kids-tv-cache-v9';
const ASSETS = ['./', './index.html', './kids-tv.png', './icon-192.png', './icon-512.png', './manifest.json', './firebase-config.js'];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      // لا يفشل التثبيت كله إذا تعذّر تخزين ملف واحد
      return Promise.all(ASSETS.map(function (url) {
        return cache.add(url).catch(function () {});
      }));
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (key) { return key !== CACHE_NAME; })
          .map(function (key) { return caches.delete(key); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

function isCodeRequest(request, url) {
  if (request.mode === 'navigate') return true;
  return /\.(?:html|js|json)$/i.test(url.pathname) || url.pathname.endsWith('/');
}

self.addEventListener('fetch', function (event) {
  const request = event.request;
  if (request.method !== 'GET') return;
  var url;
  try { url = new URL(request.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;

  if (isCodeRequest(request, url)) {
    // الشبكة أولاً حتى تصل التحديثات فوراً، والكاش عند انقطاع الاتصال
    event.respondWith(
      fetch(request).then(function (response) {
        if (response && response.ok) {
          const cloned = response.clone();
          caches.open(CACHE_NAME).then(function (cache) { cache.put(request, cloned); }).catch(function () {});
        }
        return response;
      }).catch(function () {
        return caches.match(request).then(function (cached) {
          return cached || caches.match('./index.html') || new Response('', { status: 503, statusText: 'Offline' });
        });
      })
    );
    return;
  }

  // الصور والملفات الثابتة: الكاش أولاً
  event.respondWith(
    caches.match(request).then(function (cached) {
      return cached || fetch(request).then(function (response) {
        if (response && response.ok) {
          const cloned = response.clone();
          caches.open(CACHE_NAME).then(function (cache) { cache.put(request, cloned); }).catch(function () {});
        }
        return response;
      }).catch(function () {
        return new Response('', { status: 503, statusText: 'Offline' });
      });
    })
  );
});
