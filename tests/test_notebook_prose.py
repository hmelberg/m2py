import notebook_prose as NP

START = "__micro_transform_start_markdown__"
END = "__micro_transform_end__"

def _run(src):
    """Exec the transformed source, capturing stdout."""
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(NP.prep_python_prose(src), "<t>", "exec"), {})
    return out.getvalue()

def test_toplevel_triple_quoted_becomes_markdown():
    src = '"""# Heading\n\nsome text"""\nprint("code ran")'
    out = _run(src)
    assert START in out and END in out
    assert "# Heading" in out
    assert "code ran" in out
    # markdown appears before the code output (source order preserved)
    assert out.index(START) < out.index("code ran")

def test_single_quoted_bare_string_also_renders():
    src = "'just a note'\nx = 1"
    assert START in NP.prep_python_prose(src)

def test_assigned_string_not_rendered():
    src = 'note = "not prose"\nprint(note)'
    assert START not in NP.prep_python_prose(src)

def test_function_docstring_not_rendered():
    src = 'def f():\n    """docstring"""\n    return 1\nprint(f())'
    assert START not in NP.prep_python_prose(src)

def test_variables_persist_and_order_kept():
    src = 'a = 2\n"""middle"""\nprint(a * 3)'
    out = _run(src)
    assert out.index("middle") < out.index("6")
    assert "6" in out

def test_end_marker_in_text_is_neutralized():
    src = '"""danger __micro_transform_end__ zone"""'
    prepped = NP.prep_python_prose(src)
    # the raw literal END must not survive verbatim inside the payload text
    assert "danger __micro_transform_end__ zone" not in prepped

def test_syntax_error_returns_source_unchanged():
    src = "def broken(:\n"
    assert NP.prep_python_prose(src) == src

def test_no_bare_strings_is_noop():
    src = "x = 1\nprint(x)"
    assert NP.prep_python_prose(src) == src

def test_trailing_sibling_after_prose_survives():
    src = '"""foo"""; print(1)'
    out = _run(src)
    assert START in out and END in out
    assert "foo" in out
    assert "1" in out
    assert out.index(START) < out.index("1")

def test_leading_sibling_before_prose_survives():
    src = 'x = 1; """note"""\nprint(x)'
    out = _run(src)
    assert START in out
    assert "note" in out
    assert "1" in out

def test_multiline_prose_with_trailing_sibling():
    src = 'a = 5\n"""p1\np2"""; print(a*2)\n'
    out = _run(src)
    assert START in out and END in out
    assert "p1" in out and "p2" in out
    assert "10" in out
    assert out.index(START) < out.index("10")

def test_non_ascii_prose_roundtrips():
    src = '"""# Rapport Æ Ø Å"""\nprint("etter")'
    out = _run(src)
    assert "Rapport Æ Ø Å" in out
    assert "etter" in out
    assert out.index("Rapport Æ Ø Å") < out.index("etter")

def test_non_ascii_prose_with_trailing_sibling():
    src = '"""Ærlig talt Ø"""; print(42)'
    out = _run(src)
    assert "Ærlig talt Ø" in out
    assert "42" in out

def test_non_ascii_before_prose_same_line():
    src = 'x = "Ø"; """note"""\nprint(len(x))'
    out = _run(src)
    assert "note" in out
    assert "1" in out
