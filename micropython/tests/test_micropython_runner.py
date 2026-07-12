import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import micropython_runner as mr

ES = '__micro_transform_start_'
EE = '__micro_transform_end__'


def run(capsys, code):
    ret = mr._execute_code(code)
    assert ret == ''          # kontrakt: all output via print, motoren samler
    return capsys.readouterr().out


def test_stdout_and_last_expression(capsys):
    out = run(capsys, 'print("hei")\n1 + 1')
    assert 'hei' in out and '2' in out
    assert mr._get_last_error() == ''


def test_state_persists_between_runs(capsys):
    run(capsys, 'xx = 41')
    out = run(capsys, 'xx + 1')
    assert '42' in out


def test_error_returns_traceback(capsys):
    run(capsys, '1/0')
    assert 'ZeroDivisionError' in mr._get_last_error()


def test_show_string(capsys):
    out = run(capsys, 'show("tekst")')
    assert 'tekst' in out


def test_register_and_alias_module(capsys):
    err = mr._register_module('minmod', 'verdi = 7\ndef dobbel(x):\n    return 2 * x')
    assert err == ''
    err = mr._alias_module('mm', 'minmod')
    assert err == ''
    out = run(capsys, 'import mm\nmm.dobbel(mm.verdi)')
    assert '14' in out


def test_register_module_syntax_error_returns_traceback():
    err = mr._register_module('broken', 'def f(:')
    assert 'SyntaxError' in err
    assert 'broken' not in sys.modules


def test_snapshot_rollback(capsys):
    run(capsys, 'a = 1')
    mr._snapshot()
    run(capsys, 'a = 2\nb = 3')
    mr._rollback()
    out = run(capsys, 'print(a, "b" in dir())')
    assert '1' in out and 'False' in out


def test_bind_datasets_columns(capsys):
    # 'columns'-varianten trenger pandas_mpy, som først finnes i Task 4.
    # Registrer en mini-pandas som _bind_datasets importerer — testen låser
    # KONTRAKTEN (None -> nan, kolonnedict -> frame). VIKTIG: rydd
    # sys.modules før OG etter — pytest deler prosess på tvers av testfiler,
    # og en gjenglemt mini ville skygget den ekte pandas_mpy i senere filer.
    mini = (
        'nan = float("nan")\n'
        'class DataFrame:\n'
        '    def __init__(self, cols):\n'
        '        self.cols = cols\n'
        '    def __len__(self):\n'
        '        return len(next(iter(self.cols.values()), []))\n'
        'def read_csv(f):\n'
        '    rows = [l.split(",") for l in f.getvalue().strip().split(chr(10))]\n'
        '    return DataFrame({h: [r[i] for r in rows[1:]]'
        ' for i, h in enumerate(rows[0])})\n'
    )
    sys.modules.pop('pandas_mpy', None)
    try:
        assert mr._register_module('pandas_mpy', mini) == ''
        spec = {'iris': {'kind': 'csv', 'payload': 'a,b\n1,x\n2,y\n'},
                'tall': {'kind': 'columns', 'payload': {'v': [1, None, 3]}}}
        assert mr._bind_datasets(json.dumps(spec)) == ''
        out = run(capsys, 'print(len(iris), len(tall))')
        assert '2 3' in out
    finally:
        sys.modules.pop('pandas_mpy', None)


def test_pending_signal(capsys):
    run(capsys, 'class _P(BaseException):\n'
                '    __brython_pending__ = True\n'
                'def _kast():\n'
                '    raise _P()')
    run(capsys, '_kast()')
    assert mr._get_last_error() == '__BRYTHON_PENDING__'


def test_indented_last_line_not_evaled_out_of_context(capsys):
    out = run(capsys, 'if True:\n    y = 5\n    y')
    assert mr._get_last_error() == ''
