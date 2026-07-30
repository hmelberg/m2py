#!/usr/bin/env node
// Genererer resultatblokkene for de tre delte seksjonene (felles-lagre,
// felles-forklar, felles-widgets) som ikke kan kjøres gjennom safepy eller
// m2py, fordi de er ren klientlogikk (delelenke-komprimering, steg-for-steg-
// blokksplitting, widget-parsing) uten et Python-motstykke.
//
// Kalles fra run_examples.py sin main() slik at
// `.venv/bin/python docs/hjelp_examples/run_examples.py` fortsatt er det
// ene stedet som regenererer ALLE resultatblokkene på hjelpesidene.
//
// Funksjonene kjøres IKKE ved å lime dem inn her — de trekkes ut ordrett fra
// kildefilene (js/github-storage.js, index.html, widgets/forklar-widgets.js)
// mellom to bokstavelige start/slutt-markører, og kjøres i en vm-sandkasse
// med et minimalt DOM-stubbet miljø. Endrer noen funksjonsnavnene eller
// rekkefølgen i kildefilene, feiler dette skriptet høyt (kan ikke finne
// markøren) i stedet for å stille fryse en utdatert kopi.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const REPO = process.cwd();
const OUTDIR = path.join(REPO, 'docs', 'hjelp_examples', 'output');
fs.mkdirSync(OUTDIR, { recursive: true });

function extract(filePath, startMarker, endMarker) {
  const src = fs.readFileSync(filePath, 'utf8');
  const s = src.indexOf(startMarker);
  const e = endMarker ? src.indexOf(endMarker) : src.length;
  if (s < 0 || (endMarker && e < 0)) {
    throw new Error(
      `fant ikke uttrekksmarkør i ${filePath}\n` +
      `  start: ${JSON.stringify(startMarker)}\n` +
      `  slutt: ${JSON.stringify(endMarker)}\n` +
      'Kildefunksjonen er trolig omdøpt eller flyttet — oppdater markørene i ' +
      'run_examples_js.mjs.'
    );
  }
  return src.slice(s, endMarker ? e : undefined);
}

function write(id, text) {
  fs.writeFileSync(path.join(OUTDIR, `${id}.txt`), text.trim() + '\n', 'utf8');
  console.log(`  ${id}: ${text.trim().length} tegn`);
}

// ── felles-widgets: ekte //widget-parsing fra widgets/forklar-widgets.js ──
function loadForklarWidgets() {
  const src = fs.readFileSync(path.join(REPO, 'widgets', 'forklar-widgets.js'), 'utf8');
  const sandbox = {
    window: {},
    document: { createElement: () => ({}) },
    customElements: { get: () => undefined, define: () => {} },
    HTMLElement: class {},
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: 'widgets/forklar-widgets.js' });
  const fw = sandbox.window.ForklarWidgets;
  if (!fw || typeof fw.parseWidgetLine !== 'function') {
    throw new Error('widgets/forklar-widgets.js eksporterte ikke ForklarWidgets.parseWidgetLine');
  }
  return fw;
}

function run_felles_widgets() {
  const fw = loadForklarWidgets();

  const title = fw.parseWidgetLine('//widget title {"text":"Kapittel 1","size":"full"}');
  write('felles-widgets-title', JSON.stringify(title, null, 2));

  const question = fw.parseWidgetLine(
    '//widget question {"q":"Hva er p-verdien?","options":["<0.05",">0.05"],"answer":0}'
  );
  write('felles-widgets-question', JSON.stringify(question, null, 2));

  return fw;
}

// ── felles-forklar: ekte blokksplitting fra index.html ──────────────────
function run_felles_forklar(ForklarWidgets) {
  const forklarSrc = extract(
    path.join(REPO, 'index.html'),
    '    function parseSpeechKwargs(inner) {',
    '    function buildForklarFlatWork(segments) {'
  );
  const sandbox = { ForklarWidgets };
  vm.createContext(sandbox);
  vm.runInContext(forklarSrc, sandbox, { filename: 'index.html (parseExplainBlocks-uttrekk)' });
  const parseExplainBlocks = vm.runInContext('parseExplainBlocks', sandbox);

  // Samme eksempelscript som vises i #forklar sin "Blokker"-kodeboks.
  const script = [
    '# Denne kommentaren leses OPP før koden kjøres',
    'df["alder"] = 2024 - df["fodselsar"]',
    '',
    '# Dette er neste blokk',
    'df.groupby("kjonn")["lonn"].mean()',
    '# Denne kommentaren leses etter at resultatet vises',
  ].join('\n');

  const blocks = parseExplainBlocks(script, 'python');
  write('felles-forklar-blokker', JSON.stringify(blocks, null, 2));
}

// ── felles-lagre: ekte delelenke-komprimering fra js/github-storage.js ──
async function run_felles_lagre() {
  const chunk = extract(
    path.join(REPO, 'js', 'github-storage.js'),
    '      function b64urlEncode(bytes) {',
    '      async function shareLink() {'
  );
  const sandbox = { CompressionStream, TextEncoder, Response, btoa, atob };
  vm.createContext(sandbox);
  vm.runInContext(chunk, sandbox, { filename: 'js/github-storage.js (gzip-uttrekk)' });
  const gzip = vm.runInContext('gzip', sandbox);

  const payload = JSON.stringify({
    v: 1,
    name: '',
    lang: 'python',
    script: 'print(sum(range(1, 101)))',
  });
  const packed = await gzip(payload);
  const link = 'https://din-adresse.example/app/#s=' + packed;
  write('felles-lagre-delelenke', `${payload}\n\n${link}`);
}

async function main() {
  const fw = run_felles_widgets();
  run_felles_forklar(fw);
  await run_felles_lagre();
}

main().catch((e) => {
  console.error(String(e && e.stack || e));
  process.exit(1);
});
