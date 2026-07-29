// connect/load-direktiver for Web-modus (spec 5b/5c i
// docs/superpowers/specs/2026-07-03-web-data-svar-design.md, utvidet av
// docs/superpowers/specs/2026-07-05-encrypted-external-sources-design.md §1).
//   # connect <base-url|register-id|anvil-navn> [as alias] [, key(...)][, exec(...)][, kind(...)]
//   # load <url|alias/sti> as navn [, key(...)]  — uttrekk (hel ramme)
//   # require <url> as navn                      — legacy-alias for load (D1)
//   kind(csv|parquet|duckdb|sqlite|json) — eksplisitt kildetype, hopper over sniffing
//   duckdb/sqlite: "load <alias>/<tabell> as <navn>" og "import <alias>/<tabell>.<kolonne>, ... into <navn>"
//   (punktum skiller tabell fra kolonne — bekreftet 2026-07-06, se
//   docs/superpowers/specs/2026-07-06-remote-columnar-sources-design.md)
// Ren parsing/resolusjon — ingen fetch her. Brukes av index.html
// (materialisering) og testes med deno via eval (data-directives.test.ts).
(function (global) {
  'use strict';

  var CONNECT_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*connect[ \t]+(\S+)(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/gim;
  var LOAD_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*(load|require)[ \t]+(\S+)[ \t]+as[ \t]+([A-Za-z_]\w*)((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/gim;

  // Fase 0 federert (spec 2026-07-29-federated-sources-design §3):
  //   # connect federert(<medlem>[, <medlem>...]) as alias [, key(...)][, kind(...)]
  // Medlem = URL eller register-id. Må matches FØR CONNECT_RE (uten mellomrom
  // i listen ville CONNECT_RE ellers slukt hele "federert(a,b)" som target).
  var CONNECT_FED_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*connect[ \t]+federert\(([^)]*)\)(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/gim;

  // Project A (variable-level assembly): create-dataset/import/join/load ->
  // AssemblySpec. See docs/superpowers/plans/2026-07-05-variable-level-assembly.md.
  var CREATE_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*create-dataset[ \t]+([A-Za-z_]\w*)[ \t]*,[ \t]*key\(\s*([A-Za-z_]\w*)\s*\)[ \t]*$/gim;
  var IMPORT_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*import[ \t]+(\S+(?:[ \t]*,[ \t]*\S+)*)[ \t]+into[ \t]+([A-Za-z_]\w*)(?:[ \t]+(left|inner|outer))?[ \t]*$/gim;
  var JOIN_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*join[ \t]+([A-Za-z_]\w*)[ \t]+into[ \t]+([A-Za-z_]\w*)[ \t]+on[ \t]+([A-Za-z_]\w*)(?:[ \t]+(left|inner|outer))?[ \t]*$/gim;
  var LOADAS_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*load[ \t]+([A-Za-z_]\w*(?:\/[A-Za-z_]\w*)?)[ \t]+as[ \t]+([A-Za-z_]\w*)[ \t]*$/gim;

  function isUrlish(target) {
    return /^https?:\/\//i.test(target) || target.indexOf('/api/hent?') === 0;
  }

  // ", key(<literal>|ask)" og ", exec(local|remote)" — spec §1.
  function parseOptions(tail) {
    var opts = {}, re = /(\w+)\(([^)]*)\)/g, m;
    while ((m = re.exec(tail || '')) !== null) {
      var name = m[1].toLowerCase(), val = m[2].trim();
      if (name === 'key') opts.key = val || 'ask';
      else if (name === 'exec') opts.exec = val.toLowerCase();
      else if (name === 'kind') opts.kind = val.toLowerCase();
    }
    return opts;
  }

  // key(<literal>) -> key(***) før scriptet logges eller sendes til AI.
  // key(ask) er ingen hemmelighet og beholdes.
  function scrubKeys(script) {
    return String(script || '').replace(/\b(key\()\s*(?!ask\s*\))[^)]*\)/gi, '$1***)');
  }

  function parse(script) {
    var connects = [], loads = [], errors = [], m;
    CONNECT_FED_RE.lastIndex = 0;
    while ((m = CONNECT_FED_RE.exec(script)) !== null) {
      var members = m[1].split(',').map(function (s) { return s.trim(); }).filter(Boolean);
      if (!members.length) { errors.push('federert() krever minst ett medlem: ' + m[0].trim()); continue; }
      if (!m[2]) { errors.push('connect federert(...) krever "as <alias>"'); continue; }
      connects.push({ target: null, federated: members, alias: m[2], options: parseOptions(m[3]) });
    }
    CONNECT_RE.lastIndex = 0;
    while ((m = CONNECT_RE.exec(script)) !== null) {
      if (/^federert\(/i.test(m[1])) continue;   // eies av CONNECT_FED_RE (også feiltilfellene)
      var target = m[1];
      var alias = m[2] || (isUrlish(target) ? null : target); // register-id/navn: alias = id
      if (!alias) { errors.push('connect med URL krever "as <alias>": ' + target); continue; }
      connects.push({ target: target, alias: alias, options: parseOptions(m[3]) });
    }
    LOAD_RE.lastIndex = 0;
    while ((m = LOAD_RE.exec(script)) !== null) {
      var verb = m[1].toLowerCase();
      // Legacy require er BARE vårt når målet er en URL (navngitte kilder
      // rutes til serveren av maybeRunRemote — ikke rør dem her).
      if (verb === 'require' && !isUrlish(m[2])) continue;
      loads.push({ verb: verb, target: m[2], alias: m[3], options: parseOptions(m[4]), line: m[0].trim() });
    }
    return { connects: connects, loads: loads, errors: errors };
  }

  function findRegistrySource(registry, id) {
    if (!registry) return null;
    for (var i = 0; i < registry.length; i++) if (registry[i].id === id) return registry[i];
    return null;
  }

  // Fase 0: gjør ett federert medlem om til et sub-item for fetch-laget.
  // rest = valgfri sti fra load-linjen — appendes når medlemmet er en base
  // (samme relative layout hos hver dataholder er det naturlige for
  // horisontal federering). level 'sensitive' nektes her (spec §3: pull-
  // tier er aldri nok for sensitive — krever node, som er fase 1).
  // explicitUrl: medlemmet kommer fra en register-definert members-liste der
  // url-feltet ALLTID er en URL (også relativ, f.eks. static_data/...) — den
  // skal aldri tolkes som register-id.
  function resolveFederatedMember(target, idx, rest, opts, registry, explicitUrl) {
    var sub = { id: 'm' + (idx + 1), url: '', viaProxy: false,
                key: opts.key, kind: opts.kind };
    var level = null;
    if (explicitUrl || isUrlish(target)) {
      sub.url = target;
    } else {
      var src = findRegistrySource(registry, target);
      if (!src) return { error: 'ukjent federert medlem «' + target + '» (ikke i registeret, og ikke en URL)' };
      if (src.kind === 'federated' || src.members) return { error: 'federert medlem «' + target + '» er selv federert — nesting støttes ikke' };
      sub.id = src.id;
      sub.url = src.base_url;
      sub.viaProxy = !!src.auth || src.cors === false;
      level = src.level || null;
    }
    if (level === 'sensitive') return { error: 'federert medlem «' + target + '» er sensitivt — pull-federering (fase 0) er ikke lov; krever node-medlem (fase 1)' };
    if (level) sub.level = level;
    if (rest) {
      if (sub.url.charAt(sub.url.length - 1) !== '/') sub.url += '/';
      sub.url += rest;
    }
    return sub;
  }

  function resolve(parsed, registry) {
    var byAlias = {};
    parsed.connects.forEach(function (c) { byAlias[c.alias] = c; });
    return parsed.loads.map(function (l) {
      var lopts = l.options || {};
      if (isUrlish(l.target)) {
        return { alias: l.alias, url: l.target,
                 viaProxy: l.target.indexOf('/api/hent?') === 0,
                 key: lopts.key, exec: lopts.exec, kind: lopts.kind };
      }
      var slash = l.target.indexOf('/');
      var head = slash > 0 ? l.target.slice(0, slash) : l.target;
      var rest = slash > 0 ? l.target.slice(slash + 1) : '';
      var conn = byAlias[head];
      if (!conn) {
        // Relativ sti (2026-07-30): «load static_data/person.parquet as df»
        // uten connect-linje er en fil relativt til appen, ikke et alias.
        // Regel: ./-prefiks, ELLER ukjent alias der siste segment har
        // filendelse → relativ URL. Uten endelse (load helse/tabell) beholdes
        // den tydelige alias-feilen — det er nesten alltid en glemt connect.
        var lastSeg = l.target.slice(l.target.lastIndexOf('/') + 1);
        if (l.target.charAt(0) === '.' || lastSeg.indexOf('.') > 0) {
          return { alias: l.alias, url: l.target, viaProxy: false,
                   key: lopts.key, exec: lopts.exec, kind: lopts.kind, relative: true };
        }
        return { alias: l.alias, url: '', viaProxy: false, error: 'ukjent kilde-alias «' + head + '» (mangler connect-linje?)' };
      }
      var copts = conn.options || {};
      // Fase 0 federert: inline federert(...)-connect ELLER register-oppslag
      // med kind:'federated' — begge gir ETT item med federated-liste som
      // fetch-laget fanner ut og unionerer (spec 2026-07-29 §3–4).
      var fedTargets = null, fedMeta = {};
      if (conn.federated) {
        fedTargets = conn.federated.map(function (t) { return { target: t }; });
      } else if (!isUrlish(conn.target)) {
        var srcMaybe = findRegistrySource(registry, conn.target);
        if (srcMaybe && (srcMaybe.kind === 'federated' || srcMaybe.members)) {
          // Fase 1: node-medlemmer har ingen url å pulle — de kjøres federert
          // (require i microdata-modus), aldri via load-fanout.
          var nodeMember = (srcMaybe.members || []).some(function (mm) { return mm.tier === 'node'; });
          if (nodeMember) {
            return { alias: l.alias, error: 'kilden «' + conn.target + '» har node-medlemmer — den kjøres federert i microdata-modus (require), ikke via load' };
          }
          fedTargets = (srcMaybe.members || []).map(function (mm) { return { target: mm.url || mm.id, member: mm }; });
          fedMeta = srcMaybe;
        }
      }
      if (fedTargets) {
        var mopts = { key: lopts.key || copts.key, kind: lopts.kind || copts.kind };
        var subs = [], fedErr = null;
        fedTargets.forEach(function (ft, fi) {
          if (fedErr) return;
          var sub = resolveFederatedMember(ft.target, fi, rest, mopts, registry, !!(ft.member && ft.member.url));
          if (sub.error) { fedErr = sub.error; return; }
          if (ft.member) {
            if (ft.member.id) sub.id = ft.member.id;
            if (ft.member.kind) sub.kind = ft.member.kind;
            if (ft.member.level === 'sensitive') { fedErr = 'federert medlem «' + sub.id + '» er sensitivt — pull-federering (fase 0) er ikke lov; krever node-medlem (fase 1)'; return; }
            if (ft.member.level) sub.level = ft.member.level;
          }
          subs.push(sub);
        });
        if (fedErr) return { alias: l.alias, error: fedErr };
        var fedItem = { alias: l.alias, federated: subs };
        if (fedMeta.overlap) fedItem.overlap = fedMeta.overlap;
        if (fedMeta.entity) fedItem.entity = fedMeta.entity;
        return fedItem;
      }
      var key = lopts.key || copts.key, exec = lopts.exec || copts.exec, kind = lopts.kind || copts.kind;
      var base, viaProxy = false;
      if (isUrlish(conn.target)) {
        base = conn.target;
      } else {
        var src = findRegistrySource(registry, conn.target);
        if (!src) {
          // Ikke i web-registeret: en registrert Anvil-kilde (spec §1, regel 3).
          return { alias: l.alias, anvil: conn.target, key: key, exec: exec, kind: kind };
        }
        base = src.base_url;
        viaProxy = !!src.auth || src.cors === false;
      }
      // duckdb/sqlite: én fil, flere tabeller — "stien" er tabellnavnet, ikke
      // en URL-sti (spec 2026-07-06-remote-columnar-sources-design §1).
      if (kind === 'duckdb' || kind === 'sqlite') {
        if (!rest) return { alias: l.alias, url: base, viaProxy: viaProxy, kind: kind,
          error: '«' + l.alias + '»: duckdb/sqlite-kilder krever en tabell — «load ' + head + '/<tabell> as ' + l.alias + '»' };
        return { alias: l.alias, url: base, viaProxy: viaProxy, key: key, exec: exec, kind: kind, table: rest };
      }
      if (rest) {
        if (base.charAt(base.length - 1) !== '/') base += '/';
        base += rest;
      }
      return { alias: l.alias, url: base, viaProxy: viaProxy, key: key, exec: exec, kind: kind };
    });
  }

  // Project A: parse create-dataset/import/join/load into a mode-neutral spec.
  function parseAssembly(script) {
    var errors = [], datasets = [], byName = {}, sources = {}, sourceTables = {}, m;
    // connect aliases (for source validation)
    var conns = {};
    parse(script).connects.forEach(function (c) { conns[c.alias] = true; });

    CREATE_RE.lastIndex = 0;
    while ((m = CREATE_RE.exec(script)) !== null) {
      if (byName[m[1]]) { errors.push('datasettet «' + m[1] + '» er allerede opprettet'); continue; }
      var d = { name: m[1], key: m[2], steps: [] };
      datasets.push(d); byName[m[1]] = d;
    }
    LOADAS_RE.lastIndex = 0;
    while ((m = LOADAS_RE.exec(script)) !== null) {
      var rawL = m[1], nameL = m[2];
      var slashL = rawL.indexOf('/');
      var srcL = slashL > 0 ? rawL.slice(0, slashL) : rawL;
      var tableL = slashL > 0 ? rawL.slice(slashL + 1) : null;
      var keyL = tableL ? (srcL + '__' + tableL) : srcL;
      if (byName[nameL]) { errors.push('datasettet «' + nameL + '» er allerede opprettet'); continue; }
      var dl = { name: nameL, load: keyL };
      datasets.push(dl); byName[nameL] = dl; sources[keyL] = true;
      if (tableL) sourceTables[keyL] = { source: srcL, table: tableL };
    }
    IMPORT_RE.lastIndex = 0;
    while ((m = IMPORT_RE.exec(script)) !== null) {
      var target = m[2];
      var d2 = byName[target];
      if (!d2 || d2.load) { errors.push('ukjent datasett «' + target + '» (mangler create-dataset?)'); continue; }
      var bySrc = {};
      m[1].split(',').forEach(function (ref) {
        var parts = ref.trim().split('/');
        if (parts.length !== 2) { errors.push('import krever <kilde>/<kolonne>: ' + ref.trim()); return; }
        var srcAlias = parts[0].trim(), pathPart = parts[1].trim();
        var dot = pathPart.indexOf('.');
        var table = dot > 0 ? pathPart.slice(0, dot) : null;
        var col = dot > 0 ? pathPart.slice(dot + 1) : pathPart;
        var srcKey = table ? (srcAlias + '__' + table) : srcAlias;
        sources[srcKey] = true;
        if (table) sourceTables[srcKey] = { source: srcAlias, table: table };
        (bySrc[srcKey] = bySrc[srcKey] || []).push(col);
      });
      Object.keys(bySrc).forEach(function (src) {
        d2.steps.push({ op: 'import', source: src, columns: bySrc[src], how: (m[3] || 'left') });
      });
    }
    JOIN_RE.lastIndex = 0;
    while ((m = JOIN_RE.exec(script)) !== null) {
      var tgt = m[2], d3 = byName[tgt];
      if (!d3 || d3.load) { errors.push('ukjent datasett «' + tgt + '» (mangler create-dataset?)'); continue; }
      if (!byName[m[1]]) { errors.push('ukjent datasett «' + m[1] + '» i join'); continue; }
      d3.steps.push({ op: 'join', from: m[1], on: m[3], how: (m[4] || 'left') });
    }
    return { spec: { sources: Object.keys(sources), datasets: datasets, sourceTables: sourceTables }, errors: errors };
  }

  // "# use <navn> from r|python" — kryssruntime-kopi av et datasett (parquet-
  // bro, kopisemantikk: endringer smitter ikke). Ren parsing; overføringen
  // gjøres av index.html i materialiseringsfasen for hver modus.
  // `from <kilde>` er valgfri (kortform, 2026-07-11): uten from er kilden
  // null her — parseSegmentUses() utleder den fra segmentrekkefølgen, og
  // run-start-brukere som krever eksplisitt kilde feiler med tydelig melding.
  var USE_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*use[ \t]+(\S+)(?:[ \t]+from[ \t]+(\S+))?[ \t]*$/gim;
  function parseUse(script) {
    var uses = [], errors = [], m;
    USE_RE.lastIndex = 0;
    while ((m = USE_RE.exec(script || '')) !== null) {
      var name = m[1], from = m[2] ? m[2].toLowerCase() : null;
      if (!/^[A-Za-z_]\w*$/.test(name)) { errors.push('ugyldig datasettnavn i use: «' + name + '»'); continue; }
      if (from !== null && from !== 'r' && from !== 'python' && from !== 'duckdb') { errors.push('use «' + name + '»: kilde må være r, python eller duckdb, fikk «' + m[2] + '»'); continue; }
      uses.push({ name: name, from: from });
    }
    return { uses: uses, errors: errors };
  }

  // Runtime-familie per segment-kind: microdata/pyodide deler Python-heapen
  // (use er aldri nødvendig dem imellom), duckdb og r er egne motorer.
  function runtimeFamily(kind) {
    if (kind === 'r') return 'r';
    if (kind === 'duckdb') return 'duckdb';
    return 'python';   // microdata, pyodide, ukjent → trygt valg
  }

  // Segmentnivå-use (plan 2026-07-11-segment-use-cross-runtime): trekk
  // use-linjene ut av hvert segment, utled manglende kilde som familien til
  // NÆRMESTE FOREGÅENDE segment med annen runtime enn blokken selv, og
  // returner segmentene med use-linjene strippet (de er metadata; «# use»
  // er ikke gyldig SQL, og i R/py ville de bare vært støy).
  // -> { segments: [{kind, text, uses: [{name, from}]}], errors: [...] }
  function parseSegmentUses(segments) {
    var out = [], errors = [];
    // Egen regex-instans: USE_RE deles med parseUse, og replace/exec på samme
    // globale regex-objekt tråkker i hverandres lastIndex.
    var SEG_USE_RE = new RegExp(USE_RE.source, 'gim');
    (segments || []).forEach(function (seg, i) {
      var fam = runtimeFamily(seg.kind);
      var uses = [];
      var text = String(seg.text || '').replace(SEG_USE_RE, function (line, name, fromRaw) {
        var u = { name: name, from: fromRaw ? fromRaw.toLowerCase() : null };
        if (!/^[A-Za-z_]\w*$/.test(u.name)) { errors.push('ugyldig datasettnavn i use: «' + u.name + '»'); return ''; }
        if (u.from !== null && u.from !== 'r' && u.from !== 'python' && u.from !== 'duckdb') {
          errors.push('use «' + u.name + '»: kilde må være r, python eller duckdb, fikk «' + fromRaw + '»');
          return '';
        }
        if (u.from === null) {
          for (var j = i - 1; j >= 0; j--) {
            var pf = runtimeFamily((segments[j] || {}).kind);
            if (pf !== fam) { u.from = pf; break; }
          }
          if (u.from === null) {
            errors.push('use «' + u.name + '»: fant ingen tidligere blokk med annet språk å hente fra — angi kilden: # use ' + u.name + ' from python|r|duckdb');
            return '';
          }
        }
        if (u.from === fam) {
          errors.push('use «' + u.name + '» from ' + u.from + ': blokken kjører allerede i ' + u.from + ' — datasett derfra refereres direkte');
          return '';
        }
        uses.push(u);
        return '';
      });
      out.push({ kind: seg.kind, text: text, uses: uses });
    });
    return { segments: out, errors: errors };
  }

  global.DataDirectives = { parse: parse, resolve: resolve, scrubKeys: scrubKeys, parseAssembly: parseAssembly, parseOptions: parseOptions, parseUse: parseUse, parseSegmentUses: parseSegmentUses, runtimeFamily: runtimeFamily };
})(typeof window !== 'undefined' ? window : globalThis);
