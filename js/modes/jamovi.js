(function(){ 'use strict'; var M = window.M2PY;
    // Variables from the active dataset
    function jamoviVariables() {
      var name = window.activeDatasetName;
      if (!name || !window.lastDatasetInfo || !window.lastDatasetInfo[name]) return [];
      var info = window.lastDatasetInfo[name];
      var cols = info.columns || [];
      var dtypes = info.dtypes || {};
      return cols.map(function(c) {
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
      var b64 = String(await py.runPythonAsync(
        'import base64 as _b, pandas as _pd\n' +
        '_df = e.datasets[e.active_name].copy()\n' +
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
      descriptives: {
        id: 'descriptives', title: 'Descriptives',
        roles: [{ key: 'vars', label: 'Variables', types: ['numeric'], multiple: true }, { key: 'split', label: 'Split by', types: ['nominal'], multiple: false }],
        optionSections:[{ title:'Statistics', groups:[
          { title:'Sample Size', items:[{key:'N',type:'check',label:'N',default:true},{key:'Missing',type:'check',label:'Missing',default:true}] },
          { title:'Central Tendency', items:[{key:'Mean',type:'check',label:'Mean',default:true},{key:'Median',type:'check',label:'Median',default:true},{key:'Mode',type:'check',label:'Mode',default:false},{key:'Sum',type:'check',label:'Sum',default:false}] },
          { title:'Dispersion', items:[{key:'SD',type:'check',label:'Std. deviation',default:true},{key:'Variance',type:'check',label:'Variance',default:false},{key:'Range',type:'check',label:'Range',default:false},{key:'Min',type:'check',label:'Minimum',default:true},{key:'Max',type:'check',label:'Maximum',default:true},{key:'SE',type:'check',label:'Std. error',default:false}] },
          { title:'Distribution', items:[{key:'Skewness',type:'check',label:'Skewness',default:false},{key:'Kurtosis',type:'check',label:'Kurtosis',default:false}] }
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
          var allKeys = ['N','Missing','Mean','Median','Mode','Sum','SD','Variance','Range','Min','Max','SE','Skewness','Kurtosis'];
          var want = allKeys.filter(function(k){ return opts && opts[k]; });
          if(!want.length) want = ['N','Mean','SD'];
          var rwant = 'c('+want.map(function(k){return JSON.stringify(k);}).join(',')+')';
          var rsplit = splitV ? JSON.stringify(splitV) : 'NULL';
          return "local({\n"
           +"vars<-"+rv+"; want<-"+rwant+"; splitv<-"+rsplit+";\n"
           +"Mode<-function(x){x<-x[!is.na(x)]; if(!length(x)) return(NA); ux<-unique(x); ux[which.max(tabulate(match(x,ux)))]}\n"
           +"lbl<-c(N='N',Missing='Missing',Mean='Mean',Median='Median',Mode='Mode',Sum='Sum',SD='Std. deviation',Variance='Variance',Range='Range',Min='Minimum',Max='Maximum',SE='Std. error',Skewness='Skewness',Kurtosis='Kurtosis')\n"
           +"statRow<-function(v,x,lev){ xc<-x[!is.na(x)]; n<-length(xc); o<-list()\n"
           +" if(!is.null(lev)) o[['Group']]<-lev\n"
           +" o[['Variable']]<-v\n"
           +" f<-list(N=function() n, Missing=function() sum(is.na(x)), Mean=function() mean(xc), Median=function() median(xc), Mode=function() Mode(xc), Sum=function() sum(xc), SD=function() sd(xc), Variance=function() var(xc), Range=function() max(xc)-min(xc), Min=function() min(xc), Max=function() max(xc), SE=function() sd(xc)/sqrt(n), Skewness=function(){m<-mean(xc); s<-sd(xc); (sum((xc-m)^3)/n)/s^3}, Kurtosis=function(){m<-mean(xc); s<-sd(xc); (sum((xc-m)^4)/n)/s^4-3})\n"
           +" for(k in want) o[[lbl[[k]]]]<-tryCatch(f[[k]](), error=function(e) NA)\n"
           +" as.data.frame(o, check.names=FALSE, stringsAsFactors=FALSE) }\n"
           +"rows<-list()\n"
           +"if(is.null(splitv)){ for(v in vars) rows[[length(rows)+1]]<-statRow(v, data[[v]], NULL) }\n"
           +"else { g<-as.character(data[[splitv]]); levs<-sort(unique(g[!is.na(g)])); for(lv in levs) for(v in vars) rows[[length(rows)+1]]<-statRow(v, data[[v]][!is.na(g) & g==lv], lv) }\n"
           +"do.call(rbind, rows) })";
        }
      },

      frequencies: { id:'frequencies', title:'Frequencies',
        roles:[{key:'var', label:'Variable', types:['nominal','numeric'], multiple:false}],
        buildR:function(a){ var v=a.var&&a.var[0]; if(!v) return null; var rv=JSON.stringify(v);
          return "local({ t<-table(data[["+rv+"]]); n<-sum(t); data.frame(Level=names(t), Counts=as.integer(t), Percent=round(100*as.integer(t)/n,1), Cumulative=round(100*cumsum(as.integer(t))/n,1), check.names=FALSE, stringsAsFactors=FALSE) })"; } },

      ttest_ind: { id:'ttest_ind', title:'Independent Samples T-Test',
        roles:[{key:'dv',label:'Dependent Variable',types:['numeric'],multiple:false},{key:'group',label:'Grouping Variable',types:['nominal'],multiple:false}],
        optionSections:[
          { title:'Tests', groups:[{ items:[{key:'test',type:'radio',choices:[{value:'student',label:"Student's"},{value:'welch',label:"Welch's"}],default:'welch'},{key:'mwu',type:'check',label:'Mann-Whitney U',default:false}] }] },
          { title:'Additional Statistics', groups:[{ items:[{key:'effsize',type:'check',label:"Effect size (Cohen's d)",default:false}] }] }
        ],
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
          if (mwu) {
            base += " w<-wilcox.test(y~f); mwdf<-data.frame('Test'='Mann-Whitney U', 'W'=unname(w$statistic), p=w$p.value, check.names=FALSE, stringsAsFactors=FALSE); list('T-Test'=out, 'Mann-Whitney U'=mwdf) })";
          } else {
            base += " out })";
          }
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
        optionSections:[{ title:'Correlation Coefficients', groups:[{ items:[{key:'method',type:'radio',choices:[{value:'pearson',label:'Pearson'},{value:'spearman',label:'Spearman'},{value:'kendall',label:"Kendall's tau-b"}],default:'pearson'}] }] }],
        buildR:function(a,opts){ var v=a.vars||[]; if(v.length<2) return null; var rv='c('+v.map(function(x){return JSON.stringify(x);}).join(',')+')';
          var method = (opts&&opts.method) ? opts.method : 'pearson';
          return "local({ vars<-"+rv+"; m<-cor(data[,vars,drop=FALSE], use='pairwise.complete.obs', method="+JSON.stringify(method)+"); d<-as.data.frame(round(m,3), check.names=FALSE); cbind(Variable=rownames(m), d) })"; } },

      lin_reg: { id:'lin_reg', title:'Linear Regression',
        roles:[{key:'dv',label:'Dependent Variable',types:['numeric'],multiple:false},{key:'covs',label:'Covariates',types:['numeric'],multiple:true}],
        optionSections:[{ title:'Model Coefficients', groups:[{ items:[
          {key:'ci',type:'check',label:'Confidence interval (95%)',default:false}
        ]}]}],
        buildR:function(a, opts){ var dv=a.dv&&a.dv[0], c=a.covs||[]; if(!dv||!c.length) return null; var rc='c('+c.map(function(x){return JSON.stringify(x);}).join(',')+')';
          var ciR = (opts && opts.ci) ? "ci<-suppressMessages(confint(m)); co[['95% CI Lower']]<-ci[,1]; co[['95% CI Upper']]<-ci[,2];\n" : "";
          return "local({ dv<-"+JSON.stringify(dv)+"; covs<-"+rc+"; d2<-data[,c(dv,covs),drop=FALSE]; names(d2)<-make.names(names(d2)); ndv<-make.names(dv); nco<-make.names(covs); m<-lm(as.formula(paste(ndv,'~',paste(nco,collapse='+'))), data=d2); s<-summary(m); fit<-data.frame('R-squared'=s$r.squared,'Adj. R-squared'=s$adj.r.squared,'F'=unname(s$fstatistic[1]),'df1'=unname(s$fstatistic[2]),'df2'=unname(s$fstatistic[3]),'p'=unname(pf(s$fstatistic[1],s$fstatistic[2],s$fstatistic[3],lower.tail=FALSE)),check.names=FALSE); co<-as.data.frame(s$coefficients,check.names=FALSE); co<-cbind(Term=rownames(co),co);\n"+ciR+"list('Model Fit'=fit,'Coefficients'=co) })"; } },

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
          { title:'Effect Size', groups:[{ items:[{key:'eta',type:'check',label:'η² (eta-squared)',default:true},{key:'omega',type:'check',label:'ω² (omega-squared)',default:false}] }] }
        ],
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
          // Build return value
          var rReturn = needES ? "list('ANOVA'=anovaT,'Effect Size'=es)" : "anovaT";
          return rBase + rWelch + rES + rReturn + " })"; } },

      contingency: { id:'contingency', title:'Contingency Tables (χ²)',
        roles:[{key:'rows',label:'Rows',types:['nominal'],multiple:false},{key:'cols',label:'Columns',types:['nominal'],multiple:false}],
        buildR:function(a){ var r=a.rows&&a.rows[0], c=a.cols&&a.cols[0]; if(!r||!c) return null;
          return "local({ t<-table(data[["+JSON.stringify(r)+"]], data[["+JSON.stringify(c)+"]]); ch<-suppressWarnings(chisq.test(t)); cnt<-as.data.frame.matrix(t,check.names=FALSE); cnt<-cbind(' '=rownames(cnt),cnt); test<-data.frame('Chi-squared'=unname(ch$statistic),'df'=unname(ch$parameter),'p'=ch$p.value,check.names=FALSE); list('Counts'=cnt,'Chi-squared Test'=test) })"; } },

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
    function jamoviAppendPlot(title, bitmap) {
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
      M.outputArea.appendChild(block);
    }

    // Render a structured webR toJs() result as jamovi-style tables
    function renderJamoviResult(title, struct) {
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
            td.textContent = (col.type === 'double' || col.type === 'integer') ? fmtNum(val) : (val === null ? 'NA' : String(val));
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

      M.outputArea.innerHTML = '';
      M.outputArea.appendChild(wrap);
    }

    // Jamovi measure-type icons
    function jamoviTypeIcon(type) {
      if (type === 'numeric')
        return '<svg class="jmv-type-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="1.5" y="5" width="13" height="6" rx="1" fill="none" stroke="#1f6feb" stroke-width="1.2"/><path d="M4.5 5v2.5M7 5v3.5M9.5 5v2.5M12 5v3.5" stroke="#1f6feb" stroke-width="1"/></svg>';
      return '<svg class="jmv-type-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="5" cy="6" r="2.4" fill="#e8590c"/><circle cx="11" cy="6" r="2.4" fill="#1f6feb"/><circle cx="8" cy="11" r="2.4" fill="#2f9e44"/></svg>';
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
      if (!spec) { alert('Analyse ikke funnet: ' + id); return; }

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
        msg.textContent = 'Lag/importer data først (kjør et datasett)';
        body.appendChild(msg);
      } else {
        var typeOf = {}; vars.forEach(function(v){ typeOf[v.name] = v.type; });
        var selectedVar = null; // currently highlighted source variable

        // LEFT: source variable list (shows only UNASSIGNED variables)
        var varlistDiv = document.createElement('div');
        varlistDiv.className = 'jmv-varlist';
        var varlistLabel = document.createElement('div');
        varlistLabel.className = 'jmv-role-label';
        varlistLabel.textContent = 'Variabler';
        varlistDiv.appendChild(varlistLabel);
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
          arrow.title = 'Legg til valgt variabel';
          arrow.addEventListener('click', function(){
            if (!selectedVar) return;
            var t = typeOf[selectedVar];
            if (roleSpec.types && roleSpec.types.length && roleSpec.types.indexOf(t) === -1) {
              alert('Denne rollen krever: ' + roleSpec.types.join(', ') + '. Variabel «' + selectedVar + '» er ' + t + '.');
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
            var li = document.createElement('li');
            li.innerHTML = jamoviTypeIcon(v.type) + '<span class="jmv-var-name">' + M.escapeHtml(v.name) + '</span>';
            li.dataset.varname = v.name; li.dataset.vartype = v.type;
            if (selectedVar === v.name) li.className = 'jmv-selected';
            li.addEventListener('click', function(){ selectedVar = (selectedVar === v.name) ? null : v.name; refreshVarList(); });
            // double-click → assign to first compatible role
            li.addEventListener('dblclick', function(){
              var rs = spec.roles.filter(function(r){ return !r.types || !r.types.length || r.types.indexOf(v.type) !== -1; })[0];
              if (!rs) return;
              selectedVar = v.name;
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
              li.title = 'Klikk for å fjerne';
              li.addEventListener('click', function(e){ e.stopPropagation(); assignments[rs.key] = assignments[rs.key].filter(function(x){ return x !== varname; }); refreshAll(); });
              box.appendChild(li);
            });
          });
        }
        function refreshAll(){ refreshVarList(); refreshRoles(); }
        refreshAll();

        if (spec.optionSections && spec.optionSections.length && vars.length) {
          spec.optionSections.forEach(function(sec){
            var secEl = document.createElement('div'); secEl.className = 'jmv-section' + (sec.collapsed ? ' collapsed' : '');
            var hdr = document.createElement('div'); hdr.className = 'jmv-section-hdr';
            hdr.innerHTML = '<span class="jmv-section-caret">▾</span><span>' + sec.title + '</span>';
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
      closeBtn.textContent = 'Lukk';
      closeBtn.addEventListener('click', function() { document.body.removeChild(backdrop); });
      foot.appendChild(closeBtn);

      var runBtn = document.createElement('button');
      runBtn.className = 'primary';
      runBtn.textContent = 'Kjør';
      runBtn.addEventListener('click', async function() {
        var rcode = spec.buildR(assignments, optsObj);
        if (!rcode) { alert('Velg variabler'); return; }
        document.body.removeChild(backdrop);
        M.setStatus(M.rightStatus, 'Kjører analyse…');
        try {
          await ensureJamoviDataInWebR();
          var shelter = await M.ensureWebRShelter();
          var robj = await shelter.evalR('tryCatch({' + rcode + '}, error=function(e) paste("ERROR:",conditionMessage(e)))');
          var res = await robj.toJs();
          renderJamoviResult(spec.title, res);
          // jamovi-style plots: capture R graphics into the output (after the tables)
          if (spec.buildPlots) {
            var plots = spec.buildPlots(assignments, optsObj) || [];
            for (var pi = 0; pi < plots.length; pi++) {
              try {
                var cap = await shelter.captureR(plots[pi].rCode, { captureGraphics: { width: 460, height: 320 } });
                if (cap.images && cap.images[0]) jamoviAppendPlot(plots[pi].title, cap.images[0]);
                if (cap.cleanup) await cap.cleanup();
              } catch (pe) { /* skip a single failed plot */ }
            }
          }
          M.setStatus(M.rightStatus, '');
        } catch(err) {
          M.outputArea.innerHTML = '<pre class="error">Analysefeil: ' + (err.message || String(err)) + '</pre>';
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
      rib.id = 'jamoviRibbon'; rib.className = 'jamovi-ribbon'; rib.setAttribute('data-mode-gui','jamovi'); rib.setAttribute('aria-label','jamovi analyser');
      rib.innerHTML = '<div class="jmv-group"><button type="button" class="jmv-cat" data-cat="exploration">Exploration</button>\n            <div class="jmv-menu"><button type="button" data-an="descriptives">Descriptives</button><button type="button" data-an="frequencies">Frequencies</button></div></div>\n          <div class="jmv-group"><button type="button" class="jmv-cat" data-cat="ttests">T-Tests</button>\n            <div class="jmv-menu"><button type="button" data-an="ttest_ind">Independent Samples T-Test</button><button type="button" data-an="ttest_paired">Paired Samples T-Test</button><button type="button" data-an="ttest_one">One Sample T-Test</button></div></div>\n          <div class="jmv-group"><button type="button" class="jmv-cat" data-cat="anova">ANOVA</button>\n            <div class="jmv-menu"><button type="button" data-an="anova_oneway">One-Way ANOVA</button><button type="button" data-an="kruskal">Kruskal-Wallis</button></div></div>\n          <div class="jmv-group"><button type="button" class="jmv-cat" data-cat="regression">Regression</button>\n            <div class="jmv-menu"><button type="button" data-an="correlation">Correlation Matrix</button><button type="button" data-an="lin_reg">Linear Regression</button><button type="button" data-an="log_reg">Logistic Regression</button></div></div>\n          <div class="jmv-group"><button type="button" class="jmv-cat" data-cat="frequencies">Frequencies</button>\n            <div class="jmv-menu"><button type="button" data-an="contingency">Contingency Tables (χ²)</button><button type="button" data-an="gof">χ² Goodness of Fit</button></div></div>';
      bar.appendChild(rib);
    }
    // Wire ribbon (initJamoviRibbon logic, inline not as IIFE)
    (function initJamoviRibbon() {
      var rib = document.getElementById('jamoviRibbon');
      if (!rib) return;
      rib.querySelectorAll('.jmv-cat').forEach(function(btn){ var c = btn.getAttribute('data-cat'); btn.innerHTML = (JAMOVI_CAT_ICONS[c]||'') + '<span>' + btn.textContent + '</span>'; });
      rib.querySelectorAll('.jmv-cat').forEach(function(btn){
        btn.addEventListener('click', function(e){
          e.stopPropagation();
          var g = btn.parentElement, wasOpen = g.classList.contains('open');
          rib.querySelectorAll('.jmv-group').forEach(function(x){ x.classList.remove('open'); });
          if (!wasOpen) g.classList.add('open');
        });
      });
      rib.querySelectorAll('.jmv-menu button[data-an]').forEach(function(b){
        var an = b.getAttribute('data-an');
        b.innerHTML = (JAMOVI_ICONS[an] || '') + '<span>' + b.textContent + '</span>';
        b.addEventListener('click', function(){ rib.querySelectorAll('.jmv-group').forEach(function(x){x.classList.remove('open');}); openJamoviAnalysis(an); });
      });
      document.addEventListener('click', function(){ rib.querySelectorAll('.jmv-group').forEach(function(x){x.classList.remove('open');}); });
    })();

    M.registerMode({ id:'jamovi', label:'jamovi', hlConfig:M.R_HL_CFG, handleTab:M.handleRTab, topGui:'jamovi', onActivate:function(){ if(!M.isWebRReady()) M.loadWebR(); M.updateModeGuiBar(); }, translate:{showsButton:false}, runSelf:async function(script,ctx){ await M.runHybridR(script, ctx.py, {showCommands:true}); } });
    M.updateModeGuiBar();
})();
