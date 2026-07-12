// js/examples-menu.js — ren, testbar grupperingslogikk for eksempel-menyen.
// DOM-render bor i index.html; denne modulen kjenner ingen DOM.
(function (global) {
  'use strict';

  function groupForMode(manifest, mode) {
    var list = (manifest && manifest[mode]) || [];
    var groups = [];
    var byKey = {};
    for (var i = 0; i < list.length; i++) {
      var e = list[i];
      var g = (e.group === undefined) ? null : e.group;
      var key = (g === null) ? '__null__' : g;
      if (!byKey[key]) {
        byKey[key] = { group: g, examples: [] };
        groups.push(byKey[key]);
      }
      byKey[key].examples.push({ file: e.file, label: e.label });
    }
    return groups;
  }

  global.ExamplesMenu = { groupForMode: groupForMode };
})(typeof globalThis !== 'undefined' ? globalThis : this);
