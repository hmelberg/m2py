    /* ===================================================================
       Auth module — magic-link login, bearer token, /auth/me refresh
       =================================================================== */
    (function authModule() {
      var T = window.t || function (s, p) { return p ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in p ? p[k] : m; }) : s; };
      const LS_TOKEN = 'mdapi_token';
      const LS_USER = 'mdapi_user';
      const LS_BASE = 'md_ai_api_base';
      const DEFAULT_BASE = 'https://mdataapi.anvil.app';

      const state = {
        token: localStorage.getItem(LS_TOKEN) || '',
        user: null,
      };
      try { state.user = JSON.parse(localStorage.getItem(LS_USER) || 'null'); } catch (e) {}

      function apiBase() {
        return (localStorage.getItem(LS_BASE) || DEFAULT_BASE).replace(/\/+$/, '');
      }

      const $ = (id) => document.getElementById(id);
      const dom = {};
      function cacheDom() {
        ['loginBackdrop','loginStep1','loginStep2','loginStep3',
         'loginEmail','loginSubmit','loginCancel','loginDone','loginSentEmail','loginCode','loginVerify','loginCodeError'
        ].forEach(id => { dom[id] = $(id); });
      }

      function setStep(n) {
        if (!dom.loginStep1) return;
        dom.loginStep1.style.display = n === 1 ? '' : 'none';
        dom.loginStep2.style.display = n === 2 ? '' : 'none';
        dom.loginStep3.style.display = n === 3 ? '' : 'none';
      }

      function showLogin() {
        if (!dom.loginBackdrop) return;
        setStep(1);
        dom.loginBackdrop.classList.add('open');
        setTimeout(() => dom.loginEmail && dom.loginEmail.focus(), 60);
      }
      function showLoginCodeStep() {
        showLogin();
        setStep(2);
        if (dom.loginSentEmail) dom.loginSentEmail.textContent = T('(ingen epost — bruker delt kode)');
        setTimeout(() => dom.loginCode && dom.loginCode.focus(), 60);
      }
      function hideLogin() { dom.loginBackdrop && dom.loginBackdrop.classList.remove('open'); }

      async function requestMagicLink(email) {
        const lang = (window.M2PY_LANG === 'en') ? 'en' : 'no'; // e-posten følger UI-språket
        const res = await fetch(apiBase() + '/_/api/auth/email/request', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, lang }),
        });
        if (!res.ok) {
          const text = await res.text();
          throw new Error(T('Kunne ikke sende lenke: {msg}', { msg: text || res.status }));
        }
        return res.json();
      }

      async function verifyCode(code) {
        const res = await fetch(apiBase() + '/_/api/auth/email/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code }),
        });
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || ('HTTP ' + res.status));
        }
        return res.json();
      }

      async function verifyPastedCode() {
        const code = (dom.loginCode.value || '').trim();
        if (!code) {
          dom.loginCodeError.textContent = T('Skriv inn koden.');
          return;
        }
        dom.loginCodeError.textContent = '';
        dom.loginVerify.disabled = true;
        try {
          const data = await verifyCode(code);
          persistLogin(data);
          hideLogin();
          if (typeof refreshUserPanel === 'function') refreshUserPanel();
        } catch (e) {
          dom.loginCodeError.textContent = e.message || T('Koden er ugyldig eller utløpt.');
        } finally {
          dom.loginVerify.disabled = false;
        }
      }

      async function refreshMe() {
        if (!state.token) return null;
        try {
          const res = await fetch(apiBase() + '/_/api/auth/me', {
            headers: { 'Authorization': 'Bearer ' + state.token },
          });
          if (res.status === 401) { logoutLocal(); return null; }
          if (!res.ok) return null;
          const data = await res.json();
          if (data.user) {
            state.user = data.user;
            localStorage.setItem(LS_USER, JSON.stringify(state.user));
          }
          return data;
        } catch (e) {
          return null;
        }
      }

      function logoutLocal() {
        state.token = '';
        state.user = null;
        localStorage.removeItem(LS_TOKEN);
        localStorage.removeItem(LS_USER);
        if (window.mdUpdateAskVisibility) window.mdUpdateAskVisibility();
      }

      async function logout() {
        try {
          await fetch(apiBase() + '/_/api/auth/logout', {
            method: 'POST',
            headers: state.token ? { 'Authorization': 'Bearer ' + state.token } : {},
          });
        } catch (e) {}
        logoutLocal();
      }

      function persistLogin(data) {
        state.token = data.token;
        state.user = data.user;
        localStorage.setItem(LS_TOKEN, state.token);
        localStorage.setItem(LS_USER, JSON.stringify(state.user));
        if (window.mdUpdateAskVisibility) window.mdUpdateAskVisibility();
      }

      async function handleLoginParam() {
        const params = new URLSearchParams(window.location.search);
        const code = params.get('login');
        if (!code) return false;
        // Show step3 immediately to give visual feedback
        if (dom.loginBackdrop) {
          setStep(3);
          dom.loginBackdrop.classList.add('open');
        }
        try {
          const data = await verifyCode(code);
          persistLogin(data);
          // Clean URL
          params.delete('login');
          const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
          history.replaceState({}, document.title, newUrl);
          hideLogin();
          return true;
        } catch (e) {
          alert(T('Påloggings-lenken er ugyldig eller utløpt: {msg}', { msg: e.message }));
          params.delete('login');
          history.replaceState({}, document.title, window.location.pathname);
          hideLogin();
          return false;
        }
      }

      function init() {
        cacheDom();
        if (!dom.loginBackdrop) return;

        dom.loginSubmit.addEventListener('click', async () => {
          const email = (dom.loginEmail.value || '').trim();
          if (!email || !email.includes('@')) {
            alert(T('Skriv inn en gyldig e-postadresse.'));
            return;
          }
          dom.loginSubmit.disabled = true;
          const orig = dom.loginSubmit.textContent;
          dom.loginSubmit.textContent = T('Sender…');
          try {
            await requestMagicLink(email);
            dom.loginSentEmail.textContent = email;
            setStep(2);
            setTimeout(() => dom.loginCode && dom.loginCode.focus(), 100);
          } catch (e) {
            alert(e.message);
          } finally {
            dom.loginSubmit.disabled = false;
            dom.loginSubmit.textContent = orig;
          }
        });
        dom.loginEmail.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') { e.preventDefault(); dom.loginSubmit.click(); }
        });
        dom.loginCancel.addEventListener('click', hideLogin);
        dom.loginDone.addEventListener('click', hideLogin);
        dom.loginVerify.addEventListener('click', verifyPastedCode);
        dom.loginCode.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            verifyPastedCode();
          }
        });
        dom.loginBackdrop.addEventListener('click', (e) => {
          if (e.target === dom.loginBackdrop) hideLogin();
        });

        const switchLink = document.getElementById('loginSwitchToCode');
        if (switchLink) {
          switchLink.addEventListener('click', (e) => {
            e.preventDefault();
            setStep(2);
            if (dom.loginSentEmail) dom.loginSentEmail.textContent = T('(ingen epost — bruker delt kode)');
            setTimeout(() => dom.loginCode && dom.loginCode.focus(), 60);
          });
        }

        // On load: handle ?login=, then refresh /auth/me if we have a token
        handleLoginParam().then((handled) => {
          if (state.token) refreshMe();
        });
      }

      // Public surface for aiModule and other consumers
      window.mdAuth = {
        get token() { return state.token; },
        get user() { return state.user; },
        get isLoggedIn() { return !!state.token; },
        apiBase,
        showLogin,
        showLoginCodeStep,
        hideLogin,
        refreshMe,
        logout,
      };

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
      } else {
        init();
      }
    })();
