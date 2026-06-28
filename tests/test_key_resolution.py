"""Tests for the shared merge-key resolver (m2py_runtime/keys.py).

The resolver is the single source of truth for which column a `merge` joins on.
It is called by the emulator (m2py.MicroInterpreter merge handler) and, at
translation time, by the offline translator. Semantics mirror the emulator's
into-form merge: the LEFT side of the pandas merge is the *target* (the `into`
dataset), the RIGHT side is the *source* (active dataset). So `left_on` indexes
target columns and `right_on` indexes source columns.
"""

from m2py_runtime.keys import resolve_merge_key, key_col_from_cols


# --- key_col_from_cols: entity-key precedence -----------------------------

def test_key_col_prefers_personid():
    assert key_col_from_cols(["x", "PERSONID_1", "ARBEIDSFORHOLD_ID"]) == "PERSONID_1"


def test_key_col_falls_to_unit_id():
    assert key_col_from_cols(["a", "unit_id", "b"]) == "unit_id"


def test_key_col_none_when_absent():
    assert key_col_from_cols(["a", "b"]) is None


# --- resolve_merge_key: explicit on_var -----------------------------------

def test_on_var_in_both():
    r = resolve_merge_key(
        source_cols=["PERSONID_1", "kommune", "inntekt"],
        target_cols=["PERSONID_1", "kommune"],
        on_var="kommune",
    )
    assert (r.left_on, r.right_on, r.status) == ("kommune", "kommune", "ok")


def test_on_var_only_in_target_joins_source_key():
    # on_var present only in target -> join target.on_var to source's key
    r = resolve_merge_key(
        source_cols=["PERSONID_1", "inntekt"],
        target_cols=["PERSONID_1", "famid"],
        on_var="famid",
    )
    # target.famid == source.PERSONID_1 (source key)
    assert (r.left_on, r.right_on, r.status) == ("famid", "PERSONID_1", "ok")


def test_on_var_only_in_source_joins_target_key():
    r = resolve_merge_key(
        source_cols=["PERSONID_1", "famid", "inntekt"],
        target_cols=["PERSONID_1"],
        on_var="famid",
    )
    # target.tgt_key == source.on_var
    assert (r.left_on, r.right_on, r.status) == ("PERSONID_1", "famid", "ok")


def test_on_var_in_neither_is_error():
    r = resolve_merge_key(
        source_cols=["PERSONID_1"],
        target_cols=["PERSONID_1"],
        on_var="nope",
    )
    assert r.status == "error"


# --- resolve_merge_key: implicit (no on_var) ------------------------------

def test_implicit_src_key_in_target():
    r = resolve_merge_key(
        source_cols=["PERSONID_1", "inntekt"],
        target_cols=["PERSONID_1", "alder"],
    )
    assert (r.left_on, r.right_on, r.status) == ("PERSONID_1", "PERSONID_1", "ok")


def test_implicit_common_column_fallback():
    r = resolve_merge_key(
        source_cols=["aar", "inntekt"],
        target_cols=["aar", "alder"],
    )
    # no entity key on either side -> single common column
    assert (r.left_on, r.right_on, r.status) == ("aar", "aar", "ok")


def test_implicit_no_common_is_error():
    r = resolve_merge_key(
        source_cols=["a", "b"],
        target_cols=["c", "d"],
    )
    assert r.status == "error"


# --- person-ref FNR -> PERSONID_1 cross-entity linkage --------------------

def test_person_ref_source_collapse_key_matches_target_personid():
    # source was collapsed by a mother-FNR var; target keyed by PERSONID_1.
    def is_person_ref(alias):
        return alias == "mor_fnr"

    r = resolve_merge_key(
        source_cols=["mor_fnr", "barn_inntekt"],
        target_cols=["PERSONID_1", "alder"],
        src_collapse_key="mor_fnr",
        is_person_ref=is_person_ref,
    )
    # target.PERSONID_1 == source.mor_fnr
    assert (r.left_on, r.right_on, r.status) == ("PERSONID_1", "mor_fnr", "ok")


def test_person_ref_target_collapse_key_matches_source_personid():
    def is_person_ref(alias):
        return alias == "eier_fnr"

    r = resolve_merge_key(
        source_cols=["PERSONID_1", "alder"],
        target_cols=["eier_fnr", "bil_verdi"],
        tgt_collapse_key="eier_fnr",
        is_person_ref=is_person_ref,
    )
    # target.eier_fnr == source.PERSONID_1
    assert (r.left_on, r.right_on, r.status) == ("eier_fnr", "PERSONID_1", "ok")


def test_require_parses_url_source():
    import m2py
    out = m2py.MicroParser().parse_line("require https://h/x.csv as d")
    assert out["args"] == {"source": "https://h/x.csv", "alias": "d"}
