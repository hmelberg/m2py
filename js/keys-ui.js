// UI for nøkkellageret (spec 2026-07-30-key-store-design §3.4): passorddialog
// (create/unlock/run) her; selve «Nøkler…»-modalen bygges på i samme modul.
// keys.js er UI-fri — denne fila registrerer dialogen via Keys.attachPrompt.
(function (global) {
  'use strict';
  var T = global.t || function (s, p) {
    return p ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in p ? p[k] : m; }) : s;
  };
  function $(id) { return document.getElementById(id); }

  var MSG = {
    create: 'Sett et hovedpassord for krypterte nøkler. Glemmer du det, kan de krypterte nøklene ikke gjenopprettes — da må de legges inn på nytt.',
    unlock: 'Lås opp nøkkellageret for denne økten.',
    run: 'Kjøringen bruker hemmelige nøkler: {names}. Oppgi hovedpassordet for å autorisere denne kjøringen.',
  };

  // fn({mode:'create'|'unlock'|'run', names?, ctx?}) -> Promise<passord|null>
  function promptPassword(opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      var bd = $('pwPromptBackdrop'), input = $('pwPromptInput'), confirm = $('pwPromptConfirm');
      var err = $('pwPromptError'), ok = $('pwPromptOk'), cancel = $('pwPromptCancel');
      if (!bd) return resolve(null);
      var create = opts.mode === 'create';
      $('pwPromptTitle').textContent = create ? T('Sett hovedpassord') : T('Hovedpassord');
      $('pwPromptMsg').textContent = opts.mode === 'run'
        ? T(MSG.run, { names: (opts.names || []).join(', ') })
        : T(MSG[opts.mode] || MSG.unlock);
      input.value = ''; confirm.value = '';
      confirm.style.display = create ? '' : 'none';
      if (create) confirm.placeholder = T('Gjenta passordet');
      err.style.display = 'none';
      bd.classList.add('open');
      setTimeout(function () { input.focus(); }, 60);
      function done(val) {
        bd.classList.remove('open');
        ok.removeEventListener('click', onOk);
        cancel.removeEventListener('click', onCancel);
        bd.removeEventListener('keydown', onKey);
        resolve(val);
      }
      function fail(msg) { err.textContent = msg; err.style.display = ''; input.focus(); }
      function onOk() {
        var v = input.value;
        if (!v) return fail(T('Passordet kan ikke være tomt'));
        if (create && v.length < 8) return fail(T('Minst 8 tegn'));
        if (create && v !== confirm.value) return fail(T('Passordene er ikke like'));
        done(v);
      }
      function onCancel() { done(null); }
      function onKey(e) {
        if (e.key === 'Enter') { e.preventDefault(); onOk(); }
        if (e.key === 'Escape') onCancel();
      }
      ok.addEventListener('click', onOk);
      cancel.addEventListener('click', onCancel);
      bd.addEventListener('keydown', onKey);
    });
  }

  if (global.Keys) global.Keys.attachPrompt(promptPassword);

  global.KeysUi = { promptPassword: promptPassword };
})(typeof window !== 'undefined' ? window : globalThis);
