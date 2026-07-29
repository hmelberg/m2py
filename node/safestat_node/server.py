"""safestat-node: selvbetjent federert node (fase 2, spec 2026-07-29 §6).

Same run_extended protocol as the Anvil server and the browser fan-out
expects: synchronous run at submit, one-shot status poll, permissive CORS.
Auth: optional bearer token (config/CLI) — required on everything but
OPTIONS when set. Engine: vendored copy under _engine/ (pip install), else
the repo root (checkout).

  safestat-node --config node.json
  safestat-node --port 9301 --source person=data/person.parquet --token X
"""
import argparse
import json
import pathlib
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ENGINE = pathlib.Path(__file__).resolve().parent / "_engine"
_REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ENGINE if (_ENGINE / "m2py_remote.py").exists() else _REPO))
from m2py_remote import run_remote_from_sources  # noqa: E402


def _make_handler(cfg, tasks):
    token = cfg.get("token")
    sources = cfg.get("sources", {})
    level = cfg.get("level", "public")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, Authorization")
            self.end_headers()
            self.wfile.write(body)

        def _authed(self):
            if not token:
                return True
            return self.headers.get("Authorization") == "Bearer " + token

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, Authorization")
            self.end_headers()

        def do_POST(self):
            if not self._authed():
                return self._send(401, {"error": "ugyldig eller manglende token"})
            if not self.path.startswith("/_/api/run_extended"):
                return self._send(404, {"error": "ukjent endepunkt"})
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            run_sources = []
            for s in req.get("sources", []):
                loc = sources.get(s.get("source_id"))
                if not loc:
                    return self._send(200, {"error": "ukjent kilde «%s» på denne noden"
                                            % s.get("source_id")})
                run_sources.append({"alias": s["alias"], "location": loc,
                                    "level": level})
            task_id = uuid.uuid4().hex
            try:
                tasks[task_id] = {"status": "completed",
                                  "result": run_remote_from_sources(
                                      req["script"], run_sources,
                                      federated=bool(req.get("federated")),
                                      fed_round=req.get("fed_round"))}
            except Exception as exc:
                tasks[task_id] = {"status": "failed", "error": repr(exc)}
            self._send(200, {"task_id": task_id})

        def do_GET(self):
            if not self._authed():
                return self._send(401, {"error": "ugyldig eller manglende token"})
            if not self.path.startswith("/_/api/run_extended_status"):
                return self._send(404, {"error": "ukjent endepunkt"})
            task_id = self.path.split("task_id=", 1)[-1].split("&")[0]
            self._send(200, tasks.get(task_id, {"status": "failed",
                                                "error": "ukjent task_id"}))

        def log_message(self, fmt, *args):
            print("[safestat-node:%s] %s"
                  % (self.server.server_address[1], fmt % args))

    return Handler


def create_server(cfg):
    tasks = {}
    return ThreadingHTTPServer(("127.0.0.1", int(cfg.get("port", 9301))),
                               _make_handler(cfg, tasks))


def main():
    ap = argparse.ArgumentParser(prog="safestat-node")
    ap.add_argument("--config")
    ap.add_argument("--port", type=int)
    ap.add_argument("--source", action="append", metavar="ID=PATH")
    ap.add_argument("--level", choices=["public", "protected", "sensitive"])
    ap.add_argument("--token")
    args = ap.parse_args()
    cfg = {}
    if args.config:
        cfg = json.loads(pathlib.Path(args.config).read_text())
    if args.port:
        cfg["port"] = args.port
    if args.level:
        cfg["level"] = args.level
    if args.token:
        cfg["token"] = args.token
    if args.source:
        cfg.setdefault("sources", {}).update(
            dict(pair.split("=", 1) for pair in args.source))
    if not cfg.get("sources"):
        ap.error("ingen kilder — bruk --source id=sti eller --config")
    srv = create_server(cfg)
    print("safestat-node på :%d (%s, %s%s)"
          % (srv.server_address[1], ", ".join(cfg["sources"]),
             cfg.get("level", "public"),
             ", token-beskyttet" if cfg.get("token") else ""))
    srv.serve_forever()


if __name__ == "__main__":
    main()
