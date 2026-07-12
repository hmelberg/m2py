/* dash-webr.js — JS-glue for dash v2 i R-modus (spec 2026-07-12 §5.3).
   webr/dash.R samler deklarasjoner under script-kjøringen; denne fila henter
   registeret etterpå (mount), bygger dashboardet via window.Dash (js/dash.js)
   og re-kjører funksjonskort async via evalR + captureR i en EGEN Shelter
   (aldri app-shelteret — purge her skal ikke kunne rive andres objekter).
   Ren halvdel: makeQueue — node-testet, ingen DOM/webR. */
(function (global) {
  'use strict';
  var G = {};

  // Sekvensiell kjede med per-nøkkel siste-vinner-koalescing: maks én
  // dash_run om gangen (webR-kanalen serialiserer uansett), og raske
  // widget-endringer på samme kort kollapser til nyeste verdier.
  G.makeQueue = function () {
    var chain = Promise.resolve();
    var pending = {};
    return {
      schedule: function (key, args, run) {
        var had = Object.prototype.hasOwnProperty.call(pending, key);
        pending[key] = args;
        if (had) return;
        chain = chain.then(function () {
          var a = pending[key];
          delete pending[key];
          return run(a);
        }).catch(function () {});
      },
      idle: function () { return chain; }
    };
  };

  // ---- browser-halvdel ----
  var _defsP = null;     // memoisert: jsonlite + webr/dash.R evaluert
  var _shelter = null;   // dash-webr sin egen Shelter

  G.ensureDefs = function () {
    if (_defsP) return _defsP;
    _defsP = (async function () {
      var M = global.M2PY;
      await M.loadWebR();
      var webR = M.getWebR();
      try { await webR.installPackages(['jsonlite'], { quiet: true }); } catch (e) {}
      var r = await fetch('webr/dash.R?v=' + (global.M2PY_VERSION || '1'));
      if (!r.ok) throw new Error('webr/dash.R: ' + r.status);
      await webR.evalRVoid(await r.text());
    })().catch(function (e) { _defsP = null; throw e; });
    return _defsP;
  };

  G.reset = async function () {
    if (!_defsP) return;
    await _defsP;
    await global.M2PY.getWebR().evalRVoid('.dash_reset()');
  };

  async function dashShelter() {
    if (_shelter) return _shelter;
    var webR = global.M2PY.getWebR();
    _shelter = await new webR.Shelter();
    return _shelter;
  }

  async function evalRString(code) {
    var webR = global.M2PY.getWebR();
    var obj = await webR.evalR(code);
    try {
      var js = await obj.toJs();
      return (js && js.values && js.values[0] != null) ? String(js.values[0]) : '';
    } finally {
      try { await webR.destroy(obj); } catch (e) {}
    }
  }

  function bitmapToDataUri(bmp) {
    var c = document.createElement('canvas');
    c.width = bmp.width;
    c.height = bmp.height;
    c.getContext('2d').drawImage(bmp, 0, 0);
    return c.toDataURL('image/png');
  }

  // Kjør ett funksjonskort R-side; returnér endelig payload.
  // Regler (spec §5.3): payload-JSON fra .dash_run er sannheten, MEN
  //  - fanget plott vinner over tom tekst (ggplot/base-plot-kort)
  //  - stdout vinner over tom tekst (print-paritet med python-adapterne)
  async function runCard(di, ci, rawValues) {
    var shelter = await dashShelter();
    var code = '.dash_run(' + di + ', ' + ci + ', ' +
               JSON.stringify(JSON.stringify(rawValues)) + ')';
    var cap = await shelter.captureR(code, {
      withAutoprint: false,
      captureGraphics: { width: 720, height: 480 }
    });
    try {
      var js = await cap.result.toJs();
      var payload = JSON.parse((js && js.values && js.values[0]) ||
        '{"kind":"error","message":"tomt svar fra .dash_run"}');
      if (payload.kind === 'text' && !payload.text) {
        if (cap.images && cap.images.length) {
          payload = { kind: 'image',
                      src: bitmapToDataUri(cap.images[cap.images.length - 1]) };
        } else {
          var stdout = (cap.output || [])
            .filter(function (o) { return o.type === 'stdout'; })
            .map(function (o) { return String(o.data); })
            .join('\n');
          if (stdout.trim()) payload = { kind: 'text', text: stdout.replace(/\s+$/, '') };
        }
      }
      return payload;
    } finally {
      try { await shelter.purge(); } catch (e) {}
    }
  }

  // Bygg dashboardene fra R-registeret. Kalles av runHybridR ETTER
  // renderROutputParts (tekst-output først, dashboard appendes under).
  // Venter på førsterenders (idle) så kallerens shelter-purge ikke kan
  // treffe kjøringer i flukt.
  G.mount = async function () {
    if (!_defsP) return;                 // ingen dash-defs denne økten
    await _defsP;
    var reg = null;
    try { reg = JSON.parse(await evalRString('.dash_registry_json()')); }
    catch (e) { console.warn('dash-webr: registry', e); }
    if (!reg || !reg.dashes || !reg.dashes.length) return;
    var q = G.makeQueue();

    reg.dashes.forEach(function (dashDecl, dIdx) {
      var di = dIdx + 1;
      var dashId = global.Dash.create(JSON.stringify(
        { title: dashDecl.title, layout: dashDecl.layout }));
      var sharedRaw = {};
      var cardsMeta = [];

      function effective(cm) {
        var vals = {};
        (cm.params || []).forEach(function (p) {
          if (p in cm.ownRaw) vals[p] = cm.ownRaw[p];
          else if (p in sharedRaw) vals[p] = sharedRaw[p];
        });
        return vals;
      }

      function scheduleRun(cm) {
        global.Dash.setBusy(cm.cid);
        q.schedule(di + ':' + cm.ci, effective(cm), async function (vals) {
          var payload;
          try { payload = await runCard(di, cm.ci, vals); }
          catch (e) {
            payload = { kind: 'error', message: String((e && e.message) || e) };
          }
          global.Dash.updateCard(cm.cid, JSON.stringify(payload), null);
        });
      }

      (dashDecl.cards || []).forEach(function (card, cIdx) {
        var ci = cIdx + 1;
        var opts = { title: card.title || null, area: card.at || null };
        if (!card.func) {
          opts.content = card.payload;
          global.Dash.addCard(dashId, JSON.stringify(opts), null, null);
          return;
        }
        opts.controls = card.controls || [];
        opts.content = null;
        var cm = { ci: ci, params: card.params || [], ownRaw: {}, cid: null };
        var onChange = function (valuesJson) {
          cm.ownRaw = JSON.parse(valuesJson);
          scheduleRun(cm);
        };
        cm.cid = global.Dash.addCard(dashId, JSON.stringify(opts),
                                     opts.controls.length ? onChange : null, null);
        cm.ownRaw = JSON.parse(global.Dash.initialValues(cm.cid) || '{}');
        cardsMeta.push(cm);
      });

      if (dashDecl.shared && dashDecl.shared.length) {
        global.Dash.addControls(dashId, JSON.stringify(dashDecl.shared),
          function (valuesJson) {
            sharedRaw = JSON.parse(valuesJson);
            var names = Object.keys(sharedRaw);
            cardsMeta.forEach(function (cm) {
              if (cm.params.some(function (p) { return names.indexOf(p) !== -1; }))
                scheduleRun(cm);
            });
          });
        sharedRaw = JSON.parse(global.Dash.initialValues(dashId) || '{}');
      }

      // K2: førsterender med effektive startverdier (defaults eller ds-URL)
      cardsMeta.forEach(scheduleRun);
    });

    await q.idle();
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = G;
  global.DashWebR = G;
})(typeof window !== 'undefined' ? window : globalThis);
