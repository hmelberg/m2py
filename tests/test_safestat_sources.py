import m2py_translate as t


def test_require_url_emits_read_source():
    code = t.translate(
        "require https://h/income.csv as inc\nuse inc\nsummarize wage",
        backend="pandas", source_path=None)
    assert 'ops.read_source(\'https://h/income.csv\', \'csv\')' in code


def test_require_parquet_path_emits_read_source_with_format():
    code = t.translate(
        "require data/persons.parquet as p\nuse p\nkeep if alder > 18",
        backend="pandas", source_path=None)
    assert 'ops.read_source(\'data/persons.parquet\', \'parquet\')' in code


def test_require_registry_name_is_not_a_source():
    # a registry id (no file extension) must NOT become a read_source load
    code = t.translate(
        "require no.ssb.fdb:43 as db\ncreate-dataset persons\ngenerate x = 1\nuse persons",
        backend="pandas", source_path=None)
    assert "read_source(" not in code


def test_require_keys_option_sets_join_key(tmp_path):
    code = t.translate(
        "require a.csv as a, keys(id)\nrequire b.csv as b, keys(id)\n"
        "use b\nmerge v into a",
        backend="pandas", source_path=None)
    assert "left_on='id', right_on='id'" in code
