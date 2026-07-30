// Kontosynk av nøkkellageret (fase 2, spec 2026-07-30-key-store-design §3.5):
// md_keys-dokumentet synces AS-IS til mdataapi (zero-knowledge — locked/
// secret-poster er ciphertext under hovedpassordet; kun open-poster er
// lesbare for serveren). Newest-wins på doc.updated — ISO-strenger
// sammenlignes leksikografisk, ingen klokkeparsing. Triggere: app-start
// (under), innlogging (login.js kaller syncNow) og enhver lager-mutasjon
// (Keys.onChange, debounced). Pull går via Keys.replaceDoc, som bevisst
// IKKE fyrer onChange — ellers push-løkke.
(function (global) {
  'use strict';

  var _debounceMs = 1500;
  var _timer = null;
  var _last = null;    // 'pulled' | 'pushed' | 'uptodate' | 'error' | null
  var _deps = null;    // test-injeksjon via _configure

  function deps() {
    return _deps || {
      keys: global.Keys,
      auth: global.mdAuth,
      fetchImpl: global.fetch ? global.fetch.bind(global) : null,
    };
  }

  function active() {
    var d = deps();
    return !!(d.auth && d.auth.isLoggedIn && d.keys && d.fetchImpl);
  }

  function base(d) { return String(d.auth.apiBase()).replace(/\/+$/, ''); }
  function hdrs(d) { return { 'Authorization': 'Bearer ' + d.auth.token }; }

  async function push(d) {
    var raw = d.keys.rawDoc();
    if (!raw) return;
    var res = await d.fetchImpl(base(d) + '/_/api/keystore', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, hdrs(d)),
      body: JSON.stringify({ doc: raw }),
    });
    if (!res.ok) throw new Error('keystore POST ' + res.status);
  }

  async function syncNow() {
    var d = deps();
    if (!active()) { _last = null; return 'off'; }
    try {
      var res = await d.fetchImpl(base(d) + '/_/api/keystore', { headers: hdrs(d) });
      if (!res.ok) throw new Error('keystore GET ' + res.status);
      var remote = await res.json();
      var localUpdated = d.keys.updatedAt() || '';
      var remoteUpdated = remote.updated || '';
      if (remote.doc && remoteUpdated > localUpdated) {
        d.keys.replaceDoc(remote.doc);
        _last = 'pulled';
      } else if (localUpdated && localUpdated > remoteUpdated) {
        await push(d);
        _last = 'pushed';
      } else {
        _last = 'uptodate';
      }
    } catch (e) {
      _last = 'error';
    }
    return _last;
  }

  async function pushNow() {
    var d = deps();
    if (!active()) return 'off';
    try {
      await push(d);
      _last = 'pushed';
    } catch (e) {
      _last = 'error';
    }
    return _last;
  }

  function schedulePush() {
    if (!active()) return;
    if (_timer) clearTimeout(_timer);
    _timer = setTimeout(function () { _timer = null; pushNow(); }, _debounceMs);
  }

  function status() { return { active: active(), last: _last }; }

  function _configure(overrides, debounceMs) {
    _deps = overrides || null;
    if (debounceMs != null) _debounceMs = debounceMs;
  }

  if (global.Keys && global.Keys.onChange) global.Keys.onChange(schedulePush);

  // App-start: login-token ligger allerede i localStorage (login.js), så én
  // syncNow ved oppstart henter/publiserer nyeste versjon.
  if (typeof document !== 'undefined') {
    var boot = function () { syncNow(); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else setTimeout(boot, 0);
  }

  global.KeysSync = {
    syncNow: syncNow, pushNow: pushNow, status: status, active: active,
    _configure: _configure,
  };
})(typeof window !== 'undefined' ? window : globalThis);
