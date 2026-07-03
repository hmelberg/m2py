(function(){ 'use strict'; var M = window.M2PY;
    var T = window.t || function (s, p) { return p ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in p ? p[k] : m; }) : s; };
    // Variables from the active dataset
    // User-set measure-type overrides (Variables tab), keyed "dataset::column".
    var jamoviTypeOverrides = {};
    var jamoviDataTable = null; // Tabulator instance for the Data tab
    var jamoviFilter = '';      // pandas query applied (non-destructively) to data sent to analyses

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

    // Analysis spec registry
    var JAMOVI_ANALYSES = {
      // ── Figurer (plot-only analyses; no result table, just plots) ──
      fig_histogram: { id:'fig_histogram', title:'Histogram',
        roles:[{key:'vars',label:'Variables',types:['numeric'],multiple:true}],
        buildPlots:function(a){ return (a.vars||[]).map(function(n){ var rv=JSON.stringify(n); return { title:'Histogram — '+n, rCode:'hist(data[['+rv+']], main="", xlab='+rv+', col="#cfe0f3", border="white")' }; }); } },
      fig_boxplot: { id:'fig_boxplot', title:'Box Plot',
        roles:[{key:'vars',label:'Variables',types:['numeric'],multiple:true},{key:'group',label:'Split by',types:['nominal'],multiple:false}],
        buildPlots:function(a){ var g=a.group&&a.group[0]; return (a.vars||[]).map(function(n){ var rv=JSON.stringify(n);
          var rc = g ? 'boxplot(data[['+rv+']] ~ as.factor(data[['+JSON.stringify(g)+']]), xlab='+JSON.stringify(g)+', ylab='+rv+', col="#cfe0f3")'
                     : 'boxplot(data[['+rv+']], ylab='+rv+', col="#cfe0f3", horizontal=TRUE)';
          return { title:'Box Plot — '+n, rCode:rc }; }); } },
      fig_barplot: { id:'fig_barplot', title:'Bar Plot',
        roles:[{key:'vars',label:'Variables',types:['nominal'],multiple:true}],
        buildPlots:function(a){ return (a.vars||[]).map(function(n){ var rv=JSON.stringify(n); return { title:'Bar Plot — '+n, rCode:'barplot(table(data[['+rv+']]), col="#cfe0f3", border="white", ylab="Counts")' }; }); } },
      fig_scatter: { id:'fig_scatter', title:'Scatter Plot',
        roles:[{key:'x',label:'X-Axis',types:['numeric'],multiple:false},{key:'y',label:'Y-Axis',types:['numeric'],multiple:false}],
        buildPlots:function(a){ var x=a.x&&a.x[0], y=a.y&&a.y[0]; if(!x||!y) return []; return [{ title:'Scatter — '+y+' vs '+x, rCode:'plot(data[['+JSON.stringify(x)+']], data[['+JSON.stringify(y)+']], xlab='+JSON.stringify(x)+', ylab='+JSON.stringify(y)+', pch=19, col="#3e6da9aa")' }]; } },
      descriptives: {
        id: 'descriptives', title: 'Descriptives',
        roles: [{ key: 'vars', label: 'Variables', types: ['numeric','nominal'], multiple: true }, { key: 'split', label: 'Split by', types: ['nominal'], multiple: false }],
        optionSections:[
        { title:'Output', groups:[{ items:[
          {key:'orient',type:'select',label:'Variables across',choices:[{value:'columns',label:'Columns'},{value:'rows',label:'Rows'}],default:'columns'},
          {key:'freq',type:'check',label:'Frequency tables (nominal)',default:false}
        ]}]},
        { title:'Statistics', groups:[
          { title:'Sample Size', items:[{key:'N',type:'check',label:'N',default:true},{key:'Missing',type:'check',label:'Missing',default:true}] },
          { title:'Central Tendency', items:[{key:'Mean',type:'check',label:'Mean',default:true},{key:'Median',type:'check',label:'Median',default:true},{key:'Mode',type:'check',label:'Mode',default:false},{key:'Sum',type:'check',label:'Sum',default:false}] },
          { title:'Dispersion', items:[{key:'SD',type:'check',label:'Std. deviation',default:true},{key:'Variance',type:'check',label:'Variance',default:false},{key:'Range',type:'check',label:'Range',default:false},{key:'Min',type:'check',label:'Minimum',default:true},{key:'Max',type:'check',label:'Maximum',default:true},{key:'SE',type:'check',label:'Std. error',default:false},{key:'IQR',type:'check',label:'IQR',default:false}] },
          { title:'Distribution', items:[{key:'Skewness',type:'check',label:'Skewness',default:false},{key:'Kurtosis',type:'check',label:'Kurtosis',default:false},{key:'sw',type:'check',label:'Shapiro-Wilk',default:false}] },
          { title:'Percentile Values', items:[{key:'quartiles',type:'check',label:'Quartiles (25 / 50 / 75)',default:false}] }
        ]},
        { title:'Plots', groups:[{ items:[{key:'histogram',type:'check',label:'Histogram',default:false},{key:'boxplot',type:'check',label:'Box plot',default:false}] }] }],
        buildPlots: function(a, opts){
          var v = a.vars || []; var plots = [];
          v.forEach(function(name){
            var rv = JSON.stringify(name);
            if (opts && opts.histogram) plots.push({ title:'Histogram — ' + name, rCode:'hist(data[['+rv+']], main="", xlab='+rv+', col="#cfe0f3", border="white")' });
            if (opts && opts.boxplot) plots.push({ title:'Box Plot — ' + name, rCode:'boxplot(data[['+rv+']], main="", ylab='+rv+', col="#cfe0f3", horizontal=TRUE)' });
          });
          return plots;
        },
        buildR: function(a, opts){
          var v = a.vars; if(!v||!v.length) return null;
          var splitV = a.split && a.split[0];
          var rv = 'c('+v.map(function(x){return JSON.stringify(x);}).join(',')+')';
          var allKeys = ['N','Missing','Mean','Median','Mode','Sum','SD','Variance','Range','Min','Max','SE','Skewness','Kurtosis','IQR'];
          var want = allKeys.filter(function(k){ return opts && opts[k]; });
          if(!want.length) want = ['N','Mean','SD'];
          if (opts && opts.quartiles) want = want.concat(['P25','P50','P75']);
          if (opts && opts.sw) want = want.concat(['SWW','SWp']);
          var rwant = 'c('+want.map(function(k){return JSON.stringify(k);}).join(',')+')';
          var rsplit = splitV ? JSON.stringify(splitV) : 'NULL';
          var orient = (opts && opts.orient) ? opts.orient : 'columns';
          var freqT = !!(opts && opts.freq);
          return "local({\n"
           +"vars<-"+rv+"; want<-"+rwant+"; splitv<-"+rsplit+"; orient<-"+JSON.stringify(orient)+"; freqT<-"+(freqT?'TRUE':'FALSE')+";\n"
           +"Mode<-function(x){x<-x[!is.na(x)]; if(!length(x)) return(NA); ux<-unique(x); ux[which.max(tabulate(match(x,ux)))]}\n"
           +"lbl<-c(N='N',Missing='Missing',Mean='Mean',Median='Median',Mode='Mode',Sum='Sum',SD='Std. deviation',Variance='Variance',Range='Range',Min='Minimum',Max='Maximum',SE='Std. error',Skewness='Skewness',Kurtosis='Kurtosis',IQR='IQR',P25='25th percentile',P50='50th percentile',P75='75th percentile',SWW='Shapiro-Wilk W',SWp='Shapiro-Wilk p')\n"
           +"statRow<-function(v,x,lev){ xc<-x[!is.na(x)]; n<-length(xc); o<-list()\n"
           +" if(!is.null(lev)) o[['Group']]<-lev\n"
           +" o[['Variable']]<-v\n"
           +" f<-list(N=function() n, Missing=function() sum(is.na(x)), Mean=function() mean(xc), Median=function() median(xc), Mode=function() Mode(xc), Sum=function() sum(xc), SD=function() sd(xc), Variance=function() var(xc), Range=function() max(xc)-min(xc), Min=function() min(xc), Max=function() max(xc), SE=function() sd(xc)/sqrt(n), Skewness=function(){m<-mean(xc); s<-sd(xc); (sum((xc-m)^3)/n)/s^3}, Kurtosis=function(){m<-mean(xc); s<-sd(xc); (sum((xc-m)^4)/n)/s^4-3}, IQR=function() IQR(xc,na.rm=TRUE), P25=function() unname(quantile(xc,0.25)), P50=function() unname(quantile(xc,0.5)), P75=function() unname(quantile(xc,0.75)), SWW=function(){ x2<-xc; if(length(x2)>5000){set.seed(1); x2<-sample(x2,5000)}; if(length(x2)<3) NA else unname(shapiro.test(x2)$statistic) }, SWp=function(){ x2<-xc; if(length(x2)>5000){set.seed(1); x2<-sample(x2,5000)}; if(length(x2)<3) NA else shapiro.test(x2)$p.value })\n"
           +" for(k in want) o[[lbl[[k]]]]<-tryCatch(f[[k]](), error=function(e) NA)\n"
           +" as.data.frame(o, check.names=FALSE, stringsAsFactors=FALSE) }\n"
           +"rows<-list()\n"
           +"if(is.null(splitv)){ for(v in vars) rows[[length(rows)+1]]<-statRow(v, data[[v]], NULL) }\n"
           +"else { g<-as.character(data[[splitv]]); levs<-sort(unique(g[!is.na(g)])); for(lv in levs) for(v in vars) rows[[length(rows)+1]]<-statRow(v, data[[v]][!is.na(g) & g==lv], lv) }\n"
           +"result<-do.call(rbind, rows)\n"
           +"if(orient=='columns' && is.null(splitv)){ sc<-setdiff(names(result),'Variable'); tr<-as.data.frame(t(result[,sc,drop=FALSE]), check.names=FALSE, stringsAsFactors=FALSE); names(tr)<-as.character(result[['Variable']]); tr<-cbind(' '=sc, tr); result<-tr }\n"
           +"res<-list('Descriptives'=result)\n"
           +"if(freqT){ for(v in vars){ xx<-data[[v]]; if(!is.numeric(xx)){ tb<-table(xx); res[[paste0('Frequencies \\u2014 ',v)]]<-data.frame(Level=names(tb), Counts=as.integer(tb), Percent=round(100*as.integer(tb)/sum(tb),1), check.names=FALSE, stringsAsFactors=FALSE) } } }\n"
           +"if(length(res)==1) res[[1]] else res })";
        }
      },

      frequencies: { id:'frequencies', title:'Frequencies',
        roles:[{key:'var', label:'Variable', types:['nominal','numeric'], multiple:false}],
        optionSections:[{ title:'Plots', groups:[{ items:[{key:'barplot',type:'check',label:'Bar plot',default:false}] }] }],
        buildR:function(a){ var v=a.var&&a.var[0]; if(!v) return null; var rv=JSON.stringify(v);
          return "local({ t<-table(data[["+rv+"]]); n<-sum(t); data.frame(Level=names(t), Counts=as.integer(t), Percent=round(100*as.integer(t)/n,1), Cumulative=round(100*cumsum(as.integer(t))/n,1), check.names=FALSE, stringsAsFactors=FALSE) })"; },
        buildPlots:function(a,opts){ var v=a.var&&a.var[0]; if(!(opts&&opts.barplot)||!v) return []; var rv=JSON.stringify(v);
          return [{ title:'Bar Plot — '+v, rCode:'barplot(table(data[['+rv+']]), col="#cfe0f3", border="white", ylab="Counts")' }]; } },

      ttest_ind: { id:'ttest_ind', title:'Independent Samples T-Test',
        roles:[{key:'dv',label:'Dependent Variable',types:['numeric'],multiple:false},{key:'group',label:'Grouping Variable',types:['nominal'],multiple:false}],
        optionSections:[
          { title:'Tests', groups:[{ items:[{key:'test',type:'radio',choices:[{value:'student',label:"Student's"},{value:'welch',label:"Welch's"}],default:'welch'},{key:'mwu',type:'check',label:'Mann-Whitney U',default:false}] }] },
          { title:'Additional Statistics', groups:[{ items:[{key:'effsize',type:'check',label:"Effect size (Cohen's d)",default:false},{key:'meandiffci',type:'check',label:'Confidence interval (mean diff.)',default:false},{key:'descr',type:'check',label:'Descriptives table',default:false}] }] },
          { title:'Assumption Checks', groups:[{ items:[{key:'normality',type:'check',label:'Normality (Shapiro-Wilk)',default:false},{key:'homogeneity',type:'check',label:"Homogeneity (Levene's)",default:false}] }] },
          { title:'Plots', groups:[{ items:[{key:'boxplot',type:'check',label:'Box plot',default:false},{key:'qq',type:'check',label:'Q-Q plot (normality)',default:false}] }] }
        ],
        buildPlots:function(a,opts){ var dv=a.dv&&a.dv[0], g=a.group&&a.group[0]; if(!dv||!g) return []; var plots=[]; var ry=JSON.stringify(dv), rg=JSON.stringify(g);
          if (opts&&opts.boxplot) plots.push({ title:'Box Plot — '+dv+' by '+g, rCode:'boxplot(data[['+ry+']] ~ as.factor(data[['+rg+']]), xlab='+rg+', ylab='+ry+', col="#cfe0f3")' });
          if (opts&&opts.qq) plots.push({ title:'Q-Q Plot — residuals', rCode:'{ y<-data[['+ry+']]; f<-as.factor(data[['+rg+']]); r<-y-ave(y,f,FUN=function(z) mean(z,na.rm=TRUE)); qqnorm(r, main=""); qqline(r, col="#c0392b", lwd=2) }' });
          return plots; },
        note:function(a,opts){ return ((opts&&opts.test==='student') ? "Student's" : "Welch's") + ' independent-samples t-test' + (opts&&opts.mwu ? ', with Mann-Whitney U.' : '.'); },
        buildR:function(a,opts){ var dv=a.dv&&a.dv[0], g=a.group&&a.group[0]; if(!dv||!g) return null;
          var varEqual = (opts&&opts.test==='student') ? 'TRUE' : 'FALSE';
          var testLabel = (opts&&opts.test==='student') ? 'Student t' : 'Welch t';
          var effsize = (opts&&opts.effsize) ? true : false;
          var mwu = (opts&&opts.mwu) ? true : false;
          var base = "local({ f<-as.factor(data[["+JSON.stringify(g)+"]]); y<-data[["+JSON.stringify(dv)+"]]; tt<-t.test(y~f, var.equal="+varEqual+"); md<-diff(rev(tapply(y,f,mean,na.rm=TRUE)));";
          if (effsize) {
            base += " lvs<-levels(f); m1<-mean(y[f==lvs[1]],na.rm=TRUE); m2<-mean(y[f==lvs[2]],na.rm=TRUE); s1<-sd(y[f==lvs[1]],na.rm=TRUE); s2<-sd(y[f==lvs[2]],na.rm=TRUE); n1<-sum(!is.na(y[f==lvs[1]])); n2<-sum(!is.na(y[f==lvs[2]])); d<-(m1-m2)/sqrt(((n1-1)*s1^2+(n2-1)*s2^2)/(n1+n2-2)); out<-data.frame('Test'="+JSON.stringify(testLabel)+", 't'=unname(tt$statistic), 'df'=unname(tt$parameter), 'p'=tt$p.value, 'Mean diff'=unname(md), \"Cohen's d\"=d, check.names=FALSE, stringsAsFactors=FALSE);";
          } else {
            base += " out<-data.frame('Test'="+JSON.stringify(testLabel)+", 't'=unname(tt$statistic), 'df'=unname(tt$parameter), 'p'=tt$p.value, 'Mean diff'=unname(md), check.names=FALSE, stringsAsFactors=FALSE);";
          }
          if (opts && opts.meandiffci) base += " out[['95% CI Lower']]<-tt$conf.int[1]; out[['95% CI Upper']]<-tt$conf.int[2];";
          base += " res<-list('T-Test'=out);";
          if (opts && opts.descr) base += " lv<-levels(f); dn<-sapply(lv,function(L) sum(!is.na(y[f==L]))); dm<-sapply(lv,function(L) mean(y[f==L],na.rm=TRUE)); ds<-sapply(lv,function(L) sd(y[f==L],na.rm=TRUE)); res[['Group Descriptives']]<-data.frame(Group=lv, N=dn, Mean=dm, SD=ds, SE=ds/sqrt(dn), check.names=FALSE, stringsAsFactors=FALSE);";
          if (mwu) base += " w<-wilcox.test(y~f); res[['Mann-Whitney U']]<-data.frame('Test'='Mann-Whitney U', 'W'=unname(w$statistic), p=w$p.value, check.names=FALSE, stringsAsFactors=FALSE);";
          if (opts && opts.normality) base += " ry<-y-ave(y,f,FUN=function(z) mean(z,na.rm=TRUE)); ry<-ry[!is.na(ry)]; if(length(ry)>5000){set.seed(1); ry<-sample(ry,5000)}; sw<-shapiro.test(ry); res[['Normality (Shapiro-Wilk)']]<-data.frame('Test'='Shapiro-Wilk', 'W'=unname(sw$statistic), p=sw$p.value, check.names=FALSE);";
          if (opts && opts.homogeneity) base += " med<-tapply(y,f,median,na.rm=TRUE); zz<-abs(y-med[f]); la<-anova(lm(zz~f)); res[['Homogeneity (Levene)']]<-data.frame('Test'=\"Levene's\", 'F'=la[1,'F value'], df1=la[1,'Df'], df2=la[2,'Df'], p=la[1,'Pr(>F)'], check.names=FALSE);";
          base += " if(length(res)==1) res[[1]] else res })";
          return base; } },

      ttest_paired: { id:'ttest_paired', title:'Paired Samples T-Test',
        roles:[{key:'pair',label:'Paired Variables (2)',types:['numeric'],multiple:true}],
        optionSections:[{ title:'Tests', groups:[{ items:[{key:'wilcoxon',type:'check',label:'Wilcoxon rank',default:false}] }] }],
        buildR:function(a,opts){ var v=a.pair||[]; if(v.length<2) return null;
          var wilcoxon = (opts&&opts.wilcoxon) ? true : false;
          var vx=JSON.stringify(v[0]), vy=JSON.stringify(v[1]);
          var base = "local({ x<-data[["+vx+"]]; y<-data[["+vy+"]]; tt<-t.test(x, y, paired=TRUE); out<-data.frame('Test'='Paired t', 't'=unname(tt$statistic), 'df'=unname(tt$parameter), 'p'=tt$p.value, 'Mean diff'=unname(tt$estimate), check.names=FALSE, stringsAsFactors=FALSE);";
          if (wilcoxon) {
            base += " w<-wilcox.test(x, y, paired=TRUE); wdf<-data.frame('Test'='Wilcoxon', 'V'=unname(w$statistic), p=w$p.value, check.names=FALSE, stringsAsFactors=FALSE); list('Paired T-Test'=out, 'Wilcoxon'=wdf) })";
          } else {
            base += " out })";
          }
          return base; } },

      correlation: { id:'correlation', title:'Correlation Matrix',
        roles:[{key:'vars',label:'Variables',types:['numeric'],multiple:true}],
        optionSections:[
          { title:'Correlation Coefficients', groups:[{ items:[{key:'method',type:'radio',choices:[{value:'pearson',label:'Pearson'},{value:'spearman',label:'Spearman'},{value:'kendall',label:"Kendall's tau-b"}],default:'pearson'},{key:'reportp',type:'check',label:'Report significance (p)',default:false}] }] },
          { title:'Plot', groups:[{ items:[{key:'plot',type:'check',label:'Scatterplot',default:false}] }] }
        ],
        note:function(a,opts){ var m=(opts&&opts.method)||'pearson'; var lbl={pearson:'Pearson product-moment',spearman:"Spearman's rank",kendall:"Kendall's tau-b"}[m]||m; return lbl+' correlation, pairwise-complete observations.'; },
        buildR:function(a,opts){ var v=a.vars||[]; if(v.length<2) return null; var rv='c('+v.map(function(x){return JSON.stringify(x);}).join(',')+')';
          var method = (opts&&opts.method) ? opts.method : 'pearson'; var rm=JSON.stringify(method);
          if (opts&&opts.reportp) {
            return "local({ vars<-"+rv+"; m<-cor(data[,vars,drop=FALSE], use='pairwise.complete.obs', method="+rm+"); cd<-cbind(Variable=rownames(m), as.data.frame(round(m,3), check.names=FALSE)); n<-length(vars); pm<-matrix('\\u2014',n,n,dimnames=list(vars,vars)); for(i in 1:n) for(j in 1:n) if(i!=j){ pv<-suppressWarnings(cor.test(data[[vars[i]]], data[[vars[j]]], method="+rm+")$p.value); pm[i,j]<-if(is.na(pv)) '\\u2014' else if(pv<0.001) '< .001' else formatC(pv, format='f', digits=3) }; pd<-cbind(Variable=vars, as.data.frame(pm, check.names=FALSE, stringsAsFactors=FALSE)); list('Correlation Matrix'=cd, 'p-values'=pd) })";
          }
          return "local({ vars<-"+rv+"; m<-cor(data[,vars,drop=FALSE], use='pairwise.complete.obs', method="+rm+"); d<-as.data.frame(round(m,3), check.names=FALSE); cbind(Variable=rownames(m), d) })"; },
        buildPlots:function(a,opts){ var v=a.vars||[]; if(!(opts&&opts.plot)||v.length<2) return [];
          if (v.length===2){ var x=JSON.stringify(v[0]), y=JSON.stringify(v[1]);
            return [{ title:'Scatterplot — '+v[0]+' vs '+v[1], rCode:'plot(data[['+x+']], data[['+y+']], xlab='+x+', ylab='+y+', pch=19, col="#3e6da9aa")' }]; }
          var rv='c('+v.map(function(x){return JSON.stringify(x);}).join(',')+')';
          return [{ title:'Scatterplot Matrix', rCode:'pairs(data[,'+rv+',drop=FALSE], pch=19, col="#3e6da9aa")' }]; } },

      lin_reg: { id:'lin_reg', title:'Linear Regression',
        roles:[{key:'dv',label:'Dependent Variable',types:['numeric'],multiple:false},{key:'covs',label:'Covariates',types:['numeric'],multiple:true}],
        optionSections:[
          { title:'Model Coefficients', groups:[{ items:[
            {key:'ci',type:'check',label:'Confidence interval (95%)',default:false},
            {key:'stdest',type:'check',label:'Standardized estimate',default:false}
          ]}]},
          { title:'Model Fit', groups:[{ items:[
            {key:'aic',type:'check',label:'AIC',default:false},
            {key:'bic',type:'check',label:'BIC',default:false},
            {key:'rmse',type:'check',label:'RMSE',default:false}
          ]}]},
          { title:'Plot', groups:[{ items:[{key:'plot',type:'check',label:'Scatterplot with fit line',default:false}] }] }
        ],
        note:function(a){ var dv=a.dv&&a.dv[0], c=a.covs||[]; return 'Linear model: ' + dv + ' ~ ' + c.join(' + ') + '.'; },
        buildR:function(a, opts){ var dv=a.dv&&a.dv[0], c=a.covs||[]; if(!dv||!c.length) return null; var rc='c('+c.map(function(x){return JSON.stringify(x);}).join(',')+')';
          var ciR = (opts && opts.ci) ? "ci<-suppressMessages(confint(m)); co[['95% CI Lower']]<-ci[,1]; co[['95% CI Upper']]<-ci[,2];\n" : "";
          var stdestR = (opts && opts.stdest) ? "bcoef<-coef(m); sdy<-sd(d2[[ndv]],na.rm=TRUE); sdx<-sapply(names(bcoef), function(t) if(t=='(Intercept)') NA else sd(d2[[t]],na.rm=TRUE)); co[['Std. Estimate']]<-as.numeric(bcoef)*sdx/sdy;\n" : "";
          var aicR  = (opts && opts.aic)  ? "fit[['AIC']]<-AIC(m);\n"  : "";
          var bicR  = (opts && opts.bic)  ? "fit[['BIC']]<-BIC(m);\n"  : "";
          var rmseR = (opts && opts.rmse) ? "fit[['RMSE']]<-sqrt(mean(residuals(m)^2));\n" : "";
          return "local({ dv<-"+JSON.stringify(dv)+"; covs<-"+rc+"; d2<-data[,c(dv,covs),drop=FALSE]; names(d2)<-make.names(names(d2)); ndv<-make.names(dv); nco<-make.names(covs); m<-lm(as.formula(paste(ndv,'~',paste(nco,collapse='+'))), data=d2); s<-summary(m); fit<-data.frame('R-squared'=s$r.squared,'Adj. R-squared'=s$adj.r.squared,'F'=unname(s$fstatistic[1]),'df1'=unname(s$fstatistic[2]),'df2'=unname(s$fstatistic[3]),'p'=unname(pf(s$fstatistic[1],s$fstatistic[2],s$fstatistic[3],lower.tail=FALSE)),check.names=FALSE);\n"+aicR+bicR+rmseR+"co<-as.data.frame(s$coefficients,check.names=FALSE); co<-cbind(Term=rownames(co),co);\n"+ciR+stdestR+"list('Model Fit'=fit,'Coefficients'=co) })"; },
        buildPlots:function(a,opts){ var dv=a.dv&&a.dv[0], c=a.covs||[]; if(!(opts&&opts.plot)||!dv||!c.length) return [];
          var x=JSON.stringify(c[0]), y=JSON.stringify(dv);
          return [{ title:'Scatterplot — '+dv+' vs '+c[0], rCode:'plot(data[['+x+']], data[['+y+']], xlab='+x+', ylab='+y+', pch=19, col="#3e6da9aa"); abline(lm(data[['+y+']] ~ data[['+x+']]), col="#c0392b", lwd=2)' }]; } },

      log_reg: { id:'log_reg', title:'Logistic Regression',
        roles:[{key:'dv',label:'Dependent Variable (binary)',types:['nominal'],multiple:false},{key:'covs',label:'Covariates',types:['numeric','nominal'],multiple:true}],
        optionSections:[{ title:'Model Coefficients', groups:[{ items:[
          {key:'or',type:'check',label:'Odds ratio',default:true},
          {key:'ci',type:'check',label:'Confidence interval (95%)',default:false}
        ]}]}],
        buildR:function(a, opts){ var dv=a.dv&&a.dv[0], c=a.covs||[]; if(!dv||!c.length) return null; var rc='c('+c.map(function(x){return JSON.stringify(x);}).join(',')+')';
          var orR  = (opts && opts.or)  ? "co[['Odds ratio']]<-exp(co[['Estimate']]);\n" : "";
          var ciR  = (opts && opts.ci)  ? "cl<-suppressMessages(confint.default(m)); co[['OR CI Lower']]<-exp(cl[,1]); co[['OR CI Upper']]<-exp(cl[,2]);\n" : "";
          return "local({ dv<-"+JSON.stringify(dv)+"; covs<-"+rc+"; d2<-data[,c(dv,covs),drop=FALSE]; d2[[dv]]<-as.factor(d2[[dv]]); names(d2)<-make.names(names(d2)); ndv<-make.names(dv); nco<-make.names(covs); m<-glm(as.formula(paste(ndv,'~',paste(nco,collapse='+'))), data=d2, family=binomial); s<-summary(m); co<-as.data.frame(s$coefficients,check.names=FALSE); co<-cbind(Term=rownames(co),co);\n"+orR+ciR+"fit<-data.frame('Deviance'=s$deviance,'AIC'=s$aic,'N'=nrow(d2),check.names=FALSE); list('Coefficients'=co,'Model Fit'=fit) })"; } },

      anova_oneway: { id:'anova_oneway', title:'One-Way ANOVA',
        roles:[{key:'dv',label:'Dependent Variable',types:['numeric'],multiple:false},{key:'factor',label:'Grouping Variable',types:['nominal'],multiple:false}],
        optionSections:[
          { title:'Variances', groups:[{ items:[{key:'welch',type:'check',label:"Don't assume equal (Welch's)",default:false}] }] },
          { title:'Effect Size', groups:[{ items:[{key:'eta',type:'check',label:'η² (eta-squared)',default:true},{key:'omega',type:'check',label:'ω² (omega-squared)',default:false}] }] },
          { title:'Assumption Checks', groups:[{ items:[{key:'homogeneity',type:'check',label:"Homogeneity (Levene's)",default:false},{key:'normality',type:'check',label:'Normality (Shapiro-Wilk)',default:false}] }] },
          { title:'Post Hoc Tests', groups:[{ items:[{key:'tukey',type:'check',label:'Tukey (HSD)',default:false}] }] },
          { title:'Plots', groups:[{ items:[{key:'boxplot',type:'check',label:'Box plot',default:false},{key:'qq',type:'check',label:'Q-Q plot (normality)',default:false}] }] }
        ],
        buildPlots:function(a,opts){ var dv=a.dv&&a.dv[0], f=a.factor&&a.factor[0]; if(!dv||!f) return []; var plots=[]; var ry=JSON.stringify(dv), rf=JSON.stringify(f);
          if (opts&&opts.boxplot) plots.push({ title:'Box Plot — '+dv+' by '+f, rCode:'boxplot(data[['+ry+']] ~ as.factor(data[['+rf+']]), xlab='+rf+', ylab='+ry+', col="#cfe0f3")' });
          if (opts&&opts.qq) plots.push({ title:'Q-Q Plot — residuals', rCode:'{ y<-data[['+ry+']]; g<-as.factor(data[['+rf+']]); m<-aov(y~g); r<-residuals(m); qqnorm(r, main=""); qqline(r, col="#c0392b", lwd=2) }' });
          return plots; },
        buildR:function(a, opts){ var dv=a.dv&&a.dv[0], f=a.factor&&a.factor[0]; if(!dv||!f) return null;
          var welch = opts && opts.welch;
          var eta   = opts && opts.eta;
          var omega = opts && opts.omega;
          var needES = eta || omega;
          // Always build the aov for SS (needed for effect sizes and as default ANOVA table)
          var rBase = "local({ y<-data[["+JSON.stringify(dv)+"]]; g<-as.factor(data[["+JSON.stringify(f)+"]]); m<-aov(y~g); s<-summary(m)[[1]]; d<-as.data.frame(s,check.names=FALSE); d<-cbind(Term=c('Group','Residuals')[seq_len(nrow(d))], d);\n";
          // Welch override
          var rWelch = welch ? "wt<-oneway.test(y~g, var.equal=FALSE); anovaT<-data.frame('Test'=\"Welch's F\",'F'=unname(wt$statistic),df1=unname(wt$parameter[1]),df2=unname(wt$parameter[2]),p=wt$p.value,check.names=FALSE);\n"
                             : "anovaT<-d;\n";
          // Effect size
          var rES = "";
          if (needES) {
            rES += "ss<-d[['Sum Sq']]; dfg<-d[['Df']][1]; sst<-sum(ss); msr<-d[['Mean Sq']][nrow(d)];\n";
            rES += "eta2<-ss[1]/sst; omega2<-(ss[1]-dfg*msr)/(sst+msr);\n";
            var esCols = [];
            if (eta)   esCols.push("'η²'=eta2");
            if (omega) esCols.push("'ω²'=omega2");
            rES += "es<-data.frame("+esCols.join(",")+",check.names=FALSE);\n";
          }
          // Assemble the result list (ANOVA + optional effect size / assumptions / post-hoc)
          var rAssemble = "res<-list('ANOVA'=anovaT);\n";
          if (needES) rAssemble += "res[['Effect Size']]<-es;\n";
          if (opts && opts.homogeneity) rAssemble += "med<-tapply(y,g,median,na.rm=TRUE); zz<-abs(y-med[g]); la<-anova(lm(zz~g)); res[['Homogeneity (Levene)']]<-data.frame('Test'=\"Levene's\",'F'=la[1,'F value'],df1=la[1,'Df'],df2=la[2,'Df'],p=la[1,'Pr(>F)'],check.names=FALSE);\n";
          if (opts && opts.normality) rAssemble += "rr<-residuals(m); rr<-rr[!is.na(rr)]; if(length(rr)>5000){set.seed(1); rr<-sample(rr,5000)}; sw<-shapiro.test(rr); res[['Normality (Shapiro-Wilk)']]<-data.frame('Test'='Shapiro-Wilk','W'=unname(sw$statistic),p=sw$p.value,check.names=FALSE);\n";
          if (opts && opts.tukey) rAssemble += "th<-TukeyHSD(m)$g; tk<-data.frame(Comparison=rownames(th),'Mean diff'=th[,'diff'],'Lower'=th[,'lwr'],'Upper'=th[,'upr'],'p'=th[,'p adj'],check.names=FALSE,stringsAsFactors=FALSE); res[['Post Hoc (Tukey)']]<-tk;\n";
          rAssemble += "if(length(res)==1) res[[1]] else res";
          return rBase + rWelch + rES + rAssemble + " })"; } },

      contingency: { id:'contingency', title:'Contingency Tables (χ²)',
        roles:[{key:'rows',label:'Rows',types:['nominal'],multiple:false},{key:'cols',label:'Columns',types:['nominal'],multiple:false}],
        optionSections:[{ title:'Cells', groups:[{ items:[
          {key:'expected',type:'check',label:'Expected counts',default:false},
          {key:'rowpct',type:'check',label:'Row %',default:false},
          {key:'colpct',type:'check',label:'Column %',default:false}
        ]}]},{ title:'Statistics', groups:[{ items:[
          {key:'contcorr',type:'check',label:'χ² continuity correction',default:false},
          {key:'likerat',type:'check',label:'Likelihood ratio',default:false},
          {key:'fisher',type:'check',label:"Fisher's exact test",default:false},
          {key:'cramers',type:'check',label:"Phi and Cramér's V",default:false}
        ]}]}],
        buildR:function(a,opts){ var r=a.rows&&a.rows[0], c=a.cols&&a.cols[0]; if(!r||!c) return null;
          var extra = "";
          if (opts && opts.expected) extra += "ex<-as.data.frame.matrix(round(ch$expected,1),check.names=FALSE); ex<-cbind(' '=rownames(ex),ex); res[['Expected Counts']]<-ex;\n";
          if (opts && opts.rowpct)   extra += "rp<-as.data.frame.matrix(round(100*prop.table(t,1),1),check.names=FALSE); rp<-cbind(' '=rownames(rp),rp); res[['Row %']]<-rp;\n";
          if (opts && opts.colpct)   extra += "cp<-as.data.frame.matrix(round(100*prop.table(t,2),1),check.names=FALSE); cp<-cbind(' '=rownames(cp),cp); res[['Column %']]<-cp;\n";
          var testRows = "rows<-list(data.frame(Test='χ²', Value=unname(ch$statistic), df=unname(ch$parameter), p=ch$p.value, check.names=FALSE, stringsAsFactors=FALSE));\n";
          if (opts && opts.contcorr) testRows += "cc<-suppressWarnings(chisq.test(t, correct=TRUE)); rows[[length(rows)+1]]<-data.frame(Test='χ² continuity correction', Value=unname(cc$statistic), df=unname(cc$parameter), p=cc$p.value, check.names=FALSE, stringsAsFactors=FALSE);\n";
          if (opts && opts.likerat)  testRows += "g2<-2*sum(t*log(t/ch$expected), na.rm=TRUE); dfg<-unname(ch$parameter); rows[[length(rows)+1]]<-data.frame(Test='Likelihood ratio', Value=g2, df=dfg, p=pchisq(g2, dfg, lower.tail=FALSE), check.names=FALSE, stringsAsFactors=FALSE);\n";
          // Exact Fisher only for 2x2; larger tables use Monte-Carlo (exact is intractable / hangs).
          if (opts && opts.fisher)   testRows += "ft<-tryCatch(if(nrow(t)*ncol(t)<=4) fisher.test(t) else fisher.test(t, simulate.p.value=TRUE, B=20000), error=function(e) NULL); if(!is.null(ft)){ lab<-if(nrow(t)*ncol(t)<=4) \"Fisher's exact\" else \"Fisher's exact (Monte Carlo)\"; rows[[length(rows)+1]]<-data.frame(Test=lab, Value=NA, df=NA, p=ft$p.value, check.names=FALSE, stringsAsFactors=FALSE) };\n";
          var cramersR = (opts && opts.cramers) ? "n<-sum(t); phi<-sqrt(unname(ch$statistic)/n); k<-min(nrow(t),ncol(t)); if(k>=2){ cv<-sqrt(unname(ch$statistic)/(n*(k-1))); res[['Nominal Effect Size']]<-data.frame(Statistic=c('Phi',\"Cramér's V\"), Value=c(phi,cv), check.names=FALSE, stringsAsFactors=FALSE) };\n" : "";
          return "local({ t<-table(data[["+JSON.stringify(r)+"]], data[["+JSON.stringify(c)+"]]); ch<-suppressWarnings(chisq.test(t)); cnt<-as.data.frame.matrix(t,check.names=FALSE); cnt<-cbind(' '=rownames(cnt),cnt); res<-list('Counts'=cnt);\n"+extra+testRows+"res[['Tests']]<-do.call(rbind, rows);\n"+cramersR+"res })"; } },

      ttest_one: { id:'ttest_one', title:'One Sample T-Test',
        roles:[{key:'vars',label:'Variables',types:['numeric'],multiple:true}],
        optionSections:[{ title:'Hypothesis', groups:[{ items:[{key:'mu',type:'radio',label:'Test value (μ)',choices:[{value:'0',label:'0'}],default:'0'}] }] }],
        buildR:function(a,opts){ var v=a.vars; if(!v||!v.length) return null;
          var rv='c('+v.map(function(x){return JSON.stringify(x);}).join(',')+')';
          return "local({ vars<-"+rv+"; do.call(rbind, lapply(vars, function(v){ tt<-t.test(data[[v]], mu=0); data.frame(Variable=v, t=unname(tt$statistic), df=unname(tt$parameter), p=tt$p.value, Mean=unname(tt$estimate), check.names=FALSE, stringsAsFactors=FALSE) })) })"; } },

      gof: { id:'gof', title:'χ² Goodness of Fit',
        roles:[{key:'var',label:'Variable',types:['nominal'],multiple:false}],
        buildR:function(a){ var v=a.var&&a.var[0]; if(!v) return null;
          return "local({ t<-table(data[["+JSON.stringify(v)+"]]); ch<-chisq.test(t); obs<-as.integer(t); exp<-unname(ch$expected); counts<-data.frame(Level=names(t), Observed=obs, Expected=round(exp,1), check.names=FALSE, stringsAsFactors=FALSE); test<-data.frame('χ²'=unname(ch$statistic), df=unname(ch$parameter), p=ch$p.value, check.names=FALSE); list('Proportions'=counts, 'χ² Goodness of Fit'=test) })"; } },

      kruskal: { id:'kruskal', title:'Kruskal-Wallis (One-Way Non-Parametric)',
        roles:[{key:'dv',label:'Dependent Variable',types:['numeric'],multiple:false},{key:'factor',label:'Grouping Variable',types:['nominal'],multiple:false}],
        buildR:function(a){ var dv=a.dv&&a.dv[0], f=a.factor&&a.factor[0]; if(!dv||!f) return null;
          return "local({ y<-data[["+JSON.stringify(dv)+"]]; g<-as.factor(data[["+JSON.stringify(f)+"]]); k<-kruskal.test(y~g); data.frame('Test'='Kruskal-Wallis', 'χ²'=unname(k$statistic), df=unname(k$parameter), p=k$p.value, check.names=FALSE, stringsAsFactors=FALSE) })"; } }
    };

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
      if (!c) { M.outputArea.innerHTML = ''; c = document.createElement('div'); c.id = 'jamoviResults'; M.outputArea.appendChild(c); }
      return c;
    }

    // A result card with only a title (for plot-only analyses); plots append into it.
    // Clean, idiomatic R for the syntax log (like jamovi's syntax mode) — readable and
    // re-runnable, in contrast to the verbose table-building R that actually executes.
    function jamoviCleanSyntax(spec, a, opts) {
      function f(n){ return /^[A-Za-z.][A-Za-z0-9._]*$/.test(n) ? n : '`' + n + '`'; }      // formula ref
      function d(n){ return /^[A-Za-z.][A-Za-z0-9._]*$/.test(n) ? 'data$' + n : 'data[["' + n + '"]]'; } // $ ref
      function cvec(arr){ return 'c(' + arr.map(function(n){ return '"' + n + '"'; }).join(', ') + ')'; }
      var id = spec.id, s;
      switch (id) {
        case 'descriptives': { var v = a.vars || []; if (!v.length) return null;
          return (a.split && a.split[0]) ? 'by(data[, ' + cvec(v) + '], ' + d(a.split[0]) + ', summary)' : 'summary(data[, ' + cvec(v) + '])'; }
        case 'frequencies': { var fv = a.var && a.var[0]; return fv ? 'table(' + d(fv) + ')' : null; }
        case 'gof': { var gv = a.var && a.var[0]; return gv ? 'chisq.test(table(' + d(gv) + '))' : null; }
        case 'ttest_ind': { var dv = a.dv && a.dv[0], g = a.group && a.group[0]; if (!dv || !g) return null;
          s = 't.test(' + f(dv) + ' ~ ' + f(g) + ', data = data, var.equal = ' + ((opts && opts.test === 'student') ? 'TRUE' : 'FALSE') + ')';
          if (opts && opts.mwu) s += '\nwilcox.test(' + f(dv) + ' ~ ' + f(g) + ', data = data)'; return s; }
        case 'ttest_paired': { var p = a.pair || []; if (p.length < 2) return null;
          s = 't.test(' + d(p[0]) + ', ' + d(p[1]) + ', paired = TRUE)';
          if (opts && opts.wilcoxon) s += '\nwilcox.test(' + d(p[0]) + ', ' + d(p[1]) + ', paired = TRUE)'; return s; }
        case 'ttest_one': { var ov = a.vars || []; if (!ov.length) return null;
          return ov.map(function(x){ return 't.test(' + d(x) + ', mu = 0)'; }).join('\n'); }
        case 'correlation': { var cv = a.vars || []; if (cv.length < 2) return null;
          return 'cor(data[, ' + cvec(cv) + '], use = "pairwise.complete.obs", method = "' + ((opts && opts.method) || 'pearson') + '")'; }
        case 'lin_reg': { var ld = a.dv && a.dv[0], lc = a.covs || []; if (!ld || !lc.length) return null;
          return 'summary(lm(' + f(ld) + ' ~ ' + lc.map(f).join(' + ') + ', data = data))'; }
        case 'log_reg': { var gd = a.dv && a.dv[0], gc = a.covs || []; if (!gd || !gc.length) return null;
          return 'summary(glm(' + f(gd) + ' ~ ' + gc.map(f).join(' + ') + ', data = data, family = binomial))'; }
        case 'anova_oneway': { var ad = a.dv && a.dv[0], af = a.factor && a.factor[0]; if (!ad || !af) return null;
          return 'summary(aov(' + f(ad) + ' ~ ' + f(af) + ', data = data))'; }
        case 'kruskal': { var kd = a.dv && a.dv[0], kf = a.factor && a.factor[0]; if (!kd || !kf) return null;
          return 'kruskal.test(' + f(kd) + ' ~ ' + f(kf) + ', data = data)'; }
        case 'contingency': { var r = a.rows && a.rows[0], c = a.cols && a.cols[0]; if (!r || !c) return null;
          return 'chisq.test(table(' + d(r) + ', ' + d(c) + '))'; }
        case 'fig_histogram': return (a.vars || []).map(function(x){ return 'hist(' + d(x) + ')'; }).join('\n') || null;
        case 'fig_boxplot': { var bg = a.group && a.group[0]; return (a.vars || []).map(function(x){ return bg ? 'boxplot(' + f(x) + ' ~ ' + f(bg) + ', data = data)' : 'boxplot(' + d(x) + ')'; }).join('\n') || null; }
        case 'fig_barplot': return (a.vars || []).map(function(x){ return 'barplot(table(' + d(x) + '))'; }).join('\n') || null;
        case 'fig_scatter': { var sx = a.x && a.x[0], sy = a.y && a.y[0]; return (sx && sy) ? 'plot(' + d(sx) + ', ' + d(sy) + ')' : null; }
      }
      return null;
    }

    function jamoviTitleCard(title) {
      var card = document.createElement('div'); card.className = 'jmv-result-card';
      var rm = document.createElement('button'); rm.className = 'jmv-card-remove'; rm.title = T('Fjern'); rm.textContent = '✕';
      rm.addEventListener('click', function() { card.remove(); });
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

    // Render a structured webR toJs() result as jamovi-style tables
    function renderJamoviResult(title, struct, note) {
      var wrap = document.createElement('div');
      wrap.style.cssText = 'padding:12px 18px;';

      function isDataFrame(s) {
        return s && s.type === 'list' && Array.isArray(s.names) && s.values && s.values[0] && s.values[0].type !== 'list';
      }

      function fmtNum(v) {
        if (v === null || v === undefined || (typeof v === 'number' && isNaN(v))) return 'NA';
        if (typeof v !== 'number') return String(v);
        if (Number.isInteger(v)) return String(v);
        var a = Math.abs(v);
        if (a >= 1e9 || (a > 0 && a < 1e-4)) return v.toExponential(2); // only truly extreme → sci
        if (a >= 1000) return v.toFixed(0);   // large → no decimals (jamovi-like)
        if (a >= 1) return v.toFixed(2);      // medium → 2 decimals
        return v.toPrecision(3).replace(/0+$/, '').replace(/\.$/, '');
      }

      // jamovi-style p-value: "< .001" for tiny, 3 decimals with no leading zero otherwise
      function isPCol(name) {
        return name === 'p' || /^Pr\(/.test(name) || /p[-\s]?value/i.test(name);
      }
      function fmtP(v) {
        if (v === null || v === undefined || (typeof v === 'number' && isNaN(v))) return 'NA';
        if (typeof v !== 'number') return String(v);
        if (v < 0.001) return '< .001';
        return v.toFixed(3).replace(/^(-?)0\./, '$1.');
      }

      function buildTable(t, heading) {
        var h = document.createElement('h3');
        h.className = 'jmv-result-title';
        h.textContent = heading || title;
        wrap.appendChild(h);

        if (!isDataFrame(t)) {
          var pre = document.createElement('pre');
          pre.style.cssText = 'color:#b91c1c; white-space:pre-wrap;';
          pre.textContent = JSON.stringify(t, null, 2);
          wrap.appendChild(pre);
          return;
        }

        var table = document.createElement('table');
        table.className = 'jmv-result-table';
        var thead = document.createElement('thead');
        var trh = document.createElement('tr');
        t.names.forEach(function(n) {
          var th = document.createElement('th');
          th.textContent = n;
          trh.appendChild(th);
        });
        thead.appendChild(trh);
        table.appendChild(thead);

        var tbody = document.createElement('tbody');
        var nrows = t.values[0].values.length;
        for (var r = 0; r < nrows; r++) {
          var tr = document.createElement('tr');
          for (var c = 0; c < t.names.length; c++) {
            var td = document.createElement('td');
            var col = t.values[c];
            var val = col.values[r];
            var isNumCol = (col.type === 'double' || col.type === 'integer');
            if (isNumCol && isPCol(t.names[c])) td.textContent = fmtP(val);
            else td.textContent = isNumCol ? fmtNum(val) : (val === null ? 'NA' : String(val));
            tr.appendChild(td);
          }
          tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        wrap.appendChild(table);
      }

      if (struct && struct.type === 'character') {
        var errPre = document.createElement('pre');
        errPre.style.cssText = 'color:#b91c1c; white-space:pre-wrap; padding:8px;';
        errPre.textContent = Array.isArray(struct.values) ? struct.values.join('\n') : String(struct.values);
        wrap.appendChild(errPre);
      } else if (isDataFrame(struct)) {
        buildTable(struct, title);
      } else if (struct && struct.type === 'list' && Array.isArray(struct.names)) {
        struct.values.forEach(function(sub, i) {
          buildTable(sub, struct.names[i] || title);
        });
      } else {
        var fb = document.createElement('pre');
        fb.textContent = JSON.stringify(struct, null, 2);
        wrap.appendChild(fb);
      }

      if (note) {
        var noteEl = document.createElement('div');
        noteEl.className = 'jmv-result-note';
        noteEl.innerHTML = '<i>Note.</i> ' + M.escapeHtml(note);
        wrap.appendChild(noteEl);
      }

      // Stack: append a removable result card (don't replace prior analyses).
      var card = document.createElement('div');
      card.className = 'jmv-result-card';
      var rm = document.createElement('button');
      rm.className = 'jmv-card-remove';
      rm.title = T('Fjern analyse');
      rm.textContent = '✕';
      rm.addEventListener('click', function() { card.remove(); });
      card.appendChild(rm);
      card.appendChild(wrap);
      jamoviResultsContainer().appendChild(card);
      card.scrollIntoView({ block: 'nearest' });
      return card;
    }

    // Jamovi measure-type icons
    function jamoviTypeIcon(type) {
      if (type === 'numeric') // continuous: jamovi's gold ruler
        return '<svg class="jmv-type-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="1.5" y="5.5" width="13" height="5" rx="0.5" fill="#f1bf63" stroke="#cd8500" stroke-width="1"/><path d="M4 5.5v2M6.5 5.5v3M9 5.5v2M11.5 5.5v3" stroke="#cd8500" stroke-width="0.9"/></svg>';
      // nominal: jamovi's three balls (two blue + one gold)
      return '<svg class="jmv-type-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="5.5" cy="6.7" r="3.1" fill="#a9c6f2" stroke="#226ddd" stroke-width="1"/><circle cx="10.5" cy="6.7" r="3.1" fill="#6b9de8" stroke="#226ddd" stroke-width="1"/><circle cx="8" cy="10.6" r="3.1" fill="#f1bf63" stroke="#bf7c00" stroke-width="1"/></svg>';
    }

    // Jamovi analysis ribbon icons (16×16 line SVGs)
    var JAMOVI_ICONS = {
      descriptives: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="9" width="3" height="5" rx=".5"/><rect x="6.5" y="6" width="3" height="8" rx=".5"/><rect x="11" y="3" width="3" height="11" rx=".5"/></svg>',
      frequencies: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="2" width="5" height="5" rx=".5"/><rect x="9" y="2" width="5" height="5" rx=".5"/><rect x="2" y="9" width="5" height="5" rx=".5"/><rect x="9" y="9" width="5" height="5" rx=".5"/></svg>',
      ttest_ind: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><path d="M2 3h6M5 3v10M10 5h4M12 5v6" stroke-linecap="round"/></svg>',
      ttest_paired: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><path d="M2 3h6M5 3v10M10 5h4M12 5v6" stroke-linecap="round"/><path d="M9 13.5c.8 0 1.4-.3 1.4-.3" stroke-linecap="round"/></svg>',
      correlation: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><circle cx="4" cy="11" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="7" cy="7" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="10" cy="5" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="13" cy="3" r="1.2" fill="#2b3a55" stroke="none"/><path d="M3 12.5l10-10" stroke-linecap="round"/></svg>',
      lin_reg: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><circle cx="4" cy="10" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="7" cy="8" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="10" cy="6" r="1.2" fill="#2b3a55" stroke="none"/><circle cx="13" cy="4" r="1.2" fill="#2b3a55" stroke="none"/><path d="M2.5 11.5l11-9" stroke-linecap="round"/></svg>',
      log_reg: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><path d="M2 13c1-1 1.5-4 3-5.5S8.5 5 10 4s2.5-1.5 4-1" stroke-linecap="round"/></svg>',
      anova_oneway: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="7" width="3" height="7" rx=".5"/><rect x="6.5" y="4" width="3" height="10" rx=".5"/><rect x="11" y="9" width="3" height="5" rx=".5"/></svg>',
      contingency: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="2" width="12" height="12" rx=".5"/><path d="M8 2v12M2 8h12"/></svg>',
      ttest_one: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><path d="M2 3h6M5 3v10" stroke-linecap="round"/><circle cx="12" cy="8" r="3" stroke-width="1.3"/></svg>',
      gof: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="2" width="12" height="12" rx=".5"/><path d="M8 2v12M2 8h12"/><path d="M5 5l2 2M11 5l-2 2" stroke-linecap="round"/></svg>',
      kruskal: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="#2b3a55" stroke-width="1.3"><rect x="2" y="7" width="3" height="7" rx=".5"/><rect x="6.5" y="4" width="3" height="10" rx=".5"/><rect x="11" y="9" width="3" height="5" rx=".5"/><path d="M2 6.5h3M6.5 3.5h3M11 8.5h3" stroke-linecap="round"/></svg>'
    };

    // Jamovi ribbon CATEGORY icons (16×16 line SVGs, stroke currentColor ~1.5)
    var JAMOVI_CAT_ICONS = {
      exploration: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="9" width="3" height="5" rx=".5"/><rect x="5.5" y="6" width="3" height="8" rx=".5"/><rect x="10" y="3" width="3" height="11" rx=".5"/><circle cx="12.5" cy="2" r="2" stroke-width="1.4"/><path d="M14.5 4l1.5 1.5" stroke-linecap="round"/></svg>',
      ttests: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 2h6M6 2v12" stroke-linecap="round"/><path d="M10 4h4M12 4v8" stroke-linecap="round"/></svg>',
      anova: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="6" width="3" height="8" rx=".5"/><rect x="6.5" y="2" width="3" height="12" rx=".5"/><rect x="11.5" y="8" width="3" height="6" rx=".5"/></svg>',
      regression: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="3.5" cy="11.5" r="1.2" fill="currentColor" stroke="none"/><circle cx="6.5" cy="8.5" r="1.2" fill="currentColor" stroke="none"/><circle cx="9.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/><circle cx="12.5" cy="4.5" r="1.2" fill="currentColor" stroke="none"/><path d="M2 13l12-10" stroke-linecap="round"/></svg>',
      frequencies: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="1.5" width="5.5" height="5.5" rx=".5"/><rect x="9" y="1.5" width="5.5" height="5.5" rx=".5"/><rect x="1.5" y="9" width="5.5" height="5.5" rx=".5"/><rect x="9" y="9" width="5.5" height="5.5" rx=".5"/></svg>'
    };

    // Open a jamovi analysis dialog from the spec registry
    function openJamoviAnalysis(id) {
      var spec = JAMOVI_ANALYSES[id];
      if (!spec) { alert(T('Analyse ikke funnet: {id}', { id: id })); return; }

      var vars = jamoviVariables();
      var assignments = {};
      spec.roles.forEach(function(r) { assignments[r.key] = []; });
      var activeRoleKey = spec.roles[0] ? spec.roles[0].key : null;
      var optsObj = {};

      // Build dialog DOM
      var backdrop = document.createElement('div');
      backdrop.className = 'jmv-dialog-backdrop';

      var dialog = document.createElement('div');
      dialog.className = 'jmv-dialog';
      dialog.setAttribute('role', 'dialog');
      dialog.setAttribute('aria-modal', 'true');

      var head = document.createElement('div');
      head.className = 'jmv-dialog-head';
      head.textContent = spec.title;
      dialog.appendChild(head);

      var body = document.createElement('div');
      body.className = 'jmv-dialog-body';
      dialog.appendChild(body);

      var foot = document.createElement('div');
      foot.className = 'jmv-dialog-foot';
      dialog.appendChild(foot);

      backdrop.appendChild(dialog);

      if (!vars.length) {
        // No dataset
        var msg = document.createElement('p');
        msg.style.cssText = 'color:#b91c1c; padding:8px 0;';
        msg.textContent = T('Lag/importer data først (kjør et datasett)');
        body.appendChild(msg);
      } else {
        var typeOf = {}; vars.forEach(function(v){ typeOf[v.name] = v.type; });
        var selectedVar = null; // currently highlighted source variable

        // LEFT: source variable list (shows only UNASSIGNED variables)
        var varlistDiv = document.createElement('div');
        varlistDiv.className = 'jmv-varlist';
        var varlistLabel = document.createElement('div');
        varlistLabel.className = 'jmv-role-label';
        varlistLabel.textContent = T('Variabler');
        varlistDiv.appendChild(varlistLabel);
        var varFilter = '';
        var search = document.createElement('input');
        search.type = 'text'; search.className = 'jmv-var-search'; search.placeholder = T('Søk variabel…');
        search.addEventListener('input', function(){ varFilter = search.value.toLowerCase(); refreshVarList(); });
        varlistDiv.appendChild(search);
        var ul = document.createElement('ul');
        varlistDiv.appendChild(ul);
        body.appendChild(varlistDiv);

        // RIGHT: roles, each with a ► arrow + assignment box
        var rolesDiv = document.createElement('div');
        rolesDiv.className = 'jmv-roles';
        body.appendChild(rolesDiv);
        var roleBoxEls = {};
        spec.roles.forEach(function(roleSpec){
          var lbl = document.createElement('div');
          lbl.className = 'jmv-role-label';
          lbl.textContent = roleSpec.label;
          rolesDiv.appendChild(lbl);
          var row = document.createElement('div');
          row.className = 'jmv-role-row';
          var arrow = document.createElement('button');
          arrow.type = 'button';
          arrow.className = 'jmv-arrow';
          arrow.innerHTML = '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M5 3l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
          arrow.title = T('Legg til valgt variabel');
          arrow.addEventListener('click', function(){
            if (!selectedVar) return;
            var t = typeOf[selectedVar];
            if (roleSpec.types && roleSpec.types.length && roleSpec.types.indexOf(t) === -1) {
              alert(T('Denne rollen krever: {types}. Variabel «{v}» er {t}.', { types: roleSpec.types.join(', '), v: selectedVar, t: t }));
              return;
            }
            if (!roleSpec.multiple) {
              // single-value role: return any existing occupant to the pool
              assignments[roleSpec.key] = [];
            }
            if (assignments[roleSpec.key].indexOf(selectedVar) === -1) assignments[roleSpec.key].push(selectedVar);
            selectedVar = null;
            refreshAll();
          });
          var box = document.createElement('ul');
          box.className = 'jmv-rolebox' + (roleSpec.key === activeRoleKey ? ' active' : '');
          box.dataset.rolekey = roleSpec.key;
          box.addEventListener('click', function(){ activeRoleKey = roleSpec.key; refreshAll(); });
          roleBoxEls[roleSpec.key] = box;
          row.appendChild(arrow);
          row.appendChild(box);
          rolesDiv.appendChild(row);
        });

        function assignedSet(){ var s = {}; spec.roles.forEach(function(r){ (assignments[r.key]||[]).forEach(function(v){ s[v]=true; }); }); return s; }

        function refreshVarList(){
          ul.innerHTML = '';
          var assigned = assignedSet();
          vars.forEach(function(v){
            if (assigned[v.name]) return; // moved into a role
            if (varFilter && v.name.toLowerCase().indexOf(varFilter) === -1) return;
            var li = document.createElement('li');
            li.innerHTML = jamoviTypeIcon(v.type) + '<span class="jmv-var-name">' + M.escapeHtml(v.name) + '</span>';
            li.dataset.varname = v.name; li.dataset.vartype = v.type;
            if (selectedVar === v.name) li.className = 'jmv-selected';
            li.addEventListener('click', function(){ selectedVar = (selectedVar === v.name) ? null : v.name; refreshVarList(); });
            // double-click → assign to first compatible role
            li.addEventListener('dblclick', function(){
              // assign to the ACTIVE role box if it accepts this type, else the first compatible role
              var typeOk = function(r){ return !r.types || !r.types.length || r.types.indexOf(v.type) !== -1; };
              var active = spec.roles.filter(function(r){ return r.key === activeRoleKey; })[0];
              var rs = (active && typeOk(active)) ? active : spec.roles.filter(typeOk)[0];
              if (!rs) return;
              if (!rs.multiple) assignments[rs.key] = [];
              if (assignments[rs.key].indexOf(v.name) === -1) assignments[rs.key].push(v.name);
              selectedVar = null; refreshAll();
            });
            ul.appendChild(li);
          });
        }
        function refreshRoles(){
          spec.roles.forEach(function(rs){
            var box = roleBoxEls[rs.key];
            box.className = 'jmv-rolebox' + (rs.key === activeRoleKey ? ' active' : '');
            box.innerHTML = '';
            (assignments[rs.key] || []).forEach(function(varname){
              var li = document.createElement('li');
              li.innerHTML = jamoviTypeIcon(typeOf[varname]) + '<span class="jmv-var-name">' + M.escapeHtml(varname) + '</span><span class="jmv-remove">✕</span>';
              li.title = T('Klikk for å fjerne');
              li.addEventListener('click', function(e){ e.stopPropagation(); assignments[rs.key] = assignments[rs.key].filter(function(x){ return x !== varname; }); refreshAll(); });
              box.appendChild(li);
            });
          });
        }
        function refreshAll(){ refreshVarList(); refreshRoles(); }
        refreshAll();

        if (spec.optionSections && spec.optionSections.length && vars.length) {
          spec.optionSections.forEach(function(sec, sIdx){
            // jamovi shows the first (primary) section open, the rest collapsed
            var collapsed = (sec.collapsed !== undefined) ? sec.collapsed : true;
            var secEl = document.createElement('div'); secEl.className = 'jmv-section' + (collapsed ? ' collapsed' : '');
            var hdr = document.createElement('div'); hdr.className = 'jmv-section-hdr';
            hdr.innerHTML = '<span class="jmv-section-caret">▾</span><span class="jmv-section-title">' + sec.title + '</span>';
            hdr.addEventListener('click', function(){ secEl.classList.toggle('collapsed'); });
            var bodyEl = document.createElement('div'); bodyEl.className = 'jmv-section-body';
            sec.groups.forEach(function(g){
              var gEl = document.createElement('div'); gEl.className = 'jmv-opt-group';
              if (g.title) { var gh = document.createElement('div'); gh.className = 'jmv-opt-grouphdr'; gh.textContent = g.title; gEl.appendChild(gh); }
              g.items.forEach(function(it){
                optsObj[it.key] = Array.isArray(it.default) ? it.default.slice() : it.default;
                if (it.type === 'check') {
                  var lab = document.createElement('label'); lab.className = 'jmv-opt-item';
                  var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!it.default;
                  cb.addEventListener('change', function(){ optsObj[it.key] = cb.checked; });
                  lab.appendChild(cb); lab.appendChild(document.createTextNode(' ' + it.label)); gEl.appendChild(lab);
                } else if (it.type === 'radio') {
                  it.choices.forEach(function(c){
                    var lab = document.createElement('label'); lab.className = 'jmv-opt-item';
                    var rb = document.createElement('input'); rb.type = 'radio'; rb.name = 'jmvopt_' + it.key; rb.value = c.value; rb.checked = (c.value === it.default);
                    rb.addEventListener('change', function(){ if (rb.checked) optsObj[it.key] = c.value; });
                    lab.appendChild(rb); lab.appendChild(document.createTextNode(' ' + c.label)); gEl.appendChild(lab);
                  });
                } else if (it.type === 'select') {
                  var wrap = document.createElement('label'); wrap.className = 'jmv-opt-item';
                  if (it.label) wrap.appendChild(document.createTextNode(it.label + ' '));
                  var sel = document.createElement('select'); sel.className = 'jmv-opt-select';
                  it.choices.forEach(function(c){ var o = document.createElement('option'); o.value = c.value; o.textContent = c.label; if (c.value === it.default) o.selected = true; sel.appendChild(o); });
                  sel.addEventListener('change', function(){ optsObj[it.key] = sel.value; });
                  wrap.appendChild(sel); gEl.appendChild(wrap);
                }
              });
              bodyEl.appendChild(gEl);
            });
            secEl.appendChild(hdr); secEl.appendChild(bodyEl);
            dialog.insertBefore(secEl, foot);
          });
        }
      }

      // Buttons
      var closeBtn = document.createElement('button');
      closeBtn.textContent = T('Lukk');
      closeBtn.addEventListener('click', function() { document.body.removeChild(backdrop); });
      foot.appendChild(closeBtn);

      var runBtn = document.createElement('button');
      runBtn.className = 'primary';
      runBtn.textContent = T('Kjør');
      runBtn.addEventListener('click', async function() {
        var rcode = spec.buildR ? spec.buildR(assignments, optsObj) : null;
        var plots0 = spec.buildPlots ? (spec.buildPlots(assignments, optsObj) || []) : [];
        if (!rcode && !plots0.length) { alert(T('Velg variabler')); return; }
        document.body.removeChild(backdrop);
        // Log clean, idiomatic R (jamovi-style syntax) to the (hidden) input panel.
        if (M.appendToEditor) {
          var _clean = jamoviCleanSyntax(spec, assignments, optsObj);
          if (_clean) M.appendToEditor('# ' + spec.title + '\n' + _clean);
        }
        M.setStatus(M.rightStatus, T('Kjører analyse…'));
        try {
          await ensureJamoviDataInWebR();
          var shelter = await M.ensureWebRShelter();
          var card;
          if (rcode) {
            var robj = await shelter.evalR('tryCatch({' + rcode + '}, error=function(e) paste("ERROR:",conditionMessage(e)))');
            var res = await robj.toJs();
            var note = (typeof spec.note === 'function') ? spec.note(assignments, optsObj) : (spec.note || null);
            card = renderJamoviResult(spec.title, res, note);
          } else {
            card = jamoviTitleCard(spec.title); // plot-only (Figurer)
          }
          // jamovi-style plots: capture R graphics into THIS result's card (after the tables)
          if (spec.buildPlots) {
            var plots = plots0;
            for (var pi = 0; pi < plots.length; pi++) {
              try {
                var cap = await shelter.captureR(plots[pi].rCode, { captureGraphics: { width: 460, height: 320 } });
                if (cap.images && cap.images[0]) jamoviAppendPlot(plots[pi].title, cap.images[0], card.querySelector('div') || card);
                if (cap.cleanup) await cap.cleanup();
              } catch (pe) { /* skip a single failed plot */ }
            }
          }
          M.setStatus(M.rightStatus, '');
        } catch(err) {
          M.outputArea.innerHTML = '<pre class="error">' + T('Analysefeil: {msg}', { msg: err.message || String(err) }) + '</pre>';
          M.setStatus(M.rightStatus, '');
        }
      });
      foot.appendChild(runBtn);

      // Close on backdrop click
      backdrop.addEventListener('click', function(e) {
        if (e.target === backdrop) document.body.removeChild(backdrop);
      });

      document.body.appendChild(backdrop);
    }

    // Inject ribbon DOM
    var bar = M.getModeGuiBar();
    if (bar && !document.getElementById('jamoviRibbon')) {
      var rib = document.createElement('div');
      rib.id = 'jamoviRibbon'; rib.className = 'jamovi-ribbon'; rib.setAttribute('data-mode-gui','jamovi'); rib.setAttribute('aria-label','jamovi');
      var catGroups = '<div class="jmv-group"><button type="button" class="jmv-cat" data-cat="exploration">Exploration</button>\n            <div class="jmv-menu"><button type="button" data-an="descriptives">Descriptives</button><button type="button" data-an="frequencies">Frequencies</button></div></div>\n          <div class="jmv-group"><button type="button" class="jmv-cat" data-cat="ttests">T-Tests</button>\n            <div class="jmv-menu"><button type="button" data-an="ttest_ind">Independent Samples T-Test</button><button type="button" data-an="ttest_paired">Paired Samples T-Test</button><button type="button" data-an="ttest_one">One Sample T-Test</button></div></div>\n          <div class="jmv-group"><button type="button" class="jmv-cat" data-cat="anova">ANOVA</button>\n            <div class="jmv-menu"><button type="button" data-an="anova_oneway">One-Way ANOVA</button><button type="button" data-an="kruskal">Kruskal-Wallis</button></div></div>\n          <div class="jmv-group"><button type="button" class="jmv-cat" data-cat="regression">Regression</button>\n            <div class="jmv-menu"><button type="button" data-an="correlation">Correlation Matrix</button><button type="button" data-an="lin_reg">Linear Regression</button><button type="button" data-an="log_reg">Logistic Regression</button></div></div>\n          <div class="jmv-group"><button type="button" class="jmv-cat" data-cat="frequencies">Frequencies</button>\n            <div class="jmv-menu"><button type="button" data-an="contingency">Contingency Tables (χ²)</button><button type="button" data-an="gof">χ² Goodness of Fit</button></div></div>';
      rib.innerHTML =
        '<div class="jmv-tabbar">'
        + '<button type="button" class="jmv-hamburger" title="Meny" aria-label="Meny">☰</button>'
        + '<button type="button" class="jmv-tab" data-jtab="variables">Variabler</button>'
        + '<button type="button" class="jmv-tab" data-jtab="data">Data</button>'
        + '<button type="button" class="jmv-tab active" data-jtab="analyses">Analyser</button>'
        + '<button type="button" class="jmv-tab" data-jtab="figures">Figurer</button>'
        + '<button type="button" class="jmv-tab" data-jtab="edit">Rediger</button>'
        + '<div class="jmv-app-menu" hidden><button type="button" data-jaction="examples">' + T('Åpne eksempeldatasett…') + '</button><button type="button" data-jaction="clear">' + T('Tøm resultater') + '</button><button type="button" data-jaction="about">' + T('Om jamovi-modus') + '</button></div>'
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
        +   '<button type="button" class="jmv-ribbon-btn" data-an="fig_histogram">' + (JAMOVI_ICONS.descriptives||'') + '<span>Histogram</span></button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-an="fig_boxplot"><span>Box Plot</span></button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-an="fig_barplot">' + (JAMOVI_ICONS.frequencies||'') + '<span>Bar Plot</span></button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-an="fig_scatter">' + (JAMOVI_ICONS.correlation||'') + '<span>Scatter Plot</span></button>'
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
        b.innerHTML = (JAMOVI_ICONS[an] || '') + '<span>' + b.textContent + '</span>';
        b.addEventListener('click', function(){ apanel.querySelectorAll('.jmv-group').forEach(function(x){x.classList.remove('open');}); openJamoviAnalysis(an); });
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
      // Figurer ribbon: plot buttons open a plot dialog
      rib.querySelectorAll('.jmv-ribbon-btn[data-an]').forEach(function(b){
        b.addEventListener('click', function(){ openJamoviAnalysis(b.getAttribute('data-an')); });
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
