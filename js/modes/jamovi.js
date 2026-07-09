(function(){ 'use strict'; var M = window.M2PY;
    var T = window.t || function (s, p) { return p ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in p ? p[k] : m; }) : s; };
    // Variables from the active dataset
    // User-set measure-type overrides (Variables tab), keyed "dataset::column".
    var jamoviTypeOverrides = {};
    var jamoviDataTable = null; // Tabulator instance for the Data tab
    var jamoviFilter = '';      // pandas query applied (non-destructively) to data sent to analyses
    // Fix B (Task 5 review): bumped whenever a live options panel/card is invalidated (dialog
    // reopened/closed, dataset switched, card removed) so an orphaned debounce timer / in-flight
    // rerun loop can recognize it's stale and bail. Declared here (module top) rather than next to
    // openJmvAnalysis so it's unambiguously in scope for jamoviSwitchDataset/jamoviLoadExample/
    // jamoviTitleCard, which also invalidate it.
    var jmvDialogGen = 0;

    // Write a single edited cell back to the engine's pandas DataFrame.
    async function jamoviWriteBack(cell) {
      try {
        var py = await M.loadPyodideAndM2py();
        var v = cell.getValue();
        py.globals.set('_wb_id', cell.getRow().getData().__rowid__);
        py.globals.set('_wb_col', cell.getField());
        py.globals.set('_wb_val', (v === '' ? null : v));
        await py.runPythonAsync(
          'import pandas as _pd\n' +
          '_df = e.datasets[e.active_name]\n' +
          '_df.at[_wb_id, _wb_col] = (_pd.NA if _wb_val is None else _wb_val)'
        );
      } catch (e) {
        M.setStatus(M.rightStatus, 'Lagring feilet: ' + (e.message || e));
        setTimeout(function(){ M.setStatus(M.rightStatus, ''); }, 2500);
      }
    }

    // Data tab actions: add row, delete selected row(s), compute a new variable.
    async function jamoviAddRow() {
      if (!window.activeDatasetName) return;
      var py = await M.loadPyodideAndM2py();
      // append an all-missing row at the end with a fresh index, return its id
      var newId = await py.runPythonAsync('import pandas as _pd\n_df = e.datasets[e.active_name]\n_ni = (int(_df.index.max())+1) if len(_df) else 0\n_df.loc[_ni] = _pd.NA\n_ni');
      // re-render and bring the new (empty) row into view + highlight it
      renderDataView(typeof newId === 'number' ? newId : Number(newId));
    }
    async function jamoviDeleteRow() {
      if (!jamoviDataTable) { alert(T('Åpne Data-fanen først.')); return; }
      var sel = jamoviDataTable.getSelectedData();
      if (!sel.length) { alert(T('Klikk på en rad for å velge den, og prøv igjen.')); return; }
      var ids = sel.map(function(r){ return r.__rowid__; });
      var py = await M.loadPyodideAndM2py();
      py.globals.set('_del_ids', ids);
      await py.runPythonAsync('_df = e.datasets[e.active_name]\ne.datasets[e.active_name] = _df.drop(index=[i for i in list(_del_ids)])');
      renderDataView();
    }
    async function jamoviComputeVar(name, expr) {
      var py = await M.loadPyodideAndM2py();
      py.globals.set('_cv_name', name); py.globals.set('_cv_expr', expr);
      await py.runPythonAsync('_df = e.datasets[e.active_name]\n_df[_cv_name] = _df.eval(_cv_expr)');
      var infoJson = String(await py.runPythonAsync('import json as _j\n_df = e.datasets[e.active_name]\n_j.dumps({"columns": list(map(str,_df.columns)), "dtypes": {str(c): str(_df[c].dtype) for c in _df.columns}, "nrows": int(len(_df))})'));
      window.lastDatasetInfo = window.lastDatasetInfo || {};
      window.lastDatasetInfo[window.activeDatasetName] = JSON.parse(infoJson);
      renderDataView();
    }
    function jamoviComputeVarDialog() {
      if (!window.activeDatasetName) { alert(T('Ingen aktivt datasett.')); return; }
      var cols = ((window.lastDatasetInfo || {})[window.activeDatasetName] || {}).columns || [];
      var backdrop = document.createElement('div'); backdrop.className = 'jmv-dialog-backdrop';
      var dlg = document.createElement('div'); dlg.className = 'jmv-dialog'; dlg.style.maxWidth = '560px';
      dlg.innerHTML = '<div class="jmv-dialog-head">' + T('Beregn variabel') + '</div>';
      var body = document.createElement('div'); body.className = 'jmv-dialog-body'; body.style.display = 'block';
      body.innerHTML = '<div class="jmv-cv-label">' + T('Nytt variabelnavn') + '</div>'
        + '<input class="jmv-cv-input" id="jmvCvName" placeholder="f.eks. logInntekt">'
        + '<div class="jmv-cv-label">' + T('Uttrykk (pandas)') + '</div>'
        + '<input class="jmv-cv-input" id="jmvCvExpr" placeholder="f.eks. inntekt / 1000">'
        + '<div class="jmv-ribbon-hint" style="margin-top:8px">' + T('Tilgjengelige kolonner: {cols}. Bruk backticks for navn med punktum/mellomrom (f.eks. `dan.sleep` * 2).', { cols: cols.map(function(c){ return M.escapeHtml(c); }).join(', ') }) + '</div>'
        + '<div id="jmvCvErr" style="color:#b91c1c;margin-top:6px;font-size:12px"></div>';
      dlg.appendChild(body);
      var foot = document.createElement('div'); foot.className = 'jmv-dialog-foot';
      var close = document.createElement('button'); close.textContent = T('Lukk'); close.addEventListener('click', function(){ document.body.removeChild(backdrop); });
      var ok = document.createElement('button'); ok.className = 'primary'; ok.textContent = T('Beregn');
      ok.addEventListener('click', async function(){
        var name = document.getElementById('jmvCvName').value.trim();
        var expr = document.getElementById('jmvCvExpr').value.trim();
        if (!name || !expr) { document.getElementById('jmvCvErr').textContent = T('Fyll inn navn og uttrykk.'); return; }
        ok.disabled = true;
        try { await jamoviComputeVar(name, expr); document.body.removeChild(backdrop); }
        catch(err){ document.getElementById('jmvCvErr').textContent = T('Feil: {msg}', { msg: err.message || err }); ok.disabled = false; }
      });
      foot.appendChild(close); foot.appendChild(ok); dlg.appendChild(foot);
      backdrop.appendChild(dlg); document.body.appendChild(backdrop);
    }

    // Phase 2: row filter that affects analyses (non-destructive pandas query).
    function jamoviFilterDialog() {
      if (!window.activeDatasetName) { alert(T('Ingen aktivt datasett.')); return; }
      var cols = ((window.lastDatasetInfo || {})[window.activeDatasetName] || {}).columns || [];
      var backdrop = document.createElement('div'); backdrop.className = 'jmv-dialog-backdrop';
      var dlg = document.createElement('div'); dlg.className = 'jmv-dialog'; dlg.style.maxWidth = '560px';
      dlg.innerHTML = '<div class="jmv-dialog-head">' + T('Filter — påvirker analysene') + '</div>';
      var body = document.createElement('div'); body.className = 'jmv-dialog-body'; body.style.display = 'block';
      body.innerHTML = '<div class="jmv-cv-label">' + T('Filteruttrykk (pandas query)') + '</div>'
        + '<input class="jmv-cv-input" id="jmvFiltExpr" placeholder="f.eks. grade > 70">'
        + '<div class="jmv-ribbon-hint" style="margin-top:8px">' + T('Analysene kjøres på radene som oppfyller uttrykket (dataene endres ikke). Tomt = ingen filter. Kolonner: {cols}. Backticks for navn med punktum.', { cols: cols.map(function(c){ return M.escapeHtml(c); }).join(', ') }) + '</div>'
        + '<div id="jmvFiltErr" style="margin-top:6px;font-size:12px"></div>';
      dlg.appendChild(body);
      var foot = document.createElement('div'); foot.className = 'jmv-dialog-foot';
      var close = document.createElement('button'); close.textContent = T('Lukk'); close.addEventListener('click', function(){ document.body.removeChild(backdrop); });
      var clear = document.createElement('button'); clear.textContent = 'Fjern filter'; clear.addEventListener('click', function(){ jamoviFilter = ''; document.body.removeChild(backdrop); renderDataView(); });
      var ok = document.createElement('button'); ok.className = 'primary'; ok.textContent = T('Bruk');
      ok.addEventListener('click', async function(){
        var expr = document.getElementById('jmvFiltExpr').value.trim();
        var errEl = document.getElementById('jmvFiltErr');
        if (!expr) { jamoviFilter = ''; document.body.removeChild(backdrop); renderDataView(); return; }
        ok.disabled = true;
        try {
          var py = await M.loadPyodideAndM2py();
          py.globals.set('_jf_expr', expr);
          var n = String(await py.runPythonAsync('int(len(e.datasets[e.active_name].query(_jf_expr)))'));
          jamoviFilter = expr;
          errEl.style.color = '#2f7d32'; errEl.textContent = n + ' rader oppfyller filteret.';
          setTimeout(function(){ if (backdrop.parentNode) document.body.removeChild(backdrop); renderDataView(); }, 700);
        } catch(err) { errEl.style.color = '#b91c1c'; errEl.textContent = T('Ugyldig uttrykk: {msg}', { msg: err.message || err }); ok.disabled = false; }
      });
      // prefill
      foot.appendChild(close); foot.appendChild(clear); foot.appendChild(ok); dlg.appendChild(foot);
      backdrop.appendChild(dlg); document.body.appendChild(backdrop);
      var inp = document.getElementById('jmvFiltExpr'); if (inp) inp.value = jamoviFilter;
    }

    // Phase 2: recode (bin) a numeric variable into a new categorical variable.
    async function jamoviRecodeVar(src, name, cuts, labels) {
      var py = await M.loadPyodideAndM2py();
      py.globals.set('_rc_src', src); py.globals.set('_rc_name', name);
      py.globals.set('_rc_cuts', cuts); py.globals.set('_rc_labels', labels);
      await py.runPythonAsync(
        'import pandas as _pd\n' +
        '_df = e.datasets[e.active_name]\n' +
        '_bins = [float(_x) for _x in list(_rc_cuts)]\n' +
        '_labs = [str(_x) for _x in list(_rc_labels)]\n' +
        '_df[_rc_name] = _pd.cut(_df[_rc_src], bins=_bins, labels=_labs, include_lowest=True).astype(object)'
      );
      var infoJson = String(await py.runPythonAsync('import json as _j\n_df = e.datasets[e.active_name]\n_j.dumps({"columns": list(map(str,_df.columns)), "dtypes": {str(c): str(_df[c].dtype) for c in _df.columns}, "nrows": int(len(_df))})'));
      window.lastDatasetInfo = window.lastDatasetInfo || {};
      window.lastDatasetInfo[window.activeDatasetName] = JSON.parse(infoJson);
      renderDataView();
    }
    function jamoviRecodeDialog() {
      if (!window.activeDatasetName) { alert(T('Ingen aktivt datasett.')); return; }
      var vars = jamoviVariables().filter(function(v){ return v.type === 'numeric'; });
      if (!vars.length) { alert(T('Ingen numeriske variabler å omkode.')); return; }
      var backdrop = document.createElement('div'); backdrop.className = 'jmv-dialog-backdrop';
      var dlg = document.createElement('div'); dlg.className = 'jmv-dialog'; dlg.style.maxWidth = '560px';
      dlg.innerHTML = '<div class="jmv-dialog-head">' + T('Omkod variabel (inndeling i grupper)') + '</div>';
      var body = document.createElement('div'); body.className = 'jmv-dialog-body'; body.style.display = 'block';
      body.innerHTML = '<div class="jmv-cv-label">' + T('Kildevariabel') + '</div>'
        + '<select class="jmv-cv-input" id="jmvRcSrc">' + vars.map(function(v){ return '<option>' + M.escapeHtml(v.name) + '</option>'; }).join('') + '</select>'
        + '<div class="jmv-cv-label">' + T('Nytt variabelnavn') + '</div>'
        + '<input class="jmv-cv-input" id="jmvRcName" placeholder="f.eks. gradeGruppe">'
        + '<div class="jmv-cv-label">' + T('Grenser (kommaseparert)') + '</div>'
        + '<input class="jmv-cv-input" id="jmvRcCuts" placeholder="f.eks. 0, 60, 75, 100">'
        + '<div class="jmv-cv-label">' + T('Etiketter (én færre enn grenser)') + '</div>'
        + '<input class="jmv-cv-input" id="jmvRcLabels" placeholder="' + T('f.eks. Lav, Middels, Høy') + '">'
        + '<div id="jmvRcErr" style="color:#b91c1c;margin-top:6px;font-size:12px"></div>';
      dlg.appendChild(body);
      var foot = document.createElement('div'); foot.className = 'jmv-dialog-foot';
      var close = document.createElement('button'); close.textContent = T('Lukk'); close.addEventListener('click', function(){ document.body.removeChild(backdrop); });
      var ok = document.createElement('button'); ok.className = 'primary'; ok.textContent = T('Omkod');
      ok.addEventListener('click', async function(){
        var src = document.getElementById('jmvRcSrc').value;
        var name = document.getElementById('jmvRcName').value.trim();
        var cuts = document.getElementById('jmvRcCuts').value.split(',').map(function(s){ return s.trim(); }).filter(Boolean);
        var labels = document.getElementById('jmvRcLabels').value.split(',').map(function(s){ return s.trim(); }).filter(Boolean);
        var errEl = document.getElementById('jmvRcErr');
        if (!name || cuts.length < 2 || labels.length !== cuts.length - 1) { errEl.textContent = T('Sjekk navn, grenser (minst 2) og etiketter (én færre enn grenser).'); return; }
        ok.disabled = true;
        try { await jamoviRecodeVar(src, name, cuts, labels); document.body.removeChild(backdrop); }
        catch(err){ errEl.textContent = T('Feil: {msg}', { msg: err.message || err }); ok.disabled = false; }
      });
      foot.appendChild(close); foot.appendChild(ok); dlg.appendChild(foot);
      backdrop.appendChild(dlg); document.body.appendChild(backdrop);
    }

    // Active-dataset picker (top menu, right). jamovi works on one dataset at a time;
    // microdata/python/r can create many in e.datasets.
    async function jamoviRefreshDatasetPicker() {
      var sel = document.getElementById('jamoviDatasetSelect');
      if (!sel) return;
      try {
        var py = await M.loadPyodideAndM2py();
        var json = String(await py.runPythonAsync('import json as _j\n_j.dumps({"names": list(map(str, e.datasets.keys())), "active": (str(e.active_name) if e.active_name is not None else "")})'));
        var d = JSON.parse(json);
        sel.innerHTML = '';
        if (!d.names.length) { var o = document.createElement('option'); o.textContent = T('(ingen datasett)'); o.disabled = true; sel.appendChild(o); return; }
        d.names.forEach(function(n){ var op = document.createElement('option'); op.value = n; op.textContent = n; if (n === d.active) op.selected = true; sel.appendChild(op); });
        if (d.active) window.activeDatasetName = d.active;
      } catch (e) { /* engine not ready yet */ }
    }
    async function jamoviSwitchDataset(name) {
      if (!name) return;
      var py = await M.loadPyodideAndM2py();
      py.globals.set('_ds_name', name);
      var infoJson = String(await py.runPythonAsync(
        'e.active_name = _ds_name\n' +
        'try:\n    e.sync_datasets_to_globals(globals())\nexcept Exception:\n    pass\n' +
        'import json as _j\n_df = e.datasets[_ds_name]\n_j.dumps({"columns": list(map(str,_df.columns)), "dtypes": {str(c): str(_df[c].dtype) for c in _df.columns}, "nrows": int(len(_df))})'
      ));
      window.activeDatasetName = name;
      window.lastDatasetInfo = window.lastDatasetInfo || {};
      window.lastDatasetInfo[name] = JSON.parse(infoJson);
      jamoviTypeOverrides = {}; jamoviFilter = '';   // these were per-dataset
      // Fix 2: a live options panel's variable list belongs to the old dataset — invalidate it.
      jmvDialogGen++;
      var _op = document.getElementById('jamoviOptions');
      if (_op) { _op.hidden = true; _op.innerHTML = ''; }
      // refresh the current data/variables view if shown
      var at = (document.querySelector('#jamoviRibbon .jmv-tab.active') || {}).getAttribute && document.querySelector('#jamoviRibbon .jmv-tab.active').getAttribute('data-jtab');
      if (at === 'data') renderDataView();
      else if (at === 'variables') renderVariablesView();
    }

    function jamoviVariables() {
      var name = window.activeDatasetName;
      if (!name || !window.lastDatasetInfo || !window.lastDatasetInfo[name]) return [];
      var info = window.lastDatasetInfo[name];
      var cols = info.columns || [];
      var dtypes = info.dtypes || {};
      return cols.map(function(c) {
        var ov = jamoviTypeOverrides[name + '::' + c];
        if (ov) return { name: c, type: ov };
        var d = dtypes[c] || '';
        var type = (d === 'int64' || d === 'float64') ? 'numeric' : 'nominal';
        return { name: c, type: type };
      });
    }

    // Ensure active dataset is loaded into webR as `data`
    async function ensureJamoviDataInWebR() {
      var shelter = await M.ensureWebRShelter();
      var py = await M.loadPyodideAndM2py();
      // Export the active dataset, replacing codes with value-labels (e.g. 1->Mann) so nominal
      // variables show labels in jamovi output. The engine's label_manager resolves a column's
      // codelist by its alias; we map with string-coerced keys because the series values may be
      // strings ("1") while the codelist keys are ints (1). Columns without a codelist (numeric
      // measures like inntekt) have no codelist and pass through unchanged.
      py.globals.set('_jmv_filter', jamoviFilter || '');
      var b64 = String(await py.runPythonAsync(
        'import base64 as _b, pandas as _pd\n' +
        '_df = e.datasets[e.active_name].copy()\n' +
        'try:\n' +
        '    if _jmv_filter: _df = _df.query(_jmv_filter)\n' +
        'except Exception:\n' +
        '    pass\n' +
        'def _lk(_x, _m):\n' +
        '    if _pd.isna(_x): return _x\n' +
        '    _k = str(_x).strip()\n' +
        '    if isinstance(_x, float) and _x.is_integer(): _k = str(int(_x))\n' +
        '    return _m.get(_k, _x)\n' +
        'for _c in list(_df.columns):\n' +
        '    try:\n' +
        '        _cl = e.label_manager.get_codelist_for_var(_c)\n' +
        '        if _cl:\n' +
        '            _m = {str(_key): _val for _key, _val in _cl.items()}\n' +
        '            _df[_c] = _df[_c].map(lambda _x: _lk(_x, _m))\n' +
        '    except Exception:\n' +
        '        pass\n' +
        '_b.b64encode(_df.to_csv(index=False).encode("utf-8")).decode("ascii")'
      ));
      await M.getWebR().evalRVoid(
        'data <- read.csv(textConnection(rawToChar(base64enc::base64decode("' + b64 + '"))), stringsAsFactors=FALSE, check.names=FALSE)'
      );
    }

    // Append a captured webR plot (ImageBitmap) into the output, jamovi-style.
    function jamoviAppendPlot(title, bitmap, target) {
      var block = document.createElement('div');
      block.className = 'jmv-plot-block';
      if (title) {
        var h = document.createElement('h3');
        h.className = 'jmv-result-title';
        h.textContent = title;
        block.appendChild(h);
      }
      var canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      canvas.className = 'jmv-plot-canvas';
      canvas.getContext('2d').drawImage(bitmap, 0, 0);
      block.appendChild(canvas);
      (target || M.outputArea).appendChild(block);
    }

    // The stacked-results container (jamovi keeps every analysis until removed).
    // Created lazily; the first jamovi result clears any prior (non-jamovi) output.
    function jamoviResultsContainer() {
      var c = M.outputArea.querySelector('#jamoviResults');
      if (!c) {
        M.outputArea.innerHTML = '';
        var ws = document.createElement('div'); ws.id = 'jamoviWorkspace';
        var op = document.createElement('div'); op.id = 'jamoviOptions'; op.hidden = true;
        var pane = document.createElement('div'); pane.id = 'jamoviResultsPane';
        c = document.createElement('div'); c.id = 'jamoviResults';
        pane.appendChild(c); ws.appendChild(op); ws.appendChild(pane);
        M.outputArea.appendChild(ws);
      }
      return c;
    }

    // A result card with only a title (for plot-only analyses); plots append into it.
    function jamoviTitleCard(title) {
      var card = document.createElement('div'); card.className = 'jmv-result-card';
      var rm = document.createElement('button'); rm.className = 'jmv-card-remove'; rm.title = T('Fjern'); rm.textContent = '✕';
      rm.addEventListener('click', function() {
        card.remove();
        // Fix 3: this card's analysis dialog (if still open) must stop live-updating a
        // now-detached card. All jamovi-mode cards are analysis cards, so always invalidate
        // here (jamoviSingletonCard — Data/Variabler — must NOT get this behavior).
        jmvDialogGen++;
        var _op = document.getElementById('jamoviOptions');
        if (_op) { _op.hidden = true; _op.innerHTML = ''; }
      });
      card.appendChild(rm);
      var wrap = document.createElement('div'); wrap.style.cssText = 'padding:12px 18px;';
      var h = document.createElement('h3'); h.className = 'jmv-result-title'; h.textContent = title; wrap.appendChild(h);
      card.appendChild(wrap);
      jamoviResultsContainer().appendChild(card);
      card.scrollIntoView({ block: 'nearest' });
      return card;
    }

    // A pinned/refreshable card (Variables, Data) at the top of the results stack.
    function jamoviSingletonCard(id, title) {
      var container = jamoviResultsContainer();
      var old = document.getElementById(id);
      if (old) old.remove();
      var card = document.createElement('div'); card.className = 'jmv-result-card'; card.id = id;
      var rm = document.createElement('button'); rm.className = 'jmv-card-remove'; rm.title = T('Lukk'); rm.textContent = '✕';
      rm.addEventListener('click', function() { card.remove(); });
      card.appendChild(rm);
      var wrap = document.createElement('div'); wrap.style.cssText = 'padding:12px 18px;';
      var h = document.createElement('h3'); h.className = 'jmv-result-title'; h.textContent = title; wrap.appendChild(h);
      card.appendChild(wrap);
      container.insertBefore(card, container.firstChild);
      card.scrollIntoView({ block: 'nearest' });
      return wrap;
    }

    // Variables tab: measure-type list for the active dataset (retype numeric<->nominal).
    function renderVariablesView() {
      var wrap = jamoviSingletonCard('jamoviVarCard', 'Variabler');
      var vars = jamoviVariables();
      if (!vars.length) {
        var p = document.createElement('p'); p.style.cssText = 'color:#6b7280;';
        p.textContent = T('Ingen aktivt datasett. Kjør et skript for å lage data.'); wrap.appendChild(p); return;
      }
      var name = window.activeDatasetName;
      var table = document.createElement('table'); table.className = 'jmv-result-table';
      table.innerHTML = '<thead><tr><th>' + T('Variabel') + '</th><th>' + T('Måltype') + '</th></tr></thead>';
      var tb = document.createElement('tbody');
      vars.forEach(function(v) {
        var tr = document.createElement('tr');
        var td1 = document.createElement('td'); td1.textContent = v.name; tr.appendChild(td1);
        var td2 = document.createElement('td');
        var btn = document.createElement('button'); btn.type = 'button'; btn.className = 'jmv-measure-btn';
        btn.innerHTML = jamoviTypeIcon(v.type) + '<span>' + (v.type === 'numeric' ? 'Kontinuerlig' : 'Nominal') + '</span>';
        btn.title = T('Klikk for å bytte måltype');
        btn.addEventListener('click', function() {
          jamoviTypeOverrides[name + '::' + v.name] = (v.type === 'numeric') ? 'nominal' : 'numeric';
          renderVariablesView();
        });
        td2.appendChild(btn); tr.appendChild(td2); tb.appendChild(tr);
      });
      table.appendChild(tb); wrap.appendChild(table);
      var note = document.createElement('div'); note.className = 'jmv-result-note';
      note.innerHTML = '<i>Note.</i> ' + T('Måltypen styrer hvilke roller variabelen kan fylle i analysene.');
      wrap.appendChild(note);
    }

    // Data tab: read-only preview of the active dataset (first rows, from the engine).
    async function renderDataView(focusRowId) {
      var wrap = jamoviSingletonCard('jamoviDataCard', 'Data');
      jamoviDataTable = null;
      if (!window.activeDatasetName) {
        var p = document.createElement('p'); p.style.cssText = 'color:#6b7280;'; p.textContent = T('Ingen aktivt datasett.'); wrap.appendChild(p); return;
      }
      if (typeof Tabulator === 'undefined') {
        var pe = document.createElement('p'); pe.style.cssText = 'color:#b91c1c;'; pe.textContent = T('Tabulator-biblioteket er ikke lastet.'); wrap.appendChild(pe); return;
      }
      var loading = document.createElement('p'); loading.style.cssText = 'color:#6b7280;'; loading.textContent = T('Laster data…'); wrap.appendChild(loading);
      try {
        var py = await M.loadPyodideAndM2py();
        // Fetch up to 2000 rows with a stable __rowid__ (the DataFrame index) for write-back.
        // Coded columns (with a codelist) are shown as labels and left read-only.
        var json = String(await py.runPythonAsync(
          'import json as _j, pandas as _pd\n' +
          '_df = e.datasets[e.active_name]\n' +
          '_h = _df.head(2000).copy()\n' +
          '_labeled = []\n' +
          'def _lk(_x, _m):\n' +
          '    if _pd.isna(_x): return None\n' +
          '    _k = str(int(_x)) if isinstance(_x, float) and _x.is_integer() else str(_x).strip()\n' +
          '    return _m.get(_k, _x)\n' +
          'for _c in list(_h.columns):\n' +
          '    try:\n' +
          '        _cl = e.label_manager.get_codelist_for_var(_c)\n' +
          '        if _cl:\n' +
          '            _m = {str(_key): _val for _key, _val in _cl.items()}\n' +
          '            _h[_c] = _h[_c].map(lambda _x: _lk(_x, _m)); _labeled.append(str(_c))\n' +
          '    except Exception:\n' +
          '        pass\n' +
          '_h2 = _h.astype(object).where(_h.notna(), None)\n' +
          '_recs = _h2.to_dict(orient="records")\n' +
          '_ids = list(_h.index)\n' +
          'for _k in range(len(_recs)):\n' +
          '    _recs[_k] = {str(_kk): _vv for _kk, _vv in _recs[_k].items()}\n' +
          '    _recs[_k]["__rowid__"] = (int(_ids[_k]) if isinstance(_ids[_k], (int,)) else _ids[_k])\n' +
          '_j.dumps({"cols": list(map(str,_df.columns)), "dtypes": {str(c): str(_df[c].dtype) for c in _df.columns}, "labeled": _labeled, "n": int(len(_df)), "shown": int(len(_h)), "recs": _recs})'
        ));
        var d = JSON.parse(json);
        loading.remove();
        var info = document.createElement('div'); info.className = 'jmv-result-note';
        info.innerHTML = '<i>Note.</i> ' + T('{n} rader', { n: d.n.toLocaleString(window.M2PY_LANG === 'en' ? 'en' : 'no') }) + (d.shown < d.n ? T(' (viser de første {n})', { n: d.shown }) : '') + T('. Klikk en celle for å redigere — endringer lagres i økten, men nullstilles hvis du kjører et skript på nytt.')
          + (jamoviFilter ? ' <b style="color:var(--jmv-blue-d)">· Filter aktivt: ' + M.escapeHtml(jamoviFilter) + ' (analysene bruker bare rader som oppfyller dette)</b>' : '');
        wrap.appendChild(info);
        var gridDiv = document.createElement('div'); gridDiv.className = 'jmv-data-grid'; wrap.appendChild(gridDiv);
        var columns = [{ title: '#', field: '__rowid__', width: 56, headerSort: false, editor: false, cssClass: 'jmv-rowid-col' }];
        d.cols.forEach(function(c) {
          var dt = d.dtypes[c] || '';
          var isNum = /^(int|float|uint)/i.test(dt);
          var isLabeled = d.labeled.indexOf(c) !== -1;
          columns.push({
            title: c, field: c, headerSort: true, headerFilter: 'input',
            hozAlign: isNum ? 'right' : 'left',
            editor: isLabeled ? false : (isNum ? 'number' : 'input'),
            formatter: function(cell) { var v = cell.getValue(); return (v === null || v === undefined || v === '') ? '<span style="opacity:.35">·</span>' : M.escapeHtml(String(v)); }
          });
        });
        jamoviDataTable = new Tabulator(gridDiv, {
          data: d.recs, columns: columns, index: '__rowid__',
          layout: 'fitDataStretch', height: '440px',
          pagination: 'local', paginationSize: 100, paginationSizeSelector: [50, 100, 250, 500],
          movableColumns: true, selectableRows: 1, placeholder: '(ingen data)'
        });
        jamoviDataTable.on('cellEdited', function(cell) { jamoviWriteBack(cell); });
        if (focusRowId !== undefined && focusRowId !== null) {
          jamoviDataTable.on('tableBuilt', function() {
            try {
              jamoviDataTable.setPageToRow(focusRowId).then(function() {
                jamoviDataTable.scrollToRow(focusRowId, 'center', false);
                jamoviDataTable.selectRow(focusRowId);
              }).catch(function(){});
            } catch (e) { /* row may be beyond the display cap */ }
          });
        }
      } catch (e) { if (loading.parentNode) loading.textContent = T('Kunne ikke laste data: {msg}', { msg: e.message || e }); }
    }

    // Bundled example datasets from "Learning Statistics with jamovi" (examples/lsj/).
    var JAMOVI_EXAMPLES = [
      { file:'harpo.csv',         name:'harpo',         desc:'Grades by tutor — independent t-test' },
      { file:'chico.csv',         name:'chico',         desc:'Test 1 vs Test 2 — paired t-test' },
      { file:'zeppo.csv',         name:'zeppo',         desc:'Grades — one-sample t-test' },
      { file:'clinicaltrial.csv', name:'clinicaltrial', desc:'Mood gain by drug — one-way ANOVA' },
      { file:'parenthood.csv',    name:'parenthood',    desc:'Sleep & grumpiness — correlation / regression' },
      { file:'cards.csv',         name:'cards',         desc:'Card choices — χ² goodness of fit' },
      { file:'agpp.csv',          name:'agpp',          desc:'Game & gender — χ² test of independence' },
      { file:'anscombe.csv',      name:'anscombe',      desc:"Anscombe's quartet" },
      { file:'booksales.csv',     name:'booksales',     desc:'Book sales — regression' },
      { file:'broca.csv',         name:'broca',         desc:'Aphasia groups' },
      { file:'nightgarden.csv',   name:'nightgarden',   desc:'In the Night Garden' },
      { file:'rtfm.csv',          name:'rtfm',          desc:'Reading the manual' }
    ];

    async function jamoviLoadExample(ex) {
      M.setStatus(M.rightStatus, 'Laster ' + ex.name + '…');
      try {
        var py = await M.loadPyodideAndM2py();
        var resp = await fetch('examples/lsj/' + ex.file);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var csv = await resp.text();
        var infoJson = String(await py.runPythonAsync(
          'import pandas as _pd, io as _io, json as _j\n' +
          '_df = _pd.read_csv(_io.StringIO(' + JSON.stringify(csv) + '))\n' +
          'e.datasets[' + JSON.stringify(ex.name) + '] = _df\n' +
          'e.active_name = ' + JSON.stringify(ex.name) + '\n' +
          'try:\n    e.sync_datasets_to_globals(globals())\nexcept Exception:\n    pass\n' +
          '_j.dumps({"columns": list(map(str,_df.columns)), "dtypes": {str(c): str(_df[c].dtype) for c in _df.columns}, "nrows": int(len(_df))})'
        ));
        var info = JSON.parse(infoJson);
        window.activeDatasetName = ex.name;
        window.lastDatasetInfo = window.lastDatasetInfo || {};
        window.lastDatasetInfo[ex.name] = info;
        jamoviTypeOverrides = {}; jamoviFilter = '';
        // Fix 2: same as jamoviSwitchDataset — a live options panel's variable list belongs to
        // the previous dataset.
        jmvDialogGen++;
        var _op = document.getElementById('jamoviOptions');
        if (_op) { _op.hidden = true; _op.innerHTML = ''; }
        M.setStatus(M.rightStatus, '');
        jamoviRefreshDatasetPicker();
        renderDataView();
      } catch (e) {
        M.setStatus(M.rightStatus, '');
        alert(T('Kunne ikke laste datasett: {msg}', { msg: e.message || e }));
      }
    }

    function openJamoviExamplePicker() {
      var backdrop = document.createElement('div'); backdrop.className = 'jmv-dialog-backdrop';
      var dlg = document.createElement('div'); dlg.className = 'jmv-dialog'; dlg.style.maxWidth = '540px';
      var head = document.createElement('div'); head.className = 'jmv-dialog-head'; head.textContent = T('Eksempeldatasett — Learning Statistics with jamovi'); dlg.appendChild(head);
      var body = document.createElement('div'); body.className = 'jmv-dialog-body'; body.style.display = 'block';
      var ul = document.createElement('ul'); ul.className = 'jmv-example-list';
      JAMOVI_EXAMPLES.forEach(function(ex) {
        var li = document.createElement('li');
        li.innerHTML = '<b>' + ex.name + '</b><span>' + ex.desc + '</span>';
        li.addEventListener('click', function() { document.body.removeChild(backdrop); jamoviLoadExample(ex); });
        ul.appendChild(li);
      });
      body.appendChild(ul); dlg.appendChild(body);
      var foot = document.createElement('div'); foot.className = 'jmv-dialog-foot';
      var close = document.createElement('button'); close.textContent = T('Lukk'); close.addEventListener('click', function() { document.body.removeChild(backdrop); });
      foot.appendChild(close); dlg.appendChild(foot);
      backdrop.appendChild(dlg); document.body.appendChild(backdrop);
    }

    // Jamovi measure-type icons
    function jamoviTypeIcon(type) {
      if (type === 'numeric') // continuous: jamovi's gold ruler
        return '<svg class="jmv-type-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="1.5" y="5.5" width="13" height="5" rx="0.5" fill="#f1bf63" stroke="#cd8500" stroke-width="1"/><path d="M4 5.5v2M6.5 5.5v3M9 5.5v2M11.5 5.5v3" stroke="#cd8500" stroke-width="0.9"/></svg>';
      // nominal: jamovi's three balls (two blue + one gold)
      return '<svg class="jmv-type-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="5.5" cy="6.7" r="3.1" fill="#a9c6f2" stroke="#226ddd" stroke-width="1"/><circle cx="10.5" cy="6.7" r="3.1" fill="#6b9de8" stroke="#226ddd" stroke-width="1"/><circle cx="8" cy="10.6" r="3.1" fill="#f1bf63" stroke="#bf7c00" stroke-width="1"/></svg>';
    }

    // Jamovi ribbon CATEGORY icons (16×16 line SVGs, stroke currentColor ~1.5)
    var JAMOVI_CAT_ICONS = {
      exploration: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="9" width="3" height="5" rx=".5"/><rect x="5.5" y="6" width="3" height="8" rx=".5"/><rect x="10" y="3" width="3" height="11" rx=".5"/><circle cx="12.5" cy="2" r="2" stroke-width="1.4"/><path d="M14.5 4l1.5 1.5" stroke-linecap="round"/></svg>',
      ttests: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 2h6M6 2v12" stroke-linecap="round"/><path d="M10 4h4M12 4v8" stroke-linecap="round"/></svg>',
      anova: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="6" width="3" height="8" rx=".5"/><rect x="6.5" y="2" width="3" height="12" rx=".5"/><rect x="11.5" y="8" width="3" height="6" rx=".5"/></svg>',
      regression: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="3.5" cy="11.5" r="1.2" fill="currentColor" stroke="none"/><circle cx="6.5" cy="8.5" r="1.2" fill="currentColor" stroke="none"/><circle cx="9.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/><circle cx="12.5" cy="4.5" r="1.2" fill="currentColor" stroke="none"/><path d="M2 13l12-10" stroke-linecap="round"/></svg>',
      frequencies: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="1.5" width="5.5" height="5.5" rx=".5"/><rect x="9" y="1.5" width="5.5" height="5.5" rx=".5"/><rect x="1.5" y="9" width="5.5" height="5.5" rx=".5"/><rect x="9" y="9" width="5.5" height="5.5" rx=".5"/></svg>'
    };

    // Jamovi ANALYSIS icons (16×16 line SVGs), keyed by jmv spec name.
    // Copied (not referenced) from the frozen js/modes/jamovi_v1.js JAMOVI_ICONS set.
    var JMV_AN_ICONS = {
      descriptives: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="9" width="3" height="5" rx=".5"/><rect x="6.5" y="6" width="3" height="8" rx=".5"/><rect x="11" y="3" width="3" height="11" rx=".5"/></svg>',
      ttestIS: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><path d="M2 3h6M5 3v10M10 5h4M12 5v6" stroke-linecap="round"/></svg>',
      ttestPS: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><path d="M2 3h6M5 3v10M10 5h4M12 5v6" stroke-linecap="round"/><path d="M9 13.5c.8 0 1.4-.3 1.4-.3" stroke-linecap="round"/></svg>',
      ttestOneS: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><path d="M2 3h6M5 3v10" stroke-linecap="round"/><circle cx="12" cy="8" r="3" stroke-width="1.3"/></svg>',
      anovaOneW: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="7" width="3" height="7" rx=".5"/><rect x="6.5" y="4" width="3" height="10" rx=".5"/><rect x="11" y="9" width="3" height="5" rx=".5"/></svg>',
      anova: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="7" width="3" height="7" rx=".5"/><rect x="6.5" y="4" width="3" height="10" rx=".5"/><rect x="11" y="9" width="3" height="5" rx=".5"/></svg>',
      anovaNP: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="7" width="3" height="7" rx=".5"/><rect x="6.5" y="4" width="3" height="10" rx=".5"/><rect x="11" y="9" width="3" height="5" rx=".5"/><path d="M2 6.5h3M6.5 3.5h3M11 8.5h3" stroke-linecap="round"/></svg>',
      corrMatrix: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><circle cx="4" cy="11" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="7" cy="7" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="10" cy="5" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="13" cy="3" r="1.2" fill="#2b3a55" stroke="none"/><path d="M3 12.5l10-10" stroke-linecap="round"/></svg>',
      linReg: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><circle cx="4" cy="10" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="7" cy="8" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="10" cy="6" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="13" cy="4" r="1.2" fill="#2b3a55" stroke="none"/><path d="M2.5 11.5l11-9" stroke-linecap="round"/></svg>',
      logRegBin: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><path d="M2 13c1-1 1.5-4 3-5.5S8.5 5 10 4s2.5-1.5 4-1" stroke-linecap="round"/></svg>',
      propTestN: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="2" width="12" height="12" rx=".5"/><path d="M8 2v12M2 8h12"/><path d="M5 5l2 2M11 5l-2 2" stroke-linecap="round"/></svg>',
      contTables: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="2" width="12" height="12" rx=".5"/><path d="M8 2v12M2 8h12"/></svg>',
      scat: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><circle cx="4" cy="11" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="7" cy="7" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="10" cy="5" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="13" cy="3" r="1.2" fill="#2b3a55" stroke="none"/><path d="M3 12.5l10-10" stroke-linecap="round"/></svg>'
    };
    JMV_AN_ICONS._default = JMV_AN_ICONS.descriptives;

    // ── jamovi 2.0-motor: ekte jmv/scatr i webR ─────────────────────────────
    var jmvReady = false, jmvLoadingP = null;
    async function ensureJmvLoaded() {
      if (jmvReady) return;
      if (!jmvLoadingP) {
        jmvLoadingP = (async function () {
          M.setStatus(M.rightStatus, T('Laster jamovi-motoren … (~170 MB første gang, sekunder senere)'));
          await M.ensureWebRShelter();
          var webr = M.getWebR();
          await webr.evalRVoid("webr::install(c('jmv','scatr','jsonlite'))");
          await webr.evalRVoid('suppressMessages({library(jmv); library(scatr); library(jsonlite)})');
          var helpers = await fetch('js/modes/jmv_helpers.R').then(function (r) {
            if (!r.ok) throw new Error('jmv_helpers.R: HTTP ' + r.status);
            return r.text();
          });
          await webr.evalRVoid(helpers);
          // Task 2b: fabricate a websocket stub package so jmv analyses that expect a
          // live jamovi server (e.g. jmv::contTables) don't error inside webR.
          await webr.evalRVoid('.jmv_install_stubs()');
          jmvReady = true;
          M.setStatus(M.rightStatus, '');
        })();
        jmvLoadingP.catch(function () { jmvLoadingP = null; M.setStatus(M.rightStatus, ''); });
      }
      return jmvLoadingP;
    }

    function rQuote(s) { return "'" + String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'"; }

    // Dialogtilstand -> R-kall. Opsjoner med default-verdi utelates (ren syntaks).
    function buildJmvCall(spec, values) {
      var args = ['data = data'];
      spec.options.forEach(function (o) {
        var v = values[o.name];
        if (v === undefined || v === null) return;
        if (o.type === 'Variables') {
          if (v.length) args.push(o.name + ' = c(' + v.map(rQuote).join(', ') + ')');
          return;
        }
        if (o.type === 'Variable') {
          if (v.length) args.push(o.name + ' = ' + rQuote(v[0]));
          return;
        }
        if (o.type === 'Pairs') {
          if (v.length >= 2) args.push(o.name + ' = list(list(i1 = ' + rQuote(v[0]) + ', i2 = ' + rQuote(v[1]) + '))');
          return;
        }
        if (JSON.stringify(v) === JSON.stringify(o.default)) return;
        if (o.type === 'Bool') { args.push(o.name + ' = ' + (v ? 'TRUE' : 'FALSE')); return; }
        if (o.type === 'Number' || o.type === 'Integer') {
          if (isFinite(Number(v))) args.push(o.name + ' = ' + Number(v));
          return;
        }
        args.push(o.name + ' = ' + rQuote(v)); // List, String, Level
      });
      // Fix 1: jmv's `blocks` option (type Array, default [[]]) has no dialog control — the
      // generic loop above always skips it (values.blocks never leaves its default). jmv's R
      // code renders empty (dot-filled) tables when length(blocks[[1]]) == 0, so linReg/
      // logRegBin need a synthesized single block with every assigned covariate/factor.
      // (anova's modelTerms is NOT special-cased: jmv falls back to full factorial there.)
      if (spec.options.some(function (o) { return o.name === 'blocks'; })) {
        var blockVars = (values.covs || []).concat(values.factors || []);
        if (blockVars.length) {
          args.push('blocks = list(list(' + blockVars.map(rQuote).join(', ') + '))');
        }
      }
      return spec.ns + '::' + spec.name + '(' + args.join(', ') + ')';
    }

    async function runJmvAnalysis(spec, values, cardWrap, shouldRender) {
      await ensureJmvLoaded();
      await ensureJamoviDataInWebR();
      // Nominale mål-overstyringer fra Variabler-fanen -> factor() i en lokal kopi
      var factorLines = jamoviVariables()
        .filter(function (v) { return v.type === 'nominal'; })
        .map(function (v) { return 'data[[' + rQuote(v.name) + ']] <- factor(data[[' + rQuote(v.name) + ']])'; })
        .join('\n');
      var call = buildJmvCall(spec, values);
      var rCode = 'local({\n' + factorLines + '\n.r <- ' + call +
        '\nprint(.r)\ncat("\\n##JMV##")\ncat(jsonlite::toJSON(.jmv_serialize(.r), auto_unbox = TRUE, na = "null"))\n})';
      var shelter = await M.ensureWebRShelter();
      var cap = await shelter.captureR(rCode, { captureGraphics: { width: 560, height: 400 } });
      try {
        var text = cap.output.filter(function (m) { return m.type === 'stdout'; })
          .map(function (m) { return m.data; }).join('\n');
        var idx = text.lastIndexOf('##JMV##');
        if (idx === -1) throw new Error(T('Fikk ikke resultat fra jmv'));
        if (shouldRender && !shouldRender()) return;
        renderJmvResults(cardWrap, JSON.parse(text.slice(idx + 7)), cap.images || [], call);
      } finally { if (cap.cleanup) await cap.cleanup(); }
    }

    // JSON-payload + bildekø -> DOM med eksisterende jamovi-CSS
    function renderJmvResults(cardWrap, payload, images, callString) {
      cardWrap.innerHTML = '';
      var imgQueue = images.slice();
      function fmtCell(v, fmt) {
        if (v === null || v === undefined) return '';
        if (typeof v !== 'number') return String(v);
        if (/pvalue/.test(fmt)) return v < 0.001 ? '< .001' : v.toFixed(3).replace(/^(-?)0\./, '$1.');
        if (Number.isInteger(v)) return String(v);
        var a = Math.abs(v);
        if (a >= 1e9 || (a > 0 && a < 1e-4)) return v.toExponential(2);
        if (a >= 1000) return v.toFixed(0);
        return v.toFixed(a >= 1 ? 2 : 3);
      }
      function walk(node, depth) {
        if (!node) return;
        if (node.type === 'group') {
          if (node.title && depth > 0) {
            var gh = document.createElement('h3'); gh.className = 'jmv-result-title';
            gh.style.fontWeight = '600'; gh.textContent = node.title; cardWrap.appendChild(gh);
          }
          (node.items || []).forEach(function (k) { walk(k, depth + 1); });
          return;
        }
        if (node.type === 'image') {
          var bmp = imgQueue.shift();
          if (bmp) jamoviAppendPlot(node.title || '', bmp, cardWrap);
          return;
        }
        if (node.type === 'text') {
          var pre = document.createElement('pre');
          pre.style.cssText = 'font-size:12px;white-space:pre-wrap;';
          pre.textContent = node.text || ''; cardWrap.appendChild(pre);
          return;
        }
        if (node.type !== 'table') return;
        var h = document.createElement('h3'); h.className = 'jmv-result-title';
        h.textContent = node.title || ''; cardWrap.appendChild(h);
        var cols = (node.columns && node.columns.length) ? node.columns
          : (node.colNames || []).map(function (n) { return { name: n, title: n, superTitle: '', format: '' }; });
        var table = document.createElement('table'); table.className = 'jmv-result-table';
        var thead = document.createElement('thead');
        var hasSuper = cols.some(function (c) { return c.superTitle; });
        if (hasSuper) {
          var trs = document.createElement('tr');
          for (var i = 0; i < cols.length;) {
            var stt = cols[i].superTitle, span = 1;
            while (i + span < cols.length && cols[i + span].superTitle === stt) span++;
            var th0 = document.createElement('th'); th0.colSpan = span; th0.textContent = stt || '';
            if (stt) th0.style.borderBottom = '1px solid #999';
            trs.appendChild(th0); i += span;
          }
          thead.appendChild(trs);
        }
        var trh = document.createElement('tr');
        cols.forEach(function (c) {
          var th = document.createElement('th'); th.textContent = c.title || c.name; trh.appendChild(th);
        });
        thead.appendChild(trh); table.appendChild(thead);
        var tb = document.createElement('tbody');
        var nameToIdx = {}; (node.colNames || []).forEach(function (n, i) { nameToIdx[n] = i; });
        (node.rows || []).forEach(function (row) {
          var tr = document.createElement('tr');
          cols.forEach(function (c) {
            var td = document.createElement('td');
            var ri = (c.name in nameToIdx) ? nameToIdx[c.name] : -1;
            td.textContent = ri === -1 ? '' : fmtCell(row[ri], c.format || '');
            tr.appendChild(td);
          });
          tb.appendChild(tr);
        });
        table.appendChild(tb); cardWrap.appendChild(table);
        (node.notes || []).forEach(function (n) {
          var note = document.createElement('div'); note.className = 'jmv-result-note';
          note.innerHTML = '<i>Note.</i> ' + M.escapeHtml(String(n)); cardWrap.appendChild(note);
        });
      }
      walk(payload, 0);
      if (callString) {
        var syn = document.createElement('pre');
        syn.className = 'jmv-syntax'; syn.textContent = callString;
        cardWrap.appendChild(syn);
      }
    }

    // fase 3: Tegner spec.layout (u.yaml-avledet) inn i body. Kontroll-tilstand leses/skrives
    // i values; hver endring kaller onChange() (=> scheduleRun). Deaktivering:
    //  - barn av en check disables når checken er false
    //  - noder med {enable:'navn'} disables når values[navn] er falsy
    // Task 2-tillegg (fra Task 1s review): (1) tomme grid-celler (children:[]) tegnes ikke, og
    // en grid uten noen ikke-tomme celler droppes helt (logRegBin (1,0), scat sin eneste grid).
    // (2) suppliers med targets:[] (nøstet emMeansSupplier i anova/linReg/logRegBin) hopper over
    // roleBoxBuilder helt; kun FØRSTE ikke-tomme supplier sin variabelliste tegnes (roleBoxBuilder
    // avgjør dette selv, ikke denne funksjonen — se openJmvAnalysis).
    function renderJmvLayout(root, ctx) {
      var body = ctx.body, values = ctx.values, onChange = ctx.onChange;
      // flat registry: samme DOM-element kan registreres under FLERE navn (f.eks. en
      // ciWidth-rad som både ligger i 'ci'-subWrap og har sin egen node.enable-ref til
      // 'meanDiff'); elementet skal disables hvis NOEN av dets navn er falsy (ELLER-logikk
      // over "av"-tilstandene — tilsvarer AND-semantikken i u.yaml sin enable: (a && b)).
      var enableRegs = [];
      function dep(name, el) { enableRegs.push({ name: name, el: el }); }
      function refreshDisabled() {
        var disabledFor = new Map(); // registrert element -> disabled (ELLER over dets navn)
        enableRegs.forEach(function (r) {
          var off = !values[r.name];
          disabledFor.set(r.el, (disabledFor.get(r.el) || false) || off);
        });
        disabledFor.forEach(function (off, el) { el.classList.toggle('jmv-disabled', off); });
        // Inputs/selects kan ligge under FLERE registrerte elementer på ulikt nivå (f.eks.
        // ciWidth-inputen ligger inni ci-subWrap OG, via DOM-nesting, inni meanDiff-subWrap).
        // querySelectorAll fra hvert registrert element treffer da samme input flere ganger —
        // en "av"-container (disabled) må ALDRI overstyres tilbake til enabled av en ytre "på"-
        // container. Derfor: samle input-sett per (disabled=true)-container først, og la det
        // vinne uansett iterasjonsrekkefølge.
        var disabledInputs = new Set();
        disabledFor.forEach(function (off, el) {
          if (off) el.querySelectorAll('input,select').forEach(function (i) { disabledInputs.add(i); });
        });
        disabledFor.forEach(function (off, el) {
          el.querySelectorAll('input,select').forEach(function (i) { i.disabled = disabledInputs.has(i); });
        });
      }
      function optByName(n) { return ctx.spec.options.filter(function (o) { return o.name === n; })[0]; }
      function draw(node, parent) {
        if (!node) return;
        if (node.t === 'supplier') {
          if (!node.targets || !node.targets.length) return; // tillegg 2: emMeansSupplier uten mål
          ctx.roleBoxBuilder(node.targets, parent); return;
        }
        if (node.t === 'grid') {
          // tillegg 1: hopp over tomme celler; dropp hele griden hvis <1 celle blir igjen
          var nonEmptyCells = (node.cells || []).filter(function (c) { return (c.children || []).length > 0; });
          if (nonEmptyCells.length < 1) return;
          var g = document.createElement('div'); g.className = 'jmv-grid';
          // tillegg 3: reindekser kolonner etter filtrering, ellers står gjenlevende celler
          // igjen med sin opprinnelige col (f.eks. col:1) og gir en blank ledende kolonne.
          var distinctCols = nonEmptyCells.map(function (c) { return c.col; })
            .filter(function (v, i, a) { return a.indexOf(v) === i; })
            .sort(function (a, b) { return a - b; });
          var colRank = {};
          distinctCols.forEach(function (col, i) { colRank[col] = i; });
          g.style.setProperty('--jmv-grid-cols', String(distinctCols.length));
          nonEmptyCells.forEach(function (cell) {
            var cd = document.createElement('div');
            cd.style.gridColumn = String(colRank[cell.col] + 1); cd.style.gridRow = String(cell.row + 1);
            (cell.children || []).forEach(function (k) { draw(k, cd); });
            g.appendChild(cd);
          });
          parent.appendChild(g); return;
        }
        if (node.t === 'label') {
          var grp = document.createElement('div'); grp.className = 'jmv-optgroup';
          var lb = document.createElement('div'); lb.className = 'jmv-optgroup-label';
          lb.textContent = node.label; grp.appendChild(lb);
          (node.children || []).forEach(function (k) { draw(k, grp); });
          if (node.enable) dep(node.enable, grp);
          parent.appendChild(grp); return;
        }
        if (node.t === 'collapse') {
          var sec = document.createElement('div'); sec.className = 'jmv-section' + (node.collapsed ? ' collapsed' : '');
          var hdr = document.createElement('div'); hdr.className = 'jmv-section-hdr';
          hdr.innerHTML = '<span class="jmv-section-caret">▾</span><span class="jmv-section-title">' + M.escapeHtml(node.label) + '</span>';
          hdr.addEventListener('click', function () { sec.classList.toggle('collapsed'); });
          var sb = document.createElement('div'); sb.className = 'jmv-section-body';
          (node.children || []).forEach(function (k) { draw(k, sb); });
          sec.appendChild(hdr); sec.appendChild(sb); parent.appendChild(sec); return;
        }
        if (node.t === 'check') {
          var o = optByName(node.name); if (!o) return;
          var row = document.createElement('label'); row.className = 'jmv-opt-row';
          var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!values[node.name];
          row.appendChild(cb); row.appendChild(document.createTextNode(node.label || o.title));
          parent.appendChild(row);
          var subWrap = null;
          if (node.children && node.children.length) {
            subWrap = document.createElement('div'); subWrap.className = 'jmv-suboptions';
            node.children.forEach(function (k) { draw(k, subWrap); });
            parent.appendChild(subWrap);
            dep(node.name, subWrap);
          }
          cb.addEventListener('change', function () { values[node.name] = cb.checked; refreshDisabled(); onChange(); });
          if (node.enable) { dep(node.enable, row); if (subWrap) dep(node.enable, subWrap); }
          return;
        }
        if (node.t === 'radio') {
          var row2 = document.createElement('label'); row2.className = 'jmv-opt-row';
          var rb = document.createElement('input'); rb.type = 'radio';
          rb.name = 'jmvopt_' + ctx.uid + '_' + node.option;
          rb.checked = (values[node.option] === node.part);
          rb.addEventListener('change', function () { if (rb.checked) { values[node.option] = node.part; refreshDisabled(); onChange(); } });
          row2.appendChild(rb); row2.appendChild(document.createTextNode(node.label));
          if (node.enable) dep(node.enable, row2);
          parent.appendChild(row2); return;
        }
        if (node.t === 'combo') {
          var oc = optByName(node.name); if (!oc) return;
          var rowc = document.createElement('label'); rowc.className = 'jmv-opt-row';
          if (node.label || oc.title) rowc.appendChild(document.createTextNode((node.label || oc.title) + ' '));
          var sel = document.createElement('select'); sel.className = 'jmv-opt-select';
          (oc.choices || []).forEach(function (c) {
            var op = document.createElement('option'); op.value = c.value; op.textContent = c.title;
            if (c.value === values[node.name]) op.selected = true; sel.appendChild(op);
          });
          sel.addEventListener('change', function () { values[node.name] = sel.value; refreshDisabled(); onChange(); });
          rowc.appendChild(sel); if (node.enable) dep(node.enable, rowc);
          parent.appendChild(rowc); return;
        }
        if (node.t === 'text') {
          var ot = optByName(node.name); if (!ot) return;
          var rowt = document.createElement('label'); rowt.className = 'jmv-opt-row';
          rowt.appendChild(document.createTextNode((node.label || ot.title) + ' '));
          var inp = document.createElement('input');
          var numeric = (node.format === 'number' || ot.type === 'Number' || ot.type === 'Integer');
          inp.type = numeric ? 'number' : 'text';
          inp.className = numeric ? 'jmv-opt-num' : 'jmv-opt-txt';
          inp.value = (values[node.name] === null || values[node.name] === undefined) ? '' : values[node.name];
          if (ot.min !== undefined) inp.min = ot.min;
          if (ot.max !== undefined) inp.max = ot.max;
          inp.addEventListener('change', function () {
            values[node.name] = (inp.value === '') ? ot.default
              : (numeric ? Number(inp.value) : inp.value);
            refreshDisabled(); onChange();
          });
          rowt.appendChild(inp); if (node.enable) dep(node.enable, rowt);
          parent.appendChild(rowt); return;
        }
      }
      (root.children || []).forEach(function (k) { draw(k, body); });
      refreshDisabled();
    }

    // Åpne en jamovi 2.0-analyse: dialog generert fra spec'en, dokket til venstre for
    // resultatene, med live-kjøring (debounce) hver gang en rolle/opsjon endres.
    function openJmvAnalysis(name, presets) {
      var myGen = ++jmvDialogGen; // Fix B: identifies this dialog's live-update loop
      var spec = window.JMV_SPECS && window.JMV_SPECS[name];
      if (!spec) { alert(T('Analyse ikke funnet: {id}', { id: name })); return; }
      var vars = jamoviVariables();
      if (!vars.length) { alert(T('Lag/importer data først (kjør et skript eller åpne et eksempeldatasett)')); return; }

      jamoviResultsContainer(); // sikrer workspace-DOM
      var panel = document.getElementById('jamoviOptions');
      panel.hidden = false; panel.innerHTML = '';

      var values = {};
      spec.options.forEach(function (o) {
        if (o.type === 'Variables' || o.type === 'Variable' || o.type === 'Pairs') values[o.name] = [];
        else values[o.name] = (o.default === undefined) ? null : o.default;
      });
      Object.assign(values, presets || {});

      // Resultatkort som live-oppdateres
      var card = jamoviTitleCard(spec.title);
      var cardWrap = card.querySelector('div');

      var runTimer = null, running = false, rerunWanted = false;
      function scheduleRun() {
        clearTimeout(runTimer);
        runTimer = setTimeout(async function () {
          if (myGen !== jmvDialogGen) return; // Fix B: a newer dialog superseded this one
          var roles = spec.options.filter(function (o) { return o.type === 'Variables' || o.type === 'Variable' || o.type === 'Pairs'; });
          var firstRole = roles[0];
          if (!firstRole || !(values[firstRole.name] || []).length) return; // ikke nok til å kjøre
          if (running) { rerunWanted = true; return; }
          running = true;
          try {
            // Fix B: pass a live gen check so a stale dialog's result never renders,
            // even though the R call already ran to completion.
            await runJmvAnalysis(spec, values, cardWrap, function () { return myGen === jmvDialogGen; });
          }
          catch (e) {
            if (myGen !== jmvDialogGen) return; // Fix B: don't mutate a stale/closed dialog's card
            cardWrap.innerHTML = '';
            // Fix A: only the empty-first-role gate above prevented scheduling; if OTHER
            // required roles are still empty, show a quiet hint (like real jamovi's
            // placeholder output) instead of flashing an "Analysefeil" for incomplete input.
            var anyEmpty = roles.some(function (r) { return !(values[r.name] || []).length; });
            if (anyEmpty) {
              var hint = document.createElement('p');
              hint.style.color = '#6b7280';
              hint.textContent = T('Velg variabler i panelet til venstre for å kjøre analysen.');
              cardWrap.appendChild(hint);
            } else {
              var pre = document.createElement('pre');
              pre.style.cssText = 'color:#b91c1c;white-space:pre-wrap;font-size:12px;';
              pre.textContent = T('Analysefeil: {msg}', { msg: e.message || e });
              cardWrap.appendChild(pre);
            }
          }
          finally { running = false; if (myGen === jmvDialogGen && rerunWanted) { rerunWanted = false; scheduleRun(); } }
        }, 400);
      }

      // Hode med lukkeknapp
      var head = document.createElement('div'); head.className = 'jmv-dialog-head';
      var ht = document.createElement('span'); ht.textContent = spec.title; head.appendChild(ht);
      var x = document.createElement('button'); x.textContent = '✕';
      x.style.cssText = 'border:none;background:none;cursor:pointer;font-size:14px;color:#555;';
      x.addEventListener('click', function () { clearTimeout(runTimer); panel.hidden = true; }); // Fix B: cancel pending live-update
      head.appendChild(x); panel.appendChild(head);

      var body = document.createElement('div'); body.className = 'jmv-dialog-body';
      body.style.display = 'block'; panel.appendChild(body);

      // ── Roller: variabel-liste + rollebokser (gjenbruker v1-markup/CSS). DOM-plassering
      // styres nå av spec.layout (via roleBoxBuilder) i stedet for å alltid ligge øverst. ──
      var roleOpts = spec.options.filter(function (o) { return o.type === 'Variables' || o.type === 'Variable' || o.type === 'Pairs'; });
      var assigned = function () { return roleOpts.reduce(function (a, o) { return a.concat(values[o.name] || []); }, []); };
      var srcSel = null;
      var srcList = document.createElement('ul');
      srcList.style.cssText = 'list-style:none;margin:0;padding:0;border:1px solid #828282;max-height:220px;overflow:auto;background:#fff;';
      function typeAllowed(o, v) {
        // suggested/permitted fra YAML: 'continuous'~numeric, ellers nominal/ordinal/factor
        var p = (o.permitted || []).concat(o.suggested || []);
        if (!p.length) return true;
        var wantsNum = p.indexOf('continuous') !== -1 || p.indexOf('numeric') !== -1;
        var wantsNom = p.indexOf('nominal') !== -1 || p.indexOf('ordinal') !== -1 || p.indexOf('factor') !== -1 || p.indexOf('id') !== -1;
        return (v.type === 'numeric' && wantsNum) || (v.type === 'nominal' && wantsNom) || (wantsNum && wantsNom);
      }
      function redraw() {
        srcList.innerHTML = '';
        vars.forEach(function (v) {
          if (assigned().indexOf(v.name) !== -1) return;
          var li = document.createElement('li');
          li.innerHTML = jamoviTypeIcon(v.type) + '<span class="jmv-var-name">' + M.escapeHtml(v.name) + '</span>';
          li.classList.toggle('jmv-selected', srcSel === v.name);
          li.addEventListener('click', function () { srcSel = v.name; redraw(); });
          li.addEventListener('dblclick', function () { assignTo(roleOpts[0], v.name); });
          srcList.appendChild(li);
        });
        roleOpts.forEach(function (o) {
          var ul = o.__ul; if (!ul) return; // defensiv: opsjon uten rolleboks (bør ikke skje, se rapport)
          ul.innerHTML = '';
          (values[o.name] || []).forEach(function (n) {
            var v = vars.filter(function (x) { return x.name === n; })[0] || { type: 'numeric' };
            var li = document.createElement('li');
            li.innerHTML = jamoviTypeIcon(v.type) + '<span class="jmv-var-name">' + M.escapeHtml(n) + '</span><span class="jmv-remove">✕</span>';
            li.addEventListener('click', function () {
              values[o.name] = values[o.name].filter(function (x) { return x !== n; });
              redraw(); scheduleRun();
            });
            ul.appendChild(li);
          });
        });
      }
      function assignTo(o, name) {
        if (!o || !name) return;
        var v = vars.filter(function (x) { return x.name === name; })[0];
        if (v && !typeAllowed(o, v)) return;
        // fase 3: maks fra layout-målet (t.max, satt av roleBoxBuilder som o.__max) hvis oppgitt,
        // ellers fra opsjonstypen som før (Pairs beholder sin faste to-slots-oppførsel).
        var max = (o.__max !== undefined) ? o.__max : ((o.type === 'Variable') ? 1 : (o.type === 'Pairs' ? 2 : Infinity));
        if ((values[o.name] || []).length >= max) { if (max === 1) values[o.name] = []; else return; }
        values[o.name].push(name); srcSel = null;
        redraw(); scheduleRun();
      }
      function optByName(n) { return spec.options.filter(function (o) { return o.name === n; })[0]; }
      // Bygger rollebokser for ett supplier-nodes targets (u.yaml-rekkefølge). Kun FØRSTE gang
      // (over alle suppliers i layout'et) tegnes den delte variabellisten — en evt. senere
      // ikke-tom supplier (finnes ikke i dagens 13 spec'er, men holdes robust) gjenbruker den
      // samme srcList/assignTo og tegner bare sine egne mål-bokser.
      var firstSupplierRendered = false;
      function roleBoxBuilder(targets, parent) {
        if (!firstSupplierRendered) {
          firstSupplierRendered = true;
          var varlistDiv = document.createElement('div'); varlistDiv.className = 'jmv-varlist';
          var vl = document.createElement('div'); vl.className = 'jmv-role-label'; vl.textContent = T('Variabler');
          varlistDiv.appendChild(vl); varlistDiv.appendChild(srcList);
          parent.appendChild(varlistDiv);
        }
        (targets || []).forEach(function (t) {
          var o = optByName(t.name); if (!o) return;
          if (t.max !== undefined) o.__max = t.max;
          var lab = document.createElement('div'); lab.className = 'jmv-role-label'; lab.textContent = o.title;
          var row = document.createElement('div'); row.className = 'jmv-role-row';
          var arrow = document.createElement('button'); arrow.className = 'jmv-arrow'; arrow.textContent = '→';
          arrow.addEventListener('click', function () { assignTo(o, srcSel); });
          var isSingle = (o.__max === 1) || (o.type === 'Variable' && o.__max === undefined);
          var box = document.createElement('ul'); box.className = 'jmv-rolebox' + (isSingle ? ' jmv-rolebox-single' : '');
          box.style.cssText = 'list-style:none;';
          o.__ul = box;
          row.appendChild(arrow); row.appendChild(box);
          parent.appendChild(lab); parent.appendChild(row);
        });
      }

      // ── Øvrige opsjoner: control(o)-bygger, gjenbrukt av layout-stien («Flere valg») og
      // den flate fallback-stien (analyser uten generert layout). ──
      var nonRole = spec.options.filter(function (o) { return roleOpts.indexOf(o) === -1; });
      function control(o) {
        var wrap = document.createElement('label'); wrap.className = 'jmv-opt-item';
        if (o.type === 'Bool') {
          var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!values[o.name];
          cb.addEventListener('change', function () { values[o.name] = cb.checked; scheduleRun(); });
          wrap.appendChild(cb); wrap.appendChild(document.createTextNode(' ' + o.title));
        } else if (o.type === 'List') {
          wrap.appendChild(document.createTextNode(o.title + ' '));
          var sel = document.createElement('select'); sel.className = 'jmv-opt-select';
          (o.choices || []).forEach(function (c) {
            var op = document.createElement('option'); op.value = c.value; op.textContent = c.title;
            if (c.value === values[o.name]) op.selected = true; sel.appendChild(op);
          });
          sel.addEventListener('change', function () { values[o.name] = sel.value; scheduleRun(); });
          wrap.appendChild(sel);
        } else if (o.type === 'Number' || o.type === 'Integer') {
          wrap.appendChild(document.createTextNode(o.title + ' '));
          var inp = document.createElement('input'); inp.type = 'number'; inp.value = values[o.name];
          inp.style.cssText = 'width:70px;padding:2px 4px;border:1px solid #828282;border-radius:3px;';
          if (o.min !== undefined) inp.min = o.min;
          if (o.max !== undefined) inp.max = o.max;
          inp.addEventListener('change', function () { values[o.name] = inp.value === '' ? o.default : Number(inp.value); scheduleRun(); });
          wrap.appendChild(inp);
        } else if (o.type === 'String') {
          wrap.appendChild(document.createTextNode(o.title + ' '));
          var ti = document.createElement('input'); ti.type = 'text'; ti.value = values[o.name] || '';
          ti.style.cssText = 'width:130px;padding:2px 4px;border:1px solid #828282;border-radius:3px;';
          ti.addEventListener('change', function () { values[o.name] = ti.value || null; scheduleRun(); });
          wrap.appendChild(ti);
        } else { return null; } // Level/andre: fase 2
        return wrap;
      }
      function addSection(title, opts, open) {
        var found = opts.map(function (n) { return nonRole.filter(function (o) { return o.name === n; })[0]; }).filter(Boolean);
        if (!found.length) return;
        var sec = document.createElement('div'); sec.className = 'jmv-section' + (open ? '' : ' collapsed');
        var hdr = document.createElement('div'); hdr.className = 'jmv-section-hdr';
        hdr.innerHTML = '<span class="jmv-section-caret">▾</span><span class="jmv-section-title">' + M.escapeHtml(title) + '</span>';
        hdr.addEventListener('click', function () { sec.classList.toggle('collapsed'); });
        var sb = document.createElement('div'); sb.className = 'jmv-section-body';
        found.forEach(function (o) { var c = control(o); if (c) sb.appendChild(c); });
        sec.appendChild(hdr); sec.appendChild(sb); body.appendChild(sec);
      }
      if (spec.layout) {
        renderJmvLayout(spec.layout, {
          spec: spec, values: values, body: body, onChange: scheduleRun, uid: myGen,
          roleBoxBuilder: roleBoxBuilder
        });
        // «Flere valg»-sikkerhetsnett (tillegg 3): skalar-opsjoner (Bool/List/Number/Integer/
        // String) som ingen check/radio/combo/text-node i layout'et peker på — typisk
        // 2.7.7-drift mellom u.yaml og den kuraterte layout-genereringen i Task 1 — havner
        // likevel i en sammenleggbar seksjon, i stedet for å bli utilgjengelige.
        var SCALAR_LAYOUT_TYPES = { Bool: true, List: true, Number: true, Integer: true, String: true };
        var coveredByLayout = {};
        (function collectRefs(node) {
          if (!node) return;
          if (node.t === 'check' || node.t === 'combo' || node.t === 'text') coveredByLayout[node.name] = true;
          else if (node.t === 'radio') coveredByLayout[node.option] = true;
          (node.children || []).forEach(collectRefs);
          (node.cells || []).forEach(function (c) { (c.children || []).forEach(collectRefs); });
        })(spec.layout);
        var uncovered = nonRole
          .filter(function (o) { return SCALAR_LAYOUT_TYPES[o.type] && !coveredByLayout[o.name]; })
          .map(function (o) { return o.name; });
        addSection(T('Flere valg'), uncovered, false);
      } else {
        // Dagens flate fallback for analyser uten generert layout (holdes for robusthet).
        roleBoxBuilder(roleOpts.map(function (o) { return { name: o.name }; }), body);
        addSection(T('Valg'), nonRole.map(function (o) { return o.name; }), true);
      }

      redraw(); scheduleRun();
    }

    // Inject ribbon DOM
    var bar = M.getModeGuiBar();
    if (bar && !document.getElementById('jamoviRibbon')) {
      var rib = document.createElement('div');
      rib.id = 'jamoviRibbon'; rib.className = 'jamovi-ribbon'; rib.setAttribute('data-mode-gui','jamovi'); rib.setAttribute('aria-label','jamovi');
      // Meny bygget fra window.JMV_SPECS (jamovi 2.0, Task 5) — ikke lenger hardkodet.
      var GROUP_ORDER = ['Exploration', 'T-Tests', 'ANOVA', 'Regression', 'Frequencies', 'Factor'];
      var CAT_KEYS = { 'Exploration': 'exploration', 'T-Tests': 'ttests', 'ANOVA': 'anova', 'Regression': 'regression', 'Frequencies': 'frequencies', 'Factor': 'factor' };
      var catGroups = GROUP_ORDER.map(function (g) {
        var lastSub = '';
        var items = Object.keys(window.JMV_SPECS || {})
          .map(function (k) { return window.JMV_SPECS[k]; })
          .filter(function (s) { return s.menuGroup === g; })
          .map(function (s) {
            var label = s.menuTitle + (s.menuSubtitle ? ' — ' + s.menuSubtitle : '');
            var sub = '';
            if (s.menuSubgroup && s.menuSubgroup !== lastSub) sub = '<span class="jmv-menu-sub">' + M.escapeHtml(s.menuSubgroup) + '</span>';
            lastSub = s.menuSubgroup || '';
            var icon = JMV_AN_ICONS[s.name] || JMV_AN_ICONS._default || '';
            return sub + '<button type="button" data-an="' + s.name + '">' + icon + '<span>' + M.escapeHtml(label) + '</span></button>';
          }).join('');
        return '<div class="jmv-group"><button type="button" class="jmv-cat" data-cat="' + CAT_KEYS[g] + '">' + g + '</button><div class="jmv-menu">' + items + '</div></div>';
      }).join('');
      rib.innerHTML =
        '<div class="jmv-tabbar">'
        + '<button type="button" class="jmv-hamburger" title="Meny" aria-label="Meny">☰</button>'
        + '<button type="button" class="jmv-tab" data-jtab="variables">Variabler</button>'
        + '<button type="button" class="jmv-tab" data-jtab="data">Data</button>'
        + '<button type="button" class="jmv-tab active" data-jtab="analyses">Analyser</button>'
        + '<button type="button" class="jmv-tab" data-jtab="figures">Figurer</button>'
        + '<button type="button" class="jmv-tab" data-jtab="edit">Rediger</button>'
        + '<div class="jmv-app-menu" hidden><button type="button" data-jaction="examples">' + T('Åpne eksempeldatasett…') + '</button><button type="button" data-jaction="toggle-topbar">' + T('Vis/skjul toppmenyen') + '</button><button type="button" data-jaction="clear">' + T('Tøm resultater') + '</button><button type="button" data-jaction="about">' + T('Om jamovi-modus') + '</button></div>'
        + '<div class="jmv-dataset-picker"><label for="jamoviDatasetSelect">Aktivt datasett:</label><select id="jamoviDatasetSelect"></select></div>'
        + '</div>'
        + '<div class="jmv-ribbon-area">'
        + '<div class="jmv-panel" data-jpanel="analyses">' + catGroups + '</div>'
        + '<div class="jmv-panel" data-jpanel="variables" hidden><button type="button" class="jmv-ribbon-btn" data-jaction="show-variables">' + T('Vis variabler') + '</button><span class="jmv-ribbon-hint">' + T('Måltype for hver variabel i det aktive datasettet.') + '</span></div>'
        + '<div class="jmv-panel" data-jpanel="data" hidden>'
        +   '<button type="button" class="jmv-ribbon-btn" data-jaction="show-data">Vis data</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-jaction="compute-var">Beregn variabel</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-jaction="recode-var">Omkod variabel</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-jaction="filter">Filter</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-jaction="add-row">Legg til rad</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-jaction="delete-row">Slett valgt rad</button>'
        + '</div>'
        + '<div class="jmv-panel" data-jpanel="figures" hidden>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="hist">Histogram</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="box">Box Plot</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="violin">Violin</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="bar">Bar Plot</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="scat">Scatter Plot</button>'
        + '</div>'
        + '<div class="jmv-panel" data-jpanel="edit" hidden><span class="jmv-ribbon-hint">Data redigeres via skript (Microdata/Python/R/Stata), ikke direkte i jamovi-modus.</span></div>'
        + '</div>';
      bar.appendChild(rib);
    }
    // Wire ribbon (initJamoviRibbon logic, inline not as IIFE)
    (function initJamoviRibbon() {
      var rib = document.getElementById('jamoviRibbon');
      if (!rib) return;
      var apanel = rib.querySelector('.jmv-panel[data-jpanel="analyses"]');
      // Analyses ribbon: category icons + dropdown toggles + analysis clicks
      apanel.querySelectorAll('.jmv-cat').forEach(function(btn){ var c = btn.getAttribute('data-cat'); btn.innerHTML = (JAMOVI_CAT_ICONS[c]||'') + '<span>' + btn.textContent + '</span>'; });
      apanel.querySelectorAll('.jmv-cat').forEach(function(btn){
        btn.addEventListener('click', function(e){
          e.stopPropagation();
          var g = btn.parentElement, wasOpen = g.classList.contains('open');
          apanel.querySelectorAll('.jmv-group').forEach(function(x){ x.classList.remove('open'); });
          if (!wasOpen) g.classList.add('open');
        });
      });
      apanel.querySelectorAll('.jmv-menu button[data-an]').forEach(function(b){
        var an = b.getAttribute('data-an');
        b.addEventListener('click', function(){ apanel.querySelectorAll('.jmv-group').forEach(function(x){x.classList.remove('open');}); openJmvAnalysis(an); });
      });
      // Tab bar
      function switchTab(tab){
        rib.querySelectorAll('.jmv-tab').forEach(function(t){ t.classList.toggle('active', t.getAttribute('data-jtab')===tab); });
        rib.querySelectorAll('.jmv-panel').forEach(function(p){ p.hidden = (p.getAttribute('data-jpanel')!==tab); });
        M.updateModeGuiBar(); // bar height changes with the panel
        if (tab==='variables') renderVariablesView();
        else if (tab==='data') renderDataView();
      }
      rib.querySelectorAll('.jmv-tab').forEach(function(t){
        t.addEventListener('click', function(e){ e.stopPropagation(); switchTab(t.getAttribute('data-jtab')); });
      });
      // Hamburger application menu
      var ham = rib.querySelector('.jmv-hamburger');
      var appMenu = rib.querySelector('.jmv-app-menu');
      ham.addEventListener('click', function(e){ e.stopPropagation(); appMenu.hidden = !appMenu.hidden; });
      appMenu.querySelectorAll('button[data-jaction]').forEach(function(b){
        b.addEventListener('click', function(e){
          e.stopPropagation(); appMenu.hidden = true;
          var act = b.getAttribute('data-jaction');
          if (act === 'clear') { var c = M.outputArea.querySelector('#jamoviResults'); if (c) c.innerHTML = ''; }
          else if (act === 'examples') { openJamoviExamplePicker(); }
          else if (act === 'toggle-topbar') { M.toggleTopbarVisible(); }
          else if (act === 'about') { alert(T('jamovi-modus: pek-og-klikk-analyser som genererer R og kjører det via webR på det aktive datasettet.')); }
        });
      });
      // Variables / Data ribbon-action buttons
      rib.querySelectorAll('.jmv-ribbon-btn[data-jaction]').forEach(function(b){
        b.addEventListener('click', function(){ var act = b.getAttribute('data-jaction');
          if (act==='show-variables') renderVariablesView();
          else if (act==='show-data') renderDataView();
          else if (act==='compute-var') jamoviComputeVarDialog();
          else if (act==='recode-var') jamoviRecodeDialog();
          else if (act==='filter') jamoviFilterDialog();
          else if (act==='add-row') jamoviAddRow();
          else if (act==='delete-row') jamoviDeleteRow();
        });
      });
      // Figurer ribbon: preset buttons open the jmv engine with the plot option pre-checked
      var FIG_PRESETS = {
        hist:   { an: 'descriptives', preset: { hist: true } },
        box:    { an: 'descriptives', preset: { box: true } },
        violin: { an: 'descriptives', preset: { box: true, violin: true } },
        bar:    { an: 'descriptives', preset: { bar: true } },
        scat:   { an: 'scat', preset: {} }
      };
      rib.querySelectorAll('.jmv-ribbon-btn[data-fig]').forEach(function (b) {
        b.addEventListener('click', function () {
          var f = FIG_PRESETS[b.getAttribute('data-fig')];
          openJmvAnalysis(f.an, f.preset);
        });
      });
      // Active-dataset picker
      var dsel = rib.querySelector('#jamoviDatasetSelect');
      if (dsel) {
        dsel.addEventListener('change', function(){ jamoviSwitchDataset(dsel.value); });
        dsel.addEventListener('mousedown', function(){ jamoviRefreshDatasetPicker(); });
      }
      jamoviRefreshDatasetPicker();
      // Outside click closes dropdowns + app menu
      document.addEventListener('click', function(){ apanel.querySelectorAll('.jmv-group').forEach(function(x){x.classList.remove('open');}); if (appMenu) appMenu.hidden = true; });
    })();

    M.registerMode({ id:'jamovi', label:'jamovi', hlConfig:M.R_HL_CFG, handleTab:M.handleRTab, topGui:'jamovi', onActivate:function(){ if(!M.isWebRReady()) M.loadWebR(); M.updateModeGuiBar(); jamoviRefreshDatasetPicker(); }, translate:{showsButton:false}, runSelf:async function(script,ctx){ await M.runHybridR(script, ctx.py, {showCommands:true}); } });
    M.updateModeGuiBar();
})();
