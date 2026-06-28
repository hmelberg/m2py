# statx_runner.py
import re
import io, sys

_USE_RE = re.compile(r"^\s*use\s+([^\s,]+)", re.IGNORECASE)

def _strip_comments(text):
    """Drop Stata comment lines (first non-blank char is '*', or starts with '//').
    pdexplorer.do(inline=...) cannot parse comment lines."""
    out = []
    for line in text.split("\n"):
        s = line.lstrip()
        if s.startswith("*") or s.startswith("//"):
            continue
        out.append(line)
    return "\n".join(out)

def parse_statx_chunks(script, default_name):
    """Split a statx script into (dataset_name, commands) chunks at `use NAME` lines.
    `use NAME` lines are consumed. Leading commands before any `use` use default_name.
    A chunk with only whitespace commands is dropped."""
    chunks = []
    cur_name = default_name
    cur_lines = []

    def flush():
        text = "\n".join(cur_lines).strip()
        if text:
            chunks.append((cur_name, text))

    for line in script.split("\n"):
        m = _USE_RE.match(line)
        if m:
            flush()
            cur_name = m.group(1)
            cur_lines = []
        else:
            cur_lines.append(line)
    flush()
    return chunks

def run_statx(e, script):
    import pdexplorer  # lazy: only available in the browser Pyodide runtime
    chunks = parse_statx_chunks(script, getattr(e, "active_name", None))
    buf = io.StringIO()
    for name, commands in chunks:
        commands = _strip_comments(commands)
        if not commands.strip():
            continue
        if name is None or name not in e.datasets:
            avail = ", ".join(e.datasets.keys()) or "(ingen)"
            buf.write("use: ukjent datasett '%s'. Tilgjengelige: %s\n" % (name, avail))
            continue
        pdexplorer.use(e.datasets[name])
        _old = sys.stdout
        sys.stdout = buf
        try:
            pdexplorer.do(inline=commands)
        finally:
            sys.stdout = _old
    return buf.getvalue()
