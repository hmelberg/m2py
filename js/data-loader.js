// Materialisering av connect/load-direktiver: parse → resolve → fetch.
// Ingen runtime-binding her — index.html binder bytes inn i pyodide/webr/
// duckdb med ~10 linjer per modus. deps er injiserbar for tester.
(function (global) {
  'use strict';

  var _registryCache = null;
  async function loadRegistry(fetchImpl) {
    if (_registryCache) return _registryCache;
    try {
      var r = await fetchImpl('data/data-sources.json');
      _registryCache = r.ok ? await r.json() : [];
    } catch (e) { _registryCache = []; }
    return _registryCache;
  }

  // Proxy-auth: innloggingstoken har forrang; ellers BYOK-nøkkel (hent-
  // endepunktet godtar X-Anthropic-Key via allowByok, jf. B5 i roadmapen).
  function proxyHeaders(authToken, anthropicKey) {
    if (authToken) return { 'Authorization': 'Bearer ' + authToken };
    if (anthropicKey) return { 'X-Anthropic-Key': anthropicKey };
    return {};
  }

  async function fetchLoadTarget(item, fetchImpl, authToken, anthropicKey) {
    async function viaProxy() {
      var pr = await fetchImpl('/api/hent?url=' + encodeURIComponent(item.url), { headers: proxyHeaders(authToken, anthropicKey) });
      if (!pr.ok) throw new Error('proxy ' + pr.status + ' for ' + item.alias);
      return pr;
    }
    if (item.url.indexOf('/api/hent?') === 0) {
      var r0 = await fetchImpl(item.url, { headers: proxyHeaders(authToken, anthropicKey) });
      if (!r0.ok) throw new Error('proxy ' + r0.status + ' for ' + item.alias);
      return r0;
    }
    if (item.viaProxy) return viaProxy();
    try {
      var r1 = await fetchImpl(item.url);
      if (!r1.ok) throw new Error('HTTP ' + r1.status + ' for ' + item.alias + ' (' + item.url + ')');
      return r1;
    } catch (e) {
      if (e instanceof TypeError) return viaProxy();   // CORS/nettverk → proxy
      throw e;
    }
  }

  function sniffFormat(resp, url) {
    var ct = (resp.headers.get('content-type') || '').toLowerCase();
    if (ct.indexOf('parquet') >= 0 || /\.parquet(\?|$)/.test(url)) return 'parquet';
    if (ct.indexOf('json') >= 0) return 'json';
    if (ct.indexOf('html') >= 0) return 'html';   // f.eks. Wikipedia: bind som råtekst
    return 'csv';
  }

  // Hoved-API: {loads: [{alias, bytes(Uint8Array), format}],
  //             remote: [{alias, sourceId, key}]} eller kast norsk feil.
  // remote = registrerte kilder som IKKE kan analyseres lokalt (level != public):
  // index.html ruter hele scriptet til serveren med source_keys (spec §4).
  async function resolveAndFetchLoads(script, deps) {
    deps = deps || {};
    var fetchImpl = deps.fetchImpl || (typeof fetch !== 'undefined' ? fetch.bind(global) : null);
    var DD = global.DataDirectives;
    if (!DD || !fetchImpl) return { loads: [], remote: [] };
    var parsed = DD.parse(script);
    if (!parsed.loads.length) return { loads: [], remote: [] };
    var registry = deps.registry || await loadRegistry(fetchImpl);
    var resolved = DD.resolve(parsed, registry);
    var bad = resolved.filter(function (r) { return r.error; });
    if (bad.length) throw new Error('Direktivfeil: ' + bad.map(function (b) { return b.error; }).join('; '));

    var remote = [];
    var localItems = [];
    for (var i = 0; i < resolved.length; i++) {
      var item = resolved[i];
      if (item.anvil) {
        var grant = await fetchSourceAccess(item, deps, fetchImpl);
        if (grant.remote_only || item.exec === 'remote') {
          if (item.exec === 'local') throw new Error('«' + item.anvil + '» er ikke offentlig — kan ikke kjøres lokalt (kjøres på server).');
          remote.push({ alias: item.alias, sourceId: item.anvil, key: item.key });
          continue;
        }
        item.url = grant.location;
        item.grant = grant;
        item.viaProxy = false;
      } else if (item.exec === 'remote') {
        throw new Error('exec(remote) krever en registrert kilde (navn), ikke URL: ' + item.alias);
      }
      localItems.push(item);
    }

    var loads = await Promise.all(localItems.map(async function (item) {
      var resp = await fetchLoadTarget(item, fetchImpl, deps.authToken || null, deps.anthropicKey || null);
      var buf = new Uint8Array(await resp.arrayBuffer());
      var format = sniffFormat(resp, item.url);
      var dec = await maybeDecrypt(item, buf, format, deps);
      return { alias: item.alias, bytes: dec.bytes, format: dec.format };
    }));
    return { loads: loads, remote: remote };
  }

  function fetchSourceAccess(item, deps, fetchImpl) {
    var base = (deps.apiBase || '').replace(/\/+$/, '');
    if (!base) return Promise.reject(new Error('ingen API-base konfigurert for kilden «' + item.anvil + '»'));
    var headers = deps.authToken ? { 'Authorization': 'Bearer ' + deps.authToken } : {};
    return fetchImpl(base + '/_/api/source_access?id=' + encodeURIComponent(item.anvil), { headers: headers })
      .then(function (r) {
        if (r.status === 404) throw new Error('Fant ikke kilden «' + item.anvil + '» eller du mangler tilgang — logg inn, eller kontakt eieren.');
        if (!r.ok) throw new Error('source_access ' + r.status + ' for «' + item.anvil + '»');
        return r.json();
      });
  }

  // safepy-enc-v1: sniffFormat sier json — sjekk konvolutt, verifiser
  // fingerprint (bytte-vern) og dekrypter lokalt (WebCrypto).
  async function maybeDecrypt(item, buf, format, deps) {
    var EC = global.EncCrypto;
    if (!EC || format !== 'json') return { bytes: buf, format: format };
    var env;
    try { env = JSON.parse(new TextDecoder().decode(buf)); } catch (e) { return { bytes: buf, format: format }; }
    if (!EC.isEnvelope(env)) return { bytes: buf, format: format };
    var computed = await EC.envelopeFingerprint(env);
    if (env.fingerprint && computed !== env.fingerprint)
      throw new Error('«' + item.alias + '»: ødelagt fil (fingerprint stemmer ikke)');
    if (item.grant && item.grant.fingerprint && computed !== item.grant.fingerprint)
      throw new Error('«' + item.alias + '»: filen er endret siden den ble registrert — kontakt eieren');
    var key = (item.key && item.key !== 'ask') ? item.key
            : (item.grant && item.grant.key) ? item.grant.key
            : deps.promptKey ? await deps.promptKey(item.alias)
            : null;
    if (!key) throw new Error('«' + item.alias + '» er kryptert og krever nøkkel — bruk key(...) eller key(ask)');
    var plain = await EC.decryptEnvelope(env, key);
    return { bytes: plain, format: env.payload_format || 'csv' };
  }

  global.DataLoader = { resolveAndFetchLoads: resolveAndFetchLoads, _sniffFormat: sniffFormat };
})(typeof window !== 'undefined' ? window : globalThis);
