"""Regression tests for m2py_translate.py silent-wrong-output bugs found in
the 2026-07-07 review (docs/REVIEW_2026-07-07.md, "Translators" section):

7. `_old_syntax_key` picked an arbitrary shared column as the merge key when
   more than one column overlapped, and flagged it "ok" (no TODO).
8. `_expand_loops.process` silently scrambled (or infinite-looped) unrolled
   code for a nested `for ... end` block instead of failing loudly.
"""
import pytest

import m2py_translate as t


# ---------------------------------------------------------------------------
# 7. old-syntax merge: ambiguous multi-column key
# ---------------------------------------------------------------------------

MULTI_SHARED = """create-dataset a
generate aar = 1
generate kommune = 1
drop PERSONID_1
create-dataset b
generate aar = 1
generate kommune = 1
drop PERSONID_1
use a
merge b"""


def test_old_syntax_merge_multiple_shared_columns_flags_todo():
    code = t.translate(MULTI_SHARED, backend="pandas", source_path=None)
    assert "# TODO" in code
    assert "aar" in code and "kommune" in code
    # picks the deterministic (sorted) first shared column, not whatever a
    # set happened to iterate first
    assert "on='aar'" in code


def test_old_syntax_merge_multiple_shared_columns_is_deterministic():
    codes = {t.translate(MULTI_SHARED, backend="pandas", source_path=None)
             for _ in range(5)}
    assert len(codes) == 1


def test_old_syntax_merge_single_shared_column_no_todo():
    script = """create-dataset a
generate kommune = 1
drop PERSONID_1
create-dataset b
generate kommune = 1
drop PERSONID_1
use a
merge b"""
    code = t.translate(script, backend="pandas", source_path=None)
    assert "# TODO" not in code
    assert "on='kommune'" in code


def test_old_syntax_merge_entity_key_still_resolves_cleanly():
    # both frames keep the default PERSONID_1 entity key -> unambiguous, no
    # TODO, unaffected by the multi-shared-column fix.
    script = "create-dataset a\ncreate-dataset b\nuse a\nmerge b"
    code = t.translate(script, backend="pandas", source_path=None)
    assert "# TODO" not in code
    assert "on='PERSONID_1'" in code


# ---------------------------------------------------------------------------
# 8. nested for...end loops
# ---------------------------------------------------------------------------

NESTED_FOR = """create-dataset a
for i in 1:2
  for j in 1:2
    generate x_${i}_${j} = ${i} + ${j}
  end
end
"""


def test_nested_for_loop_raises_clear_error():
    with pytest.raises(ValueError, match="nested"):
        t.translate(NESTED_FOR, backend="pandas", source_path=None)


def test_single_level_for_loop_still_unrolls():
    script = "create-dataset a\nfor i in 1:3\n  generate x_${i} = ${i}\nend\n"
    code = t.translate(script, backend="pandas", source_path=None)
    assert "target='x_1'" in code
    assert "target='x_2'" in code
    assert "target='x_3'" in code


def test_multi_level_for_loop_with_semicolon_still_zips():
    # microdata expresses multi-dimensional loops with `;` in a single `for`,
    # not with nested for-blocks -- must keep working.
    script = ("create-dataset a\nfor i in 1:2; j in 3:4\n"
              "  generate x_${i}_${j} = ${i} + ${j}\nend\n")
    code = t.translate(script, backend="pandas", source_path=None)
    for combo in ("x_1_3", "x_1_4", "x_2_3", "x_2_4"):
        assert f"target='{combo}'" in code
