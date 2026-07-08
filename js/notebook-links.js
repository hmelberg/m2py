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

  if (typeof module !== 'undefined' && module.exports) module.exports = NL;
  else global.NotebookLinks = NL;
})(typeof window !== 'undefined' ? window : globalThis);
