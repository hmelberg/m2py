# Plan: Remove `fd/` prefix from variable metadata

## Goal

- **Metadata**: Variable keys in `variable_metadata.json` become **NAME only** (e.g. `BEFOLKNING_KOMMNR_FAKTISK`) instead of `fd/NAME`. No `fd/` (or any prefix) in the file.
- **Scripts**: Import syntax **unchanged**: user still writes `require no.ssb.fdb:51 as db` and `import db/BEFOLKNING_KOMMNR_FAKTISK ... as bosted`. The **PREFIX** (e.g. `db`) is required for realism but is not part of the variable identity; we only use **NAME** for lookup.
- **UI**: Tab/autocomplete and suggestions use and show **variable name only** (NAME). Optional: after `require `, Tab could suggest e.g. `no.ssb.fdb:51`.

---

## 1. Current use of `fd/` and prefix

### 1.1 `variable_metadata.json`

- **Structure**: `{ "variables": { "fd/BEFOLKNING_KJOENN": { ... }, ... } }`.
- **Keys**: Always `fd/` + variable name. Used as the single source of truth for catalog in both frontend and backend.

### 1.2 Frontend (`microdata_runner.html`)

| Location | Current behavior | After change |
|----------|------------------|--------------|
| **Catalog load** | `microdataVariableNames = Object.keys(microdataCatalog.variables)` → list of `"fd/NAME"`. | Same line → list of `"NAME"`. |
| **getVariableShortDescription(varLabel)** | Looks up `microdataCatalog.variables[varLabel]`; if miss and no `/`, finds key where `k.split('/').pop() === varLabel`. | Look up `variables[varLabel]` only (varLabel is already NAME). Remove the `.find(k => k.split('/').pop() === varLabel)` fallback. |
| **getVariableDescription(varId)** | Uses `varId` as key; URL = base + `varId.split('/').pop()`. | Key is already NAME; URL = base + varId. |
| **Autocomplete – variable list** | `microdataVariableNames`; filter by `short = full.split('/').pop()` when `importLike`; suggest `label: shortName`, `insertText: shortName`. | Names are already short; no split. `label` and `insertText` stay as name. For **import** context, script still needs PREFIX/NAME: either keep `insertText: shortName` (user types `db/` manually) or set `insertText` to `connectionAlias + '/' + shortName` if we infer alias from script (see 2.4). |
| **Help / variable match** | `microdataVariableNames.some(v => v.toLowerCase() === lower)` – full key. | Same with NAME. |

### 1.3 Backend (`m2py.py`)

| Component | Current behavior | After change |
|-----------|------------------|--------------|
| **Catalog source** | `data.get('variables', data)` → keys `fd/NAME`. Passed from HTML as `microdataCatalog.variables`. | JSON keys are NAME. Catalog = `{ "NAME": meta, ... }`. |
| **MockDataEngine._catalog_by_short** | `{ k.split('/')[-1]: v for k, v in self.catalog.items() if '/' in k }` → short name → meta. | **Remove** or **redefine**: if catalog keys are NAME, either drop `_catalog_by_short` and use `catalog` only, or set `_catalog_by_short = self.catalog` (identity). All lookups that use `short_name = var_path.split('/')[-1]` then use `catalog.get(short_name)` or `catalog.get(var_name)` directly. |
| **MockDataEngine.generate()** | `meta = self.catalog.get(var_path) or self.catalog.get(var_name) or _catalog_by_short.get(short_name)`. `var_path` from import is e.g. `db/BEFOLKNING_KOMMNR_FAKTISK`. | Use `short_name = var_path.split('/')[-1] if var_path else ''`; then `meta = self.catalog.get(short_name) or self.catalog.get(var_name)`. No `fd/` normalization. |
| **MockDataEngine.rule_based** | Loaded from JSON `rule_based[].variable`; stored under both full key and short. Lookup: `rule_based.get(var_name) or rule_based.get(var_path)`. | In JSON, `variable` should be NAME. Lookup: `rule_based.get(var_name) or rule_based.get(short_name)`. |
| **LabelManager** | `var_alias_to_path`: alias → normalized path (`fd/SHORT`). `get_codelist_for_var`: `catalog.get(path)`, `catalog.get(var_name)`, `_catalog_by_short.get(var_name.split('/')[-1])`. | `register_var_alias(alias, var_path)`: store `alias → short_name` (i.e. `var_path.split('/')[-1]`). No `fd/` in path. `get_codelist_for_var`: `path = var_alias_to_path.get(var_name)` then `catalog.get(path)`; and/or `catalog.get(var_name)`. Catalog keys are NAME. |
| **LabelManager._load_from_catalog** | Iterates `for var_path, meta in self.catalog.items()`; `short = var_path.split('/')[-1]`. | Keys are NAME; use key as-is for codelist name (e.g. `f"{key}_labels"` or meta’s `codelist`). |
| **StatsEngine / others** | Any `catalog.get(var_path)` or `_catalog_by_short.get(...)` | Use NAME only (from `var_path.split('/')[-1]` where var_path comes from parser). |
| **translate_script_to_python** | Comment line can show `fd/var`; no functional use of prefix. | Can show `var` only or keep `prefix/var` in comment for readability; no catalog dependency. |

