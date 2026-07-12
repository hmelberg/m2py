# Fase 0-notat: MicroPython-spike

Dato: 2026-07-12. Tre separate kjøre-kontekster ble brukt, og de holdes fra
hverandre gjennom hele notatet fordi de IKKE er samme binær/VM-build:

1. **unix-micropython** — `brew install micropython` ga v1.28.0 (unix-porten).
   Kjørt direkte: `micropython micropython/tests/spike_primitives.py`.
2. **wasm via Node** — samme wasm/js-artefakter som nettleseren skal bruke
   (`@micropython/micropython-webassembly-pyscript@1.27.0`, lastet ned lokalt
   til `/tmp/mpyspike/`), kjørt headless med et Node-ESM-script i stedet for
   nettleser (avvik godkjent av oppdragsgiver). Node har verken `window` eller
   DOM, så `js`-brobygningen ble testet mot `globalThis` i stedet for
   `window` — samme underliggende mekanisme (i nettleseren er `window` en
   `globalThis`-egenskap), men ekte DOM-objekter (`document` osv.) er **ikke**
   testet.
3. **wasm i nettleser** — kjørt 2026-07-12 (Task 7, browser-røyk via
   Playwright MCP mot `python3 -m http.server 8901`, Chromium):
   `http://localhost:8901/web_examples/mpy_spike.html`. BOOT: **18 ms** —
   godt under briefens forventning (500 ms) og faktisk i samme størrelsesorden
   som Node-tallet under (9–14 ms), altså ikke det kunstig lave Node-tallet
   man kunne fryktet. js-interop (`js.Math.floor` og `window.__spikeCb`-
   callback via ekte `window`, ikke `globalThis`-proxy) ga samme OK-resultat
   som Node-kjøringen. Primitiv-sjekkene ga identisk OK/FEIL-mønster som
   wasm-via-Node (se lista under) — ingen nye avvik oppdaget i ekte
   nettleser-VM. Forbehold 1 under er dermed lukket.

GATE-vurderingen i dette notatet er basert på **wasm-via-Node**-resultatene
(punkt 2), fordi det er samme VM/dialekt som nettleseren kjører — ikke på
unix-micropython, som har et litt annet stdlib-utvalg og en annen
versjon (v1.28.0 vs v1.27.0).

## Boot-tid

- **wasm via Node**: 9–14 ms over 4 målinger (`loadMicroPython` til ferdig
  instansiert VM, lokale filer, `stdout` no-op). **Indikativ, ikke nettleser-tall.**
- **wasm i nettleser**: **18 ms** (Chromium, Playwright MCP, 2026-07-12,
  `python3 -m http.server 8901` + `web_examples/mpy_spike.html`,
  `loadMicroPython` til ferdig instansiert VM). Godt under briefens mål
  (500 ms) og under Brython-boot-sammenligningen (~1500–3000 ms).

## Primitiv-sjekker: full OK/FEIL-liste

### unix-micropython (v1.28.0, `micropython micropython/tests/spike_primitives.py`)

```
OK   c_binascii_base64
OK   c_class_features
OK   c_compile_eval
OK   c_compile_exec
FEIL c_csv_missing: ImportError("no module named 'csv'",)
FEIL c_datetime_missing: ImportError("no module named 'datetime'",)
OK   c_format_thousands
OK   c_json_floats
OK   c_module_trick
OK   c_print_exception
FEIL c_re_split_class: AttributeError("module 're' has no attribute 'split'",)
OK   c_stringio
FEIL c_sys_stdout_assign: AttributeError("'module' object has no attribute 'stdout'",)
SPIKE FERDIG
```

### wasm via Node (v1.27.0, samme `spike_primitives.py`, samme kode som `mpy_spike.html` kjører)

```
js.Math.floor: 1
callback: 42                    (js-interop, via globalThis.__spikeCb i stedet for window.__spikeCb)
FEIL c_binascii_base64: TypeError("can't convert str to int",)
OK   c_class_features
OK   c_compile_eval
OK   c_compile_exec
FEIL c_csv_missing: ImportError("no module named 'csv'",)
OK   c_datetime_missing        (import lykkes — se avvik under)
OK   c_format_thousands
OK   c_json_floats
OK   c_module_trick
OK   c_print_exception
FEIL c_re_split_class: AttributeError("module 're' has no attribute 'split'",)
OK   c_stringio
FEIL c_sys_stdout_assign: AttributeError("'module' object has no attribute 'stdout'",)
SPIKE FERDIG
```

### Avvik mellom unix- og wasm-kjøring (verdt å merke seg for senere tasks)

