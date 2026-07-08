// Sesjonskontekst: avleder {nivå, sted} fra scriptets direktiver + kjent
// kildemetadata, til bunnlinje-badgene [Språk][Nivå][Sted] (spec
// docs/superpowers/specs/2026-07-08-mode-level-place-design.md — plan i
// ~/.claude/plans). KUN visning/pre-flight: serveren håndhever alltid selv.
//
// Nivåer (klient): open < unknown < restricted < he — mest-restriktive-vinner,
// samme prinsipp som resolve_policy i m2py_protection.py. `unknown` rangerer
// over `open` med vilje: aldri grønt badge for en kilde vi ikke kan gå god for.
//
// Ren parsing — ingen DOM her. Nettverk kun i metaFor() (memoisert).
// Testes med node:test + vm (tests/js/session-context.test.js).
(function (global) {
  'use strict';

  var LEVEL_ORDER = { open: 0, unknown: 1, restricted: 2, he: 3 };

  // require-direktivets to former — de SAMME regexene som index.html's
  // deriveSafeStatExecutor bruker (delt her så de ikke driver fra hverandre).
  // Dialekt-moduser (python/r/duckdb) skriver require som kommentar; i
  // safestat/microdata er require en ekte DSL-setning (og en kommentert
  // require er nettopp utkommentert).
  var REQUIRE_SRC = {
    comment: '^[ \\t]*(?:#|--|\\/\\/)[ \\t]*require\\s+(\\S+)\\s+as\\s+(\\w+)(?:\\s*,\\s*exec\\(\\s*(local|remote)\\s*\\))?',
    bare: '^\\s*require\\s+(\\S+)\\s+as\\s+(\\w+)(?:\\s*,\\s*exec\\(\\s*(local|remote)\\s*\\))?'
  };
  function requireRe(commentDirectives) {
    return new RegExp(REQUIRE_SRC[commentDirectives ? 'comment' : 'bare'], 'gim');
  }

  // Per-linje-matchere (linjenummer trengs for badge-tooltip og exec-toggle).
  var REQUIRE_LINE = { comment: new RegExp(REQUIRE_SRC.comment, 'i'), bare: new RegExp(REQUIRE_SRC.bare, 'i') };
  // Speiler CONNECT_RE/LOAD_RE i js/data-directives.js (linjeanker der er ^...$ gim).
  var CONNECT_LINE = /^[ \t]*(?:#|--|\/\/)[ \t]*connect[ \t]+(\S+)(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/i;
  var LOAD_LINE = /^[ \t]*(?:#|--|\/\/)[ \t]*load[ \t]+(\S+)[ \t]+as[ \t]+([A-Za-z_]\w*)((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/i;
  var PROFILE_LINE = /^\s*(?:#|\/\/|--)\s*options\.profile\s*=\s*("[^"]*"|'[^']*'|\S+)\s*$/i;
  var EXEC_OPT = /\s*,\s*exec\(\s*(?:local|remote)\s*\)/i;

  function isUrlish(target) {
    return /^https?:\/\//i.test(target) || String(target).indexOf('/api/hent?') === 0;
  }
  function parseOptions(tail) {
    if (global.DataDirectives && global.DataDirectives.parseOptions)
      return global.DataDirectives.parseOptions(tail);
    var opts = {}, re = /(\w+)\(([^)]*)\)/g, m;
    while ((m = re.exec(tail || '')) !== null) {
      if (m[1].toLowerCase() === 'exec') opts.exec = m[2].trim().toLowerCase();
    }
    return opts;
  }
  function bareRequireMode(mode) { return mode === 'safestat' || mode === 'microdata'; }

  // Nivå for én navngitt kilde ut fra metadata (normalisert form, se metaFor):
  //   {public, default_exec, level, kind, local_profile, remote_only,
  //    unknown, pending} — alle felter valgfrie.
  // -> { level, why } der why er en kode index.html oversetter til tekst.
  function levelForMeta(m) {
    if (!m || m.pending) return { level: 'unknown', why: 'pending' };
    if (m.unknown) return { level: 'unknown', why: 'unknown-source' };
    if (m.kind === 'safepy-he-v1' || m.he) return { level: 'he', why: 'he-envelope' };
    if (m.local_profile === 'strict' || m.strict) return { level: 'restricted', why: 'grant-strict' };
    if (m.level === 'protected' || m.level === 'sensitive') return { level: 'restricted', why: 'level-' + m.level };
    if (m.public === false) return { level: 'restricted', why: 'non-public' };
    return { level: 'open', why: 'public' };
  }

  // Hovedinngang. script: editorinnhold. mode: activeEditorMode.
  // sourceMeta: { [navnEllerAlias]: meta } — typisk cachedMeta().
  // Synkron og billig (to regex-pass) — trygg å kalle på input-debounce.
  function derive(script, mode, sourceMeta) {
    script = String(script || '');
    sourceMeta = sourceMeta || {};
    var bare = bareRequireMode(mode);
    var lines = script.split(/\r?\n/);
    var level = 'open';
    var levelReasons = [];
    var directiveLines = [];
    var sourceIds = [];
    var m, i;

    function metaOf(name, alias) {
      return sourceMeta[name] || (alias && sourceMeta[alias]) || null;
    }
    function bump(name, alias, lv) {
      if (LEVEL_ORDER[lv.level] > LEVEL_ORDER[level]) level = lv.level;
      if (lv.level !== 'open') levelReasons.push({ name: name, alias: alias || null, why: lv.why, level: lv.level });
    }

    for (i = 0; i < lines.length; i++) {
      var ln = lines[i];
      if ((m = PROFILE_LINE.exec(ln)) !== null) {
        var pv = m[1].replace(/^["']|["']$/g, '').toLowerCase();
        if (pv === 'strict') bump('options.profile', null, { level: 'restricted', why: 'profile-strict' });
        continue;
      }
      var entry = null;
      if ((m = REQUIRE_LINE[bare ? 'bare' : 'comment'].exec(ln)) !== null) {
        entry = { lineNo: i + 1, kind: 'require', target: m[1], alias: m[2], exec: m[3] ? m[3].toLowerCase() : null };
      } else if (!bare && (m = LOAD_LINE.exec(ln)) !== null) {
        entry = { lineNo: i + 1, kind: 'load', target: m[1], alias: m[2], exec: parseOptions(m[3]).exec || null };
      } else if (!bare && (m = CONNECT_LINE.exec(ln)) !== null) {
        entry = { lineNo: i + 1, kind: 'connect', target: m[1], alias: m[2] || m[1], exec: parseOptions(m[3]).exec || null };
      }
      if (!entry) continue;

      var url = isUrlish(entry.target);
      // load via connect-alias («load pasj/tab as df»): nivået bæres av
      // connect-linjen; selve load-linjen er nøytral med mindre målet er URL.
      var headName = url ? null : String(entry.target).split('/')[0];
      var meta = url ? metaOf(entry.target, entry.alias) : metaOf(headName, entry.alias);

      var entryLv = meta ? levelForMeta(meta) : null;
      if (!url && entryLv && entryLv.level === 'he') {
        // Homomorf kryptert kilde: bare serveren kan aggregere den — alltid
        // tvunget remote, uansett hva grant/default ellers sier.
        if (entry.kind !== 'load') sourceIds.push(headName);
        bump(headName, entry.alias, entryLv);
        entry.place = 'remote'; entry.choosable = false; entry.placeWhy = 'forced-remote';
        directiveLines.push(entry);
        continue;
      }
      if (url) {
        // URL-kilder er åpne inntil noteFetchedLoad evt. avslører en konvolutt.
        bump(entry.target, entry.alias, entryLv || { level: 'open', why: 'url' });
        entry.place = 'local'; entry.choosable = false; entry.placeWhy = 'url-local';
      } else if (entry.kind === 'require') {
        sourceIds.push(headName);
        bump(headName, entry.alias, levelForMeta(meta));
        if (!bare) {
          // Dagens adferd (maybeRunRemote): navngitt require i dialekt-modus
          // ruter alltid til serveren.
          entry.place = 'remote'; entry.choosable = false; entry.placeWhy = 'named-dialect';
        } else if (!meta || meta.pending || meta.unknown) {
          entry.place = 'remote'; entry.choosable = false; entry.placeWhy = 'unknown-source';
        } else if (meta.public === false || meta.default_exec === 'strict_remote' || meta.remote_only) {
          entry.place = 'remote'; entry.choosable = false; entry.placeWhy = 'forced-remote';
        } else {
          entry.defaultPlace = meta.default_exec === 'remote' ? 'remote' : 'local';
          entry.place = entry.exec || entry.defaultPlace;
          // microdata-modus har ingen exec()-støtte i kjørebanen.
          entry.choosable = mode !== 'microdata';
          entry.placeWhy = entry.exec ? 'exec-directive' : 'default';
        }
      } else {
        // connect/load mot navngitt kilde (web-register eller Anvil-grant).
        if (entry.kind === 'connect') sourceIds.push(headName);
        bump(headName, entry.alias, levelForMeta(meta));
        if (meta && (meta.remote_only || meta.public === false)) {
          entry.place = 'remote'; entry.choosable = false; entry.placeWhy = 'forced-remote';
        } else if (!meta || meta.pending || meta.unknown) {
          entry.place = entry.exec === 'remote' ? 'remote' : 'local';
          entry.choosable = false; entry.placeWhy = 'unknown-source';
        } else {
          entry.defaultPlace = 'local';
          entry.place = entry.exec || 'local';
          entry.choosable = true;
          entry.placeWhy = entry.exec ? 'exec-directive' : 'default';
        }
      }
      directiveLines.push(entry);
    }

    var place = directiveLines.some(function (l) { return l.place === 'remote'; }) ? 'remote' : 'local';
    // Kun trygt å tilby toggle når HVER direktivlinje kan flyttes — blandet
    // tvunget/valgbart gir kjøringsfeil i dag (kan ikke kombinere kilder).
    var placeChoosable = directiveLines.length > 0 &&
      directiveLines.every(function (l) { return l.choosable; });
    var placeReasons = directiveLines
      .filter(function (l) { return !l.choosable || l.exec; })
      .map(function (l) { return { name: l.target, why: l.placeWhy, place: l.place }; });

    return {
      level: level, levelReasons: levelReasons,
      place: place, placeChoosable: placeChoosable, placeReasons: placeReasons,
      directiveLines: directiveLines, sourceIds: sourceIds
    };
  }

  // Skriv exec(local|remote) inn i scriptets valgbare direktivlinjer, eller
  // fjern opsjonen (value === null). Skriptet forblir eneste sannhetskilde —
  // badgen holder aldri egen state. Rører KUN linjer derive selv fant som
  // valgbare; exec som matcher linjens default skrives ikke (holder scriptet
  // rent, og gjør applyExec(applyExec(s, v), null) === s modulo whitespace).
  function applyExec(script, value, mode, sourceMeta) {
    var d = derive(script, mode, sourceMeta);
    var lines = String(script || '').split(/\r?\n/);
    d.directiveLines.forEach(function (l) {
      if (!l.choosable) return;
      var idx = l.lineNo - 1;
      var stripped = lines[idx].replace(EXEC_OPT, '');
      if (value && value !== (l.defaultPlace || 'local')) {
        lines[idx] = stripped.replace(/[ \t]*$/, '') + ', exec(' + value + ')';
      } else {
        lines[idx] = stripped;
      }
    });
    return lines.join('\n');
  }

  // HE-nivå (homomorf kryptert kilde): kun fasade-verbene er lovlige.
  // Pre-flight før POST — serveren håndhever uansett selv.
  var HE_VERBS = ['group_agg', 'value_counts', 'crosstab', 'ols'];
  function checkHeVerbs(script) {
    var lines = String(script || '').split(/\r?\n/);
    var offending = [];
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i];
      if (!ln.trim()) continue;
      if (/^\s*(#|\/\/|--)/.test(ln)) continue;                 // kommentar/direktiv
      if (REQUIRE_LINE.bare.test(ln)) continue;                 // bare-require er metadata
      if (!new RegExp('^\\s*(?:' + HE_VERBS.join('|') + ')\\b', 'i').test(ln)) {
        offending.push({ lineNo: i + 1, text: ln.trim() });
      }
    }
    return { ok: offending.length === 0, offending: offending };
  }

  // ── Metadata-cache (Steg 2) ────────────────────────────────────────────
  // Én source_info-henting per kilde-id per økt; badgen re-rendres når svar
  // kommer. 404/feil -> {unknown:true} — badge-oppslag skal ALDRI utløse
  // «be om tilgang»-flyten (den hører til kjøring, se renderAccessDeniedError).
  var _metaCache = {};   // navn -> {pending:bool, value:meta}

  function cachedMeta() {
    var out = {};
    Object.keys(_metaCache).forEach(function (k) {
      out[k] = _metaCache[k].pending ? { pending: true } : _metaCache[k].value;
    });
    return out;
  }

  // deps: {apiBase, authToken, fetchImpl, webRegistry} — webRegistry er
  // data/data-sources.json-lista (offentlige web-kilder: alltid open/local).
  // Returnerer promise som løses når ALLE navnene har metadata i cachen.
  function metaFor(names, deps) {
    deps = deps || {};
    var fetchImpl = deps.fetchImpl || (typeof fetch !== 'undefined' ? fetch.bind(global) : null);
    var jobs = (names || []).map(function (name) {
      if (_metaCache[name] && !_metaCache[name].error) return _metaCache[name].promise || Promise.resolve();
      var reg = (deps.webRegistry || []).find ? (deps.webRegistry || []).find(function (s) { return s.id === name; }) : null;
      if (reg) {
        _metaCache[name] = { pending: false, value: { public: true, default_exec: 'local' } };
        return Promise.resolve();
      }
      if (!fetchImpl || !deps.apiBase) {
        _metaCache[name] = { pending: false, value: { unknown: true } };
        return Promise.resolve();
      }
      var headers = deps.authToken ? { 'Authorization': 'Bearer ' + deps.authToken } : {};
      var entry = { pending: true, value: null };
      entry.promise = fetchImpl(deps.apiBase.replace(/\/+$/, '') + '/_/api/source_info?id=' + encodeURIComponent(name), { headers: headers })
        .then(function (r) { return r.ok ? r.json() : { unknown: true }; })
        .then(function (info) {
          entry.pending = false;
          entry.value = (!info || info.error) ? { unknown: true } : info;
        })
        .catch(function () { entry.pending = false; entry.value = { unknown: true }; entry.error = true; });
      _metaCache[name] = entry;
      return entry.promise;
    });
    return Promise.all(jobs).then(cachedMeta);
  }

  // Kjørebanen VET mer enn source_info (grant-level, strict, konvoluttype fra
  // faktisk hentede bytes) — mat det tilbake så badgen oppgraderes etter
  // første kjøring selv uten server-støtte for level/kind i source_info.
  function noteFetchedLoad(name, info) {
    if (!name || !info) return;
    var prev = (_metaCache[name] && _metaCache[name].value) || {};
    var next = Object.assign({}, prev);
    if (info.level) next.level = info.level;
    if (info.strict) next.local_profile = 'strict';
    if (info.envelopeKind) next.kind = info.envelopeKind;
    if (info.public !== undefined) next.public = info.public;
    delete next.unknown; delete next.pending;
    _metaCache[name] = { pending: false, value: next };
  }

  function _resetCacheForTests() { _metaCache = {}; }

  global.SessionContext = {
    LEVEL_ORDER: LEVEL_ORDER, HE_VERBS: HE_VERBS,
    requireRe: requireRe,
    derive: derive, applyExec: applyExec, checkHeVerbs: checkHeVerbs,
    metaFor: metaFor, cachedMeta: cachedMeta, noteFetchedLoad: noteFetchedLoad,
    _resetCacheForTests: _resetCacheForTests
  };
})(typeof window !== 'undefined' ? window : globalThis);
