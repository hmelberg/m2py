# statx_runner.py
import re

_USE_RE = re.compile(r"^\s*use\s+([^\s,]+)", re.IGNORECASE)

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
