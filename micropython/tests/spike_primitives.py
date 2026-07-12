# spike_primitives.py — fase 0-sjekker for MicroPython-modusen. Kjøres BÅDE
# under unix-micropython (micropython spike_primitives.py) og i wasm-spiken
# (web_examples/mpy_spike.html). Ingen pytest — bare OK/FEIL-linjer.
import sys

def check(name, fn):
    try:
        fn()
        print('OK   ' + name)
    except BaseException as e:
        print('FEIL ' + name + ': ' + repr(e))

def c_compile_eval():
    assert eval(compile('1+1', '<t>', 'eval'), {}) == 2

def c_compile_exec():
    g = {}
    exec(compile('x = 41\nx += 1', '<t>', 'exec'), g)
    assert g['x'] == 42

def c_module_trick():
    # Bærebjelken i _register_module (Task 2): et vanlig objekt i sys.modules
    # må fungere for både `import m` og `from m import navn`.
    class _Mod:
        def __init__(self, name, g):
            self.__name__ = name
            self._g = g
        def __getattr__(self, k):
            try:
                return self._g[k]
            except KeyError:
                raise AttributeError(k)
    g = {'__name__': 'spikemod'}
    exec(compile('x = 42\ndef f():\n    return x', 'spikemod.py', 'exec'), g)
    sys.modules['spikemod'] = _Mod('spikemod', g)
    import spikemod
    assert spikemod.f() == 42
    from spikemod import x
    assert x == 42

def c_stringio():
    import io
    b = io.StringIO()
    b.write('abc')
    assert b.getvalue() == 'abc'

def c_print_exception():
    # _format_exc i runneren (Task 2) bruker denne under MicroPython
    import io
    try:
        1 / 0
    except ZeroDivisionError as e:
        buf = io.StringIO()
        sys.print_exception(e, buf)
        assert 'ZeroDivisionError' in buf.getvalue()

def c_sys_stdout_assign():
    # Forventet FEIL i MicroPython (readonly) — informasjonspunkt som
    # begrunner stdout-via-motoren-designet. OK i CPython.
    import io
    old = sys.stdout
    sys.stdout = io.StringIO()
    sys.stdout = old

def c_binascii_base64():
    import binascii
    assert binascii.a2b_base64('aGVp') == b'hei'

def c_json_floats():
    import json
    v = json.loads('{"a": [1.5, null]}')
    assert v['a'][0] == 1.5 and v['a'][1] is None
    assert '{:g}'.format(v['a'][0]) == '1.5'   # Brython-fella finnes IKKE her

def c_format_thousands():
    # Forventet FEIL i MicroPython ({:,} støttes ikke) — dokumentasjonspunkt
    assert '{:,}'.format(1234) == '1,234'

def c_re_split_class():
    import re
    assert re.split('[_\\-]', 'a_b-c') == ['a', 'b', 'c']

def c_class_features():
    class A:
        def __init__(self):
            self._v = 1
        @property
        def v(self):
            return self._v
        @staticmethod
        def s():
            return 2
    class B(A):
        def __init__(self):
            super().__init__()
    assert B().v == 1 and A.s() == 2

def c_csv_missing():
    # Forventet FEIL i MicroPython (ingen csv-modul) — begrunner _parse_csv_text
    import csv  # noqa

def c_datetime_missing():
    # Forventet FEIL i wasm-porten — begrunner try/except rundt datetime i plotly-porten
    import datetime  # noqa

for _n, _f in sorted(globals().items()):
    if _n.startswith('c_'):
        check(_n, _f)
print('SPIKE FERDIG')