### 1.4 Parser / import

- **Import pattern**: Already accepts any `PREFIX/NAME` (e.g. `db/BEFOLKNING_KOMMNR_FAKTISK`). `var_path` is the full string. No change to parsing.
- **Require**: `require no.ssb.fdb:51 as db` → args `{"source": "no.ssb.fdb:51", "alias": "db"}`. Backend does not use this for catalog; it’s for user discipline. Optional: frontend can use the last `require ... as <alias>` to offer `insertText = alias + '/' + shortName` in import context.

### 1.5 Other files

- **build_variable_metadata.py**: `key = f"fd/{variabel}"` → `key = variabel` (or keep a prefix only if adding new vars from CSV and you want a temporary convention; for this plan we assume no prefix).
- **Tests** (run_test.py, test_*.py): Use `fd/BEFOLKNING_*` in import lines. After change, scripts still use **PREFIX/NAME** (e.g. `fd/` or `db/`); only metadata keys change. So test scripts can keep `import fd/...` or switch to `import db/...`; backend will resolve by NAME.

---

## 2. Safe migration plan (no code changes yet)

### 2.1 Metadata

1. **Rename all keys** in `variable_metadata.json` from `fd/NAME` to `NAME` (one-time script or manual).
2. **rule_based**: Ensure each `variable` field is NAME (or update backend to accept both and normalize to NAME).
3. **References**: No other file references `fd/` in JSON keys except the catalog consumer code.

### 2.2 Backend (m2py.py)

1. **MockDataEngine**  
   - Stop building `_catalog_by_short` from splitting on `/`, or set `_catalog_by_short = dict(self.catalog)`.  
   - Everywhere: obtain `short_name = (var_path or '').split('/')[-1]` when you have a full import path; then `meta = self.catalog.get(short_name) or self.catalog.get(var_name)`.  
   - Remove any `catalog.get(var_path)` when `var_path` can be `db/NAME`; use `short_name` for lookup.

2. **LabelManager**  
   - `register_var_alias(alias, var_path)`: set `self.var_alias_to_path[alias] = var_path.split('/')[-1]` (store NAME only).  
   - `get_codelist_for_var`: use stored value (NAME) and `catalog.get(...)`; remove dependency on `fd/`.  
   - `_load_from_catalog`: iterate `for var_name, meta in self.catalog.items()` (key is already NAME).

3. **First (old) LabelManager class** (around line 432): If still referenced anywhere, apply same idea or remove if dead code.

4. **StatsEngine / PlotHandler / Regression / etc.**: Any `catalog.get(var_path)` or `_catalog_by_short` → use NAME (from `var_path.split('/')[-1]` or `var_name`).

