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


def prep_python_prose(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    spans = []  # (start_line_1based, end_line_1based, text)
    for node in tree.body:
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            spans.append((node.lineno, node.end_lineno, node.value.value))
    if not spans:
        return src

    lines = src.split("\n")
    start_map = {s[0]: s for s in spans}          # 1-based start line -> span
    covered = set()
    for s in spans:
        for ln in range(s[0], s[1] + 1):
            covered.add(ln)

    out = []
    for i, line in enumerate(lines, start=1):
        if i in start_map:
            out.append(_emit_line(start_map[i][2]))
        elif i in covered:
            continue                              # inside a multi-line prose span already emitted
        else:
            out.append(line)
    return "\n".join(out)
