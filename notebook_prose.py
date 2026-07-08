"""Render top-level bare-string statements as markdown embeds.

A Python script written notebook-style can carry prose as top-level string
literals sitting alone as statements (triple- or single-quoted). This module
rewrites each such statement into a print() that emits the markdown embed
markers the front-end already renders. Strings assigned to names, and
docstrings inside functions/classes, are left as normal code.
"""
import ast

_START = "__micro_transform_start_markdown__"
_END = "__micro_transform_end__"


def _emit_line(text):
    safe = str(text).replace(_END, "")           # neutralize an injected end marker
    payload = "\n" + _START + "\n" + safe + "\n" + _END + "\n"
    return "print(%r)" % (payload,)               # repr escapes everything, reproduces exactly


def _line_start_byte_offsets(data):
    """Absolute UTF-8 byte offset of the start of each 1-based line."""
    offsets = [0]
    start = 0
    while True:
        idx = data.find(b"\n", start)
        if idx == -1:
            break
        offsets.append(idx + 1)
        start = idx + 1
    return offsets


def _to_byte_offset(line_starts, lineno, col_offset):
    # ast column offsets are already UTF-8 byte offsets.
    return line_starts[lineno - 1] + col_offset


def prep_python_prose(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    spans = []  # (start_byte, end_byte, text)
    data = src.encode("utf-8")
    line_starts = _line_start_byte_offsets(data)
    for node in tree.body:
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            start = _to_byte_offset(line_starts, node.lineno, node.col_offset)
            end = _to_byte_offset(line_starts, node.end_lineno, node.end_col_offset)
            spans.append((start, end, node.value.value))
    if not spans:
        return src

    out = data
    for start, end, text in sorted(spans, key=lambda s: s[0], reverse=True):
        out = out[:start] + _emit_line(text).encode("utf-8") + out[end:]
    return out.decode("utf-8")
