import m2py_translate as t

SCRIPT = ("create-dataset p\nimport INNTEKT/WLONN as lonn\n"
          "summarize lonn\nregress lonn alder")


def test_default_prints_results():
    code = t.translate(SCRIPT, backend="pandas", source_path=None)
    assert "print(result_1)" in code and "print(result_2)" in code


def test_print_results_false_suppresses_print_but_keeps_result_vars():
    code = t.translate(SCRIPT, backend="pandas", source_path=None,
                       print_results=False)
    assert "print(result_" not in code          # no prints
    assert "result_1 = ops.summarize(" in code  # result objects still created
    assert "result_2 = ops.regress(" in code
