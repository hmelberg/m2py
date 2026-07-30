// Felles klient-side nøkkellager med policyer (spec 2026-07-30-key-store-design).
// Én localStorage-post `md_keys` (v2-JSON). Tre policyer per nøkkel:
//   open   — klartekst, ingen friksjon (openstat-standarden)
//   locked — AES-256-GCM under hovedpassordet; låses opp én gang per økt
//   secret — som locked, men passord én gang per KJØRING (runScope); caches aldri
// Avledet hovednøkkel lever KUN i closure-minne (aldri sessionStorage) — reload
// spør igjen. Modulen er UI-fri: passorddialogen injiseres via Keys.attachPrompt
// (samme testbarhets-mønster som enc-crypto.js: kjøres under node:test/vm).
(function (global) {
  'use strict';

  var LS = 'md_keys';
  var KDF_ITERS = 600000;
  var VERIFIER_TEXT = 'safestat-keys-verifier';
  var NAME_RE = /^[A-Za-z0-9_-]{1,32}$/;
  var POLICIES = { open: 1, locked: 1, secret: 1 };

  var _prompt = null;   // async ({mode:'create'|'unlock'|'run', names?, ctx?}) -> passord|null
  var _master = null;   // CryptoKey for økten (locked-poster)
  var _session = {};    // navn -> klartekst; KUN locked-poster, fylles ved opplåsing
  var _run = null;      // navn -> klartekst; KUN secret-poster, innenfor runScope

  function readDoc() {
    var raw = null;
    try { raw = JSON.parse(global.localStorage.getItem(LS) || 'null'); } catch (e) {}
    if (!raw || typeof raw !== 'object') return { v: 2, entries: {} };
    if (raw.v !== 2) {
      // openstat v1: flatt {type: verdi} — alt migreres som open.
      var doc = { v: 2, entries: {} };
      Object.keys(raw).forEach(function (k) {
        if (raw[k] && typeof raw[k] === 'string') doc.entries[k] = { policy: 'open', value: raw[k], created: today() };
      });
      return doc;
    }
    if (!raw.entries) raw.entries = {};
    return raw;
  }
  function writeDoc(doc) { global.localStorage.setItem(LS, JSON.stringify(doc)); }
  function today() { return new Date().toISOString().slice(0, 10); }

  function assertName(name) {
    name = String(name || '');
    if (!NAME_RE.test(name)) throw new Error('ugyldig nøkkelnavn «' + name + '» (a-z, 0-9, - og _; maks 32 tegn)');
    if (name.toLowerCase() === 'ask') throw new Error('«ask» er reservert — key(ask) betyr «spør ved kjøring»');
  }

  // -- krypto (WebCrypto, ingen avhengigheter) ---------------------------
  function b64e(bytes) {
    var s = '';
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
  }
  function b64d(str) {
    var bin = atob(str);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  async function derive(password, kdf) {
    var base = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey(
      { name: 'PBKDF2', hash: 'SHA-256', salt: b64d(kdf.salt), iterations: kdf.iters },
      base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  }
  async function encText(key, text) {
    var iv = new Uint8Array(12);
    crypto.getRandomValues(iv);
    var ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, key, new TextEncoder().encode(text)));
    return { iv: b64e(iv), ct: b64e(ct) };
  }
  async function decText(key, env) {
    try {
      var pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(env.iv) }, key, b64d(env.ct));
      return new TextDecoder().decode(pt);
    } catch (e) {
      throw new Error('feil passord (eller ødelagt nøkkellager)');
    }
  }

  async function askPassword(opts) {
    if (!_prompt) throw new Error('nøkkellageret mangler passorddialog — Keys.attachPrompt er ikke kalt');
    var pw = await _prompt(opts);
    if (!pw) throw new Error('avbrutt — ingen passord oppgitt');
    return pw;
  }

  // Avled og verifiser mot verifikatoren; kaster «feil passord» ved bom.
  async function verifiedKey(password, doc) {
    var mk = await derive(password, doc.kdf);
    await decText(mk, doc.verifier);
    return mk;
  }

  // Sørger for at hovedpassord finnes og at _master er satt (økt-opplåsing).
  // Låser samtidig opp alle locked-poster inn i _session, slik at get() kan
  // være synkron etterpå. secret-poster går ALDRI inn i _session.
  async function ensureUnlocked(ctx) {
    if (_master) return;
    var doc = readDoc();
    if (!doc.kdf) {
      var pw = await askPassword({ mode: 'create', ctx: ctx });
      var salt = new Uint8Array(16);
      crypto.getRandomValues(salt);
      doc.kdf = { alg: 'PBKDF2-SHA-256', iters: KDF_ITERS, salt: b64e(salt) };
      _master = await derive(pw, doc.kdf);
      doc.verifier = await encText(_master, VERIFIER_TEXT);
      writeDoc(doc);
      _session = {};
      return;
    }
    var pw2 = await askPassword({ mode: 'unlock', ctx: ctx });
    var mk = await verifiedKey(pw2, doc);
    _master = mk;
    _session = {};
    var names = Object.keys(doc.entries);
    for (var i = 0; i < names.length; i++) {
      if (doc.entries[names[i]].policy === 'locked')
        _session[names[i]] = await decText(_master, doc.entries[names[i]]);
    }
  }

  // Engangsmigreringer ved modul-lasting.
  (function migrate() {
    var raw = null;
    try { raw = JSON.parse(global.localStorage.getItem(LS) || 'null'); } catch (e) {}
    var changed = !!(raw && raw.v !== 2);          // v1-format skrives om
    var doc = readDoc();
    var legacy = global.localStorage.getItem('md_anthropic_key');
    if (legacy) {
      if (!doc.entries.anthropic) doc.entries.anthropic = { policy: 'open', value: legacy, created: today() };
      global.localStorage.removeItem('md_anthropic_key');
      changed = true;
    }
    if (changed) writeDoc(doc);
  })();

  function get(name) {
    var e = readDoc().entries[name];
    if (!e) return null;
    if (e.policy === 'open') return e.value;
    if (e.policy === 'locked') return Object.prototype.hasOwnProperty.call(_session, name) ? _session[name] : null;
    return null;   // secret: aldri via synkron get — bruk resolve/runScope
  }

  async function set(name, value, policy) {
    assertName(name);
    if (!value) throw new Error('tom nøkkelverdi — bruk Keys.remove for å slette');
    var doc = readDoc();
    var existing = doc.entries[name];
    policy = policy || (existing && existing.policy) || 'open';
    if (!POLICIES[policy]) throw new Error('ukjent policy: ' + policy);
    var created = (existing && existing.created) || today();
    if (policy === 'open') {
      doc.entries[name] = { policy: 'open', value: String(value), created: created };
      writeDoc(doc);
      delete _session[name];
      return;
    }
    await ensureUnlocked(name);
    doc = readDoc();   // ensureUnlocked kan ha skrevet kdf/verifier
    var env = await encText(_master, String(value));
    doc.entries[name] = { policy: policy, iv: env.iv, ct: env.ct, created: created };
    writeDoc(doc);
    if (policy === 'locked') _session[name] = String(value); else delete _session[name];
  }

  function remove(name) {
    var doc = readDoc();
    delete doc.entries[name];
    writeDoc(doc);
    delete _session[name];
  }

  function registered() {
    var e = readDoc().entries;
    return Object.keys(e).map(function (n) { return { name: n, policy: e[n].policy }; });
  }

  function policyOf(name) {
    var e = readDoc().entries[name];
    return e ? e.policy : null;
  }

  async function resolve(name, ctx) {
    var e = readDoc().entries[name];
    if (!e) return null;
    if (e.policy === 'open') return e.value;
    if (e.policy === 'locked') {
      await ensureUnlocked(ctx);
      return Object.prototype.hasOwnProperty.call(_session, name) ? _session[name] : null;
    }
    // secret — runScope (Task 3) fyller kjøringscachen; enkeltbruk her:
    if (_run && Object.prototype.hasOwnProperty.call(_run, name)) return _run[name];
    var doc = readDoc();
    var pw = await askPassword({ mode: 'run', names: [name], ctx: ctx });
    var mk = await verifiedKey(pw, doc);
    return decText(mk, e);   // transient — caches ikke
  }

  async function setPolicy(name, policy) {
    if (!POLICIES[policy]) throw new Error('ukjent policy: ' + policy);
    var doc = readDoc();
    var e = doc.entries[name];
    if (!e) throw new Error('ukjent nøkkel: ' + name);
    if (e.policy === policy) return;
    var plain;
    if (e.policy === 'open') plain = e.value;
    else { await ensureUnlocked(name); plain = await decText(_master, e); }
    await set(name, plain, policy);
  }

  async function changePassword(oldPw, newPw) {
    var doc = readDoc();
    if (!doc.kdf) throw new Error('ingen hovedpassord er satt');
    if (!newPw) throw new Error('nytt passord kan ikke være tomt');
    var oldKey = await verifiedKey(oldPw, doc);
    var names = Object.keys(doc.entries);
    var plains = {};
    for (var i = 0; i < names.length; i++) {
      if (doc.entries[names[i]].policy !== 'open')
        plains[names[i]] = await decText(oldKey, doc.entries[names[i]]);
    }
    var salt = new Uint8Array(16);
    crypto.getRandomValues(salt);
    doc.kdf = { alg: 'PBKDF2-SHA-256', iters: KDF_ITERS, salt: b64e(salt) };
    var mk = await derive(newPw, doc.kdf);
    doc.verifier = await encText(mk, VERIFIER_TEXT);
    for (var n in plains) {
      var env = await encText(mk, plains[n]);
      doc.entries[n].iv = env.iv;
      doc.entries[n].ct = env.ct;
    }
    writeDoc(doc);   // ÉN atomisk skriving — aldri halvveis re-kryptert lager
    _master = mk;
    _session = {};
    for (var n2 in plains) if (doc.entries[n2].policy === 'locked') _session[n2] = plains[n2];
  }

  function lockNow() { _master = null; _session = {}; _run = null; }

  function resetEncrypted() {
    var doc = readDoc();
    Object.keys(doc.entries).forEach(function (n) {
      if (doc.entries[n].policy !== 'open') delete doc.entries[n];
    });
    delete doc.kdf;
    delete doc.verifier;
    writeDoc(doc);
    lockNow();
  }

  function status() {
    var doc = readDoc();
    return { hasPassword: !!doc.kdf, unlocked: !!_master };
  }

  function attachPrompt(fn) { _prompt = fn; }

  global.Keys = {
    get: get, set: set, remove: remove, registered: registered, policy: policyOf,
    resolve: resolve, setPolicy: setPolicy, changePassword: changePassword,
    lockNow: lockNow, resetEncrypted: resetEncrypted, status: status,
    attachPrompt: attachPrompt,
  };
})(typeof window !== 'undefined' ? window : globalThis);
