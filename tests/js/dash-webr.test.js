const test = require('node:test');
const assert = require('node:assert');
const G = require('../../js/dash-webr.js');

test('makeQueue: sekvensiell, per-nøkkel siste-vinner-koalescing', async () => {
  const q = G.makeQueue();
  const ran = [];
  const run = (tag) => (args) => new Promise((res) =>
    setTimeout(() => { ran.push([tag, args]); res(); }, 5));
  q.schedule('a', 1, run('a'));
  q.schedule('a', 2, run('a'));   // koalesceres: kun nyeste args kjøres
  q.schedule('b', 9, run('b'));
  await q.idle();
  assert.deepStrictEqual(ran, [['a', 2], ['b', 9]]);
});

test('makeQueue: feil i én jobb stopper ikke kjeden', async () => {
  const q = G.makeQueue();
  const ran = [];
  q.schedule('x', 1, () => Promise.reject(new Error('boom')));
  q.schedule('y', 2, (args) => { ran.push(args); return Promise.resolve(); });
  await q.idle();
  assert.deepStrictEqual(ran, [2]);
});

test('makeQueue: ny endring under kjøring gir ny kjøring etterpå', async () => {
  const q = G.makeQueue();
  const ran = [];
  let firstStarted;
  const gate = new Promise((r) => { firstStarted = r; });
  q.schedule('a', 1, async (args) => { firstStarted(); ran.push(args); });
  await gate;
  q.schedule('a', 2, async (args) => { ran.push(args); });
  await q.idle();
  assert.deepStrictEqual(ran, [1, 2]);
});
