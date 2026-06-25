"""Tiny webhook sink for Apollo's async phone-reveal callbacks.

Apollo's `reveal_phone_number` does NOT return the mobile inline — it POSTs the
enriched person (with phone_numbers) to a public `webhook_url` seconds-to-minutes
later. This server catches those POSTs and appends each raw payload to
`phone_callbacks.jsonl`, one JSON object per line. `reveal_mobiles.py` then reads
that file and writes the numbers into the Google Sheet.

Run:  python webhook_server.py [port]   (default 8755)
GET / returns 'ok' (health check for the tunnel).
"""
import datetime
import http.server
import json
import sys

OUT = "phone_callbacks.jsonl"


class Handler(http.server.BaseHTTPRequestHandler):
    def _ok(self, msg=b"ok"):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(msg)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        rec = {"ts": datetime.datetime.now().isoformat(),
               "path": self.path, "body": raw}
        with open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"  [callback] {rec['ts']} {self.path} ({n} bytes)", flush=True)
        self._ok()

    def do_GET(self):
        self._ok()

    def log_message(self, *a):  # silence default request logging
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8755
    print(f"webhook sink listening on 127.0.0.1:{port} -> {OUT}", flush=True)
    http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
