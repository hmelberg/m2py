"""Lokal federert node for utvikling/smoke (fase 1, spec 2026-07-29 §5/§7).

Implements just enough of the Anvil run_extended protocol for the browser
fan-out: synchronous run at submit time, one-shot status poll. NOT a
production node — no auth, permissive CORS, meant for localhost only.

  python3 scripts/dev_federert_node.py --port 9301 \
      --source person=static_data/federert/nord/person.parquet [--level public]
"""
import argparse
import json
import pathlib
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from m2py_remote import run_remote_from_sources  # noqa: E402

TASKS = {}
SOURCES = {}
LEVEL = "public"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/_/api/run_extended"):
            return self._send(404, {"error": "ukjent endepunkt"})
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        sources = []
        for s in req.get("sources", []):
            loc = SOURCES.get(s.get("source_id"))
            if not loc:
                return self._send(200, {"error": "ukjent kilde «%s» på denne noden"
                                        % s.get("source_id")})
            sources.append({"alias": s["alias"], "location": loc, "level": LEVEL})
        task_id = uuid.uuid4().hex
        try:
            TASKS[task_id] = {"status": "completed",
                              "result": run_remote_from_sources(
                                  req["script"], sources,
                                  federated=bool(req.get("federated")))}
        except Exception as exc:
            TASKS[task_id] = {"status": "failed", "error": repr(exc)}
        self._send(200, {"task_id": task_id})

    def do_GET(self):
        if not self.path.startswith("/_/api/run_extended_status"):
            return self._send(404, {"error": "ukjent endepunkt"})
        task_id = self.path.split("task_id=", 1)[-1].split("&")[0]
        self._send(200, TASKS.get(task_id, {"status": "failed",
                                            "error": "ukjent task_id"}))

    def log_message(self, fmt, *args):
        print("[node:%s] %s" % (self.server.server_address[1], fmt % args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--source", action="append", required=True,
                    metavar="ID=PATH")
    ap.add_argument("--level", default="public",
                    choices=["public", "protected", "sensitive"])
    args = ap.parse_args()
    global LEVEL
    LEVEL = args.level
    for pair in args.source:
        sid, path = pair.split("=", 1)
        SOURCES[sid] = path
    print(f"federert dev-node på :{args.port} ({', '.join(SOURCES)}, {LEVEL})")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
