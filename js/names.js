// js/names.js — navneregister-oppslag (dashboard-spec 2026-07-09 §4).
// Ren pick() (node-testet) + tynn lookup() med tre kilder i fallback-rekke:
// remote-register → localStorage-cache → medfølgende names.json.
// Ingen avhengigheter til resten av appen.
(function (global) {
  'use strict';
  var N = {};
  N.REGISTRY_URL = 'https://raw.githubusercontent.com/hmelberg/dashstatlink/main/names.json';
  var LS_KEY = 'm2py_names_cache';

  // Verdi kan være streng (dotted ref eller URL) eller objekt med .url
  // (metadata-formen, spec §4) — alt annet er miss.
  N.pick = function (registry, name) {
    if (!registry || typeof registry !== 'object') return null;
    var v = registry[name];
    if (typeof v === 'string') return v;
    if (v && typeof v === 'object' && typeof v.url === 'string') return v.url;
    return null;
  };

  N.lookup = async function (name) {
    var reg = null;
    try {
      var res = await fetch(N.REGISTRY_URL, { cache: 'no-cache' });
      if (res.ok) {
        reg = await res.json();
        try { localStorage.setItem(LS_KEY, JSON.stringify(reg)); } catch (_) {}
      }
    } catch (_) {}
    if (!reg) { try { reg = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (_) {} }
    if (!reg) { try { var r2 = await fetch('names.json'); if (r2.ok) reg = await r2.json(); } catch (_) {} }
    return N.pick(reg, name);
  };

  // Vennlig feilbanner ved ukjent navn (spec §4) — selvforsynt DOM.
  N.showNameError = function (name, t) {
    if (typeof document === 'undefined') return;
    var tf = t || function (s) { return s; };
    var bar = document.createElement('div');
    bar.className = 'names-error-banner';
    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;padding:10px 16px;'
      + 'background:#b23;color:#fff;font:14px system-ui;display:flex;justify-content:space-between;align-items:center';
    var span = document.createElement('span');
    span.textContent = tf('Fant ikke navnet i navneregisteret:') + ' «' + name + '»';
    var x = document.createElement('button');
    x.textContent = '×';
    x.setAttribute('aria-label', tf('Lukk'));
    x.style.cssText = 'background:none;border:none;color:#fff;font-size:18px;cursor:pointer';
    x.onclick = function () { bar.remove(); };
    bar.appendChild(span); bar.appendChild(x);
    document.body.appendChild(bar);
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = N;
  global.DashboardNames = N;
})(typeof window !== 'undefined' ? window : globalThis);
