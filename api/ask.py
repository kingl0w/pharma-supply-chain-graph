"""vercel serverless wrapper around the graph-rag consumer.

vercel's python runtime invokes a BaseHTTPRequestHandler subclass named
`handler`; the whole repo is bundled, so we import supplygraph from src/.
env in the vercel dashboard: NEO4J_URI/USER/PASSWORD + LLM_BASE_URL/MODEL/API_KEY.

module level is stdlib-only on purpose: the supplygraph import (and through it
the neo4j driver) happens inside do_POST, so serving the static page and the
health check can never crash on a missing dependency or unreachable db.
"""
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

MAX_QUESTION = 300

# vercel's entrypoint model sends every path to this app; public/** normally
# serves from the CDN first, but the root path lands here, so serve the page
# ourselves for the fixed whitelist below. no dynamic paths: no traversal risk.
PUBLIC = os.path.join(os.path.dirname(__file__), "..", "public")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/graph-data.json": ("graph-data.json", "application/json")}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        self._send_raw(code, json.dumps(obj).encode(), "application/json")

    def _send_raw(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in STATIC:
            fname, ctype = STATIC[path]
            # public/ is on the CDN but not always in the function bundle, and an
            # uncaught OSError here is a FUNCTION_INVOCATION_FAILED: try the
            # __file__-relative path, then project-cwd (vercel's stated cwd), then
            # redirect to the CDN copy (the documented app-route-to-static pattern).
            for base in (PUBLIC, "public"):
                try:
                    with open(os.path.join(base, fname), "rb") as f:
                        self._send_raw(200, f.read(), ctype)
                    return
                except OSError:
                    continue
            if path != "/" + fname:               # loop guard: /index.html never redirects to itself
                self.send_response(307)
                self.send_header("Location", "/" + fname)
                self.end_headers()
                return
            self._send(500, {"error": f"static file {fname} missing from function bundle"})
            return
        if path.rstrip("/") == "/api/ask":
            self._send(200, {"status": "ok"})
            return
        if path.rstrip("/") == "/api/warm":
            # aura free pauses after 3 idle days and only the console can resume it,
            # so no request can wake a paused db — this keeps it from idling at all.
            # pinged daily by .github/workflows/keep-warm.yml.
            try:
                from supplygraph import rag  # deferred: see module docstring
                with rag._driver() as driver, driver.session() as session:
                    session.run("RETURN 1").consume()
            except Exception as e:
                traceback.print_exc()
                self._send(500, {"error": str(e)})
                return
            self._send(200, {"status": "warm"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0].rstrip("/") != "/api/ask":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            question = json.loads(self.rfile.read(length) or b"{}")["question"].strip()
        except (ValueError, KeyError, TypeError, AttributeError):
            self._send(400, {"error": 'POST JSON {"question": "..."}'})
            return
        if not question or len(question) > MAX_QUESTION:
            self._send(400, {"error": f"question must be 1-{MAX_QUESTION} chars"})
            return
        # ponytail: fresh driver per invocation; pool if traffic ever matters
        try:
            from supplygraph import rag  # deferred: see module docstring
            with rag._driver() as driver, driver.session() as session:
                res = rag.answer(question, session)
        except (Exception, SystemExit) as e:  # llm.py raises SystemExit when unreachable
            traceback.print_exc()             # full trace to vercel's function logs
            self._send(500, {"error": str(e)})
            return
        self._send(200, {k: res[k] for k in ("answer", "cypher", "citations", "rows")})

    def log_message(self, *a):
        pass
