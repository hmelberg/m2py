    // ── Del / Åpne fra URL / Koble til GitHub ────────────────────────────────
    (function initScriptSharing() {
      var T = window.t || function (s, p) { return p ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in p ? p[k] : m; }) : s; };
      const $ = (id) => document.getElementById(id);
      const dropdown = $('hamburgerDropdown');
      function closeAllSubmenus() {
        ['filSubmenu', 'githubSubmenu', 'examplesDropdown', 'langSubmenu'].forEach((id) => {
          const el = $(id); if (el) el.classList.remove('open');
        });
      }
      const closeMenu = () => {
        if (dropdown) dropdown.classList.remove('open');
        closeAllSubmenus();
      };

      function currentLang() {
        return (typeof activeEditorMode !== 'undefined') ? activeEditorMode : 'microdata';
      }
      // Sett editor-innhold + språk slik at modus-buffrene holdes konsistente.
      function setEditor(text, lang) {
        if (window.mdClearOutput) window.mdClearOutput();
        lang = (lang === 'python' || lang === 'r' || lang === 'duckdb') ? lang : 'microdata';
        if (typeof editorContent !== 'undefined') editorContent[lang] = text;
        if (typeof switchEditorMode === 'function' && typeof activeEditorMode !== 'undefined' && lang !== activeEditorMode) {
          switchEditorMode(lang); // laster editorContent[lang] inn i scriptInput
        } else {
          const si = $('scriptInput');
          if (si) si.value = text;
        }
        if (window.updateLineNumbers) window.updateLineNumbers();
      }
      function langFromPath(p) {
        const s = (p || '').toLowerCase().split('?')[0];
        if (s.endsWith('.py')) return 'python';
        if (s.endsWith('.r')) return 'r';
        if (s.endsWith('.sql')) return 'duckdb';
        return 'microdata';
      }

      // --- base64url + gzip via innebygd CompressionStream ---
      function b64urlEncode(bytes) {
        let bin = '';
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      }
      function b64urlDecode(s) {
        s = s.replace(/-/g, '+').replace(/_/g, '/');
        while (s.length % 4) s += '=';
        const bin = atob(s);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        return bytes;
      }
      async function gzip(str) {
        const cs = new CompressionStream('gzip');
        const w = cs.writable.getWriter();
        w.write(new TextEncoder().encode(str)); w.close();
        const buf = await new Response(cs.readable).arrayBuffer();
        return b64urlEncode(new Uint8Array(buf));
      }
      async function gunzip(b64) {
        const ds = new DecompressionStream('gzip');
        const w = ds.writable.getWriter();
        w.write(b64urlDecode(b64)); w.close();
        return await new Response(ds.readable).text();
      }

      // key(<literal>) i scriptet er en hemmelighet (samme regel som AI-veien,
      // se js/ai-chat.js scrubScript / js/data-directives.js scrubKeys) — masker
      // den før teksten forlater nettleseren via delelenke eller GitHub-lagring.
      // DataDirectives lastes før dette scriptet (index.html), men vi sjekker
      // robust for lastrekkefølge-avvik og feiler aldri selve delingen/lagringen.
      function scrubSecrets(text) {
        try {
          if (window.DataDirectives && typeof window.DataDirectives.scrubKeys === 'function') {
            const scrubbed = window.DataDirectives.scrubKeys(text);
            return { text: scrubbed, changed: scrubbed !== text };
          }
        } catch (_) { /* skrubber utilgjengelig/feilet — del uskrubbet under */ }
        return { text: text, changed: false };
      }

      function toast(msg) {
        let t = $('mdShareToast');
        if (!t) {
          t = document.createElement('div');
          t.id = 'mdShareToast';
          t.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--accent,#2563eb);color:#fff;padding:8px 16px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 2px 8px rgba(0,0,0,.2);transition:opacity .4s;';
          document.body.appendChild(t);
        }
        t.textContent = msg;
        t.style.opacity = '1';
        clearTimeout(t._timer);
        t._timer = setTimeout(() => { t.style.opacity = '0'; }, 1700);
      }

      // --- Verb 1: Del via fragment-lenke ---
      async function shareLink() {
        closeMenu();
        const si = $('scriptInput');
        const script = si ? si.value : '';
        if (!script.trim()) { alert(T('Editoren er tom — ingenting å dele.')); return; }
        try {
          const scrub = scrubSecrets(script);
          const payload = JSON.stringify({
            v: 1,
            name: ($('scriptName') && $('scriptName').value) || '',
            lang: currentLang(),
            script: scrub.text
          });
          const packed = await gzip(payload);
          const link = location.origin + location.pathname + '#s=' + packed;
          if (link.length > 8000) {
            alert(T('Scriptet er for stort for en delelenke ({n} tegn i URL). Bruk «Last ned kode» (fil) eller GitHub i stedet.', { n: link.length }));
            return;
          }
          await navigator.clipboard.writeText(link);
          toast(scrub.changed
            ? T('Delelenke kopiert til utklippstavlen — nøkler fjernet fra delt script (bruk key(ask))')
            : T('Delelenke kopiert til utklippstavlen'));
        } catch (e) {
          alert(T('Kunne ikke lage delelenke: {msg}', { msg: e.message || e }));
        }
      }

      async function fetchFirstOk(urls) {
        for (var i = 0; i < urls.length; i++) {
          try { const r = await fetch(urls[i]); if (r.ok) return await r.text(); } catch (_) {}
        }
        throw new Error('not found (tried main, master)');
      }

      async function loadNotebookScript(urls, primaryUrl) {
        const text = await fetchFirstOk(urls);
        setEditor(text, langFromPath(primaryUrl));
        setCurrent(null);
        const nameEl = $('scriptName');
        if (nameEl) {
          const fn = decodeURIComponent(primaryUrl.split('?')[0].split('/').pop() || '');
          if (fn) nameEl.value = fn.replace(/\.(txt|py|r|sql)$/i, '');
        }
      }

      async function openFromFragment() {
        // Legacy #s= inline share (unchanged), stripped after handling.
        const share = location.hash.match(/[#&]s=([^&]+)/);
        if (share) {
          try {
            const data = JSON.parse(await gunzip(share[1]));
            if (data && typeof data.script === 'string') {
              setEditor(data.script, data.lang);
              setCurrent(null);
              if (data.name && $('scriptName')) $('scriptName').value = data.name;
              toast(T('Delt script åpnet'));
            }
          } catch (e) { console.warn('Kunne ikke åpne delt script fra lenke:', e); }
          finally { history.replaceState(null, document.title, location.pathname + location.search); }
          return;
        }

        // New notebook fragments (dotted / raw). Kept in the URL (durable link).
        const cls = window.NotebookLinks && window.NotebookLinks.classifyHash(location.hash);
        if (!cls || cls.kind === 'share') return;
        const urls = cls.kind === 'raw' ? [cls.raw] : cls.urls;
        const primary = urls[0];
        try {
          await loadNotebookScript(urls, primary);
        } catch (e) {
          if ($('openUrlError')) $('openUrlError').textContent =
            T('Kunne ikke hente notebook-lenken: {msg}', { msg: e.message || e });
          console.warn('notebook fragment load:', e);
          window.mdNotebookAutorun = null;
          return;
        }
        window.mdNotebookAutorun = (cls.action === 'output')
          ? { url: primary, mode: langFromPath(primary) }
          : null;
        if (window.mdNotebookMaybeAutorun) window.mdNotebookMaybeAutorun();
      }

      // --- Verb 2: Åpne fra URL ---
      const LS_RECENT = 'm2py_recent_urls';
      function getRecent() {
        try { return JSON.parse(localStorage.getItem(LS_RECENT) || '[]'); } catch (_) { return []; }
      }
      function pushRecent(url) {
        let r = getRecent().filter((u) => u !== url);
        r.unshift(url);
        try { localStorage.setItem(LS_RECENT, JSON.stringify(r.slice(0, 10))); } catch (_) {}
      }
      function renderRecent() {
        const wrap = $('openUrlRecentWrap'), list = $('openUrlRecent');
        if (!wrap || !list) return;
        const r = getRecent();
        if (!r.length) { wrap.style.display = 'none'; return; }
        wrap.style.display = '';
        list.innerHTML = '';
        r.forEach((url) => {
          const b = document.createElement('button');
          b.type = 'button';
          b.className = 'ai-modal-btn';
          b.style.cssText = 'display:block;width:100%;text-align:left;margin:3px 0;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
          b.textContent = url;
          b.title = url;
          b.onclick = () => { $('openUrlInput').value = url; };
          list.appendChild(b);
        });
      }
      async function fetchUrl(url) {
        const err = $('openUrlError');
        if (err) err.textContent = '';
        const normalized = (url || '').trim();
        if (!normalized) return;
        const go = $('openUrlGo'); if (go) go.disabled = true;
        try {
          const resp = await fetch(normalized);
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          const text = await resp.text();
          setEditor(text, langFromPath(normalized));
          setCurrent(null); // ikke lenger knyttet til en GitHub-fil
          const nameEl = $('scriptName');
          if (nameEl) {
            const fn = decodeURIComponent(normalized.split('?')[0].split('/').pop() || '');
            if (fn) nameEl.value = fn.replace(/\.(txt|py|r)$/i, '');
          }
          pushRecent(normalized);
          pushRecentFile({ kind: 'url', url: normalized });
          $('openUrlBackdrop').style.display = 'none';
          toast(T('Script hentet fra URL'));
        } catch (e) {
          if (err) err.textContent = T('Kunne ikke hente URL-en. Bruk en direkte «raw»-lenke som tillater henting (CORS) — f.eks. GitHub raw eller gist. Feil: {msg}', { msg: e.message || e });
        } finally {
          if (go) go.disabled = false;
        }
      }
      function openUrlModal() {
        closeMenu();
        renderRecent();
        const err = $('openUrlError'); if (err) err.textContent = '';
        $('openUrlBackdrop').style.display = 'flex';
        setTimeout(() => { const i = $('openUrlInput'); if (i) i.focus(); }, 50);
      }

      // --- Verb 3: GitHub som filbasert lager ─────────────────────────────────
      // Profiler {label,pat,repo,branch} i m2py_github_profiles + aktiv-indeks.
      // Gjeldende fil ligger i m2py_github_current.
      const LS_PAT = 'm2py_github_pat', LS_REPO = 'm2py_github_repo', LS_BRANCH = 'm2py_github_branch';
      const LS_PROFILES = 'm2py_github_profiles', LS_ACTIVE = 'm2py_github_active', LS_CURRENT = 'm2py_github_current';
      // Filer som ikke gir mening i editoren skjules; alt annet (inkl. filer
      // uten endelse) vises, så en fil lagret som «test» dukker også opp.
      const BINARY_EXT = /\.(png|jpe?g|gif|bmp|svg|ico|webp|pdf|zip|gz|tgz|tar|7z|rar|xlsx?|docx?|pptx?|parquet|feather|sav|dta|rds|rdata|pkl|npy|npz|bin|exe|dll|so|dylib|mp[34]|wav|mov|avi|ttf|otf|woff2?)$/i;
      let lastTree = null; // hurtigbuffer av filstier fra siste tre-henting
      let ghSavedSnapshot = null; // editor-innhold som samsvarer med lagret GitHub-fil

      function ghHeaders(pat) {
        return { 'Authorization': 'Bearer ' + pat, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
      }
      function utf8ToB64(str) {
        const bytes = new TextEncoder().encode(str);
        let bin = '';
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        return btoa(bin);
      }
      function b64ToUtf8(b64) {
        const bin = atob((b64 || '').replace(/\s/g, ''));
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        return new TextDecoder().decode(bytes);
      }
      function ghContentsUrlFor(repo, path) {
        return 'https://api.github.com/repos/' + repo + '/contents/' +
          path.split('/').map(encodeURIComponent).join('/');
      }

      // Profiler
      function rawProfiles() {
        try { const a = JSON.parse(localStorage.getItem(LS_PROFILES) || 'null'); return Array.isArray(a) ? a : null; } catch (_) { return null; }
      }
      function saveProfiles(arr, active) {
        try {
          localStorage.setItem(LS_PROFILES, JSON.stringify(arr));
          if (active != null) localStorage.setItem(LS_ACTIVE, String(active));
        } catch (_) {}
      }
      function getProfiles() {
        let a = rawProfiles();
        if (a) return a;
        // Migrer fra gammelt enkelt-oppsett (pat/repo/branch) til én profil
        const oldPat = localStorage.getItem(LS_PAT), oldRepo = localStorage.getItem(LS_REPO);
        if (oldPat || oldRepo) {
          a = [{ pat: oldPat || '', repo: oldRepo || '', branch: localStorage.getItem(LS_BRANCH) || 'main' }];
          saveProfiles(a, 0);
          return a;
        }
        return [];
      }
      function getActiveIndex() {
        const a = getProfiles();
        let i = parseInt(localStorage.getItem(LS_ACTIVE) || '0', 10);
        if (isNaN(i) || i < 0 || i >= a.length) i = 0;
        return i;
      }
      // Aktiv profil som {pat,repo,branch}
      function ghSettings() {
        const p = getProfiles()[getActiveIndex()];
        return p ? { pat: p.pat || '', repo: p.repo || '', branch: p.branch || 'main' } : { pat: '', repo: '', branch: 'main' };
      }
      function ghConfigured() {
        const s = ghSettings();
        return !!s.pat && /^[^/\s]+\/[^/\s]+$/.test(s.repo);
      }
      // Gjeldende fil
      function getCurrent() {
        try { return JSON.parse(localStorage.getItem(LS_CURRENT) || 'null'); } catch (_) { return null; }
      }
      function setCurrent(c) {
        try { localStorage.setItem(LS_CURRENT, JSON.stringify(c)); } catch (_) {}
        if (!c) ghSavedSnapshot = null;
        updateCurrentIndicator();
      }
      // Outline-ikoner (Feather-stil) ved siden av filnavnet: floppy = shortcut
      // til «Lagre» (vises kun når man jobber med en GitHub-fil).
      const SVG_SAVE = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>';
      function ghIsDirty() {
        const si = $('scriptInput');
        return ghSavedSnapshot != null && si && si.value !== ghSavedSnapshot;
      }
      function markSaved() {
        const si = $('scriptInput');
        ghSavedSnapshot = si ? si.value : '';
        updateCurrentIndicator();
      }

      // Nylig brukte filer (GitHub + URL) for hurtig gjenåpning
      const LS_RECENT_FILES = 'm2py_recent_files';
      const SVG_CHEVRON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';
      function getRecentFiles() {
        try { const a = JSON.parse(localStorage.getItem(LS_RECENT_FILES) || '[]'); return Array.isArray(a) ? a : []; } catch (_) { return []; }
      }
      function recentKey(e) { return e.kind === 'github' ? 'gh:' + e.repo + '@' + e.branch + '/' + e.path : 'url:' + e.url; }
      function pushRecentFile(e) {
        let a = getRecentFiles().filter((x) => recentKey(x) !== recentKey(e));
        a.unshift(e);
        try { localStorage.setItem(LS_RECENT_FILES, JSON.stringify(a.slice(0, 5))); } catch (_) {}
        updateRecentChevron();
      }
      function updateRecentChevron() {
        const wrap = $('ghRecentWrap');
        if (wrap) wrap.style.display = getRecentFiles().length ? 'inline-flex' : 'none';
      }
      function getPatForRepo(repo) {
        const m = getProfiles().find((p) => p.repo === repo);
        if (m && m.pat) return m.pat;
        return ghSettings().pat || '';
      }
      function renderRecentMenu() {
        const menu = $('ghRecentMenu'); if (!menu) return;
        const a = getRecentFiles();
        menu.innerHTML = '<div class="examples-dropdown-title">' + T('Nylige filer') + '</div>';
        if (!a.length) {
          menu.innerHTML += '<div style="padding:6px 14px;color:var(--text-muted);font-size:13px;">Ingen nylige.</div>';
        } else {
          a.forEach((e) => {
            const b = document.createElement('button'); b.type = 'button';
            const base = e.kind === 'github'
              ? (e.path.split('/').pop() || e.path)
              : decodeURIComponent((e.url || '').split('?')[0].split('/').pop() || e.url);
            b.textContent = base;
            b.title = e.kind === 'github' ? ('GitHub: ' + e.repo + '/' + e.path) : e.url;
            b.onclick = () => { menu.classList.remove('open'); reopenRecent(e); };
            menu.appendChild(b);
          });
        }
        const hr = document.createElement('hr');
        hr.style.cssText = 'margin:4px 0;border-color:#334155;';
        menu.appendChild(hr);
        const more = document.createElement('button'); more.type = 'button';
        more.textContent = T('Flere filer (GitHub)');
        more.title = T('Bla gjennom alle filene i GitHub-repoet');
        more.onclick = () => { menu.classList.remove('open'); openPicker(); };
        menu.appendChild(more);
      }
      async function reopenRecent(e) {
        if (e.kind === 'url') { await fetchUrl(e.url); return; }
        const pat = getPatForRepo(e.repo);
        if (!pat) { openSettings(T('Sett opp GitHub-tilgang for {repo} først.', { repo: e.repo })); return; }
        try {
          const resp = await fetch(ghContentsUrlFor(e.repo, e.path) + '?ref=' + encodeURIComponent(e.branch), { headers: ghHeaders(pat) });
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          const data = await resp.json();
          setEditor(b64ToUtf8(data.content), langFromPath(e.path));
          const nameEl = $('scriptName');
          if (nameEl) nameEl.value = (e.path.split('/').pop() || '').replace(/\.(txt|py|r)$/i, '');
          setCurrent({ repo: e.repo, branch: e.branch, path: e.path });
          markSaved();
          toast(T('Hentet fra GitHub: {path}', { path: e.path }));
        } catch (err) { alert(T('Kunne ikke åpne: {msg}', { msg: err.message || err })); }
      }
      function ghIconHost() {
        let host = $('ghIndicatorHost');
        if (host) return host;
        const name = $('scriptName');
        if (!name || !name.parentNode) return null;
        if (!$('ghIconStyle')) {
          const st = document.createElement('style');
          st.id = 'ghIconStyle';
          // Standardfarge som de andre topplinje-ikonene; amber når ulagret.
          st.textContent =
            '#ghSaveIcon{color:var(--text-muted)}' +
            '#ghSaveIcon:hover{color:var(--accent)}' +
            '#ghSaveIcon.dirty{color:#d97706}' +
            '#ghSaveIcon.dirty:hover{color:#b45309}';
          document.head.appendChild(st);
        }
        host = document.createElement('span');
        host.id = 'ghIndicatorHost';
        host.style.cssText = 'display:inline-flex;align-items:center;vertical-align:middle;';
        const save = document.createElement('span');
        save.id = 'ghSaveIcon';
        save.style.cssText = 'display:none;align-items:center;margin-left:4px;cursor:pointer;';
        save.innerHTML = SVG_SAVE;
        save.addEventListener('click', function () { doSave(); });
        // Chevron: nylig brukte filer
        const recentWrap = document.createElement('span');
        recentWrap.id = 'ghRecentWrap';
        recentWrap.style.cssText = 'position:relative;display:none;align-items:center;margin-left:4px;';
        const recentBtn = document.createElement('span');
        recentBtn.id = 'ghRecentBtn';
        recentBtn.title = T('Nylige filer');
        recentBtn.style.cssText = 'display:inline-flex;align-items:center;color:var(--text-muted);cursor:pointer;';
        recentBtn.innerHTML = SVG_CHEVRON;
        const recentMenu = document.createElement('div');
        recentMenu.id = 'ghRecentMenu';
        recentMenu.className = 'examples-dropdown';
        recentBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          const willOpen = !recentMenu.classList.contains('open');
          recentMenu.classList.remove('open');
          if (willOpen) { renderRecentMenu(); recentMenu.classList.add('open'); }
        });
        recentMenu.addEventListener('click', function (e) { e.stopPropagation(); });
        document.addEventListener('click', function () { recentMenu.classList.remove('open'); });
        recentWrap.appendChild(recentBtn);
        recentWrap.appendChild(recentMenu);
        // Rekkefølge: nylige (▾) først, så lagre (floppy) — nærmest filnavnet til høyre.
        host.appendChild(recentWrap);
        host.appendChild(save);
        name.parentNode.insertBefore(host, name.nextSibling);
        return host;
      }
      function updateCurrentIndicator() {
        if (!ghIconHost()) return;
        updateRecentChevron();
        const cur = getCurrent();
        const save = $('ghSaveIcon');
        if (cur && cur.path && langFromPath(cur.path) === currentLang()) {
          const dirty = ghIsDirty();
          if (save) {
            save.style.display = 'inline-flex';
            save.classList.toggle('dirty', dirty);
            const loc = cur.repo + '/' + cur.path + (cur.branch && cur.branch !== 'main' ? '@' + cur.branch : '');
            save.title = 'GitHub: ' + loc + (dirty ? T(' — ulagrede endringer, klikk for å lagre') : T(' — lagret, klikk for å lagre igjen'));
          }
        } else {
          if (save) save.style.display = 'none';
        }
      }

      // Innstillinger-dialog
      function renderProfileSelect() {
        const sel = $('ghProfileSelect'); if (!sel) return;
        const a = getProfiles(), active = getActiveIndex();
        sel.innerHTML = '';
        if (!a.length) {
          const o = document.createElement('option'); o.value = '-1'; o.textContent = T('(ingen profil ennå)'); sel.appendChild(o);
        } else {
          a.forEach((p, idx) => {
            const o = document.createElement('option');
            o.value = String(idx);
            o.textContent = (p.repo || '(ny profil)') + (p.branch && p.branch !== 'main' ? '@' + p.branch : '');
            sel.appendChild(o);
          });
          sel.value = String(active);
        }
      }
      function loadProfileIntoFields(i) {
        const p = getProfiles()[i] || { pat: '', repo: '', branch: 'main' };
        $('ghPat').value = p.pat || '';
        $('ghRepo').value = p.repo || '';
        $('ghBranch').value = p.branch || 'main';
        // Tilbakestill token-feltet til maskert ved bytte
        $('ghPat').type = 'password';
        const tog = $('ghPatToggle'); if (tog) tog.textContent = T('Vis');
      }
      function openSettings(msg) {
        closeMenu();
        renderProfileSelect();
        loadProfileIntoFields(getActiveIndex());
        $('ghError').textContent = msg || ''; $('ghStatus').textContent = '';
        $('githubBackdrop').style.display = 'flex';
      }
      function settingsRead() {
        return {
          pat: $('ghPat').value.trim(),
          repo: $('ghRepo').value.trim(),
          branch: $('ghBranch').value.trim() || 'main'
        };
      }
      function settingsValidate(f) {
        const err = $('ghError'); err.textContent = '';
        if (!f.pat) { err.textContent = T('Mangler token.'); return false; }
        if (!/^[^/\s]+\/[^/\s]+$/.test(f.repo)) { err.textContent = T('Repo må være på formen eier/navn.'); return false; }
        return true;
      }
      function settingsSave() {
        const f = settingsRead();
        if (!settingsValidate(f)) return;
        let a = getProfiles(), i = getActiveIndex();
        if (!a.length) { a = [f]; i = 0; } else { a[i] = f; }
        saveProfiles(a, i);
        lastTree = null; // repo/branch kan ha endret seg
        $('githubBackdrop').style.display = 'none';
        toast(T('GitHub-innstillinger lagret'));
        updateCurrentIndicator();
      }
      function profileNew() {
        const a = getProfiles();
        a.push({ pat: '', repo: '', branch: 'main' });
        const i = a.length - 1;
        saveProfiles(a, i);
        renderProfileSelect();
        loadProfileIntoFields(i);
        $('ghError').textContent = ''; $('ghStatus').textContent = '';
        const repo = $('ghRepo'); if (repo) repo.focus();
      }
      function profileDelete() {
        const a = getProfiles();
        if (!a.length) return;
        const i = getActiveIndex();
        const name = a[i].repo || (T('Profil') + ' ' + (i + 1));
        if (!confirm(T('Slette profilen «{name}»?', { name: name }))) return;
        a.splice(i, 1);
        const ni = Math.max(0, Math.min(i, a.length - 1));
        saveProfiles(a, ni);
        renderProfileSelect();
        loadProfileIntoFields(a.length ? ni : 0);
        $('ghStatus').textContent = ''; $('ghError').textContent = '';
        updateCurrentIndicator();
      }
      function patToggle() {
        const inp = $('ghPat'), btn = $('ghPatToggle');
        if (!inp) return;
        if (inp.type === 'password') { inp.type = 'text'; if (btn) btn.textContent = T('Skjul'); }
        else { inp.type = 'password'; if (btn) btn.textContent = T('Vis'); }
      }
      async function patCopy() {
        const inp = $('ghPat'); if (!inp || !inp.value) return;
        try {
          await navigator.clipboard.writeText(inp.value);
          const btn = $('ghPatCopy');
          if (btn) { const o = btn.textContent; btn.textContent = T('Kopiert!'); setTimeout(() => { btn.textContent = o; }, 1500); }
        } catch (_) {}
      }
      async function settingsTest() {
        const f = settingsRead();
        if (!settingsValidate(f)) return;
        const status = $('ghStatus'), err = $('ghError');
        err.textContent = ''; status.textContent = T('Tester…');
        try {
          const resp = await fetch('https://api.github.com/repos/' + f.repo, { headers: ghHeaders(f.pat) });
          if (!resp.ok) throw new Error('HTTP ' + resp.status +
            (resp.status === 404 ? T(' (repo ikke funnet / ingen tilgang)') : resp.status === 401 ? T(' (ugyldig token)') : ''));
          const data = await resp.json();
          status.textContent = T('✓ Tilkoblet: {repo}', { repo: data.full_name || f.repo }) + (data.private ? T(' (privat)') : T(' (offentlig)'));
        } catch (e) {
          status.textContent = ''; err.textContent = T('Tilkobling feilet: {msg}', { msg: e.message || e });
        }
      }

      // Filvelger
      async function fetchTree(s) {
        const url = 'https://api.github.com/repos/' + s.repo + '/git/trees/' + encodeURIComponent(s.branch) + '?recursive=1';
        const resp = await fetch(url, { headers: ghHeaders(s.pat) });
        if (!resp.ok) throw new Error('HTTP ' + resp.status + (resp.status === 404 ? T(' (repo/branch ikke funnet)') : ''));
        const data = await resp.json();
        lastTree = (data.tree || []).filter((n) => n.type === 'blob').map((n) => n.path);
        return lastTree;
      }
      function renderPicker(filter) {
        const list = $('ghPickerList'); if (!list) return;
        const all = lastTree || [];
        const q = (filter || '').toLowerCase();
        const items = all.filter((p) => !BINARY_EXT.test(p) && (!q || p.toLowerCase().indexOf(q) !== -1));
        list.innerHTML = '';
        if (!items.length) {
          const msg = all.length
            ? (q ? T('Ingen treff på filteret.') : T('Ingen filer å vise.'))
            : 'Repoet/branchen er tom — eller branch-navnet stemmer ikke (sjekk Innstillinger).';
          list.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:13px;">' + msg + '</div>';
          return;
        }
        items.slice(0, 500).forEach((p) => {
          const b = document.createElement('button');
          b.type = 'button'; b.className = 'ai-modal-btn';
          b.style.cssText = 'display:block;width:100%;text-align:left;margin:2px 0;font-size:13px;';
          b.textContent = p; b.title = p;
          b.onclick = () => pickFile(p);
          list.appendChild(b);
        });
      }
      async function openPicker() {
        closeMenu();
        if (!ghConfigured()) { openSettings(T('Sett opp GitHub-tilkobling først.')); return; }
        const err = $('ghPickerError'); if (err) err.textContent = '';
        const list = $('ghPickerList');
        if (list) list.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:13px;">' + T('Henter filliste…') + '</div>';
        const filter = $('ghPickerFilter'); if (filter) filter.value = '';
        $('ghPickerBackdrop').style.display = 'flex';
        try {
          await fetchTree(ghSettings());
          renderPicker('');
        } catch (e) {
          if (err) err.textContent = T('Kunne ikke hente filliste: {msg}', { msg: e.message || e });
          if (list) list.innerHTML = '';
        }
      }
      async function pickFile(path) {
        const s = ghSettings();
        const err = $('ghPickerError'); if (err) err.textContent = '';
        try {
          const resp = await fetch(ghContentsUrlFor(s.repo, path) + '?ref=' + encodeURIComponent(s.branch), { headers: ghHeaders(s.pat) });
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          const data = await resp.json();
          setEditor(b64ToUtf8(data.content), langFromPath(path));
          const nameEl = $('scriptName');
          if (nameEl) nameEl.value = (path.split('/').pop() || '').replace(/\.(txt|py|r)$/i, '');
          setCurrent({ repo: s.repo, branch: s.branch, path: path });
          markSaved();
          pushRecentFile({ kind: 'github', repo: s.repo, branch: s.branch, path: path });
          $('ghPickerBackdrop').style.display = 'none';
          toast(T('Hentet fra GitHub: {path}', { path: path }));
        } catch (e) {
          if (err) err.textContent = T('Kunne ikke hente filen: {msg}', { msg: e.message || e });
        }
      }

      // Skriving
      // Skrubber alltid key(<literal>)-hemmeligheter av editorteksten før den
      // forlater nettleseren (samme regel som shareLink) og returnerer om noe
      // ble fjernet, slik at kallerne kan varsle brukeren om det.
      async function putFile(s, path, content) {
        const scrub = scrubSecrets(content);
        content = scrub.text;
        // Hent eksisterende sha (kreves for å overskrive en fil som finnes)
        let sha = null;
        const head = await fetch(ghContentsUrlFor(s.repo, path) + '?ref=' + encodeURIComponent(s.branch), { headers: ghHeaders(s.pat) });
        if (head.ok) sha = (await head.json()).sha;
        const body = { message: 'Update ' + path + ' via Microdata Script Runner', content: utf8ToB64(content), branch: s.branch };
        if (sha) body.sha = sha;
        const resp = await fetch(ghContentsUrlFor(s.repo, path), { method: 'PUT', headers: ghHeaders(s.pat), body: JSON.stringify(body) });
        if (!resp.ok) {
          let msg = 'HTTP ' + resp.status;
          try { const ej = await resp.json(); if (ej.message) msg += ' – ' + ej.message; } catch (_) {}
          if (resp.status === 409) msg += T(' (filen er endret på GitHub — bruk «Oppdater» og prøv igjen)');
          throw new Error(msg);
        }
        return scrub.changed;
      }
      async function doSave() {
        closeMenu();
        if (!ghConfigured()) { openSettings(T('Sett opp GitHub-tilkobling først.')); return; }
        const s = ghSettings();
        const cur = getCurrent();
        // Also require the branch to match: a file opened from `dev` must not be
        // silently PUT to the profile's current branch (e.g. `main`). On a repo
        // OR branch mismatch, route to "Save As" so the destination is explicit.
        if (!cur || !cur.path || cur.repo !== s.repo || cur.branch !== s.branch) { openSaveAs(); return; }
        // Don't overwrite a file whose extension belongs to a different editor
        // mode (e.g. saving a Python buffer over a microdata .txt) — route to Save As.
        if (langFromPath(cur.path) !== currentLang()) { openSaveAs(); return; }
        const si = $('scriptInput');
        try {
          const changed = await putFile(s, cur.path, si ? si.value : '');
          setCurrent({ repo: s.repo, branch: s.branch, path: cur.path });
          markSaved();
          toast(changed
            ? T('Lagret til GitHub: {path} — nøkler fjernet fra delt script (bruk key(ask))', { path: cur.path })
            : T('Lagret til GitHub: {path}', { path: cur.path }));
        } catch (e) { alert(T('Kunne ikke lagre: {msg}', { msg: e.message || e })); }
      }
      function openSaveAs() {
        if (!ghConfigured()) { openSettings(T('Sett opp GitHub-tilkobling først.')); return; }
        const err = $('ghSaveAsError'); if (err) err.textContent = '';
        const s = ghSettings();
        const cur = getCurrent();
        const input = $('ghSaveAsPath');
        if (input) {
          if (cur && cur.path && cur.repo === s.repo && langFromPath(cur.path) === currentLang()) {
            input.value = cur.path;
          } else {
            const nm = (($('scriptName') && $('scriptName').value) || 'script').trim();
            input.value = nm.replace(/\s+/g, '_'); // endelse legges til automatisk ved lagring
          }
        }
        const dl = $('ghFolderList');
        if (dl) {
          dl.innerHTML = '';
          const folders = new Set();
          (lastTree || []).forEach((p) => { const i = p.lastIndexOf('/'); if (i > 0) folders.add(p.slice(0, i + 1)); });
          Array.from(folders).slice(0, 50).forEach((f) => { const o = document.createElement('option'); o.value = f; dl.appendChild(o); });
        }
        $('ghSaveAsBackdrop').style.display = 'flex';
        setTimeout(() => { const i = $('ghSaveAsPath'); if (i) i.focus(); }, 50);
      }
      function ensureExt(path) {
        const last = path.split('/').pop();
        if (last.indexOf('.') !== -1) return path; // har allerede endelse
        const ext = currentLang() === 'python' ? '.py' : currentLang() === 'r' ? '.r' : '.txt';
        return path + ext;
      }
      async function saveAsConfirm() {
        const err = $('ghSaveAsError'); if (err) err.textContent = '';
        let path = $('ghSaveAsPath').value.trim();
        if (!path) { if (err) err.textContent = T('Skriv en filsti.'); return; }
        path = ensureExt(path);
        const s = ghSettings();
        const si = $('scriptInput');
        try {
          const changed = await putFile(s, path, si ? si.value : '');
          setCurrent({ repo: s.repo, branch: s.branch, path: path });
          markSaved();
          pushRecentFile({ kind: 'github', repo: s.repo, branch: s.branch, path: path });
          const nameEl = $('scriptName');
          if (nameEl) nameEl.value = (path.split('/').pop() || '').replace(/\.(txt|py|r)$/i, '');
          $('ghSaveAsBackdrop').style.display = 'none';
          toast(changed
            ? T('Lagret til GitHub: {path} — nøkler fjernet fra delt script (bruk key(ask))', { path: path })
            : T('Lagret til GitHub: {path}', { path: path }));
        } catch (e) { if (err) err.textContent = T('Kunne ikke lagre: {msg}', { msg: e.message || e }); }
      }
      async function doRefresh() {
        closeMenu();
        const cur = getCurrent();
        if (!cur || !cur.path) { alert(T('Ingen gjeldende GitHub-fil å oppdatere. Bruk «Åpne fil…» først.')); return; }
        if (!confirm(T('Hente «{path}» på nytt fra GitHub? Ulagrede lokale endringer går tapt.', { path: cur.path }))) return;
        const s = ghSettings();
        try {
          const resp = await fetch(ghContentsUrlFor(cur.repo, cur.path) + '?ref=' + encodeURIComponent(cur.branch), { headers: ghHeaders(s.pat) });
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          const data = await resp.json();
          setEditor(b64ToUtf8(data.content), langFromPath(cur.path));
          markSaved();
          toast(T('Hentet på nytt fra GitHub: {path}', { path: cur.path }));
        } catch (e) { alert(T('Kunne ikke oppdatere: {msg}', { msg: e.message || e })); }
      }

      // --- Kobling av knapper ---
      // Modalene ligger etter dette scriptet i dokumentet, så vi venter på at
      // DOM-en er ferdig parset før vi kobler på lyttere.
      function wire() {
        function on(id, fn) { const el = $(id); if (el) el.addEventListener('click', fn); }

        // Små outline-ikoner på menyvalgene (samme stil overalt).
        (function addMenuIcons() {
          const wrapSvg = (inner) => '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:8px;flex-shrink:0">' + inner + '</svg>';
          const FOLDER = '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>';
          const SETTINGS = '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>';
          const SAVE = '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>';
          const map = {
            menuFilBtn: FOLDER,
            menuExamplesBtn: '<path d="M2 4h7a3 3 0 0 1 3 3v13a2.5 2.5 0 0 0-2.5-2.5H2z"/><path d="M22 4h-7a3 3 0 0 0-3 3v13a2.5 2.5 0 0 1 2.5-2.5H22z"/>',
            menuUploadData: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
            menuGithubBtn: '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
            menuForklar: '<polygon points="5 3 19 12 5 21 5 3"/>',
            menuSettings: SETTINGS,
            menuNew: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>',
            menuOpenUrl: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
            menuLoad: FOLDER,
            menuShareLink: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>',
            menuSave: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
            menuWebExamples: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
            ghMenuSettings: SETTINGS,
            ghMenuOpen: FOLDER,
            ghMenuSave: SAVE,
            ghMenuSaveAs: SAVE,
            ghMenuRefresh: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'
          };
          Object.keys(map).forEach((id) => {
            const btn = $(id);
            if (!btn || btn.querySelector('svg')) return;
            btn.insertAdjacentHTML('afterbegin', wrapSvg(map[id]));
            btn.style.display = 'flex';
            btn.style.alignItems = 'center';
          });
        })();

        on('menuShareLink', shareLink);
        on('menuOpenUrl', openUrlModal);

        on('openUrlCancel', () => { $('openUrlBackdrop').style.display = 'none'; });
        on('openUrlGo', () => fetchUrl($('openUrlInput').value));
        const ui = $('openUrlInput');
        if (ui) ui.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); fetchUrl(ui.value); } });
        const oub = $('openUrlBackdrop');
        if (oub) oub.addEventListener('click', (e) => { if (e.target === oub) oub.style.display = 'none'; });

        // Undermeny-toggler (Fil + GitHub) — samme klikk-mønster som «Eksempler».
        function wireSubmenu(btnId, subId) {
          const btn = $(btnId), sub = $(subId);
          if (!btn || !sub) return;
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const willOpen = !sub.classList.contains('open');
            closeAllSubmenus();
            if (willOpen) sub.classList.add('open');
          });
          sub.addEventListener('click', (e) => e.stopPropagation());
        }
        wireSubmenu('menuFilBtn', 'filSubmenu');
        wireSubmenu('menuGithubBtn', 'githubSubmenu');
        document.addEventListener('click', closeAllSubmenus);
        // Start alltid med kollapsede undermenyer når hamburgeren åpnes.
        const hbBtn = $('hamburgerBtn');
        if (hbBtn) hbBtn.addEventListener('click', closeAllSubmenus);
        on('ghMenuSettings', () => openSettings());
        on('ghMenuOpen', openPicker);
        on('ghMenuSave', doSave);
        on('ghMenuSaveAs', () => { closeMenu(); openSaveAs(); });
        on('ghMenuRefresh', doRefresh);

        // Innstillinger-dialog
        on('ghSettingsClose', () => { $('githubBackdrop').style.display = 'none'; });
        on('ghSettingsTest', settingsTest);
        on('ghSettingsSave', settingsSave);
        on('ghProfileNew', profileNew);
        on('ghProfileDelete', profileDelete);
        on('ghPatToggle', patToggle);
        on('ghPatCopy', patCopy);
        const psel = $('ghProfileSelect');
        if (psel) psel.addEventListener('change', function () {
          const i = parseInt(this.value, 10);
          if (i >= 0) {
            try { localStorage.setItem(LS_ACTIVE, String(i)); } catch (_) {}
            loadProfileIntoFields(i);
            $('ghError').textContent = ''; $('ghStatus').textContent = '';
            updateCurrentIndicator();
          }
        });
        const ghb = $('githubBackdrop');
        if (ghb) ghb.addEventListener('click', (e) => { if (e.target === ghb) ghb.style.display = 'none'; });

        // Filvelger
        on('ghPickerCancel', () => { $('ghPickerBackdrop').style.display = 'none'; });
        on('ghPickerRefresh', openPicker);
        const pf = $('ghPickerFilter');
        if (pf) pf.addEventListener('input', () => renderPicker(pf.value));
        const pb = $('ghPickerBackdrop');
        if (pb) pb.addEventListener('click', (e) => { if (e.target === pb) pb.style.display = 'none'; });

        // Lagre som
        on('ghSaveAsCancel', () => { $('ghSaveAsBackdrop').style.display = 'none'; });
        on('ghSaveAsConfirm', saveAsConfirm);
        const sp = $('ghSaveAsPath');
        if (sp) sp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); saveAsConfirm(); } });
        const sb = $('ghSaveAsBackdrop');
        if (sb) sb.addEventListener('click', (e) => { if (e.target === sb) sb.style.display = 'none'; });

        // Live ulagret-indikator: oppdater lagre-ikonet når editoren endres.
        const si = $('scriptInput');
        if (si) si.addEventListener('input', updateCurrentIndicator);

        updateCurrentIndicator();
      }

      // Lar eksterne lastere (Nytt script, lokal fil, eksempler) koble fra
      // gjeldende GitHub-fil, så «Lagre» ikke overskriver feil fil.
      window.mdGithubClearCurrent = function () { setCurrent(null); };
      window.mdGithubRefreshIndicator = function () { updateCurrentIndicator(); };

      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
      else wire();

      // Åpne delt script hvis URL inneholder #s= (etter at resten har lastet)
      if (document.readyState === 'complete') openFromFragment();
      else window.addEventListener('load', openFromFragment);
    })();
