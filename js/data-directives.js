// connect/load-direktiver for Web-modus (spec 5b/5c i
// docs/superpowers/specs/2026-07-03-web-data-svar-design.md, utvidet av
// docs/superpowers/specs/2026-07-05-encrypted-external-sources-design.md §1).
//   # connect <base-url|register-id|anvil-navn> [as alias] [, key(...)][, exec(...)]
//   # load <url|alias/sti> as navn [, key(...)]  — uttrekk (hel ramme)
//   # require <url> as navn                      — legacy-alias for load (D1)
// Ren parsing/resolusjon — ingen fetch her. Brukes av index.html
// (materialisering) og testes med deno via eval (data-directives.test.ts).
(function (global) {
  'use strict';

  var CONNECT_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*connect[ \t]+(\S+)(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/gim;
  var LOAD_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*(load|require)[ \t]+(\S+)[ \t]+as[ \t]+([A-Za-z_]\w*)((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/gim;

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
    CONNECT_RE.lastIndex = 0;
    while ((m = CONNECT_RE.exec(script)) !== null) {
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

  function resolve(parsed, registry) {
    var byAlias = {};
    parsed.connects.forEach(function (c) { byAlias[c.alias] = c; });
    return parsed.loads.map(function (l) {
      var lopts = l.options || {};
      if (isUrlish(l.target)) {
        return { alias: l.alias, url: l.target,
                 viaProxy: l.target.indexOf('/api/hent?') === 0,
                 key: lopts.key, exec: lopts.exec };
      }
      var slash = l.target.indexOf('/');
      var head = slash > 0 ? l.target.slice(0, slash) : l.target;
      var rest = slash > 0 ? l.target.slice(slash + 1) : '';
      var conn = byAlias[head];
      if (!conn) return { alias: l.alias, url: '', viaProxy: false, error: 'ukjent kilde-alias «' + head + '» (mangler connect-linje?)' };
      var copts = conn.options || {};
      var key = lopts.key || copts.key, exec = lopts.exec || copts.exec;
      var base, viaProxy = false;
      if (isUrlish(conn.target)) {
        base = conn.target;
      } else {
        var src = findRegistrySource(registry, conn.target);
        if (!src) {
          // Ikke i web-registeret: en registrert Anvil-kilde (spec §1, regel 3).
          return { alias: l.alias, anvil: conn.target, key: key, exec: exec };
        }
        base = src.base_url;
        viaProxy = !!src.auth || src.cors === false;
      }
      if (rest) {
        if (base.charAt(base.length - 1) !== '/') base += '/';
        base += rest;
      }
      return { alias: l.alias, url: base, viaProxy: viaProxy, key: key, exec: exec };
    });
  }

  global.DataDirectives = { parse: parse, resolve: resolve, scrubKeys: scrubKeys };
})(typeof window !== 'undefined' ? window : globalThis);
