import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import brython_runner as br

ES = '__micro_transform_start_'
EE = '__micro_transform_end__'

def test_stdout_and_last_expression():
    out = br._execute_code('print("hei")\n1 + 1')
    assert 'hei' in out and '2' in out
    assert br._get_last_error() == ''

def test_state_persists_between_runs():
    br._execute_code('xx = 41')
    out = br._execute_code('xx + 1')
    assert '42' in out

def test_figure_embed_marker():
    br._execute_code('import pandas_brython as pd\nimport plotly_express_brython as pe\n'
                     'df = pd.DataFrame({"x":[1,2],"y":[3,4]})')
    out = br._execute_code('pe.scatter(df, x="x", y="y")')
    assert (ES + 'figure__') in out and EE in out
    payload = out.split(ES + 'figure__')[1].split(EE)[0].strip()
    assert 'data' in json.loads(payload)

def test_dataframe_tablehtml_marker():
    out = br._execute_code('df')
    assert (ES + 'tablehtml__') in out and '<table' in out

def test_show_multiple():
    out = br._execute_code('show(df, "tekst")')
    assert (ES + 'tablehtml__') in out and 'tekst' in out

def test_error_returns_traceback():
    out = br._execute_code('1/0')
    err = br._get_last_error()
    assert 'ZeroDivisionError' in err

def test_bind_datasets_csv_and_columns():
    spec = {'iris': {'kind': 'csv', 'payload': 'a,b\n1,x\n2,y\n'},
            'tall': {'kind': 'columns', 'payload': {'v': [1, 2, 3]}}}
    msg = br._bind_datasets(json.dumps(spec))
    assert msg == ''
    out = br._execute_code('str(len(iris)) + "," + str(len(tall))')
    assert '2,3' in out

def test_indented_last_line_not_evaled_out_of_context():
    # Last physical line is indented (inside the if-block) but is itself a
    # valid expression after .strip() ('y'). Must not be split into
    # exec(body) + eval(tail) — that execs the block without the last line
    # and then evals 'y' at top level, raising a spurious NameError.
    out = br._execute_code('if False:\n    y = 99\n    y')
    assert br._get_last_error() == ''
    assert out == ''

def test_indented_last_line_in_for_loop_not_displayed():
    br._execute_code('nums_rt = {"a": 10, "b": 30}')
    out = br._execute_code('for k_rt in nums_rt:\n    v_rt = nums_rt[k_rt]\n    v_rt')
    assert br._get_last_error() == ''
    assert '30' not in out

def test_multiline_trailing_call_displays_figure():
    # Reproduces the app's own starter example: a trailing call whose
    # arguments wrap across two physical lines, second line indented.
    # The last PHYSICAL line ('           title="t")') is indented, so a
    # purely line-based last-line check misses it entirely and the figure
    # is silently dropped. Statement-aware detection must find the call's
    # start (column 0) and eval the whole multi-line tail.
    br._execute_code('import pandas_brython as pd\nimport plotly_express_brython as pe\n'
                      'df_ml = pd.DataFrame({"x": [1, 2], "y": [3, 4]})')
    out = br._execute_code(
        'pe.scatter(df_ml, x="x", y="y",\n'
        '           title="t")'
    )
    assert (ES + 'figure__') in out and EE in out
    assert br._get_last_error() == ''

def test_multiline_trailing_expression_with_earlier_lines():
    # Earlier top-level statement, then a trailing multi-line parenthesized
    # arithmetic expression — must exec the earlier line and eval+display
    # the multi-line tail.
    out = br._execute_code(
        'a_ml = 3\n'
        '(a_ml +\n'
        ' 4)'
    )
    assert '7' in out
    assert br._get_last_error() == ''

def test_black_style_call_closing_paren_at_column_0():
    # Black-style formatting puts the lone closing ')' at column 0. The
    # naive "last column-0 line" is just ')' — compiling that alone as
    # 'eval' fails, so the scanner must walk further upward to the call's
    # true start ('pe_bs.scatter(') and succeed there instead of giving up.
    br._execute_code('import pandas_brython as pd\nimport plotly_express_brython as pe_bs\n'
                      'df_bs = pd.DataFrame({"x": [1, 2], "y": [3, 4]})')
    out = br._execute_code(
        'pe_bs.scatter(\n'
        '    df_bs, x="x", y="y"\n'
        ')'
    )
    assert (ES + 'figure__') in out and EE in out
    assert br._get_last_error() == ''

