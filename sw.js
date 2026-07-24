// IMPORTANT: bump CACHE whenever PRECACHE_URLS (or any precached asset) changes,
// otherwise clients keep serving the stale cache. The Pyodide version string is
// duplicated across this file (PRECACHE_URLS below), index.html and
// export_data*.html — update all together when upgrading Pyodide.
const PYODIDE_VERSION = 'v314.0.2';
const CACHE = 'm2py-v15';
const CDN_HOSTS = new Set([
  'cdn.jsdelivr.net',
  'cdn.plot.ly',
  'files.pythonhosted.org',
  'pypi.org',
  'webr.r-wasm.org',    // webR-runtime (jamovi-modus)
  'repo.r-wasm.org'     // wasm-R-pakker: jmv, scatr m.fl. (~170 MB, cache-first)
]);
// Cache-skew-fiksen (portet fra openstat 2026-07-23): den gamle ENUMERERTE
// listen driftet — den manglet bl.a. duckdb_bridge.py, pyodide/dash.py og
// mockdata_export.py, som dermed falt til ren HTTP-cache med heuristisk TTL
// (observert stale-krasj etter deploy tre ganger i openstat 2026-07-20..22).
// Nå dekkes ALLE lokale .py-filer av én suffiks-regel, så nye filer aldri
// kan glemmes.
function isLocalPySwr(pathname) {
  return pathname.endsWith('.py') || pathname.endsWith('/variable_metadata.json');
}

const PRECACHE_URLS = [
  'https://cdn.jsdelivr.net/pyodide/' + PYODIDE_VERSION + '/full/pyodide.js',
  'https://cdn.jsdelivr.net/pyodide/' + PYODIDE_VERSION + '/full/pyodide.mjs',
  'https://cdn.jsdelivr.net/pyodide/' + PYODIDE_VERSION + '/full/pyodide.asm.wasm',
  'https://cdn.jsdelivr.net/pyodide/' + PYODIDE_VERSION + '/full/pyodide-lock.json',
  'https://cdn.jsdelivr.net/pyodide/' + PYODIDE_VERSION + '/full/python_stdlib.zip',
  'https://cdn.plot.ly/plotly-2.32.0.min.js',
  'https://cdn.jsdelivr.net/npm/markdown-it@14.1.0/dist/markdown-it.min.js',
  'https://cdn.jsdelivr.net/npm/brython@3.12.0/brython.min.js',
  'https://cdn.jsdelivr.net/npm/brython@3.12.0/brython_stdlib.js'
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

  if (url.origin === self.location.origin && isLocalPySwr(url.pathname)) {
    e.respondWith(staleWhileRevalidate(e.request));
    return;
  }

  // App-shell assets (index.html, app.css, js/*.js, command_help.js,
  // widgets/forklar-widgets.js) intentionally fall through to plain
  // network/HTTP-cache — they are NOT precached or runtime-cached here.
  // If you ever add the shell to the SW for offline support, add index.html
  // alongside its css/js and bump CACHE.
});

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;
  try {
    const res = await fetch(req);
    // Cache only real, inspectable responses. Opaque (cross-origin no-cors)
    // responses are padded to a large fixed size in the quota (~7MB each) — and
    // our CDN (jsdelivr) sends CORS, so res.ok is the right gate.
    if (res && res.ok) {
      cache.put(req, res.clone()).catch(() => {});
      return res;
    }
    // Transient 4xx/5xx (CDN-blipp): prøv cachet kopi før vi gir feilen videre —
    // en resolved !ok-respons nådde aldri catch-fallbacken under.
    const stale = await cache.match(req, { ignoreSearch: true });
    return stale || res;
  } catch (err) {
    const fallback = await cache.match(req, { ignoreSearch: true });
    if (fallback) return fallback;
    throw err;
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE);
  // Cache-skew-fiksen (portet fra openstat 2026-07-23): nøkkelen inkluderer nå
  // SØKESTRENGEN. Versjonerte fetcher (?v=M2PY_VERSION) gir dermed cache-MISS
  // ved versjonsbump → ferskt nettverkssvar på FØRSTE last etter deploy, i
  // stedet for SWR-ens serve-stale-først. Gamle versjonsnøkler ryddes ved
  // CACHE-navnebump (activate-sveipet).
  const key = new Request(req.url);
  const hit = await cache.match(key);
  // 'no-cache': revalider mot server (304 ved uendret). Default cache-modus
  // kunne hente stale svar fra HTTP-diskcachen (kun Last-Modified-header →
  // heuristisk freshness) og overskrive Cache Storage med gammelt innhold.
  const network = fetch(req.url, { cache: 'no-cache' }).then(res => {
    if (res && res.ok) cache.put(key, res.clone()).catch(() => {});
    return res;
  });
  // Never resolve to undefined (that breaks respondWith). If we have a cached
  // copy, serve it and let the network revalidate in the background; otherwise
  // return the network promise — if it rejects, respondWith yields a normal
  // network error rather than an undefined response.
  if (hit) { network.catch(() => {}); return hit; }
  return network;
}
