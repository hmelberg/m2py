# Kjøres under unix-micropython: micropython micropython/tests/mpy_smoke_pandas.py
# Dialekt-røyk for pandas_mpy — feiler høylytt med traceback ved dialektbrudd.
import sys
sys.path.insert(0, 'micropython')
import pandas_mpy as pd

df = pd.DataFrame({'by': ['Oslo', 'Bergen', 'Oslo'], 'v': [10, 20, 30]})
assert len(df) == 3
g = df.groupby('by')['v'].mean()
assert '<table' in df.to_html()
sub = df[df['v'] > 10]
assert len(sub) == 2
df['dobbel'] = df['v'] * 2
assert list(df['dobbel']) == [20, 40, 60]
from io import StringIO
df2 = pd.read_csv(StringIO('a,b\n1,"x,y"\n2,z\n'))
assert len(df2) == 2
s = pd.Series([1, 2, 3, 4, 5])
s.iloc[1:3] = pd.Series([100, 200])
assert list(s) == [1, 100, 200, 4, 5]
print('MPY-PANDAS-RØYK OK')
