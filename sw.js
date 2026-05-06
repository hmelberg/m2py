const CACHE = 'm2py-v2';
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

const PRECACHE_URLS = [
  'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.js',
  'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.asm.wasm',
  'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.asm.js',
  'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide-lock.json',
  'https://cdn.plot.ly/plotly-2.32.0.min.js',
  'https://cdn.jsdelivr.net/npm/markdown-it@14.1.0/dist/markdown-it.min.js'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache =>
      Promise.allSettled(
        PRECACHE_URLS.map(u =>
          fetch(u, { cache: 'no-cache' })
            .then(r => (r && (r.ok || r.type === 'opaque')) ? cache.put(u, r) : null)
            .catch(() => null)
        )
      )
    ).then(() => self.skipWaiting())
  );
});

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
