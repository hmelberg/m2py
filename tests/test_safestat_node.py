"""safestat-node-serveren (fase 2): config, token-auth, run_extended."""
import json
import pathlib
import sys
import threading
import urllib.request
import urllib.error

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "node"))
from safestat_node import server as node_server


@pytest.fixture
def running_node(tmp_path):
    src = tmp_path / "demo.csv"
    pd.DataFrame({"grp": [1] * 6 + [2] * 7}).to_csv(src, index=False)
    cfg = {"port": 0, "level": "public", "token": "hemmelig",
           "sources": {"demo": str(src)}}
    srv = node_server.create_server(cfg)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def _post(url, body, token=None):
    req = urllib.request.Request(url + "/_/api/run_extended",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    return urllib.request.urlopen(req)


def test_token_required(running_node):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(running_node, {"script": "", "sources": []})
    assert exc.value.code == 401


def test_run_extended_with_token(running_node):
    body = {"script": "create-dataset demo\ntabulate grp",
            "sources": [{"alias": "demo", "source_id": "demo"}],
            "federated": True}
    sub = json.loads(_post(running_node, body, token="hemmelig").read())
    req = urllib.request.Request(
        running_node + "/_/api/run_extended_status?task_id=" + sub["task_id"],
        headers={"Authorization": "Bearer hemmelig"})
    st = json.loads(urllib.request.urlopen(req).read())
    assert st["status"] == "completed"
    assert st["result"]["stats"][0]["kind"] == "tabulate"
