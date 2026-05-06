const CACHE = 'm2py-v1';
const CDN_HOSTS = new Set([
  'cdn.jsdelivr.net',
  'cdn.plot.ly',
  'files.pythonhosted.org',
  'pypi.org'
]);
const LOCAL_SWR_SUFFIXES = [
  '/m2py.py',
  '/functions.py',
  '/variable_metadata.json',
  '/mockdata_core.py',
  '/mockdata_realism.py'
];

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(keys => Promise.all(
    keys.filter(k => k !== CACHE).map(k => caches.delete(k))
  )).then(() => self.clients.claim())
));

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  if (CDN_HOSTS.has(url.hostname)) {
    e.respondWith(cacheFirst(e.request));
    return;
  }

  if (url.origin === self.location.origin &&
      LOCAL_SWR_SUFFIXES.some(s => url.pathname.endsWith(s))) {
    e.respondWith(staleWhileRevalidate(e.request));
    return;
  }
});

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res && (res.ok || res.type === 'opaque')) {
      cache.put(req, res.clone()).catch(() => {});
    }
    return res;
  } catch (err) {
    const fallback = await cache.match(req, { ignoreSearch: true });
    if (fallback) return fallback;
    throw err;
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE);
  const keyUrl = new URL(req.url);
  const key = new Request(keyUrl.origin + keyUrl.pathname);
  const hit = await cache.match(key);
  const network = fetch(req).then(res => {
    if (res && res.ok) cache.put(key, res.clone()).catch(() => {});
    return res;
  }).catch(() => hit);
  return hit || network;
}
