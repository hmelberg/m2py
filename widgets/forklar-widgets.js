/**
 * Forklar-widgets: modal-baserte UI-steg fra //widget NAME { ...json }
 * Web component: <forklar-widget-shell> (én instans på body)
 */
(function () {
  'use strict';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function parseWidgetLine(line) {
    const t = (line || '').trim();
    if (!t.startsWith('//')) return null;
    /** Tillat både `//widget title { ... }` og `//widget title{ ... }` (valgfritt mellomrom før {). */
    const m = t.match(/^\s*\/\/\s*widget\s+(\w+)/i);
    if (!m) return null;
    const name = m[1];
    const brace = t.indexOf('{');
    if (brace < 0) return { error: 'Mangler JSON-objekt etter //widget ' + name };
    const jsonStr = t.slice(brace);
    try {
      return { name: name, payload: JSON.parse(jsonStr) };
    } catch (e) {
      return { error: (e && e.message) ? e.message : String(e) };
    }
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, Math.max(0, ms | 0));
    });
  }

  function pollAbort(explainAbortRef) {
    return new Promise(function (resolve) {
      const iv = setInterval(function () {
        if (explainAbortRef && explainAbortRef.aborted) {
          clearInterval(iv);
          resolve(true);
        }
      }, 60);
    });
  }

  function getMdRenderer() {
    if (typeof window.markdownit === 'function') {
      try {
        return window.markdownit({ html: false, linkify: true, breaks: true });
      } catch (e) {
        return null;
      }
    }
    return null;
  }

  function renderMarkdownHtml(text) {
    const raw = String(text || '');
    const md = getMdRenderer();
    if (md) {
      try {
        return md.render(raw);
      } catch (e) {
        return '<pre class="forklar-w-md-fallback">' + escapeHtml(raw) + '</pre>';
      }
    }
    return '<pre class="forklar-w-md-fallback">' + escapeHtml(raw) + '</pre>';
  }

  function shuffleArray(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const t = a[i];
      a[i] = a[j];
      a[j] = t;
    }
    return a;
  }

  function effectClass(effect) {
    const e = effect && effect.type;
    if (!e || e === 'none') return '';
    if (e === 'fade' || e === 'fade-in') return 'forklar-w-anim--fade-in';
    if (e === 'fade-in-up' || e === 'slide-up') return 'forklar-w-anim--slide-up';
    if (e === 'zoom-in') return 'forklar-w-anim--zoom-in';
    if (e === 'blur-in') return 'forklar-w-anim--blur-in';
    return 'forklar-w-anim--fade-in';
  }

  function effectDurationMs(effect, fallback) {
    if (effect && effect.duration_ms != null && !isNaN(parseFloat(effect.duration_ms))) {
      return Math.max(0, parseFloat(effect.duration_ms));
    }
    return fallback;
  }

  let shellEl = null;

  function ensureShell() {
    if (shellEl && shellEl.isConnected) return shellEl;
    shellEl = document.createElement('forklar-widget-shell');
    shellEl.setAttribute('aria-hidden', 'true');
    shellEl.innerHTML =
      '<div class="forklar-widget-backdrop"></div>' +
      '<div class="forklar-widget-panel-wrap">' +
      '  <div class="forklar-widget-panel" role="dialog" aria-modal="true">' +
      '    <div class="forklar-widget-titlebar" id="forklarWidgetTitlebar"></div>' +
      '    <div class="forklar-widget-body forklar-widget-body--center" id="forklarWidgetBody"></div>' +
      '    <div class="forklar-widget-actions" id="forklarWidgetActions"></div>' +
      '  </div>' +
      '</div>';
    document.body.appendChild(shellEl);
    return shellEl;
  }

  function injectStylesOnce() {
    if (document.getElementById('forklar-widget-styles')) return;
    const st = document.createElement('style');
    st.id = 'forklar-widget-styles';
    st.textContent =
      'forklar-widget-shell{--forklar-w-radius:14px;--forklar-w-shadow:0 24px 64px rgba(15,23,42,0.18);position:fixed;inset:0;z-index:320;display:none;align-items:center;justify-content:center;padding:max(12px,2.5vw);box-sizing:border-box;pointer-events:none}' +
      'forklar-widget-shell.forklar-widget-open{display:flex;pointer-events:auto}' +
      '.forklar-widget-backdrop{position:absolute;inset:0;background:rgba(15,23,42,0.48);backdrop-filter:blur(2px);-webkit-backdrop-filter:blur(2px);transition:opacity 0.35s ease}' +
      'body[data-theme="dark"] .forklar-widget-backdrop{background:rgba(0,0,0,0.62)}' +
      'forklar-widget-shell.forklar-w-mode-broadcast .forklar-widget-backdrop{background:linear-gradient(165deg,rgba(8,12,24,0.88) 0%,rgba(15,18,32,0.92) 45%,rgba(5,8,18,0.94) 100%);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)}' +
      'forklar-widget-shell.forklar-w-leaving{pointer-events:none}' +
      'forklar-widget-shell.forklar-w-leaving .forklar-widget-backdrop,forklar-widget-shell.forklar-w-leaving .forklar-widget-panel-wrap{opacity:0;transition:opacity 0.65s ease}' +
      '.forklar-widget-panel-wrap{position:relative;max-height:min(90vh,920px);width:100%;display:flex;align-items:center;justify-content:center}' +
      '.forklar-widget-panel{background:var(--bg-panel);color:var(--text);border:1px solid var(--border);border-radius:var(--forklar-w-radius);box-shadow:var(--forklar-w-shadow);max-width:100%;overflow:hidden;display:flex;flex-direction:column;min-height:0}' +
      '.forklar-widget-panel--sm{max-width:min(100%,520px)}' +
      '.forklar-widget-panel--md{max-width:min(100%,640px)}' +
      '.forklar-widget-panel--lg{max-width:min(100%,860px)}' +
      '.forklar-widget-panel--xl{max-width:min(100%,1040px)}' +
      '.forklar-widget-panel--xxl{max-width:min(100%,1200px)}' +
      '.forklar-widget-panel--fullscreen{width:min(98vw,1180px);max-height:min(93vh,940px)}' +
      'forklar-widget-shell.forklar-w-mode-broadcast .forklar-widget-panel{background:transparent;border:none;box-shadow:none;max-height:none;border-radius:0}' +
      'forklar-widget-shell.forklar-w-mode-broadcast .forklar-widget-panel.forklar-widget-panel--title{max-width:min(96vw,1320px);width:100%}' +
      'forklar-widget-shell.forklar-w-title-window .forklar-widget-backdrop{background:rgba(6,8,18,0.42)!important;backdrop-filter:blur(8px)!important;-webkit-backdrop-filter:blur(8px)!important}' +
      'forklar-widget-shell.forklar-w-title-window.forklar-w-mode-broadcast .forklar-widget-panel.forklar-widget-panel--title{background:linear-gradient(160deg,rgba(22,26,44,0.96) 0%,rgba(10,12,26,0.98) 100%);border:1px solid rgba(255,255,255,0.1);border-radius:18px;box-shadow:0 28px 72px rgba(0,0,0,0.55);overflow:hidden;max-height:min(85vh,680px)}' +
      'forklar-widget-shell.forklar-w-title-window--medium .forklar-widget-panel.forklar-widget-panel--title{max-width:min(92vw,780px)!important;width:100%}' +
      'forklar-widget-shell.forklar-w-title-window--small .forklar-widget-panel.forklar-widget-panel--title{max-width:min(92vw,520px)!important;width:100%}' +
      'forklar-widget-shell.forklar-w-title-window--small .forklar-w-title-main{font-size:clamp(1.25rem,4vw,2.35rem)!important}' +
      'forklar-widget-shell.forklar-w-title-window--medium .forklar-w-title-main{font-size:clamp(1.45rem,4.5vw,3rem)!important}' +
      '.forklar-widget-titlebar{padding:14px 22px 0;font-size:12px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-muted)}' +
      '.forklar-widget-titlebar:empty{display:none}' +
      '.forklar-widget-body{padding:20px 24px 22px;overflow:auto;flex:1;min-height:0;font-size:var(--base-font-size,14px);line-height:1.55}' +
      '.forklar-widget-body--center{display:flex;flex-direction:column;align-items:center}' +
      '.forklar-widget-body--center > *{max-width:100%}' +
      '.forklar-widget-body--text-left{text-align:left;align-items:stretch}' +
      '.forklar-widget-body .forklar-w-md-wrap{max-width:38rem;margin:0 auto;text-align:left}' +
      '.forklar-widget-body .forklar-w-md-wrap h1,.forklar-widget-body .forklar-w-md-wrap h2,.forklar-widget-body .forklar-w-md-wrap h3{text-align:center;margin-top:0.4em}' +
      '.forklar-widget-body .forklar-w-md-fallback{white-space:pre-wrap;margin:0;font:inherit}' +
      '.forklar-widget-body img.forklar-w-image{max-width:100%;height:auto;display:block;margin:0 auto;border-radius:10px}' +
      '.forklar-widget-body .forklar-w-img-caption{margin-top:10px;font-size:13px;color:var(--text-muted)}' +
      '.forklar-widget-body .forklar-w-html-wrap{max-width:100%;text-align:left;font-size:var(--base-font-size,14px);line-height:1.55}' +
      '.forklar-widget-body .forklar-w-svg-wrap{display:flex;align-items:center;justify-content:center;max-width:100%}' +
      '.forklar-widget-body .forklar-w-svg-holder{display:flex;align-items:center;justify-content:center;overflow:hidden}' +
      '.forklar-widget-body .forklar-w-svg-holder svg{display:block;max-width:100%;height:auto}' +
      '.forklar-widget-actions{padding:12px 22px 18px;display:flex;flex-wrap:wrap;gap:8px;justify-content:center;border-top:1px solid var(--border)}' +
      '.forklar-widget-actions:empty{display:none}' +
      '.forklar-w-btn{display:inline-flex;align-items:center;justify-content:center;padding:6px 16px;min-height:32px;font-size:13px;font-weight:600;border-radius:9px;border:1px solid transparent;cursor:pointer;transition:background 0.15s ease,transform 0.1s ease,box-shadow 0.15s ease}' +
      '.forklar-w-btn--primary{background:var(--accent);color:#f8fafc;border-color:transparent;box-shadow:0 1px 2px rgba(15,23,42,0.12)}' +
      '.forklar-w-btn--primary:hover{filter:brightness(1.06)}' +
      '.forklar-w-btn--primary:active{transform:translateY(1px)}' +
      '.forklar-w-q-prompt{margin:0 0 14px 0;font-size:17px;font-weight:600;line-height:1.35;text-align:center;max-width:min(100%,52rem)}' +
      '.forklar-w-q-outer{width:100%;max-width:min(100%,56rem);margin:0 auto}' +
      '.forklar-w-q-choices{display:flex;flex-direction:column;gap:10px;margin-bottom:14px;text-align:left}' +
      '.forklar-w-q-choices label{display:flex;align-items:flex-start;gap:10px;cursor:pointer;padding:10px 12px;border-radius:11px;border:2px solid var(--border);background:var(--bg-code);transition:border-color 0.2s ease,background 0.2s ease,opacity 0.2s ease}' +
      '.forklar-w-q-label--dim{opacity:0.42}' +
      '.forklar-w-q-label--correct{border-color:#16a34a!important;background:rgba(22,163,74,0.14)!important;opacity:1!important}' +
      '.forklar-w-q-label--wrong{border-color:#dc2626!important;background:rgba(220,38,38,0.12)!important;opacity:1!important}' +
      'body[data-theme="dark"] .forklar-w-q-label--correct{background:rgba(22,163,74,0.18)!important}' +
      'body[data-theme="dark"] .forklar-w-q-label--wrong{background:rgba(220,38,38,0.16)!important}' +
      '.forklar-w-q-input{width:100%;padding:9px 12px;border-radius:10px;border:2px solid var(--border);background:var(--bg-code);color:var(--text);font:inherit;box-sizing:border-box;transition:border-color 0.2s ease,background 0.2s ease}' +
      '.forklar-w-q-input--correct{border-color:#16a34a!important;background:rgba(22,163,74,0.08)!important}' +
      '.forklar-w-q-input--wrong{border-color:#dc2626!important;background:rgba(220,38,38,0.08)!important}' +
      '.forklar-w-q-reveal{margin-top:12px;padding:10px 12px;border-radius:10px;font-size:14px;font-weight:600;text-align:center}' +
      '.forklar-w-q-reveal--ok{color:#15803d;background:rgba(22,163,74,0.12);border:1px solid rgba(22,163,74,0.35)}' +
      '.forklar-w-q-reveal--bad{color:var(--text);background:var(--bg-panel);border:1px solid var(--border)}' +
      '.forklar-w-q-reveal--bad strong{color:#16a34a;font-weight:700}' +
      '.forklar-w-q-msg{min-height:1.25em;font-size:12px;color:#e11d48;margin-bottom:8px;text-align:center}' +
      '.forklar-w-broadcast-stage{width:100%;text-align:center;padding:min(6vh,48px) min(24px,4vw)}' +
      '.forklar-w-title-main{font-size:clamp(1.75rem,5.5vw,3.75rem);font-weight:750;letter-spacing:0.14em;line-height:1.12;color:#f1f5f9;text-transform:uppercase;text-shadow:0 2px 32px rgba(0,0,0,0.45),0 0 1px rgba(0,0,0,0.8)}' +
      '.forklar-w-title-sub{margin-top:clamp(12px,2.5vw,28px);font-size:clamp(0.95rem,2.4vw,1.35rem);font-weight:500;letter-spacing:0.06em;color:rgba(226,232,240,0.88);opacity:0;transition:opacity 0.45s ease;text-shadow:0 1px 18px rgba(0,0,0,0.4)}' +
      '.forklar-w-title-sub.forklar-w-visible{opacity:1}' +
      '.forklar-w-anim--fade-in .forklar-w-title-main,.forklar-w-anim--fade-in .forklar-w-title-sub{animation:forklarWFadeIn 0.55s ease forwards}' +
      '.forklar-w-anim--slide-up .forklar-w-title-main{animation:forklarWSlideUp 0.6s ease forwards}' +
      '.forklar-w-anim--zoom-in .forklar-w-title-main{animation:forklarWZoomIn 0.55s ease forwards}' +
      '.forklar-w-anim--blur-in .forklar-w-title-main{animation:forklarWBlurIn 0.6s ease forwards}' +
      '@keyframes forklarWFadeIn{from{opacity:0}to{opacity:1}}' +
      '@keyframes forklarWSlideUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}' +
      '@keyframes forklarWZoomIn{from{opacity:0;transform:scale(0.94)}to{opacity:1;transform:scale(1)}}' +
      '@keyframes forklarWBlurIn{from{opacity:0;filter:blur(8px)}to{opacity:1;filter:blur(0)}}';
    document.head.appendChild(st);
  }

  if (!customElements.get('forklar-widget-shell')) {
    class ForklarWidgetShell extends HTMLElement {
      constructor() {
        super();
      }
    }
    customElements.define('forklar-widget-shell', ForklarWidgetShell);
  }

  /**
   * Generisk parallell-tale for widgets. Leser kun payload.speak (eksplisitt
   * narrasjon). Brukes av markdown/image/html/svg; title har sin egen
   * speakForTitle med fade-synkronisering.
   */
  async function speakForWidget(api, payload) {
    const speakUtteranceWithOpts = api && api.speakUtteranceWithOpts;
    const getForklarVoices = api && api.getForklarVoices;
    if (!speakUtteranceWithOpts) return;
    const text = payload && payload.speak != null ? String(payload.speak).trim() : '';
    if (!text) return;
    const opts = {
      lang: payload.speak_lang || 'nb-NO',
      voiceName: payload.speak_voice,
      pitch: payload.speak_pitch,
      rate: payload.speak_rate,
      volume: payload.speak_volume
    };
    if (!opts.voiceName && getForklarVoices) {
      const vNb = getForklarVoices();
      opts.voice = vNb.female || vNb.male;
    }
    await speakUtteranceWithOpts(text, opts);
  }

  /**
   * Felles interaksjons-loop for visuelle widgets med parallell tale.
   * Venter til EN av: brukeren klikker OK, explainAbort utløses,
   * eller auto_advance_ms-timeren utløper. Avbryter tale ved exit.
   * Fyrer speakForWidget i bakgrunnen med valgfri speak_after_ms-delay.
   */
  async function awaitWidgetInteraction(userDone, payload, explainAbortRef, api) {
    const p = payload || {};
    const speakDelay = p.speak_after_ms != null ? Math.max(0, parseFloat(p.speak_after_ms) || 0) : 0;
    (async function () {
      try {
        if (speakDelay > 0) await sleep(speakDelay);
        if (explainAbortRef && explainAbortRef.aborted) return;
        await speakForWidget(api, p);
      } catch (e) {}
    })();
    const racers = [userDone, pollAbort(explainAbortRef)];
    if (p.auto_advance_ms != null && !isNaN(parseFloat(p.auto_advance_ms))) {
      const ms = Math.max(0, parseFloat(p.auto_advance_ms));
      racers.push(new Promise(function (resolve) { setTimeout(function () { resolve(false); }, ms); }));
    }
    await Promise.race(racers);
    try { if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel(); } catch (e) {}
  }

  async function speakForTitle(api, payload) {
    const speakUtteranceWithOpts = api && api.speakUtteranceWithOpts;
    const getForklarVoices = api && api.getForklarVoices;
    if (!speakUtteranceWithOpts) return;
    let text = '';
    if (payload.speak != null && String(payload.speak).trim() !== '') {
      text = String(payload.speak).trim();
    } else if (payload.speak_text === true) {
      text = String(payload.text || '');
      if (payload.speak_subtitle === true && payload.subtitle) {
        text = (text ? text + ' ' : '') + String(payload.subtitle);
      }
    }
    if (!text.trim()) return;
    const opts = {
      lang: payload.speak_lang || 'nb-NO',
      voiceName: payload.speak_voice,
      pitch: payload.speak_pitch,
      rate: payload.speak_rate,
      volume: payload.speak_volume
    };
    if (!opts.voiceName && getForklarVoices) {
      const vNb = getForklarVoices();
      opts.voice = vNb.female || vNb.male;
    }
    await speakUtteranceWithOpts(text, opts);
  }

  function openShell(backdropStyle, panelClass, options) {
    options = options || {};
    injectStylesOnce();
    const sh = ensureShell();
    sh.classList.remove(
      'forklar-w-leaving',
      'forklar-w-mode-broadcast',
      'forklar-w-mode-card',
      'forklar-w-title-window',
      'forklar-w-title-window--small',
      'forklar-w-title-window--medium'
    );
    sh.classList.add(options.mode === 'broadcast' ? 'forklar-w-mode-broadcast' : 'forklar-w-mode-card');
    const backdrop = sh.querySelector('.forklar-widget-backdrop');
    const panel = sh.querySelector('.forklar-widget-panel');
    const bodyEl = sh.querySelector('#forklarWidgetBody');
    if (panel) panel.removeAttribute('style');
    if (bodyEl) {
      bodyEl.className = 'forklar-widget-body ' + (options.bodyClass != null ? options.bodyClass : 'forklar-widget-body--center');
    }
    if (backdrop && backdropStyle) {
      backdrop.setAttribute('style', backdropStyle);
    } else if (backdrop) {
      backdrop.removeAttribute('style');
    }
    if (panel) {
      panel.className = 'forklar-widget-panel ' + (panelClass || 'forklar-widget-panel--md');
    }
    sh.classList.add('forklar-widget-open');
    sh.setAttribute('aria-hidden', 'false');
    return sh;
  }

  function closeShell() {
    if (!shellEl) return;
    shellEl.classList.remove(
      'forklar-widget-open',
      'forklar-w-leaving',
      'forklar-w-mode-broadcast',
      'forklar-w-mode-card',
      'forklar-w-title-window',
      'forklar-w-title-window--small',
      'forklar-w-title-window--medium'
    );
    shellEl.setAttribute('aria-hidden', 'true');
    const tb = shellEl.querySelector('#forklarWidgetTitlebar');
    const body = shellEl.querySelector('#forklarWidgetBody');
    const act = shellEl.querySelector('#forklarWidgetActions');
    if (tb) tb.innerHTML = '';
    if (body) {
      body.className = 'forklar-widget-body forklar-widget-body--center';
      body.innerHTML = '';
    }
    if (act) act.innerHTML = '';
  }

  function modalSizeClass(modal) {
    const m = (modal || 'md').toLowerCase();
    if (m === 'sm') return 'forklar-widget-panel--sm';
    if (m === 'lg') return 'forklar-widget-panel--lg';
    if (m === 'xl') return 'forklar-widget-panel--xl';
    if (m === 'xxl') return 'forklar-widget-panel--xxl';
    if (m === 'fullscreen') return 'forklar-widget-panel--fullscreen';
    return 'forklar-widget-panel--md';
  }

  async function showModal(name, payload, explainAbortRef, api) {
    injectStylesOnce();
    const p = payload && typeof payload === 'object' ? payload : {};
    const n = String(name || '').toLowerCase();

    if (n === 'error') {
      return renderError(p, explainAbortRef, api);
    }
    if (n === 'markdown') {
      return renderMarkdown(p, explainAbortRef, api);
    }
    if (n === 'title') {
      return renderTitle(p, explainAbortRef, api);
    }
    if (n === 'question') {
      return renderQuestion(p, explainAbortRef, api);
    }
    if (n === 'image') {
      return renderImage(p, explainAbortRef, api);
    }
    if (n === 'html') {
      return renderHtml(p, explainAbortRef, api);
    }
    if (n === 'svg') {
      return renderSvg(p, explainAbortRef, api);
    }
    return renderError({ message: 'Ukjent widget: ' + String(name) }, explainAbortRef, api);
  }

  function raceUserOrAbort(userPromise, explainAbortRef) {
    return Promise.race([userPromise, pollAbort(explainAbortRef)]);
  }

  async function renderError(payload, explainAbortRef, api) {
    const msg = escapeHtml((payload && payload.message) || 'Feil');
    openShell(null, 'forklar-widget-panel--md', { mode: 'card' });
    const sh = shellEl;
    const tb = sh.querySelector('#forklarWidgetTitlebar');
    const body = sh.querySelector('#forklarWidgetBody');
    const act = sh.querySelector('#forklarWidgetActions');
    tb.textContent = 'Feil';
    body.innerHTML = '<p class="forklar-w-q-prompt">' + msg + '</p>';
    const userDone = new Promise(function (resolve) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'forklar-w-btn forklar-w-btn--primary';
      btn.textContent = 'OK';
      btn.addEventListener('click', function () {
        resolve(false);
      });
      act.appendChild(btn);
    });
    await raceUserOrAbort(userDone, explainAbortRef);
    try {
      if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel();
    } catch (e) {}
    closeShell();
  }

  async function renderMarkdown(payload, explainAbortRef, api) {
    const p = payload || {};
    const title = p.title ? String(p.title) : '';
    const okLabel = p.ok_label || 'OK';
    const modal = modalSizeClass(p.modal || 'lg');
    const mdSource = p.body != null ? p.body : (p.text || '');
    openShell(null, modal, { mode: 'card' });
    const sh = shellEl;
    const tb = sh.querySelector('#forklarWidgetTitlebar');
    const body = sh.querySelector('#forklarWidgetBody');
    const act = sh.querySelector('#forklarWidgetActions');
    tb.textContent = title;
    body.innerHTML = '<div class="forklar-w-md-wrap">' + renderMarkdownHtml(mdSource) + '</div>';
    const canHideOk = p.hide_ok === true && p.auto_advance_ms != null;
    const userDone = new Promise(function (resolve) {
      if (canHideOk) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'forklar-w-btn forklar-w-btn--primary';
      btn.textContent = okLabel;
      btn.addEventListener('click', function () { resolve(false); });
      act.appendChild(btn);
    });
    await awaitWidgetInteraction(userDone, p, explainAbortRef, api);
    closeShell();
  }

  async function renderTitle(payload, explainAbortRef, api) {
    const p = payload || {};
    const enter = p.enter || { type: 'fade', duration_ms: 550 };
    const entClass = effectClass(enter);
    const fadeInMs = p.fade_in_ms != null ? Number(p.fade_in_ms) : effectDurationMs(enter, 550);
    const fadeOutMs = p.fade_out_ms != null ? Number(p.fade_out_ms) : 700;
    const displayTotal =
      p.display_ms != null
        ? Number(p.display_ms)
        : p.auto_advance_ms != null
          ? Number(p.auto_advance_ms)
          : 3800;
    const holdMs = Math.max(200, displayTotal - fadeInMs - fadeOutMs);

    const panelCardStyle = [];
    if (p.background) panelCardStyle.push('background:' + p.background);
    if (p.border) panelCardStyle.push('border:' + p.border);
    if (p.border_radius) panelCardStyle.push('border-radius:' + p.border_radius);
    if (p.padding) panelCardStyle.push('padding:' + p.padding);
    if (p.box_shadow) panelCardStyle.push('box-shadow:' + p.box_shadow);

    const mainTextStyle = [];
    if (p.color) mainTextStyle.push('color:' + p.color);
    if (p.font_family) mainTextStyle.push('font-family:' + p.font_family);
    if (p.font_size) mainTextStyle.push('font-size:' + p.font_size);
    if (p.font_weight != null) mainTextStyle.push('font-weight:' + p.font_weight);
    if (p.letter_spacing) mainTextStyle.push('letter-spacing:' + p.letter_spacing);
    if (p.text_transform != null && String(p.text_transform).trim() !== '') {
      mainTextStyle.push('text-transform:' + p.text_transform);
    }

    let backdropStyle = '';
    if (p.background_opacity != null && !isNaN(parseFloat(p.background_opacity))) {
      const o = Math.max(0, Math.min(1, parseFloat(p.background_opacity)));
      backdropStyle = 'background:rgba(8,10,20,' + (0.55 + o * 0.38) + ')';
    }
    if (p.backdrop_blur != null && !isNaN(parseFloat(p.backdrop_blur)) && parseFloat(p.backdrop_blur) > 0) {
      const b = parseFloat(p.backdrop_blur);
      backdropStyle += (backdropStyle ? ';' : '') + 'backdrop-filter:blur(' + b + 'px);-webkit-backdrop-filter:blur(' + b + 'px)';
    }

    openShell(backdropStyle || null, 'forklar-widget-panel--title', { mode: 'broadcast' });
    const sh = shellEl;
    var titleSize = (p.size != null ? String(p.size) : 'full').toLowerCase();
    if (titleSize === 'small' || titleSize === 'medium') {
      sh.classList.add('forklar-w-title-window', titleSize === 'small' ? 'forklar-w-title-window--small' : 'forklar-w-title-window--medium');
    }
    const panelEl = sh.querySelector('.forklar-widget-panel');
    var titlePanelStyle = panelCardStyle.slice();
    if (p.modal === 'fullscreen') titlePanelStyle.push('max-width:min(98vw,1400px)');
    else if (p.modal === 'xl') titlePanelStyle.push('max-width:min(96vw,1320px)');
    if (panelEl) {
      if (titlePanelStyle.length) panelEl.setAttribute('style', titlePanelStyle.join(';'));
      else panelEl.removeAttribute('style');
    }
    const tb = sh.querySelector('#forklarWidgetTitlebar');
    const body = sh.querySelector('#forklarWidgetBody');
    const act = sh.querySelector('#forklarWidgetActions');
    if (tb) tb.innerHTML = '';
    if (act) act.innerHTML = '';

    const stage = document.createElement('div');
    stage.className = 'forklar-w-broadcast-stage ' + (entClass || '').trim();
    if (fadeInMs) stage.style.animationDuration = fadeInMs / 1000 + 's';

    const inner = document.createElement('div');
    inner.className = 'forklar-w-title-wrap';
    const main = document.createElement('div');
    main.className = 'forklar-w-title-main';
    main.textContent = String(p.text || '');
    if (mainTextStyle.length) main.setAttribute('style', mainTextStyle.join(';'));

    const sub = document.createElement('div');
    sub.className = 'forklar-w-title-sub';
    sub.textContent = String(p.subtitle || '');
    if (p.subtitle_color) sub.style.color = p.subtitle_color;
    if (p.subtitle_font_size) sub.style.fontSize = p.subtitle_font_size;

    inner.appendChild(main);
    inner.appendChild(sub);
    stage.appendChild(inner);
    body.innerHTML = '';
    body.appendChild(stage);

    const subDelay = p.subtitle_delay_ms != null ? parseFloat(p.subtitle_delay_ms) : 400;
    const subDur = p.subtitle_duration_ms != null ? parseFloat(p.subtitle_duration_ms) : null;
    if (p.subtitle) {
      setTimeout(function () {
        sub.classList.add('forklar-w-visible');
      }, Math.max(0, subDelay));
      if (subDur != null && !isNaN(subDur) && subDur > 0) {
        setTimeout(function () {
          sub.classList.remove('forklar-w-visible');
        }, Math.max(0, subDelay) + subDur);
      }
    }

    function finish() {
      try {
        if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel();
      } catch (e) {}
      closeShell();
    }

    if (p.show_ok === true) {
      const userDone = new Promise(function (resolve) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'forklar-w-btn forklar-w-btn--primary';
        btn.textContent = p.ok_label || 'OK';
        btn.addEventListener('click', function () {
          resolve(false);
        });
        act.appendChild(btn);
      });
      await sleep(Math.min(fadeInMs, 500));
      const speakAfter = p.speak_after_ms != null ? parseFloat(p.speak_after_ms) : 0;
      await sleep(Math.max(0, speakAfter));
      if (!(explainAbortRef && explainAbortRef.aborted)) await speakForTitle(api, p);
      await raceUserOrAbort(userDone, explainAbortRef);
      finish();
      return;
    }

    await sleep(Math.min(fadeInMs, 800));
    const speakAfter = p.speak_after_ms != null ? parseFloat(p.speak_after_ms) : 0;
    await sleep(Math.max(0, speakAfter));
    if (!(explainAbortRef && explainAbortRef.aborted)) await speakForTitle(api, p);

    const abortedDuringHold = await raceUserOrAbort(sleep(holdMs), explainAbortRef);
    if (abortedDuringHold) {
      finish();
      return;
    }
    sh.classList.add('forklar-w-leaving');
    await sleep(fadeOutMs);
    finish();
  }

  async function renderQuestion(payload, explainAbortRef, api) {
    const p = payload || {};
    const prompt = String(p.prompt || 'Spørsmål');
    const choices = Array.isArray(p.choices) ? p.choices.map(String) : null;
    const shuffle = !!p.shuffle;
    const caseSensitive = !!p.case_sensitive;
    const submitLabel = p.submit_label || (choices ? 'Svar' : 'Send');
    const feedbackMs = p.feedback_delay_ms != null ? Math.max(400, Number(p.feedback_delay_ms)) : 1600;
    const requireCorrect = p.require_correct === true;
    let correctIndex = null;
    let correctStr = null;
    if (choices && choices.length) {
      if (typeof p.correct === 'number' && !isNaN(p.correct)) {
        correctIndex = p.correct | 0;
      } else if (p.correct != null) {
        const want = String(p.correct);
        correctIndex = choices.indexOf(want);
        if (correctIndex < 0) correctIndex = 0;
      } else {
        correctIndex = 0;
      }
    } else {
      correctStr = p.correct != null ? String(p.correct) : '';
    }

    let displayChoices = choices
      ? choices.map(function (c, i) {
          return { label: c, orig: i };
        })
      : null;
    if (displayChoices && shuffle) {
      displayChoices = shuffleArray(displayChoices);
    }

    const modal = modalSizeClass(p.modal || 'xxl');
    openShell(null, modal, { mode: 'card' });
    const sh = shellEl;
    const tb = sh.querySelector('#forklarWidgetTitlebar');
    const body = sh.querySelector('#forklarWidgetBody');
    const act = sh.querySelector('#forklarWidgetActions');
    tb.textContent = 'Spørsmål';
    const outer = document.createElement('div');
    outer.className = 'forklar-w-q-outer';
    const msgEl = document.createElement('div');
    msgEl.className = 'forklar-w-q-msg';
    const qEl = document.createElement('p');
    qEl.className = 'forklar-w-q-prompt';
    qEl.textContent = prompt;
    outer.appendChild(msgEl);
    outer.appendChild(qEl);
    body.appendChild(outer);

    let inputEl = null;
    let radios = null;
    const labelEls = [];

    if (displayChoices && displayChoices.length) {
      const wrap = document.createElement('div');
      wrap.className = 'forklar-w-q-choices';
      const name = 'forklar-q-' + Math.random().toString(36).slice(2);
      radios = [];
      for (let i = 0; i < displayChoices.length; i++) {
        const lab = document.createElement('label');
        const r = document.createElement('input');
        r.type = 'radio';
        r.name = name;
        r.value = String(i);
        radios.push(r);
        lab.appendChild(r);
        const span = document.createElement('span');
        span.textContent = displayChoices[i].label;
        lab.appendChild(span);
        labelEls.push(lab);
        wrap.appendChild(lab);
      }
      outer.appendChild(wrap);
    } else {
      inputEl = document.createElement('input');
      inputEl.type = 'text';
      inputEl.className = 'forklar-w-q-input';
      inputEl.setAttribute('autocomplete', 'off');
      outer.appendChild(inputEl);
    }

    function getMcSelectedIndex() {
      for (let i = 0; i < radios.length; i++) {
        if (radios[i].checked) return i;
      }
      return -1;
    }

    function freeTextIsCorrect() {
      const v = (inputEl.value || '').trim();
      if (!v) return false;
      const a = caseSensitive ? v : v.toLowerCase();
      const b = caseSensitive ? correctStr : correctStr.toLowerCase();
      return a === b;
    }

    const userDone = new Promise(function (resolve) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'forklar-w-btn forklar-w-btn--primary';
      btn.textContent = submitLabel;
      btn.addEventListener('click', function () {
        (async function () {
          if (btn.disabled) return;
          if (displayChoices && radios) {
            const sel = getMcSelectedIndex();
            if (sel < 0) {
              msgEl.textContent = 'Velg et alternativ.';
              return;
            }
            const pickedOrig = displayChoices[sel].orig;
            const isOk = pickedOrig === correctIndex;
            if (requireCorrect) {
              if (!isOk) {
                var hint = '';
                if (p.on_wrong === 'show_correct' && choices) {
                  hint = 'Riktig svar: ' + choices[correctIndex];
                }
                msgEl.textContent = hint || 'Ikke riktig, prøv igjen.';
                return;
              }
              msgEl.textContent = '';
              btn.disabled = true;
              resolve(false);
              return;
            }
            btn.disabled = true;
            for (let i = 0; i < radios.length; i++) {
              radios[i].disabled = true;
            }
            for (let j = 0; j < labelEls.length; j++) {
              const orig = displayChoices[j].orig;
              labelEls[j].classList.add('forklar-w-q-label--dim');
              if (orig === correctIndex) {
                labelEls[j].classList.remove('forklar-w-q-label--dim');
                labelEls[j].classList.add('forklar-w-q-label--correct');
              }
              if (j === sel && orig !== correctIndex) {
                labelEls[j].classList.remove('forklar-w-q-label--dim');
                labelEls[j].classList.add('forklar-w-q-label--wrong');
              }
            }
            msgEl.textContent = '';
            await raceUserOrAbort(sleep(feedbackMs), explainAbortRef);
            resolve(false);
            return;
          }

          const v = (inputEl.value || '').trim();
          if (!v) {
            msgEl.textContent = 'Skriv et svar.';
            return;
          }
          const isOk = freeTextIsCorrect();
          if (requireCorrect) {
            if (!isOk) {
              if (p.on_wrong === 'show_correct' && correctStr) {
                msgEl.textContent = 'Riktig svar: ' + correctStr;
              } else {
                msgEl.textContent = 'Ikke riktig, prøv igjen.';
              }
              return;
            }
            btn.disabled = true;
            inputEl.classList.add('forklar-w-q-input--correct');
            msgEl.textContent = '';
            resolve(false);
            return;
          }
          btn.disabled = true;
          inputEl.disabled = true;
          if (isOk) {
            inputEl.classList.add('forklar-w-q-input--correct');
            const revOk = document.createElement('div');
            revOk.className = 'forklar-w-q-reveal forklar-w-q-reveal--ok';
            revOk.textContent = 'Riktig!';
            outer.appendChild(revOk);
          } else {
            inputEl.classList.add('forklar-w-q-input--wrong');
            const revBad = document.createElement('div');
            revBad.className = 'forklar-w-q-reveal forklar-w-q-reveal--bad';
            if (correctStr) {
              revBad.innerHTML = 'Riktig svar: <strong>' + escapeHtml(correctStr) + '</strong>';
            } else {
              revBad.textContent = 'Ikke riktig.';
            }
            outer.appendChild(revBad);
          }
          msgEl.textContent = '';
          await raceUserOrAbort(sleep(feedbackMs), explainAbortRef);
          resolve(false);
        })();
      });
      act.appendChild(btn);
      if (inputEl) {
        inputEl.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter') btn.click();
        });
      }
    });

    await raceUserOrAbort(userDone, explainAbortRef);
    try {
      if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel();
    } catch (e) {}
    closeShell();
  }

  async function renderImage(payload, explainAbortRef, api) {
    const p = payload || {};
    const src = String(p.src || '').trim();
    const modal = modalSizeClass(p.modal || 'lg');
    openShell(null, modal, { mode: 'card' });
    const sh = shellEl;
    const tb = sh.querySelector('#forklarWidgetTitlebar');
    const body = sh.querySelector('#forklarWidgetBody');
    const act = sh.querySelector('#forklarWidgetActions');
    tb.textContent = p.title ? String(p.title) : '';
    const cap = p.caption ? String(p.caption) : '';
    const alt = p.alt != null ? String(p.alt) : cap || '';
    const maxH = p.max_height || 'min(50vh, 360px)';
    if (!src) {
      body.innerHTML = '<p>Bilde mangler (src).</p>';
    } else {
      body.innerHTML =
        '<img class="forklar-w-image" src="' +
        escapeHtml(src) +
        '" alt="' +
        escapeHtml(alt) +
        '" style="max-height:' +
        escapeHtml(String(maxH)) +
        ';object-fit:' +
        (p.fit === 'cover' ? 'cover' : 'contain') +
        '"/>';
      if (cap) {
        body.innerHTML += '<div class="forklar-w-img-caption">' + escapeHtml(cap) + '</div>';
      }
      const img = body.querySelector('img');
      if (img) {
        img.addEventListener('error', function () {
          img.replaceWith(document.createTextNode('Kunne ikke laste bildet.'));
        });
      }
    }
    const okLabel = p.ok_label || 'OK';
    const canHideOk = p.hide_ok === true && p.auto_advance_ms != null;
    const userDone = new Promise(function (resolve) {
      if (canHideOk) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'forklar-w-btn forklar-w-btn--primary';
      btn.textContent = okLabel;
      btn.addEventListener('click', function () { resolve(false); });
      act.appendChild(btn);
    });
    await awaitWidgetInteraction(userDone, p, explainAbortRef, api);
    closeShell();
  }

  async function renderHtml(payload, explainAbortRef, api) {
    const p = payload || {};
    const html = String(p.body != null ? p.body : (p.html != null ? p.html : ''));
    const title = p.title ? String(p.title) : '';
    const okLabel = p.ok_label || 'OK';
    const modal = modalSizeClass(p.modal || 'lg');
    openShell(null, modal, { mode: 'card' });
    const sh = shellEl;
    const tb = sh.querySelector('#forklarWidgetTitlebar');
    const body = sh.querySelector('#forklarWidgetBody');
    const act = sh.querySelector('#forklarWidgetActions');
    tb.textContent = title;
    body.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'forklar-w-html-wrap';
    wrap.innerHTML = html;
    body.appendChild(wrap);
    const canHideOk = p.hide_ok === true && p.auto_advance_ms != null;
    const userDone = new Promise(function (resolve) {
      if (canHideOk) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'forklar-w-btn forklar-w-btn--primary';
      btn.textContent = okLabel;
      btn.addEventListener('click', function () { resolve(false); });
      act.appendChild(btn);
    });
    await awaitWidgetInteraction(userDone, p, explainAbortRef, api);
    closeShell();
  }

  async function renderSvg(payload, explainAbortRef, api) {
    const p = payload || {};
    const svg = String(p.body != null ? p.body : (p.svg != null ? p.svg : '')).trim();
    const title = p.title ? String(p.title) : '';
    const caption = p.caption ? String(p.caption) : '';
    const maxH = p.max_height || 'min(60vh, 520px)';
    const okLabel = p.ok_label || 'OK';
    const modal = modalSizeClass(p.modal || 'lg');
    openShell(null, modal, { mode: 'card' });
    const sh = shellEl;
    const tb = sh.querySelector('#forklarWidgetTitlebar');
    const body = sh.querySelector('#forklarWidgetBody');
    const act = sh.querySelector('#forklarWidgetActions');
    tb.textContent = title;
    body.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'forklar-w-svg-wrap';
    const holder = document.createElement('div');
    holder.className = 'forklar-w-svg-holder';
    holder.style.maxHeight = maxH;
    holder.innerHTML = svg || '<p>SVG mangler.</p>';
    const svgEl = holder.querySelector('svg');
    if (svgEl) {
      if (!svgEl.getAttribute('width') && !svgEl.style.width) svgEl.style.maxWidth = '100%';
      if (!svgEl.getAttribute('height') && !svgEl.style.height) svgEl.style.maxHeight = maxH;
    }
    wrap.appendChild(holder);
    body.appendChild(wrap);
    if (caption) {
      const cap = document.createElement('div');
      cap.className = 'forklar-w-img-caption';
      cap.textContent = caption;
      body.appendChild(cap);
    }
    const canHideOk = p.hide_ok === true && p.auto_advance_ms != null;
    const userDone = new Promise(function (resolve) {
      if (canHideOk) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'forklar-w-btn forklar-w-btn--primary';
      btn.textContent = okLabel;
      btn.addEventListener('click', function () { resolve(false); });
      act.appendChild(btn);
    });
    await awaitWidgetInteraction(userDone, p, explainAbortRef, api);
    closeShell();
  }

  window.ForklarWidgets = {
    parseWidgetLine: parseWidgetLine,
    showModal: showModal
  };
})();
