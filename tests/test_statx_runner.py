# tests/test_statx_runner.py
import sys, types
from statx_runner import parse_statx_chunks, run_statx

class _FakeEngine:
    def __init__(self, datasets, active):
        self.datasets = datasets
        self.active_name = active

def _install_fake_pdexplorer(calls):
    mod = types.ModuleType("pdexplorer")
    def use(df): calls.append(("use", id(df)))
    def do(inline=None, filename=None): print("DID:" + (inline or ""))
    mod.use = use; mod.do = do
    sys.modules["pdexplorer"] = mod

def test_unknown_dataset_message():
    e = _FakeEngine({"folk": object()}, "folk")
    _install_fake_pdexplorer([])
    out = run_statx(e, "use hus\nsummarize x")
    assert "hus" in out and "folk" in out  # names the missing + available

def test_runs_do_on_resolved_dataset():
    df = object()
    e = _FakeEngine({"folk": df}, "folk")
    calls = []; _install_fake_pdexplorer(calls)
    out = run_statx(e, "summarize x")            # no use -> active 'folk'
    assert ("use", id(df)) in calls
    assert "DID:summarize x" in out

def test_no_use_returns_single_chunk_with_default():
    assert parse_statx_chunks("summarize x\nregress y x", "folk") == [("folk", "summarize x\nregress y x")]

def test_leading_use_sets_name():
    assert parse_statx_chunks("use folk\nsummarize x", None) == [("folk", "summarize x")]

def test_switch_between_datasets():
    out = parse_statx_chunks("summarize x\nuse hus\ntabulate y", "folk")
    assert out == [("folk", "summarize x"), ("hus", "tabulate y")]

def test_use_with_options_ignored():
    assert parse_statx_chunks("use folk, clear\nsummarize x", None) == [("folk", "summarize x")]

def test_empty_leading_chunk_dropped():
    assert parse_statx_chunks("use folk\nsummarize x", None) == [("folk", "summarize x")]

from statx_runner import _strip_comments

def test_strip_star_and_slash_comments():
    src = "* header\nsummarize x\n  * indented comment\n// other comment\nregress y x"
    assert _strip_comments(src) == "summarize x\nregress y x"

def test_strip_keeps_noncomment_lines_with_inline_star():
    # a '*' NOT at line start is not a comment (e.g. multiplication) — keep the line
    assert _strip_comments("generate z = x * 2") == "generate z = x * 2"

def test_run_statx_strips_comments_before_do():
    import sys, types
    e_datasets = {"folk": object()}
    class E:
        datasets = e_datasets
        active_name = "folk"
    received = {}
    mod = types.ModuleType("pdexplorer")
    mod.use = lambda df: None
    def _do(inline=None, filename=None): received["inline"] = inline
    mod.do = _do
    sys.modules["pdexplorer"] = mod
    from statx_runner import run_statx
    run_statx(E(), "* a comment\nsummarize x")
    assert received["inline"] == "summarize x"
