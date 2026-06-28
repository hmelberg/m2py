"""Pure, browser-independent helpers for the DuckDB editor mode.

These parse a SQL script so the run orchestration in index.html knows which
datasets to register as DuckDB views, which tables the script creates (to
materialize back into micro_interpreter.datasets), and which trailing SELECT to
preview. The actual DuckDB execution happens in the browser via window.__duck.

Constraints: no `duckdb` import (browser-only), no `js` import (Pyodide-only).
This module must run under plain pytest.
"""
import io
import re

__all__ = [
    "split_sql_statements",
    "extract_referenced_tables",
    "extract_created_tables",
    "build_preview_select",
    "df_to_parquet_bytes",
]


def split_sql_statements(sql):
    """Split a SQL script on top-level semicolons, ignoring those inside string
    literals ('…'/"…"), -- line comments and /* … */ block comments. Returns a
    list of non-empty, stripped statements (their own comments preserved)."""
    stmts, buf = [], []
    i, n = 0, len(sql)
    in_single = in_double = in_line = in_block = False
    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_line:
            buf.append(c)
            if c == "\n":
                in_line = False
            i += 1
        elif in_block:
            buf.append(c)
            if c == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block = False
            else:
                i += 1
        elif in_single:
            if c == "'" and nxt == "'":
                buf.append(c)
                buf.append(nxt)
                i += 2
            else:
                buf.append(c)
                if c == "'":
                    in_single = False
                i += 1
        elif in_double:
            buf.append(c)
            if c == '"':
                in_double = False
            i += 1
        elif c == "-" and nxt == "-":
            in_line = True
            buf.append(c)
            i += 1
        elif c == "/" and nxt == "*":
            in_block = True
            buf.append(c)
            i += 1
        elif c == "'":
            in_single = True
            buf.append(c)
            i += 1
        elif c == '"':
            in_double = True
            buf.append(c)
            i += 1
        elif c == ";":
            s = "".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []
            i += 1
        else:
            buf.append(c)
            i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def _scrub(sql):
    """Return sql with -- and /* */ comments removed, single-quoted string
    contents replaced by a space, and double-quote characters dropped (so quoted
    identifiers survive as bare tokens). Used for identifier scanning."""
    out = []
    i, n = 0, len(sql)
    in_single = in_line = in_block = False
    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_line:
            if c == "\n":
                in_line = False
                out.append(c)
            i += 1
        elif in_block:
            if c == "*" and nxt == "/":
                in_block = False
                i += 2
                out.append(" ")
            else:
                i += 1
        elif in_single:
            if c == "'" and nxt == "'":
                i += 2
            elif c == "'":
                in_single = False
                out.append(" ")
                i += 1
            else:
                i += 1
        elif c == "-" and nxt == "-":
            in_line = True
            i += 2
        elif c == "/" and nxt == "*":
            in_block = True
            i += 2
        elif c == "'":
            in_single = True
            i += 1
        elif c == '"':
            i += 1  # drop the quote char, keep inner identifier text
        else:
            out.append(c)
            i += 1
    return "".join(out)


def extract_referenced_tables(statements, known):
    """Known dataset names that appear as identifier tokens anywhere in the SQL
    (case-insensitive). Order follows `known`; deduped."""
    scrubbed = _scrub(" ; ".join(statements))
    found = []
    for name in known:
        if name in found:
            continue
        if re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", scrubbed, re.IGNORECASE):
            found.append(name)
    return found


_CREATE_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?\"?([A-Za-z_]\w*)\"?",
    re.IGNORECASE,
)


def extract_created_tables(statements):
    """Targets of CREATE [OR REPLACE] [TEMP] TABLE [IF NOT EXISTS] name.
    Order-preserving, deduped, unquoted."""
    names = []
    for stmt in statements:
        for m in _CREATE_RE.finditer(_scrub(stmt)):
            nm = m.group(1)
            if nm not in names:
                names.append(nm)
    return names


def build_preview_select(statements):
    """The last statement if it begins with SELECT or WITH (a previewable result
    set), else None."""
    if not statements:
        return None
    last = statements[-1]
    head = _scrub(last).lstrip().upper()
    if head.startswith("SELECT") or head.startswith("WITH"):
        return last
    return None


def df_to_parquet_bytes(df):
    """Serialize a DataFrame to Parquet bytes (pyarrow engine)."""
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    return buf.getvalue()
