# micropython micropython/tests/mpy_smoke_plotly.py
import sys, json
sys.path.insert(0, 'micropython')
import pandas_mpy as pd
import plotly_express_mpy as pe

df = pd.DataFrame({'x': [1, 2, 3], 'y': [3.5, None, 4.0], 'k': ['a', 'b', 'a']})
for fig in (pe.scatter(df, x='x', y='y'),
            pe.bar(df, x='k', y='x'),
            pe.line(df, x='x', y='y'),
            pe.histogram(df, x='k'),
            pe.pie(df, names='k', values='x')):
    d = json.loads(fig.to_plotly_json_str())
    assert 'data' in d and 'layout' in d
print('MPY-PLOTLY-RØYK OK')
