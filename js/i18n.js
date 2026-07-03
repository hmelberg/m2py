// i18n.js — UI-språkmekanisme (norsk er kildespråk; ordbøker per språk i js/i18n/).
// Norsk tekst er selve nøkkelen: t('Nytt script') slår opp i M2PY_I18N[lang] og
// faller tilbake til nøkkelen (norsk) hvis oversettelsen mangler. Dermed kan
// ingenting knekke av en manglende oversettelse.
(function () {
  'use strict';

  var LANG_KEY = 'microdata_ui_lang';
  var STASH_KEY = 'm2py_lang_stash';

  // Språk appen støtter. Nytt språk = legg til her + egen ordbok js/i18n/<kode>.js.
  var SUPPORTED = ['no', 'en'];
  window.M2PY_LANGS = SUPPORTED;

  function detectInitialLang() {
    try {
      var stored = localStorage.getItem(LANG_KEY);
      if (SUPPORTED.indexOf(stored) !== -1) return stored;
    } catch (e) {}
    var langs = (navigator.languages && navigator.languages.length)
      ? navigator.languages : [navigator.language || ''];
    for (var i = 0; i < langs.length; i++) {
      var p = String(langs[i]).toLowerCase().split('-')[0];
      if (p === 'no' || p === 'nb' || p === 'nn') return 'no';
      if (SUPPORTED.indexOf(p) !== -1) return p;
    }
    return 'en'; // ukjent nettleserspråk → engelsk
  }

  var LANG = detectInitialLang();
  window.M2PY_LANG = LANG;
  try { document.documentElement.lang = LANG; } catch (e) {}

  function normKey(s) {
    s = String(s).replace(/\s+/g, ' ').trim();
    return s.normalize ? s.normalize('NFC') : s;
  }

  function debugOn() {
    try { return localStorage.getItem('m2py_i18n_debug') === '1'; } catch (e) { return false; }
  }
  window.__i18nMissing = window.__i18nMissing || new Set();

  // t('Kunne ikke åpne: {msg}', { msg: e.message }) — {navn}-plassholdere
  // erstattes også i fallbacken, så norsk fungerer uendret uten oversettelse.
  window.t = function (key, params) {
    var s = key;
    var dict = (window.M2PY_I18N || {})[LANG];
    if (dict && Object.prototype.hasOwnProperty.call(dict, key)) {
      s = dict[key];
    } else if (LANG !== 'no' && debugOn()) {
      window.__i18nMissing.add(key);
    }
    if (params) {
      s = s.replace(/\{(\w+)\}/g, function (m, k) {
        return Object.prototype.hasOwnProperty.call(params, k) ? params[k] : m;
      });
    }
    return s;
  };

  function lookup(key) {
    var dict = (window.M2PY_I18N || {})[LANG];
    if (dict && Object.prototype.hasOwnProperty.call(dict, key)) return dict[key];
    return null;
  }

  // Oversetter statisk markup merket med data-i18n-attributter. Nøkkelen leses
  // fra DOM-en (entiteter som &#248; er allerede dekodet). Idempotent: etter
  // oversettelse finnes ikke den engelske teksten som nøkkel, så andre gangs
  // kjøring endrer ingenting. Ren no-op når språket er norsk.
  window.applyTranslations = function (root) {
    if (LANG === 'no') return;
    root = root || document;
    var i, el, key, val;

    var textEls = root.querySelectorAll('[data-i18n]');
    for (i = 0; i < textEls.length; i++) {
      el = textEls[i];
      key = normKey(el.textContent);
      val = lookup(key);
      if (val !== null) el.textContent = val;
      else if (key && debugOn()) window.__i18nMissing.add(key);
    }

    var htmlEls = root.querySelectorAll('[data-i18n-html]');
    for (i = 0; i < htmlEls.length; i++) {
      el = htmlEls[i];
      key = normKey(el.textContent);
      val = lookup(key);
      if (val !== null) el.innerHTML = val; // verdier forfattes i repoet (js/i18n/*.js)
      else if (key && debugOn()) window.__i18nMissing.add(key);
    }

    var attrs = [['data-i18n-title', 'title'], ['data-i18n-placeholder', 'placeholder'], ['data-i18n-aria', 'aria-label']];
    for (var a = 0; a < attrs.length; a++) {
      var marked = root.querySelectorAll('[' + attrs[a][0] + ']');
      for (i = 0; i < marked.length; i++) {
        el = marked[i];
        key = normKey(el.getAttribute(attrs[a][1]) || '');
        if (!key) continue;
        val = lookup(key);
        if (val !== null) el.setAttribute(attrs[a][1], val);
        else if (debugOn()) window.__i18nMissing.add(key);
      }
    }
  };

  // Hjelper for objekter med parallelle feltoversettelser, f.eks.
  // i18nField(help, 'description') → help.description_en på engelsk (om satt).
  window.i18nField = function (obj, field) {
    if (!obj) return undefined;
    if (LANG !== 'no' && obj[field + '_' + LANG]) return obj[field + '_' + LANG];
    return obj[field];
  };

  // Språkbytte: lagre valget, ta vare på editorinnholdet (ingen autosave i
  // appen!) og last siden på nytt. Reload gir konsistent UI via vanlig boot.
  window.m2pySetLang = function (lang) {
    if (SUPPORTED.indexOf(lang) === -1) return;
    if (lang === LANG) return;
    try {
      var si = document.getElementById('scriptInput');
      var sn = document.getElementById('scriptName');
      sessionStorage.setItem(STASH_KEY, JSON.stringify({
        script: si ? si.value : '',
        name: sn ? sn.value : ''
      }));
    } catch (e) {}
    try { localStorage.setItem(LANG_KEY, lang); } catch (e) {}
    location.reload();
  };

  function restoreStash() {
    var raw = null;
    try {
      raw = sessionStorage.getItem(STASH_KEY);
      if (raw !== null) sessionStorage.removeItem(STASH_KEY);
    } catch (e) {}
    if (raw === null) return;
    try {
      var data = JSON.parse(raw);
      var si = document.getElementById('scriptInput');
      var sn = document.getElementById('scriptName');
      if (si && typeof data.script === 'string') {
        si.value = data.script;
        si.dispatchEvent(new Event('input', { bubbles: true }));
      }
      if (sn && typeof data.name === 'string') sn.value = data.name;
    } catch (e) {}
  }

  // Feilsøking: finn synlig norsk tekst som mangler oversettelse (kjør i konsollen
  // med engelsk UI): window.__i18nScan()
  window.__i18nScan = function () {
    var out = [];
    var no = /[æøåÆØÅ]/;
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var n;
    while ((n = walker.nextNode())) {
      var p = n.parentElement;
      if (!p || p.closest('script, style, textarea, #outputArea')) continue;
      if (no.test(n.nodeValue) && p.offsetParent !== null) {
        out.push({ text: normKey(n.nodeValue), el: p });
      }
    }
    var attrEls = document.querySelectorAll('[title], [placeholder], [aria-label]');
    for (var i = 0; i < attrEls.length; i++) {
      var el = attrEls[i];
      ['title', 'placeholder', 'aria-label'].forEach(function (a) {
        var v = el.getAttribute(a);
        if (v && no.test(v)) out.push({ attr: a, text: normKey(v), el: el });
      });
    }
    console.table(out.map(function (o) { return { where: o.attr || 'text', text: o.text.slice(0, 90) }; }));
    return out;
  };

  // Pass 1 kjøres umiddelbart (markupen over <script>-taggene er allerede
  // parset); pass 2 på DOMContentLoaded tar markupen etter (modaler nederst).
  window.applyTranslations(document);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { window.applyTranslations(document); });
  }
  if (document.readyState === 'complete') setTimeout(restoreStash, 0);
  else window.addEventListener('load', function () { setTimeout(restoreStash, 0); });
})();