def test_unindented_continuation_line_displays_value():
    # `sum(nums,\n0)` — the second physical line ('0)') starts at column 0
    # but is NOT itself a new top-level statement; it's an unindented
    # continuation of the wrapped call on the previous line. The last
    # column-0 candidate's tail ('0)') fails to compile as 'eval', so the
    # scanner must walk upward to the real start ('sum(nums,') and succeed.
    br._execute_code('nums_uc = [1, 2, 3]')
    out = br._execute_code('sum(nums_uc,\n0)')
    assert '6' in out
    assert br._get_last_error() == ''

def test_bare_trailing_multiline_string_displays():
    # A bare multi-line triple-quoted string literal as the trailing
    # top-level statement. Its own last column-0 line ('b"""') is not
    # valid 'eval' source by itself; the scanner must walk up to the
    # opening '"""a' line and eval the whole string.
    out = br._execute_code('"""a\nb"""')
    assert 'a\nb' in out
    assert br._get_last_error() == ''

def test_trailing_multiline_string_assignment_not_misdisplayed():
    # A multi-line string literal used inside an assignment, followed by no
    # further top-level statement. Every column-0 candidate's tail is a
    # syntactically broken fragment (unterminated string literal, since the
    # string's closing quotes are followed by more source), so none compile
    # as 'eval' — must fall back to plain-exec with no display, and must
    # NOT mis-evaluate a fragment like '1 + 1' out of context.
    out = br._execute_code('s_ms = """hello\n1 + 1"""')
    assert out == ''
    assert br._get_last_error() == ''

def test_long_trailing_expression_beyond_scan_cap_displays():
    # A single trailing expression spanning many column-0 lines (one list
    # item per line, unindented) — more than the scan cap. The capped
    # upward scan alone would exhaust its candidates before reaching line 0
    # (the expression's true start), silently dropping the display. The
    # whole-code fallback candidate (index 0) must catch this.
    expr = 'sum([' + chr(10).join(str(i) + ',' for i in range(60)) + chr(10) + '])'
    out = br._execute_code(expr)
    assert str(sum(range(60))) in out
    assert br._get_last_error() == ''

# ── lazy library registration (_register_module / _alias_module) ──────────

def test_register_module_import_works():
    err = br._register_module('lazydemo_a', 'value = 41\ndef bump(x):\n    return x + 1\n')
    assert err == ''
    out = br._execute_code('import lazydemo_a\nlazydemo_a.bump(lazydemo_a.value)')
    assert br._get_last_error() == ''
    assert '42' in out

def test_register_module_is_idempotent():
    assert br._register_module('lazydemo_b', 'value = 1\n') == ''
    assert br._register_module('lazydemo_b', 'value = 2\n') == ''  # no-op, not re-exec
    out = br._execute_code('import lazydemo_b\nlazydemo_b.value')
    assert '1' in out

def test_register_module_syntax_error_reports_and_skips():
    err = br._register_module('lazydemo_bad', 'def broken(:\n')
    assert 'SyntaxError' in err
    assert 'lazydemo_bad' not in sys.modules

def test_register_module_runtime_error_reports_and_skips():
    err = br._register_module('lazydemo_boom', 'raise ValueError("boom")\n')
    assert 'ValueError' in err and 'boom' in err
    assert 'lazydemo_boom' not in sys.modules

def test_alias_module():
    br._register_module('lazydemo_c', 'value = 7\n')
    assert br._alias_module('lazydemo_c_alias', 'lazydemo_c') == ''
    out = br._execute_code('import lazydemo_c_alias\nlazydemo_c_alias.value')
    assert '7' in out

def test_alias_unknown_module_errors():
    assert br._alias_module('nope_alias', 'nope_canonical') != ''

if __name__ == '__main__':
    # NOTE: iterate in declaration order (not sorted alphabetically) — several
    # tests share state via module globals (e.g. test_figure_embed_marker
    # defines `df`, which test_dataframe_tablehtml_marker and test_show_multiple
    # consume). CPython 3.7+ guarantees globals() preserves definition order.
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn(); print('PASS', name)
