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

  if (typeof module !== 'undefined' && module.exports) module.exports = NL;
  else global.NotebookLinks = NL;
})(typeof window !== 'undefined' ? window : globalThis);
