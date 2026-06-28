# Lazy mode-module system + jamovi extraction

**Goal:** Move jamovi out of the core (index.html + app.css) into an on-demand module
`js/modes/jamovi.js` + `css/modes/jamovi.css`, loaded only when the user first selects
jamovi. Establish a reusable `window.M2PY` contract + `loadModeModule()` loader so future
modes (statx/python/r) can follow the same pattern.

## The M2PY contract (added to core, ~after updateModeGuiBar at line ~3245)
```js
window.M2PY = {
  registerMode: function(p){ modeRegistry[p.id] = p;
    if (typeof editorContent !== 'undefined' && !(p.id in editorContent)) editorContent[p.id] = '';
    if (typeof editorBP !== 'undefined' && !(p.id in editorBP)) editorBP[p.id] = new Set(); },
  currentMode: function(){ return currentMode(); },
  updateModeGuiBar: function(){ return updateModeGuiBar(); },
  getModeGuiBar: function(){ return document.getElementById('modeGuiBar'); },
  get outputArea(){ return outputArea; },
  get rightStatus(){ return rightStatus; },
  setStatus: function(el, msg){ return setStatus(el, msg); },
  escapeHtml: function(s){ return escapeHtml(s); },
  R_HL_CFG: R_HL_CFG,
  handleRTab: handleRTab,
  loadPyodideAndM2py: function(){ return loadPyodideAndM2py(); },
  runHybridR: function(){ return runHybridR.apply(null, arguments); },
  loadWebR: function(){ return loadWebR(); },
  isWebRReady: function(){ return webRReady; },
  getWebR: function(){ return webR; },
  ensureWebRShelter: async function(){ if (!webRReady) await loadWebR(); if (!webRShelter) webRShelter = await new webR.Shelter(); return webRShelter; }
};
var MODE_MODULES = { jamovi: { js: 'js/modes/jamovi.js', css: 'css/modes/jamovi.css' } };
var _modeModuleP = {};
function loadModeModule(id){
  if (_modeModuleP[id]) return _modeModuleP[id];
  var m = MODE_MODULES[id];
  if (!m) return Promise.resolve();
  _modeModuleP[id] = new Promise(function(resolve, reject){
    if (m.css){ var l = document.createElement('link'); l.rel='stylesheet'; l.href=m.css; document.head.appendChild(l); }
    var s = document.createElement('script'); s.src = m.js;
    s.onload = function(){ resolve(); };
    s.onerror = function(){ reject(new Error('mode module load failed: ' + id)); };
    document.body.appendChild(s);
  });
  return _modeModuleP[id];
}
```

## Lazy hook (initModeSwitcher click handler, line ~3851)
Make the listener async; before switching, load the module if needed:
```js
b.addEventListener('click', async function() {
  menu.classList.remove('open');
  var target = b.dataset.mode;
  if (target === activeEditorMode || scriptRunInProgress) return;
  if (MODE_MODULES[target] && !_modeModuleP[target]) {
    try { await loadModeModule(target); } catch(e){ console.error(e); return; }
  }
  switchEditorMode(target);
});
```
(No init-restore needed: app always boots in microdata, activeEditorMode='microdata' at line 4006.)

## Removed from core
- modeRegistry.jamovi entry (lines 3181-3185) → becomes M2PY.registerMode in the module.
- jamovi-specific block (3246-3835): jamoviVariables, ensureJamoviDataInWebR, JAMOVI_ANALYSES,
  jamoviAppendPlot, renderJamoviResult, jamoviTypeIcon, JAMOVI_ICONS, JAMOVI_CAT_ICONS,
  openJamoviAnalysis, initJamoviRibbon IIFE.
- #jamoviRibbon markup (inside #modeGuiBar, lines 144-154) — keep #modeGuiBar empty.
- jamovi CSS in app.css (.jamovi-ribbon, .jmv-*, --jmv-* tokens) → css/modes/jamovi.css.
- KEEP in core: updateModeGuiBar, .mode-gui-bar CSS (generic), the data-mode="jamovi" dropdown button.

## Module transform rules (core ref → M.*)
webRReady→M.isWebRReady(); webR→M.getWebR(); the lazy `if(!webRShelter)…` + uses → `var shelter=await M.ensureWebRShelter()` then shelter.evalR/captureR; loadWebR→M.loadWebR; loadPyodideAndM2py→M.loadPyodideAndM2py; outputArea→M.outputArea; setStatus→M.setStatus; rightStatus→M.rightStatus; escapeHtml→M.escapeHtml; runHybridR→M.runHybridR; updateModeGuiBar→M.updateModeGuiBar; the registry entry → M.registerMode({...}); ribbon HTML injected into M.getModeGuiBar().
