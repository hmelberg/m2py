// Plane B browser encryptor (safepy homomorphic-release design §3).
//
// Produces a "safepy-he-v1" artifact whose ciphertexts safepy/phe can decrypt
// and aggregate. The wire format is locked by tests/fixtures_he/ in the safepy
// repo (regenerated from THIS module) plus test_he.py's interop tests.
//
// Interop contract (must not drift without a coordinated format change):
//   - Paillier with g = n+1 (paillier-bigint defaults to a RANDOM g, which
//     phe cannot decrypt — we override it explicitly below).
//   - value = fixed-point int round(x * scale); the ciphertext is the RAW
//     Paillier integer c = (n+1)^m · r^n mod n², hex-encoded (no EncodedNumber
//     wrapper). Plaintext is reduced into [0, n); negatives wrap and safepy
//     maps the upper half of [0, n) back to negative on decrypt.
//   - per value column we ship: ct (Σx), ct_sq (Σx²), mask (0/1 validity, so
//     count = Σ mask handles NaN). Group columns stay plaintext.
//
// `paillier` is injected (the paillier-bigint module) so this file runs both in
// the browser (CDN import) and under Node (npm import) without a build step.

const FORMAT = "safepy-he-v1";
const DEFAULT_SCALE = 1_000_000;

function encode(x, scale) {
  return BigInt(Math.round(Number(x) * scale));
}

// pandas-style linear-interpolation quantile of a numeric array (NaNs dropped).
function quantile(values, q) {
  const v = values.filter((x) => Number.isFinite(x)).slice().sort((a, b) => a - b);
  if (v.length === 0) return NaN;
  const pos = (v.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return v[lo];
  return v[lo] + (v[hi] - v[lo]) * (pos - lo);
}

/**
 * Encrypt tabular data into a safepy-he-v1 artifact.
 *
 * @param {object} paillier  the paillier-bigint module (generateRandomKeys, PublicKey)
 * @param {Array<object>} rows  array of row objects (values already coarsened by the owner)
 * @param {object} opts
 * @param {string[]} opts.valueCols   encrypted numeric columns
 * @param {string[]} opts.groupCols   plaintext group/filter columns
 * @param {number}  [opts.scale]      fixed-point scale (default 1e6)
 * @param {number}  [opts.keyBits]    Paillier modulus bits (default 2048)
 * @param {[number,number]|null} [opts.winsorize]  (low, high) percentiles clipped before encryption
 * @param {function} [opts.onProgress]  called with (done, total) cell counts
 * @returns {Promise<{dataset: object, key: object, fingerprint: string}>}
 */
export async function encryptDataframe(paillier, rows, opts) {
  const {
    valueCols, groupCols,
    scale = DEFAULT_SCALE, keyBits = 2048,
    winsorize = null, onProgress = null,
  } = opts;

  for (const c of [...groupCols, ...valueCols]) {
    if (rows.length && !(c in rows[0])) throw new Error(`unknown column: ${c}`);
  }

  const { publicKey, privateKey } = await paillier.generateRandomKeys(keyBits);
  const n = publicKey.n;
  const pub = new paillier.PublicKey(n, n + 1n);        // force g = n+1
  const hex = (b) => b.toString(16);
  const enc = (m) => hex(pub.encrypt(((m % n) + n) % n));

  const total = valueCols.length * rows.length;
  let done = 0;

  const dataset = {
    format: FORMAT,
    n_rows: rows.length,
    public_key: { n: hex(n) },
    group_columns: {},
    value_columns: {},
  };
  for (const c of groupCols) {
    dataset.group_columns[c] = rows.map((r) => {
      const v = r[c];
      return v === null || v === undefined || v === "" ? null : String(v);
    });
  }

  for (const c of valueCols) {
    let vals = rows.map((r) => Number(r[c]));
    if (winsorize) {
      const lo = quantile(vals, winsorize[0]);
      const hi = quantile(vals, winsorize[1]);
      vals = vals.map((x) => (Number.isFinite(x) ? Math.min(Math.max(x, lo), hi) : x));
    }
    const ct = [], ct_sq = [], mask = [];
    for (const x of vals) {
      const valid = Number.isFinite(x);
      const m = valid ? encode(x, scale) : 0n;
      ct.push(enc(m));
      ct_sq.push(enc(m * m));
      mask.push(enc(valid ? 1n : 0n));
      done += 1;
      if (onProgress && (done % 200 === 0 || done === total)) onProgress(done, total);
    }
    dataset.value_columns[c] = {
      scale, ct, ct_sq, mask,
      winsorize: winsorize ? [Number(winsorize[0]), Number(winsorize[1])] : null,
    };
  }

  const key = { p: hex(privateKey._p), q: hex(privateKey._q), n: hex(n) };
  return { dataset, key, fingerprint: await datasetFingerprint(dataset) };
}

// sha256 of canonical JSON — matches safepy.he.dataset_fingerprint (json.dumps
// sort_keys=True, separators=(",",":")). Uses WebCrypto (browser) or node:crypto.
export async function datasetFingerprint(dataset) {
  const canon = canonicalJson(dataset);
  const bytes = new TextEncoder().encode(canon);
  if (typeof crypto !== "undefined" && crypto.subtle) {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  const { createHash } = await import("node:crypto");   // Node fallback
  return createHash("sha256").update(bytes).digest("hex");
}

// Deterministic JSON with sorted keys and no spaces — byte-identical to
// Python's json.dumps(sort_keys=True, separators=(",",":")).
function canonicalJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  const keys = Object.keys(value).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(value[k])).join(",") + "}";
}