5. **Tests**: Ensure they run with `import fd/NAME` or `import db/NAME`; backend should resolve by NAME.

### 2.3 Frontend (microdata_runner.html)

1. **microdataVariableNames**: Already `Object.keys(microdataCatalog.variables)`; after key rename this is just list of NAME. No code change except no longer needing to strip prefix for display.
2. **getVariableShortDescription**: Take parameter as NAME; lookup `microdataCatalog.variables[varLabel]`. Remove the fallback that finds key by `k.split('/').pop() === varLabel`.
3. **getVariableDescription**: Same; key is NAME; URL = base + varId.
4. **Autocomplete**: For variables, list and filter by NAME; `label` and (for non-import) `insertText` = NAME. For **import** context, either keep `insertText: shortName` (user types prefix manually) or implement “last require alias” and use `insertText: inferredAlias + '/' + shortName`.
5. **Variable help match**: Compare with NAME only.

### 2.4 Optional: require + Tab and import insertText

- **After `require `**: On Tab, suggest e.g. `no.ssb.fdb:51` (and optionally other sources) so the user can complete the connection string.
- **After `import <alias>/` or `import ` (with alias known)**: Infer alias from the last line matching `require\s+.+?\s+as\s+(\w+)` in the script; then for variable suggestions in import context set `insertText: alias + '/' + name` so that choosing a variable inserts `db/BEFOLKNING_KOMMNR_FAKTISK` (correct syntax) while metadata and lookup remain NAME-only.

### 2.5 Build script

- **build_variable_metadata.py**: When creating or updating keys, use `variabel` (NAME) as key, not `f"fd/{variabel}"`.

### 2.6 Order of operations

1. **Backend**: Change catalog usage to “NAME only” (treat incoming catalog as NAME keys; normalize all var_path to NAME for lookup). This works even if JSON still has `fd/` keys (we’d use `split('/')[-1]` for lookup), but then we’d have two ways to look up. Cleaner: rename JSON keys first, then backend assumes NAME.
2. **Rename JSON keys**: `fd/NAME` → `NAME` in `variable_metadata.json` (and in `rule_based[].variable` if needed).
3. **Frontend**: Assume keys are NAME; simplify getVariableShortDescription and getVariableDescription; adjust autocomplete if desired.
4. **Optional**: Add require-Tab suggestion and import insertText with inferred alias.
5. **Tests**: Run all tests; fix any that assert on `fd/` in catalog or output.

---

## 3. Risk summary

| Risk | Mitigation |
|------|------------|
| Forgotten `catalog.get(var_path)` with `var_path = db/NAME` | Grep for `catalog.get` and `var_path`; ensure we use `short_name` for lookup. |
| LabelManager alias → path | Store NAME only; tabulate/labels will still resolve by NAME. |
| Frontend still sending old keys | Catalog is built from same JSON; after key rename, frontend sends NAME keys. |
| rule_based variables | Use NAME in JSON; backend lookup by NAME/short only. |
| External tools or docs that assume `fd/` | Document that metadata uses NAME only; scripts still use PREFIX/NAME in syntax. |

---

## 4. Summary

- **Eliminate `fd/` from metadata**: Keys in `variable_metadata.json` become **NAME** only.
- **Import syntax unchanged**: User still writes `require ... as db` and `import db/NAME ...`; we only use **NAME** for catalog/labels/autocomplete.
- **Tab/autocomplete**: Search and display by **variable name** only; optional: Tab after `require ` suggests `no.ssb.fdb:51`, and in import context we can suggest `alias/NAME` by inferring alias from the last `require ... as alias`.
- **Safe approach**: Rename JSON keys; update backend to use NAME for all catalog and label lookups (normalize `var_path` to NAME with `split('/')[-1]`); update frontend to treat keys as NAME and simplify lookups; then add optional require/import UX improvements.

No codebase changes have been made yet; this document is analysis and plan only.
