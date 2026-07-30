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

  // Kryptolaget kommer i Task 2 — stubber så open-policyen står alene.
  async function ensureUnlocked() { throw new Error('kryptering kommer i Task 2'); }
  async function encText() { throw new Error('kryptering kommer i Task 2'); }

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

  function attachPrompt(fn) { _prompt = fn; }

  global.Keys = {
    get: get, set: set, remove: remove, registered: registered, policy: policyOf,
    attachPrompt: attachPrompt,
  };
})(typeof window !== 'undefined' ? window : globalThis);