- **`c_binascii_base64`**: OK i unix (v1.28.0, godtar `str`-input til
  `a2b_base64`), **FEIL** i wasm (v1.27.0, krever `bytes`-input —
  `binascii.a2b_base64(b'aGVp')` fungerer fint, `binascii.a2b_base64('aGVp')`
  gir `TypeError`). Trolig en byggkonfig-/versjonsforskjell mellom portene.
  Dokumentasjonspunkt for senere kode som bruker `binascii` — bruk alltid
  `bytes`-input.
- **`c_datetime_missing`**: FEIL (mangler) i unix, men **OK** (finnes!) i
  wasm — motsatt av det briefen antok («Forventet FEIL i wasm-porten»). Bra
  nyhet for `plotly_express`-porten i Task 5: try/except rundt `datetime`
  kan trolig droppes, men behold defensivt siden dette ikke er verifisert i
  ekte nettleser ennå.
- `c_re_split_class`, `c_sys_stdout_assign`, `c_csv_missing`: FEIL i begge —
  konsistent, som forventet i briefen (`re.split` mangler i denne
  MicroPython-bygningen, `sys.stdout` er read-only, `csv`-modul finnes ikke).
- `c_format_thousands` (`'{:,}'.format(...)`): **OK** i begge kjøringer —
  briefen antok FEIL, men begge builds støtter faktisk `{:,}`. Positivt avvik,
  ingen handling nødvendig.

## js-interop (kun testet i wasm, unix-micropython har ingen `js`-modul)

- `import js` + attributtlesing + funksjonskall (`js.Math.floor(1.5)` → `1`):
  **OK**.
- Python-callback til JS (`js.__spikeCb(lambda x: x * 2)` → kaller callback
  med `21`, returnerer `42`): **OK**, testet via `globalThis.__spikeCb` siden
  Node mangler `window`. Samme brometode brukes for `window` i nettleseren
  (`window` er en egenskap på `globalThis` der), så dette regnes som
  representativt for js-broen — men ekte DOM-API (`document`, event-lytting
  osv.) er ikke øvd på og bør sjekkes manuelt ved nettleser-verifisering.

## Rå (uportert) pandas_brython.py under MicroPython-wasm

**FEILET** — `SyntaxError: invalid syntax` ved kompilering, `pandas_brython.py`
linje 1028:

```
title = f"<caption>Series{name if (name:=('' if self.name is None else ' ' + html.escape(str(self.name)))) is not None else ''}</caption>"
```

Årsak: MicroPython-parseren (både 1.27.0-wasm, sannsynligvis også
unix-varianten) takler ikke en `:=`-walrus-tilordning nestet inne i et
f-string-uttrykk på denne formen. Dette er et konkret, isolert fase 0-funn
som går rett inn i porte-jobben i **Task 4**: minst dette ene stedet i
`pandas_brython.py` må skrives om til vanlig tilordning før `Series._repr_html_`
kan kjøre under MicroPython. (Kompileringen feiler før noe kjører, så det er
ukjent om det finnes flere slike steder — full skanning hører til Task 4.)

## GATE-vurdering

Gate-kriteriet fra briefen: `c_module_trick`, js-interop (inkl. callback),
`c_compile_*`, `c_stringio` og `c_print_exception` skal alle være OK i wasm.

Alle fem er **OK** i wasm-via-Node-kjøringen:

- `c_module_trick`: OK
- js-interop (attributt + kall + callback): OK
- `c_compile_eval`: OK
- `c_compile_exec`: OK
- `c_stringio`: OK
- `c_print_exception`: OK

## **GATE BESTÅTT**

Forbehold (ikke gate-blokkerende, men bør lukkes før Task 2 begynner i
praksis):

1. ~~Faktisk nettleser-kjøring av `web_examples/mpy_spike.html` er ikke
   gjort~~ — **LUKKET 2026-07-12 (Task 7)**: kjørt i ekte Chromium via
   Playwright MCP, BOOT 18 ms, samme OK/FEIL-mønster og js-interop (ekte
   `window`) som Node-proxyen. Se punkt 3 og boot-tid-seksjonen over.
2. `c_binascii_base64`-avviket (str vs. bytes) og `c_re_split_class`-feilen
   er informasjonspunkter med kjente fallbacks i senere tasks, ikke
   gate-blokkerende (per briefens instruks om at enkeltsjekker som feiler er
   informasjon).
3. Rå `pandas_brython.py` feiler på kompilering (walrus-i-f-string ved linje
   1028) — forventet og dokumentert som input til Task 4, ikke en overraskelse
   som endrer gate-utfallet.
