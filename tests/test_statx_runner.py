# tests/test_statx_runner.py
from statx_runner import parse_statx_chunks

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
