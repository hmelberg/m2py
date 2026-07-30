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

  // -- «Nøkler…»-modalen (spec §3.4) --------------------------------------
  var POLICY_LABEL = { open: 'åpen', locked: 'låst', secret: 'hemmelig' };

  function maskedValue(entry) {
    if (entry.policy === 'secret') return '••••••••';
    var v = global.Keys.get(entry.name);
    if (v == null) return T('(låst)');
    return '••••' + String(v).slice(-4);
  }

  function renderList() {
    var tb = $('keysTbody');
    if (!tb) return;
    tb.innerHTML = '';
    global.Keys.registered().forEach(function (entry) {
      var tr = document.createElement('tr');
      var td1 = document.createElement('td');
      td1.textContent = entry.name;
      var td2 = document.createElement('td');
      td2.textContent = maskedValue(entry);
      var td3 = document.createElement('td');
      var sel = document.createElement('select');
      ['open', 'locked', 'secret'].forEach(function (p) {
        var o = document.createElement('option');
        o.value = p; o.textContent = T(POLICY_LABEL[p]); o.selected = p === entry.policy;
        sel.appendChild(o);
      });
      sel.addEventListener('change', function () {
        global.Keys.setPolicy(entry.name, sel.value)
          .then(refresh)
          .catch(function (e) { alert(e.message); refresh(); });
      });
      td3.appendChild(sel);
      var td4 = document.createElement('td');
      var del = document.createElement('button');
      del.type = 'button'; del.textContent = T('Slett');
      del.addEventListener('click', function () {
        if (confirm(T('Slette nøkkelen «{name}»?', { name: entry.name }))) {
          global.Keys.remove(entry.name);
          refresh();
        }
      });
      td4.appendChild(del);
      tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3); tr.appendChild(td4);
      tb.appendChild(tr);
    });
  }

  function refresh() {
    renderList();
    var st = global.Keys.status();
    var status = $('keysPwStatus');
    if (status) status.textContent = !st.hasPassword ? T('Ingen hovedpassord satt ennå')
      : st.unlocked ? T('Opplåst i denne økten') : T('Låst');
    var lockBtn = $('keysLockBtn');
    if (lockBtn) lockBtn.style.display = st.unlocked ? '' : 'none';
    var pwBtn = $('keysPwChangeBtn');
    if (pwBtn) pwBtn.style.display = st.hasPassword ? '' : 'none';
    var forgotBtn = $('keysForgotBtn');
    if (forgotBtn) forgotBtn.style.display = st.hasPassword ? '' : 'none';
    var defSel = $('keysDefaultPolicy');
    if (defSel) defSel.value = global.Keys.getDefaultPolicy();
  }

  function wire() {
    var addBtn = $('keysAddBtn');
    if (!addBtn || addBtn._wired) return;
    addBtn._wired = true;
    addBtn.addEventListener('click', function () {
      var name = $('keysAddName').value.trim();
      var value = $('keysAddValue').value;
      var policy = $('keysAddPolicy').value;
      global.Keys.set(name, value, policy)
        .then(function () { $('keysAddName').value = ''; $('keysAddValue').value = ''; refresh(); })
        .catch(function (e) { alert(e.message); });
    });
    $('keysClose').addEventListener('click', function () { $('keysBackdrop').classList.remove('open'); });
    $('keysLockBtn').addEventListener('click', function () { global.Keys.lockNow(); refresh(); });
    $('keysDefaultPolicy').addEventListener('change', function (e) { global.Keys.setDefaultPolicy(e.target.value); });
    $('keysPwChangeBtn').addEventListener('click', async function () {
      var oldPw = await promptPassword({ mode: 'unlock' });
      if (!oldPw) return;
      var newPw = await promptPassword({ mode: 'create' });
      if (!newPw) return;
      global.Keys.changePassword(oldPw, newPw)
        .then(function () { alert(T('Hovedpassordet er byttet')); refresh(); })
        .catch(function (e) { alert(e.message); });
    });
    $('keysForgotBtn').addEventListener('click', function () {
      var enc = global.Keys.registered().filter(function (e) { return e.policy !== 'open'; });
      var msg = T('Glemt passord kan ikke gjenopprettes. {n} krypterte nøkler SLETTES, og du må legge dem inn på nytt. Fortsette?', { n: enc.length });
      if (confirm(msg) && confirm(T('Er du helt sikker? Dette kan ikke angres.'))) {
        global.Keys.resetEncrypted();
        refresh();
      }
    });
    $('keysEncryptAllBtn').addEventListener('click', async function () {
      var open = global.Keys.registered().filter(function (e) { return e.policy === 'open'; });
      try {
        for (var i = 0; i < open.length; i++) await global.Keys.setPolicy(open[i].name, 'locked');
      } catch (e) { alert(e.message); }
      refresh();
    });
  }

  function openModal() {
    wire();
    refresh();
    $('keysBackdrop').classList.add('open');
  }

  if (global.Keys) global.Keys.attachPrompt(promptPassword);

  global.KeysUi = { promptPassword: promptPassword, open: openModal };
})(typeof window !== 'undefined' ? window : globalThis);
