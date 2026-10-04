const CACHE_NAME = 'kids-tv-cache-v3';
const ASSETS = ['./', './index.html', './kids-tv.png', './manifest.json', './firebase-config.js'];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(ASSETS);
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
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function (event) {
  if (event.request.method !== 'GET') return;
  var requestUrl;
  try{requestUrl=new URL(event.request.url);}catch(e){return;}
  if(requestUrl.origin!==self.location.origin)return;

  event.respondWith(
    caches.match(event.request).then(function (cached) {
      return cached || fetch(event.request).then(function (response) {
        if(response.ok){
          const cloned = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(event.request, cloned);
          });
        }
        return response;
      }).catch(function () {
        if (event.request.mode === 'navigate') return caches.match('./index.html');
        return caches.match(event.request).then(function (cachedResponse) {
          return cachedResponse || new Response('', { status: 503, statusText: 'Offline' });
        });
      });
    })
  );
});
