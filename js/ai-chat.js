    /* ===================================================================
       AI assistant — sidebar wiring + API calls
       =================================================================== */
    (function aiModule() {
      const LS_KEY_BASE = 'md_ai_api_base';
      const LS_KEY_APIKEY = 'md_ai_api_key';
      const LS_KEY_AIMODE = 'md_ai_mode';   // 'fast' | 'anvil'
      const DEFAULT_BASE = 'https://mdataapi.anvil.app';

      const state = {
        sending: false,
        history: [],   // {role, html|text, raw}
        get apiBase() { return (localStorage.getItem(LS_KEY_BASE) || DEFAULT_BASE).replace(/\/+$/, ''); },
        get apiKey()  { return localStorage.getItem(LS_KEY_APIKEY) || ''; },
        // AI mode: 'fast' = rask edge-funksjon, 'anvil' = full vurdering via Anvil-API
        get anvilMode() { return localStorage.getItem(LS_KEY_AIMODE) === 'anvil'; },
        set anvilMode(v) { localStorage.setItem(LS_KEY_AIMODE, v ? 'anvil' : 'fast'); },
      };

      const md = (window.markdownit ? window.markdownit({ breaks: true, linkify: true }) : null);

      const $ = (id) => document.getElementById(id);
      const dom = {};
      function cacheDom() {
        ['aiToggleBtn','aiSidebar','aiCloseBtn','aiSettingsBtn','aiClearBtn',
         'aiThread','aiInput','aiSendFastBtn','aiSendV2Btn','aiAbortBtn',
         'aiIncludeScript','menuAiMode',
         'aiSettingsBackdrop','aiCfgBaseUrl','aiCfgApiKey','aiCfgSave','aiCfgCancel',
         'aiCfgLoggedIn','aiCfgLoggedOut','aiCfgUserEmail','aiCfgUserMeta',
         'aiCfgLogout','aiCfgAdmin','aiCfgLogin',
         'sidebarRight','sidebarOpenTab','scriptInput'
        ].forEach(id => { dom[id] = $(id); });
        dom.containers = document.querySelectorAll('.container');
      }

      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({
          '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
        }[c]));
      }

      function setOpen(open) {
        if (open) {
          // Mutually exclusive with Datasett sidebar
          if (dom.sidebarRight && !dom.sidebarRight.classList.contains('collapsed')) {
            dom.sidebarRight.classList.add('collapsed');
            dom.containers.forEach(c => c.classList.remove('sidebar-open'));
          }
          // Always make sure the Datasett open-tab is reachable; the original
          // code uses a `.hidden` class to hide it while Datasett is open.
          if (dom.sidebarOpenTab) dom.sidebarOpenTab.classList.remove('hidden');
          dom.aiSidebar.classList.add('open');
          dom.aiSidebar.setAttribute('aria-hidden', 'false');
          dom.containers.forEach(c => c.classList.add('ai-open'));
          dom.aiToggleBtn.classList.add('active');
          if (state.history.length === 0) renderEmpty();
          setTimeout(() => dom.aiInput.focus(), 60);
        } else {
          dom.aiSidebar.classList.remove('open');
          dom.aiSidebar.setAttribute('aria-hidden', 'true');
          dom.containers.forEach(c => c.classList.remove('ai-open'));
          dom.aiToggleBtn.classList.remove('active');
          // Make sure the Datasett tab is reachable after the AI panel goes away.
          if (dom.sidebarOpenTab && dom.sidebarRight && dom.sidebarRight.classList.contains('collapsed')) {
            dom.sidebarOpenTab.classList.remove('hidden');
          }
        }
      }
      function toggleOpen() { setOpen(!dom.aiSidebar.classList.contains('open')); }

      function renderEmpty() {
        dom.aiThread.innerHTML = '';
        const wrap = document.createElement('div');
        wrap.className = 'ai-empty';
        wrap.innerHTML = '<div class="ai-empty-title">Hei! Hva kan jeg hjelpe med?</div>' +
          '<div>Spør om en analyse, et skript, eller hva en kommando gjør.</div>' +
          '<div class="ai-empty-examples">' +
            '<button type="button" class="ai-empty-example" data-q="Vis sammendragsstatistikk for inntekt og kjønn">Vis sammendragsstatistikk for inntekt og kjønn</button>' +
            '<button type="button" class="ai-empty-example" data-q="What does reshape long do?">What does reshape long do?</button>' +
            '<button type="button" class="ai-empty-example" data-q="Hvilke variabler finnes for utdanning?">Hvilke variabler finnes for utdanning?</button>' +
          '</div>';
        dom.aiThread.appendChild(wrap);
        wrap.querySelectorAll('.ai-empty-example').forEach(btn => {
          btn.addEventListener('click', () => {
            dom.aiInput.value = btn.dataset.q;
            autoresize();
            sendMessage(true);
          });
        });
      }

      function appendUserMessage(text) {
        const wrap = document.createElement('div');
        wrap.className = 'ai-msg ai-msg-user';
        wrap.innerHTML = '<div class="ai-bubble"></div>';
        wrap.querySelector('.ai-bubble').textContent = text;
        dom.aiThread.appendChild(wrap);
        scrollToBottom();
      }

      function appendThinking() {
        const wrap = document.createElement('div');
        wrap.className = 'ai-msg ai-msg-assistant';
        wrap.innerHTML = '<div class="ai-thinking"><span class="ai-thinking-dot"></span><span class="ai-thinking-dot"></span><span class="ai-thinking-dot"></span><span style="margin-left:4px">Tenker…</span></div>';
        dom.aiThread.appendChild(wrap);
        scrollToBottom();
        return wrap;
      }

      function appendError(node, msg) {
        node.innerHTML = '';
        const err = document.createElement('div');
        err.className = 'ai-error';
        err.textContent = msg;
        node.appendChild(err);
        scrollToBottom();
      }

      function appendAssistantText(node, text, meta) {
        node.innerHTML = '';
        const bubble = document.createElement('div');
        bubble.className = 'ai-bubble';
        bubble.innerHTML = md ? md.render(text || '') : escapeHtml(text || '').replace(/\n/g, '<br>');
        bubble._rawMd = text || '';
        node.appendChild(bubble);
        if (meta) appendMeta(node, meta);
        attachCodeBlockActions(bubble);
        attachResponseInsertBar(node, text || '');
        scrollToBottom();
      }

      function appendAssistantScript(node, script, rationale, meta) {
        node.innerHTML = '';
        const bubble = document.createElement('div');
        bubble.className = 'ai-bubble';
        if (rationale) {
          const rationaleHtml = md ? md.render(rationale) : '<p>' + escapeHtml(rationale) + '</p>';
          bubble.innerHTML += rationaleHtml;
        }
        // Custom code-block markup with action buttons
        const cbWrap = document.createElement('div');
        cbWrap.className = 'ai-codeblock-wrap';
        const pre = document.createElement('pre');
        const code = document.createElement('code');
        code.textContent = script;
        pre.appendChild(code);
        cbWrap.appendChild(pre);
        const actions = document.createElement('div');
        actions.className = 'ai-codeblock-actions';
        actions.innerHTML =
          '<button type="button" class="ai-codeblock-btn" data-act="copy">📋 Kopier</button>';
        cbWrap.appendChild(actions);
        bubble.appendChild(cbWrap);
        actions.addEventListener('click', (e) => {
          const btn = e.target.closest('.ai-codeblock-btn');
          if (!btn) return;
          handleCodeAction(btn.dataset.act, script, btn);
        });
        // Validation warnings (unknown variables / commands / parse errors)
        const warning = renderValidationWarnings(meta && meta.validation);
        if (warning) bubble.appendChild(warning);
        node.appendChild(bubble);
        if (meta) appendMeta(node, meta);
        // Response-level "Sett inn" bar (synthesize markdown from rationale + code)
        const rawMd = (rationale ? rationale + '\n\n' : '') + '```microdata\n' + script + '\n```';
        bubble._rawMd = rawMd;
        attachResponseInsertBar(node, rawMd);
        scrollToBottom();
      }

      function renderValidationWarnings(validation) {
        if (!validation || validation.passed || !validation.errors || !validation.errors.length) {
          return null;
        }
        const wrap = document.createElement('div');
        wrap.className = 'ai-validation-warning';
        const title = document.createElement('div');
        title.className = 'ai-validation-warning-title';
        title.textContent = '⚠ Valideringsadvarsler';
        wrap.appendChild(title);

        const groups = { unknown_variable: [], unknown_command: [], parse: [], runtime: [], other: [] };
        for (const e of validation.errors) {
          const k = e.kind in groups ? e.kind : 'other';
          groups[k].push(e);
        }

        const renderChips = (label, errs, suggestionTemplate) => {
          if (!errs.length) return;
          const sec = document.createElement('div');
          sec.className = 'ai-validation-section';
          const lab = document.createElement('div');
          lab.className = 'ai-validation-section-label';
          lab.textContent = label;
          sec.appendChild(lab);
          const chips = document.createElement('div');
          chips.className = 'ai-validation-chips';
          errs.forEach(e => {
            const chip = document.createElement('span');
            chip.className = 'ai-chip';
            chip.textContent = e.token || e.message || '?';
            chip.title = (e.message || '') + ' — klikk for å foreslå alternativ';
            chip.addEventListener('click', () => {
              if (!dom.aiInput) return;
              dom.aiInput.value = suggestionTemplate.replace('{token}', e.token || '');
              autoresize();
              dom.aiInput.focus();
            });
            chips.appendChild(chip);
          });
          sec.appendChild(chips);
          wrap.appendChild(sec);
        };

        renderChips('Ukjente variabler', groups.unknown_variable, 'Bruk en annen variabel for {token}');
        renderChips('Ukjente kommandoer', groups.unknown_command, 'Skriv om uten å bruke {token}');

        const others = [...groups.parse, ...groups.runtime, ...groups.other];
        if (others.length) {
          const sec = document.createElement('div');
          sec.className = 'ai-validation-section';
          const lab = document.createElement('div');
          lab.className = 'ai-validation-section-label';
          lab.textContent = 'Andre advarsler';
          sec.appendChild(lab);
          const ul = document.createElement('ul');
          ul.className = 'ai-validation-bullets';
          others.forEach(e => {
            const li = document.createElement('li');
            const lineHint = e.line_no ? ('linje ' + e.line_no + ': ') : '';
            li.textContent = lineHint + (e.message || e.kind);
            ul.appendChild(li);
          });
          sec.appendChild(ul);
          wrap.appendChild(sec);
        }

        return wrap;
      }

      function appendAssistantVariableList(node, variables, meta) {
        node.innerHTML = '';
        const bubble = document.createElement('div');
        bubble.className = 'ai-bubble';
        if (!variables || !variables.length) {
          bubble.textContent = 'Ingen variabler funnet.';
        } else {
          const intro = document.createElement('p');
          intro.textContent = `Fant ${variables.length} variabler:`;
          bubble.appendChild(intro);
          const list = document.createElement('ul');
          list.style.margin = '0'; list.style.paddingLeft = '18px';
          variables.forEach(v => {
            const li = document.createElement('li');
            li.style.marginBottom = '4px';
            li.innerHTML = '<code>' + escapeHtml(v.name) + '</code> — ' + escapeHtml(v.short_title || '');
            list.appendChild(li);
          });
          bubble.appendChild(list);
        }
        node.appendChild(bubble);
        if (meta) appendMeta(node, meta);
        scrollToBottom();
      }

      function appendMeta(node, meta) {
        // Meta-linja (intent · modell · tid · tokens · cache) er støy for brukeren — vises ikke.
      }

      function commentize(text) {
        return String(text).split('\n').map(l => '// ' + l).join('\n');
      }

      // Build editor content from a full markdown response, preserving document
      // order ("legg de etter hverandre"). includeComments=false → only the code
      // blocks; true → prose rendered as // comments interleaved with the code.
      function buildInsertContent(rawMd, includeComments) {
        if (!rawMd) return '';
        const re = /```[^\n]*\r?\n([\s\S]*?)```/g;
        const parts = [];
        let last = 0, m;
        while ((m = re.exec(rawMd)) !== null) {
          if (includeComments) {
            const prose = rawMd.slice(last, m.index).trim();
            if (prose) parts.push(commentize(prose));
          }
          const code = (m[1] || '').replace(/\s+$/, '');
          if (code.trim()) parts.push(code);
          last = re.lastIndex;
        }
        if (includeComments) {
          const tail = rawMd.slice(last).trim();
          if (tail) parts.push(commentize(tail));
        }
        // No fenced code at all: comment the whole thing when asked, else nothing.
        if (parts.length === 0 && includeComments) {
          const all = rawMd.trim();
          if (all) parts.push(commentize(all));
        }
        return parts.join('\n\n');
      }

      function hasCodeBlock(rawMd) {
        return !!rawMd && /```[\s\S]*?```/.test(rawMd);
      }

      // Response-level action bar shown under the whole answer: an "include
      // explanation as comment" checkbox and a single "Sett inn" button that
      // replaces the editor content.
      function attachResponseInsertBar(node, rawMd) {
        if (!dom.scriptInput || !hasCodeBlock(rawMd)) return;
        const bar = document.createElement('div');
        bar.className = 'ai-response-actions';

        const lbl = document.createElement('label');
        lbl.className = 'ai-include-row';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(' Inkluder forklaring som kommentar'));

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ai-response-insert-btn';
        btn.textContent = 'Sett inn';
        btn.title = 'Sett svaret inn i editoren (erstatter innholdet)';
        btn.addEventListener('click', () => {
          const content = buildInsertContent(rawMd, cb.checked);
          if (!content) return;
          dom.scriptInput.value = content;
          dom.scriptInput.dispatchEvent(new Event('input', { bubbles: true }));
          flash(btn, '✓ Satt inn');
        });

        // Knapp før checkbox (horisontalt).
        bar.appendChild(btn);
        bar.appendChild(lbl);
        node.appendChild(bar);
      }

      function handleCodeAction(act, script, btn) {
        if (act === 'copy') {
          navigator.clipboard.writeText(script).then(() => flash(btn, '✓ Kopiert'));
        }
      }

      function flash(btn, label) {
        const original = btn.textContent;
        btn.textContent = label;
        btn.classList.add('flash');
        setTimeout(() => { btn.textContent = original; btn.classList.remove('flash'); }, 1200);
      }

      function attachCodeBlockActions(bubble) {
        // For markdown-rendered code blocks, attach a small copy button
        bubble.querySelectorAll('pre').forEach(pre => {
          if (pre.parentElement.classList.contains('ai-codeblock-wrap')) return;
          const codeEl = pre.querySelector('code') || pre;
          const text = codeEl.textContent;
          if (!text || text.length < 12) return;
          const wrap = document.createElement('div');
          wrap.className = 'ai-codeblock-wrap';
          pre.parentElement.insertBefore(wrap, pre);
          wrap.appendChild(pre);
          const actions = document.createElement('div');
          actions.className = 'ai-codeblock-actions';
          actions.innerHTML =
            '<button type="button" class="ai-codeblock-btn" data-act="copy">📋 Kopier</button>';
          wrap.appendChild(actions);
          actions.addEventListener('click', (e) => {
            const btn = e.target.closest('.ai-codeblock-btn');
            if (!btn) return;
            handleCodeAction(btn.dataset.act, text, btn);
          });
        });
      }

      function scrollToBottom() {
        dom.aiThread.scrollTop = dom.aiThread.scrollHeight;
      }

      async function callApi(path, body) {
        const auth = window.mdAuth;
        const token = auth && auth.token;
        if (!token && !state.apiKey) {
          // Defer to caller to handle (sendMessage triggers login modal)
          throw new Error('Ikke logget inn');
        }
        const isGet = body == null;
        const opts = {
          method: isGet ? 'GET' : 'POST',
          headers: token
            ? { 'Authorization': 'Bearer ' + token }
            : { 'X-API-Key': state.apiKey },
        };
        if (!isGet) {
          opts.headers['Content-Type'] = 'application/json';
          opts.body = JSON.stringify(body);
        }
        const res = await fetch(state.apiBase + '/_/api' + path, opts);
        const text = await res.text();
        let json;
        try { json = JSON.parse(text); } catch (e) { json = { error: text }; }
        if (!res.ok) {
          const msg = json.error || ('HTTP ' + res.status);
          const err = new Error(msg);
          err.payload = json;
          err.status = res.status;
          // 401 with bearer → token expired/revoked; clear and prompt re-login
          if (res.status === 401 && token && auth) {
            auth.logout();
            auth.showLogin();
          }
          throw err;
        }
        return json;
      }

      function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

      async function pollTask(taskId, onTick) {
        const maxWaitMs = 180000;       // 3-minute ceiling
        const intervalMs = 1500;
        const start = Date.now();
        while (Date.now() - start < maxWaitMs) {
          await sleep(intervalMs);
          const elapsed = Math.round((Date.now() - start) / 1000);
          if (onTick) onTick(elapsed);
          let status;
          try {
            status = await callApi('/task_status?task_id=' + encodeURIComponent(taskId), null);
          } catch (e) {
            if (e.status === 404) {
              throw new Error('Bakgrunnsoppgaven ble ikke funnet (task_id ugyldig).');
            }
            throw e;
          }
          if (status.status === 'completed') return status.result;
          if (status.status === 'failed' || status.status === 'killed') {
            throw new Error('Bakgrunnsoppgave feilet: ' + (status.error || status.status));
          }
          // 'running' → loop
        }
        throw new Error('Bakgrunnsoppgaven brukte mer enn 3 min — avbrutt.');
      }

      function detectLang(text) {
        // Crude: if it has Norwegian chars or common NO words, treat as 'no', else 'en'.
        if (/[æøåÆØÅ]/.test(text)) return 'no';
        const noWords = /\b(hva|hvordan|kjør|skript|gjør|finnes|vis|inntekt|kjønn|kommune|alder)\b/i;
        if (noWords.test(text)) return 'no';
        const enWords = /\b(what|how|show|run|script|does|find|income|gender|age)\b/i;
        if (enWords.test(text)) return 'en';
        return 'no';
      }

      async function sendMessage(fast, useV2) {
        if (state.sending) return;
        const text = dom.aiInput.value.trim();
        if (!text) return;
        // Gate on login: if neither bearer token nor legacy API-key, show login modal.
        const auth = window.mdAuth;
        const isAuthed = (auth && auth.token) || state.apiKey;
        if (!isAuthed) {
          if (auth) auth.showLogin();
          return;
        }
        state.sending = true;
        if (dom.aiSendFastBtn) dom.aiSendFastBtn.disabled = true;

        // Clear empty state on first message
        if (state.history.length === 0) dom.aiThread.innerHTML = '';

        appendUserMessage(text);
        state.history.push({ role: 'user', text });
        dom.aiInput.value = '';
        autoresize();

        const thinkingNode = appendThinking();
        const lang = detectLang(text);

        const includeScript = dom.aiIncludeScript.checked && dom.scriptInput && dom.scriptInput.value.trim();

        // Fast path: single-shot, no-repair edge function. Streams markdown;
        // the result is validated locally via Pyodide+m2py (see runFastQuery).
        if (fast) {
          const ctrl = new AbortController();
          state.abortCtrl = ctrl;
          if (dom.aiAbortBtn) dom.aiAbortBtn.style.display = '';
          try {
            const meta = useV2
              ? await runFastQueryV2(text, lang, includeScript ? dom.scriptInput.value : '', thinkingNode, ctrl.signal)
              : await runFastQuery(text, lang, includeScript ? dom.scriptInput.value : '', thinkingNode, ctrl.signal);
            state.history.push({ role: 'assistant', meta });
          } catch (e) {
            if (e.name !== 'AbortError') appendError(thinkingNode, '✗ ' + e.message);
          } finally {
            state.abortCtrl = null;
            if (dom.aiAbortBtn) dom.aiAbortBtn.style.display = 'none';
            state.sending = false;
            if (dom.aiSendFastBtn) dom.aiSendFastBtn.disabled = false;
            dom.aiInput.focus();
          }
          return;
        }

        try {
          let resp, intent, result;
          if (includeScript) {
            resp = await callApi('/revise', {
              script: dom.scriptInput.value,
              revision: text,
              lang,
              max_repair: 1,
            });
            intent = resp.intent || 'revise';
          } else {
            resp = await callApi('/query', { question: text, lang });
            intent = resp.intent || 'qa';
          }

          // Async path: poll background task until it completes.
          if (resp.task_id) {
            const tickEl = thinkingNode.querySelector('.ai-thinking');
            const finalEnv = await pollTask(resp.task_id, (sec) => {
              if (!tickEl) return;
              let elapsed = tickEl.querySelector('.ai-tick-elapsed');
              if (!elapsed) {
                elapsed = document.createElement('span');
                elapsed.className = 'ai-tick-elapsed';
                elapsed.style.marginLeft = '4px';
                elapsed.style.opacity = '0.7';
                tickEl.appendChild(elapsed);
              }
              elapsed.textContent = ' ' + sec + 's';
            });
            result = (finalEnv && finalEnv.result) || {};
            intent = (finalEnv && finalEnv.intent) || intent;
            if (finalEnv && !finalEnv.classifier && resp.classifier) finalEnv.classifier = resp.classifier;
            resp = Object.assign({}, resp, finalEnv);
          } else {
            result = resp.result || resp;
          }

          const meta = {
            intent,
            model: result.model || (resp.classifier && resp.classifier.model),
            latency_ms: resp.latency_ms,
            validation: result.validation,
          };

          if (intent === 'script_gen' || intent === 'revise') {
            const script = result.script || '';
            const rationale = result.rationale || '';
            if (script) {
              appendAssistantScript(thinkingNode, script, rationale, meta);
            } else {
              appendAssistantText(thinkingNode, rationale || 'Ingen skript ble generert.', meta);
            }
          } else if (intent === 'variable_search') {
            appendAssistantVariableList(thinkingNode, result.variables || [], meta);
          } else {
            // qa or unknown
            const answer = result.answer || result.rationale || '(tomt svar)';
            appendAssistantText(thinkingNode, answer, meta);
          }
          state.history.push({ role: 'assistant', meta });
        } catch (e) {
          appendError(thinkingNode, '✗ ' + e.message);
        } finally {
          state.sending = false;
          if (dom.aiSendFastBtn) dom.aiSendFastBtn.disabled = false;
          dom.aiInput.focus();
        }
      }

      // ── Fast path: stream from the /api/kode-svar edge function (single-shot,
      //    no repair), render markdown live, then validate the emitted script
      //    locally in Pyodide+m2py and show a pass/⚠ badge. Returns meta.
      // Render markdown inn i boblen under streaming (faller tilbake til ren
      // tekst hvis markdown-it mangler eller parsing feiler på ufullstendig md).
      function streamRenderMd(bubble, textMd) {
        if (md) {
          try { bubble.innerHTML = md.render(textMd || ''); return; }
          catch (_) { /* fall through */ }
        }
        bubble.textContent = textMd || '';
      }

      async function runFastQuery(text, lang, scriptContext, thinkingNode, signal) {
        const auth = window.mdAuth;
        const token = auth && auth.token;
        const headers = token
          ? { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }
          : { 'X-API-Key': state.apiKey, 'Content-Type': 'application/json' };
        const t0 = Date.now();
        const resp = await fetch('/api/kode-svar', {
          method: 'POST',
          headers,
          body: JSON.stringify({ question: text, lang, script: scriptContext || '' }),
          signal,
        });
        if (resp.status === 401) {
          if (token && auth) { auth.logout(); auth.showLogin(); }
          throw new Error('Innloggingen er utløpt. Logg inn på nytt.');
        }
        if (!resp.ok || !resp.body) {
          throw new Error('HTTP ' + resp.status + ' ' + (await resp.text()));
        }

        // Render incrementally into an assistant bubble.
        thinkingNode.innerHTML = '';
        const bubble = document.createElement('div');
        bubble.className = 'ai-bubble';
        thinkingNode.appendChild(bubble);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let accumulated = '';
        let _lastRender = 0;
        let inputTokens = 0, outputTokens = 0, cacheRead = 0, cacheCreate = 0;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let nl;
          while ((nl = buffer.indexOf('\n\n')) >= 0) {
            const event = buffer.slice(0, nl);
            buffer = buffer.slice(nl + 2);
            const dataLine = event.split('\n').find(l => l.startsWith('data:'));
            if (!dataLine) continue;
            let obj;
            try { obj = JSON.parse(dataLine.slice(5).trim()); }
            catch (_) { continue; }   // ignore non-JSON keep-alive lines
            if (obj.type === 'text') {
              accumulated += obj.text;
              // Render markdown live (lett strupet) i stedet for rå tekst.
              const _now = Date.now();
              if (_now - _lastRender > 70) {
                _lastRender = _now;
                streamRenderMd(bubble, accumulated);
                scrollToBottom();
              }
            } else if (obj.type === 'done') {
              inputTokens = obj.inputTokens || 0;
              outputTokens = obj.outputTokens || 0;
              cacheRead = obj.cacheReadTokens || 0;
              cacheCreate = obj.cacheCreationTokens || 0;
            } else if (obj.type === 'error') {
              throw new Error(obj.message || 'Ukjent feil fra server');
            }
          }
        }

        // Final markdown render + code-block action buttons (reuse existing).
        if (md) {
          try { bubble.innerHTML = md.render(accumulated || ''); }
          catch (_) { bubble.textContent = accumulated; }
        } else {
          bubble.textContent = accumulated;
        }
        attachCodeBlockActions(bubble);
        bubble._rawMd = accumulated;

        const meta = {
          intent: 'raskt',
          model: 'kode-svar',
          latency_ms: Date.now() - t0,
          tokens: { input: inputTokens, output: outputTokens, cacheRead, cacheCreate },
        };
        appendMeta(thinkingNode, meta);
        attachResponseInsertBar(thinkingNode, accumulated);

        // Valider første microdata-kodeblokk lokalt (ikke-blokkerende).
        // Vi viser ingen «validert»-tekst ved suksess (støy) — kun advarsler ved feil.
        const script = extractFirstMicrodataBlock(accumulated);
        if (script) {
          validateMicrodataLocal(script).then(vr => {
            if (vr.skipped || vr.passed) return;
            const warn = renderValidationWarnings(vr);
            if (warn) bubble.appendChild(warn);
          }).catch(() => {});
        }
        return meta;
      }

      // One streaming request to /api/kode-svar-v2. Renders markdown live into
      // `bubble`. Returns { accumulated, tokens }. Mirrors runFastQuery's stream
      // parsing; factored out so the repair round can call it again.
      async function streamKodeSvarV2(payload, bubble, signal) {
        const auth = window.mdAuth;
        const token = auth && auth.token;
        const headers = token
          ? { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }
          : { 'X-API-Key': state.apiKey, 'Content-Type': 'application/json' };
        const resp = await fetch('/api/kode-svar-v2', {
          method: 'POST', headers, body: JSON.stringify(payload), signal,
        });
        if (resp.status === 401) {
          if (token && auth) { auth.logout(); auth.showLogin(); }
          throw new Error('Innloggingen er utløpt. Logg inn på nytt.');
        }
        if (!resp.ok || !resp.body) {
          throw new Error('HTTP ' + resp.status + ' ' + (await resp.text()));
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', accumulated = '', _lastRender = 0;
        let inputTokens = 0, outputTokens = 0, cacheRead = 0, cacheCreate = 0;
        let firstByte = false;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let nl;
          while ((nl = buffer.indexOf('\n\n')) >= 0) {
            const event = buffer.slice(0, nl);
            buffer = buffer.slice(nl + 2);
            const dataLine = event.split('\n').find(l => l.startsWith('data:'));
            if (!dataLine) continue;
            let obj;
            try { obj = JSON.parse(dataLine.slice(5).trim()); } catch (_) { continue; }
            if (obj.type === 'text') {
              if (!firstByte) { firstByte = true; bubble.textContent = ''; }
              accumulated += obj.text;
              const _now = Date.now();
              if (_now - _lastRender > 70) {
                _lastRender = _now;
                streamRenderMd(bubble, accumulated);
                scrollToBottom();
              }
            } else if (obj.type === 'done') {
              inputTokens = obj.inputTokens || 0;
              outputTokens = obj.outputTokens || 0;
              cacheRead = obj.cacheReadTokens || 0;
              cacheCreate = obj.cacheCreationTokens || 0;
            } else if (obj.type === 'error') {
              throw new Error(obj.message || 'Ukjent feil fra server');
            }
          }
        }
        return { accumulated, tokens: { input: inputTokens, output: outputTokens, cacheRead, cacheCreate } };
      }

      // Concatenate all fenced code-block bodies (any language) so name-grounding
      // can scan the #micro import inside a python/r answer without prose noise.
      function extractAllCode(md) {
        if (!md) return '';
        const re = /```\w*\s*\n([\s\S]*?)```/g;
        let m, out = [];
        while ((m = re.exec(md)) !== null) out.push(m[1]);
        return out.join('\n');
      }

      // Collect db/NAME (or alias/NAME) tokens whose NAME is not in the loaded
      // catalog — the cheapest, most damaging failure (invented variable names).
      function findUnknownVarNames(script) {
        if (!script || typeof microdataVariableNames === 'undefined' || !microdataVariableNames.length) return [];
        const known = new Set(microdataVariableNames);
        const re = /\b[a-zA-Z_]\w*\/([A-Z][A-Z0-9_]+)\b/g;
        const bad = new Set();
        let m;
        while ((m = re.exec(script)) !== null) {
          if (!known.has(m[1])) bad.add(m[1]);
        }
        return Array.from(bad);
      }

      // Turn a validation result + unknown-name list into a compact error string
      // for the repair prompt. Returns '' when there is nothing to fix.
      function buildRepairErrors(vr, unknownNames) {
        const parts = [];
        if (unknownNames && unknownNames.length) {
          parts.push('Ukjente variabelnavn (finnes ikke i katalogen): ' + unknownNames.join(', '));
        }
        if (vr && !vr.skipped && !vr.passed && Array.isArray(vr.errors)) {
          for (const e of vr.errors) {
            const tok = e.token ? (e.token + ': ') : '';
            parts.push('- ' + tok + (e.message || e.kind || 'feil'));
          }
        }
        return parts.join('\n');
      }

      async function runFastQueryV2(text, lang, scriptContext, thinkingNode, signal) {
        const t0 = Date.now();
        thinkingNode.innerHTML = '';
        const bubble = document.createElement('div');
        bubble.className = 'ai-bubble';
        bubble.textContent = 'Finner relevante variabler…';
        thinkingNode.appendChild(bubble);

        const mode = (typeof activeEditorMode !== 'undefined' && activeEditorMode) ? activeEditorMode : 'microdata';
        const payload = { question: text, lang, script: scriptContext || '', mode };
        const { accumulated, tokens } = await streamKodeSvarV2(payload, bubble, signal);

        // Final render + actions (reuse v1 helpers).
        if (md) { try { bubble.innerHTML = md.render(accumulated || ''); } catch (_) { bubble.textContent = accumulated; } }
        else { bubble.textContent = accumulated; }
        attachCodeBlockActions(bubble);
        bubble._rawMd = accumulated;

        const meta = { intent: 'raskt-v2', model: 'kode-svar-v2', latency_ms: Date.now() - t0, tokens };
        appendMeta(thinkingNode, meta);
        attachResponseInsertBar(thinkingNode, accumulated);

        if (mode === 'microdata') {
          // Validate; on failure, attempt ONE repair round, then badge.
          let script = extractFirstMicrodataBlock(accumulated);
          let repaired = false;
          let finalBubble = bubble;
          while (script) {
            let vr;
            try { vr = await validateMicrodataLocal(script); } catch (_) { vr = { skipped: true }; }
            const unknown = findUnknownVarNames(script);
            const hasErrors = (!vr.skipped && !vr.passed) || unknown.length > 0;
            if (!hasErrors || repaired) {
              if (hasErrors) {
                const warn = renderValidationWarnings(
                  vr.skipped ? { passed: false, errors: unknown.map(n => ({ kind: 'unknown_variable', token: n, message: 'finnes ikke i katalogen' })) } : vr
                );
                if (warn) finalBubble.appendChild(warn);
              }
              break;
            }
            // One repair round: new bubble, re-call with prior script + errors.
            repaired = true;
            const note = document.createElement('div');
            note.className = 'ai-thinking';
            note.textContent = 'Retter feil og prøver på nytt…';
            thinkingNode.appendChild(note);
            const repairBubble = document.createElement('div');
            repairBubble.className = 'ai-bubble';
            thinkingNode.appendChild(repairBubble);
            const errStr = buildRepairErrors(vr, unknown);
            let r2;
            try {
              r2 = await streamKodeSvarV2(
                { question: text, lang, script: scriptContext || '', mode, prior_script: script, errors: errStr },
                repairBubble, signal,
              );
            } catch (e) {
              note.remove();
              repairBubble.textContent = '✗ ' + (e && e.message ? e.message : String(e));
              break;
            }
            note.remove();
            if (md) { try { repairBubble.innerHTML = md.render(r2.accumulated || ''); } catch (_) { repairBubble.textContent = r2.accumulated; } }
            else { repairBubble.textContent = r2.accumulated; }
            attachCodeBlockActions(repairBubble);
            repairBubble._rawMd = r2.accumulated;
            attachResponseInsertBar(thinkingNode, r2.accumulated);
            finalBubble = repairBubble;
            meta.tokens.input += r2.tokens.input; meta.tokens.output += r2.tokens.output;
            meta.tokens.cacheRead += r2.tokens.cacheRead; meta.tokens.cacheCreate += r2.tokens.cacheCreate;
            script = extractFirstMicrodataBlock(r2.accumulated);
          }
        } else {
          // Python/R: no m2py repair. Ground variable names in the #micro block only.
          const unknown = findUnknownVarNames(extractAllCode(accumulated));
          if (unknown.length) {
            const warn = renderValidationWarnings({
              passed: false,
              errors: unknown.map(n => ({ kind: 'unknown_variable', token: n, message: 'finnes ikke i katalogen' })),
            });
            if (warn) bubble.appendChild(warn);
          }
        }
        return meta;
      }

      // Tolk resultater: strøm en tolkning av output (kommandoer + resultater)
      // inn i en assistent-boble. Speiler runFastQuery, men mot /api/tolk-resultat.
      async function runInterpretQuery(payload, thinkingNode, signal) {
        const auth = window.mdAuth;
        const token = auth && auth.token;
        const headers = token
          ? { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }
          : { 'X-API-Key': state.apiKey, 'Content-Type': 'application/json' };
        const resp = await fetch('/api/tolk-resultat', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            script: payload.script || '',
            output: payload.output || '',
            språk: payload.lang || 'auto',
          }),
          signal,
        });
        if (resp.status === 401) {
          if (token && auth) { auth.logout(); auth.showLogin(); }
          throw new Error('Innloggingen er utløpt. Logg inn på nytt.');
        }
        if (!resp.ok || !resp.body) {
          throw new Error('HTTP ' + resp.status + ' ' + (await resp.text()));
        }
        thinkingNode.innerHTML = '';
        const bubble = document.createElement('div');
        bubble.className = 'ai-bubble';
        thinkingNode.appendChild(bubble);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', accumulated = '', _lastRender = 0;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let nl;
          while ((nl = buffer.indexOf('\n\n')) >= 0) {
            const event = buffer.slice(0, nl);
            buffer = buffer.slice(nl + 2);
            const dataLine = event.split('\n').find(l => l.startsWith('data:'));
            if (!dataLine) continue;
            let obj;
            try { obj = JSON.parse(dataLine.slice(5).trim()); } catch (_) { continue; }
            if (obj.type === 'text') {
              accumulated += obj.text;
              const _now = Date.now();
              if (_now - _lastRender > 70) {
                _lastRender = _now;
                streamRenderMd(bubble, accumulated);
                scrollToBottom();
              }
            } else if (obj.type === 'error') {
              throw new Error(obj.message || 'Ukjent feil fra server');
            }
          }
        }
        if (md) {
          try { bubble.innerHTML = md.render(accumulated || ''); }
          catch (_) { bubble.textContent = accumulated; }
        } else {
          bubble.textContent = accumulated;
        }
        bubble._rawMd = accumulated;
        // Kopier-knapp for tolkningen.
        const actions = document.createElement('div');
        actions.className = 'ai-codeblock-actions';
        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'ai-codeblock-btn';
        copyBtn.textContent = '📋 Kopier tolkning';
        copyBtn.addEventListener('click', () => {
          navigator.clipboard.writeText(accumulated).then(() => flash(copyBtn, '✓ Kopiert')).catch(() => {});
        });
        actions.appendChild(copyBtn);
        thinkingNode.appendChild(actions);
        state.history.push({ role: 'assistant', meta: { intent: 'tolkning' } });
      }

      // Pull the first ```microdata / ``` code block that looks like a
      // microdata script out of streamed markdown.
      function extractFirstMicrodataBlock(textMd) {
        if (!textMd) return '';
        const re = /```(\w*)\s*\n([\s\S]*?)```/g;
        let m;
        while ((m = re.exec(textMd)) !== null) {
          const lang = (m[1] || '').toLowerCase();
          const body = (m[2] || '').trim();
          if (lang === 'python' || lang === 'py' || lang === 'r') continue;
          if (/\b(require|create-dataset|import\s+\w+\/|use\s+\w)/.test(body)) return body;
          if (lang === 'microdata') return body;
        }
        return '';
      }

      // Run the script through a throwaway m2py interpreter on synthetic data
      // (disclosure control off, so only structural/runtime errors surface).
      // Returns {passed, errors:[{kind,message}]} or {skipped:true}.
      async function validateMicrodataLocal(script) {
        let py;
        try { py = await loadPyodideAndM2py(); }
        catch (_) { return { skipped: true }; }
        if (!py) return { skipped: true };
        const base = window.location.href.replace(/[^/]+$/, '');
        const catalogJson = (typeof microdataCatalog !== 'undefined' && microdataCatalog && microdataCatalog.variables)
          ? JSON.stringify(microdataCatalog.variables) : null;
        const pyCode =
          'import json, sys\n' +
          '_script = ' + JSON.stringify(script) + '\n' +
          '_catalog_json = ' + (catalogJson !== null ? JSON.stringify(catalogJson) : 'None') + '\n' +
          '_base = ' + JSON.stringify(base) + '\n' +
          '_m = sys.modules.get("m2py")\n' +
          '_prev_dc = getattr(_m, "M2PY_DISCLOSURE_CONTROL", "0") if _m is not None else "0"\n' +
          '_out = json.dumps({"passed": False, "errors": [{"kind": "runtime", "message": "validator unavailable"}]})\n' +
          'try:\n' +
          '    if _m is not None:\n' +
          '        _m.M2PY_DISCLOSURE_CONTROL = "0"\n' +
          '    from m2py import MicroInterpreter\n' +
          '    _cat = json.loads(_catalog_json) if _catalog_json else None\n' +
          '    _vi = MicroInterpreter(catalog=_cat, metadata_base_url=_base)\n' +
          '    try:\n' +
          '        _vi.data_engine.default_rows = 200\n' +
          '    except Exception:\n' +
          '        pass\n' +
          '    _err = None\n' +
          '    try:\n' +
          '        if hasattr(_vi, "run_script_async"):\n' +
          '            _err = "ASYNC"\n' +
          '        else:\n' +
          '            _vi.run_script(_script)\n' +
          '    except Exception as _ex:\n' +
          '        _err = f"{type(_ex).__name__}: {_ex}"\n' +
          '    if _err == "ASYNC":\n' +
          '        _out = json.dumps({"async": True})\n' +
          '    elif _err is None:\n' +
          '        _out = json.dumps({"passed": True, "errors": []})\n' +
          '    else:\n' +
          '        _out = json.dumps({"passed": False, "errors": [{"kind": "runtime", "message": _err}]})\n' +
          'except Exception as _ex2:\n' +
          '    _out = json.dumps({"skipped": True, "error": f"{type(_ex2).__name__}: {_ex2}"})\n' +
          'finally:\n' +
          '    if _m is not None:\n' +
          '        _m.M2PY_DISCLOSURE_CONTROL = _prev_dc\n' +
          '_out\n';
        let raw;
        try { raw = await py.runPythonAsync(pyCode); }
        catch (_) { return { skipped: true }; }
        let parsed;
        try { parsed = JSON.parse(raw); } catch (_) { return { skipped: true }; }
        if (parsed.skipped) return { skipped: true };
        // Async interpreter variant — run via the async API and re-check.
        if (parsed.async) {
          return await validateMicrodataLocalAsync(py, script, catalogJson, base);
        }
        return parsed;
      }

      async function validateMicrodataLocalAsync(py, script, catalogJson, base) {
        const setup =
          'import json, sys\n' +
          '_script = ' + JSON.stringify(script) + '\n' +
          '_catalog_json = ' + (catalogJson !== null ? JSON.stringify(catalogJson) : 'None') + '\n' +
          '_base = ' + JSON.stringify(base) + '\n' +
          '_m = sys.modules.get("m2py")\n' +
          'globals()["_prev_dc"] = getattr(_m, "M2PY_DISCLOSURE_CONTROL", "0") if _m is not None else "0"\n' +
          'if _m is not None:\n' +
          '    _m.M2PY_DISCLOSURE_CONTROL = "0"\n' +
          'from m2py import MicroInterpreter\n' +
          '_cat = json.loads(_catalog_json) if _catalog_json else None\n' +
          '_vi = MicroInterpreter(catalog=_cat, metadata_base_url=_base)\n' +
          'try:\n' +
          '    _vi.data_engine.default_rows = 200\n' +
          'except Exception:\n' +
          '    pass\n' +
          'globals()["_vi"] = _vi\n';
        try { await py.runPythonAsync(setup); } catch (_) { return { skipped: true }; }
        let raw;
        try {
          raw = await py.runPythonAsync(
            '_err = None\n' +
            'try:\n' +
            '    await _vi.run_script_async(_script)\n' +
            'except Exception as _ex:\n' +
            '    _err = f"{type(_ex).__name__}: {_ex}"\n' +
            'finally:\n' +
            '    if _m is not None:\n' +
            '        _m.M2PY_DISCLOSURE_CONTROL = _prev_dc\n' +
            'json.dumps({"passed": _err is None, "errors": [] if _err is None else [{"kind": "runtime", "message": _err}]})\n'
          );
        } catch (_) { return { skipped: true }; }
        try { return JSON.parse(raw); } catch (_) { return { skipped: true }; }
      }

      function autoresize() {
        const ta = dom.aiInput;
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';  // ~5 linjer maks, så scroller den
      }

      function categoryLabel(cat) {
        return ({ internal: 'Internal', kurs: 'Kurs', credits: 'Credits', free: 'Free' }[cat] || cat || '?');
      }

      function refreshUserPanel() {
        const auth = window.mdAuth;
        const user = auth && auth.user;
        if (user) {
          dom.aiCfgLoggedIn.style.display = '';
          dom.aiCfgLoggedOut.style.display = 'none';
          dom.aiCfgUserEmail.textContent = user.email || '';
          const bits = [];
          bits.push('Kategori: ' + categoryLabel(user.category));
          if (typeof user.credits === 'number') bits.push('Saldo: ' + user.credits);
          if (user.is_superuser) bits.push('Superuser');
          if (user.is_admin) bits.push('Admin');
          if (user.expires_at) bits.push('Utløper: ' + user.expires_at.slice(0, 10));
          dom.aiCfgUserMeta.textContent = bits.join(' · ');
          dom.aiCfgAdmin.style.display = user.is_admin ? '' : 'none';
        } else {
          dom.aiCfgLoggedIn.style.display = 'none';
          dom.aiCfgLoggedOut.style.display = '';
        }
        // Keep admin hamburger menu section in sync
        const adminSec = document.getElementById('adminMenuSection');
        if (adminSec) {
          adminSec.style.display = (user && user.is_admin) ? '' : 'none';
        }
      }

      function openSettings() {
        dom.aiCfgBaseUrl.value = state.apiBase;
        dom.aiCfgApiKey.value = state.apiKey;
        refreshUserPanel();
        // Refresh /auth/me in background so the displayed credits/category are up-to-date
        if (window.mdAuth && window.mdAuth.token) {
          window.mdAuth.refreshMe().then(refreshUserPanel);
        }
        dom.aiSettingsBackdrop.classList.add('open');
      }
      function closeSettings() { dom.aiSettingsBackdrop.classList.remove('open'); }
      function saveSettings() {
        const base = dom.aiCfgBaseUrl.value.trim() || DEFAULT_BASE;
        const key = dom.aiCfgApiKey.value.trim();
        localStorage.setItem(LS_KEY_BASE, base);
        localStorage.setItem(LS_KEY_APIKEY, key);
        closeSettings();
      }

      function clearChat() {
        state.history = [];
        renderEmpty();
      }

      function init() {
        cacheDom();
        if (!dom.aiSidebar) return;

        dom.aiToggleBtn.addEventListener('click', toggleOpen);
        dom.aiCloseBtn.addEventListener('click', () => setOpen(false));
        dom.aiSettingsBtn.addEventListener('click', openSettings);
        dom.aiClearBtn.addEventListener('click', clearChat);
        dom.aiCfgSave.addEventListener('click', saveSettings);
        dom.aiCfgCancel.addEventListener('click', closeSettings);
        dom.aiSettingsBackdrop.addEventListener('click', (e) => {
          if (e.target === dom.aiSettingsBackdrop) closeSettings();
        });

        // Auth-related buttons in the settings modal
        if (dom.aiCfgLogin) {
          dom.aiCfgLogin.addEventListener('click', () => {
            closeSettings();
            if (window.mdAuth) window.mdAuth.showLogin();
          });
        }
        if (dom.aiCfgLogout) {
          dom.aiCfgLogout.addEventListener('click', async () => {
            if (window.mdAuth) await window.mdAuth.logout();
            refreshUserPanel();
          });
        }
        if (dom.aiCfgAdmin) {
          dom.aiCfgAdmin.addEventListener('click', () => {
            window.location.href = 'admin.html';
          });
        }

        // Send uses the AI mode chosen in the hamburger menu: fast edge-fn or
        // full Anvil-path (sendMessage(fast) — fast=true => rask).
        function sendCurrent() { sendMessage(!state.anvilMode); }
        if (dom.aiSendFastBtn) dom.aiSendFastBtn.addEventListener('click', sendCurrent);
        if (dom.aiSendV2Btn) dom.aiSendV2Btn.addEventListener('click', () => sendMessage(true, true));
        if (dom.aiAbortBtn) dom.aiAbortBtn.addEventListener('click', () => { if (state.abortCtrl) state.abortCtrl.abort(); });
        dom.aiInput.addEventListener('input', autoresize);
        dom.aiInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendCurrent();   // Enter = send (modus fra menyen); Shift+Enter = ny linje
          }
        });

        // AI-modus-bryter i hamburgermenyen
        function updateAiModeLabel() {
          if (dom.menuAiMode) {
            dom.menuAiMode.textContent = 'AI-svar: ' + (state.anvilMode ? 'Anvil (full vurdering)' : 'Rask');
          }
        }
        if (dom.menuAiMode) {
          dom.menuAiMode.addEventListener('click', () => {
            state.anvilMode = !state.anvilMode;
            updateAiModeLabel();
            const dd = document.getElementById('hamburgerDropdown');
            if (dd) dd.classList.remove('open');
          });
        }
        updateAiModeLabel();

        // Keyboard shortcut Ctrl+I
        document.addEventListener('keydown', (e) => {
          if ((e.ctrlKey || e.metaKey) && (e.key === 'i' || e.key === 'I')) {
            e.preventDefault();
            toggleOpen();
          } else if (e.key === 'Escape') {
            if (dom.aiSettingsBackdrop.classList.contains('open')) closeSettings();
          }
        });

        // If Datasett sidebar opens later, close AI to keep mutual exclusion.
        if (dom.sidebarRight) {
          const observer = new MutationObserver(() => {
            const datasettOpen = !dom.sidebarRight.classList.contains('collapsed');
            const aiOpen = dom.aiSidebar.classList.contains('open');
            if (datasettOpen && aiOpen) setOpen(false);
          });
          observer.observe(dom.sidebarRight, { attributes: true, attributeFilter: ['class'] });
        }

        // Auth gate is in sendMessage; no auto-open of settings on first AI-panel
        // toggle. Users see the panel and the empty state; only Send triggers login.

        // Offentlig: åpne AI-panelet og send et spørsmål (brukes av hurtigspør-boksen i toppen).
        window.mdAskAi = function(question) {
          if (!question || !question.trim()) return;
          setOpen(true);
          dom.aiInput.value = question;
          autoresize();
          sendMessage(!state.anvilMode);
        };

        // Offentlig: åpne AI-panelet og tolk resultatene (output) fra forrige kjøring.
        window.mdInterpretResults = function(payload) {
          payload = payload || {};
          if (!payload.output || !payload.output.trim()) return;
          if (state.sending) return;
          const auth = window.mdAuth;
          const isAuthed = (auth && auth.token) || state.apiKey;
          if (!isAuthed) { if (auth) auth.showLogin(); return; }
          setOpen(true);
          if (state.history.length === 0) dom.aiThread.innerHTML = '';
          appendUserMessage('Tolk resultatene fra forrige kjøring.');
          state.history.push({ role: 'user', text: 'Tolk resultatene' });
          const thinkingNode = appendThinking();
          state.sending = true;
          if (dom.aiSendFastBtn) dom.aiSendFastBtn.disabled = true;
          const ctrl = new AbortController();
          state.abortCtrl = ctrl;
          if (dom.aiAbortBtn) dom.aiAbortBtn.style.display = '';
          runInterpretQuery(payload, thinkingNode, ctrl.signal)
            .catch(e => { if (e.name !== 'AbortError') appendError(thinkingNode, '✗ ' + e.message); })
            .finally(() => {
              state.abortCtrl = null;
              if (dom.aiAbortBtn) dom.aiAbortBtn.style.display = 'none';
              state.sending = false;
              if (dom.aiSendFastBtn) dom.aiSendFastBtn.disabled = false;
              if (dom.aiInput) dom.aiInput.focus();
            });
        };
      }

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
      } else {
        init();
      }
    })();
