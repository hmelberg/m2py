(function (global) {
  'use strict';
  var NL = {};
  var LABEL_MODE = { py: 'python', r: 'r', duck: 'duckdb' }; // extensible: statx, jamovi

  NL.hostnameMode = function (hostname) {
    var host = String(hostname || '').toLowerCase();
    var firstLabel = host.split('.')[0];
    if (Object.prototype.hasOwnProperty.call(LABEL_MODE, firstLabel)) return LABEL_MODE[firstLabel];
    if (host.indexOf('micro') !== -1) return 'microdata';
    return 'python';
  };

  var RAW_BASE = 'https://raw.githubusercontent.com/';

  // "user.repo.a.b.file.ext" -> [main url, master url]; null if it can't be a dotted ref.
  NL.resolveDotted = function (dotted) {
    var tokens = String(dotted || '').split('.');
    // need user, repo, >=1 path token, and an extension token => >=4 tokens,
    // last token is the extension, second-to-last+ form the file stem/path.
    if (tokens.length < 4) return null;
    var user = tokens[0], repo = tokens[1];
    var rest = tokens.slice(2);                 // [...path segs..., stem, ext]
    var ext = rest.pop();
    if (!user || !repo || !ext || rest.length < 1) return null;
    var path = rest.join('/') + '.' + ext;      // dots between path segs -> slashes
    return ['main', 'master'].map(function (br) {
      return RAW_BASE + user + '/' + repo + '/' + br + '/' + path;
    });
  };

  NL.classifyHash = function (hash) {
    var h = String(hash || '');
    if (h.charAt(0) === '#') h = h.slice(1);
    if (!h) return null;
    if (/^s=/.test(h)) return { action: 'open', kind: 'share' };

    // raw-url fallback: url=... or output=...
    var mRaw = h.match(/^(output|url)=(.+)$/);
    if (mRaw) {
      return { action: mRaw[1] === 'output' ? 'output' : 'open', kind: 'raw', raw: decodeURIComponent(mRaw[2]) };
    }

    // dotted shorthand, optional "output." prefix
    var action = 'open', dotted = h;
    if (/^output\./.test(h)) { action = 'output'; dotted = h.slice('output.'.length); }
    var urls = NL.resolveDotted(dotted);
    if (!urls) return null;
    return { action: action, kind: 'dotted', urls: urls };
  };

  NL.welcomeVariant = function (hostname, app, isOutputOnly) {
    if (isOutputOnly) return null;
    if (NL.hostnameMode(hostname) === 'microdata') return 'microdata';
    return app === 'safestat' ? 'safestat_general' : 'openstat_general';
  };

  var MD_START = '__micro_transform_start_markdown__';
  var MD_END = '__micro_transform_end__';

  function emitMarkdownR(text) {
    var safe = String(text).split(MD_END).join('');          // neutralize injected end marker
    var block = '\n' + MD_START + '\n' + safe + '\n' + MD_END + '\n';
    return 'cat(' + JSON.stringify(block) + ')';             // JSON string ≈ R double-quoted literal
  }

  NL.rProsePrep = function (src) {
    var lines = String(src == null ? '' : src).split('\n');
    var out = [], buf = null;
    function flush() {
      if (buf && buf.length) out.push(emitMarkdownR(buf.join('\n')));
      buf = null;
    }
    for (var i = 0; i < lines.length; i++) {
      var m = lines[i].match(/^\s*#'\s?(.*)$/);
      if (m) { if (!buf) buf = []; buf.push(m[1]); }
      else { flush(); out.push(lines[i]); }
    }
    flush();
    return out.join('\n');
  };

  NL.autorunNeedsGate = function (app, hasSecret) {
    return app === 'safestat' || !!hasSecret;
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = NL;
  else global.NotebookLinks = NL;
})(typeof window !== 'undefined' ? window : globalThis);
