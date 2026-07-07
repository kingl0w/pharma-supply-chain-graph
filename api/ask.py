"""vercel serverless wrapper around the graph-rag consumer.

vercel's python runtime invokes a BaseHTTPRequestHandler subclass named
`handler`; the whole repo is bundled, so we import supplygraph from src/.
env in the vercel dashboard: NEO4J_URI/USER/PASSWORD + LLM_BASE_URL/MODEL/API_KEY.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from supplygraph import rag  # noqa: E402

MAX_QUESTION = 300


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, {"status": "ok"})

    def do_POST(self):
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
            with rag._driver() as driver, driver.session() as session:
                res = rag.answer(question, session)
        except (Exception, SystemExit) as e:  # llm.py raises SystemExit when unreachable
            self._send(500, {"error": str(e)})
            return
        self._send(200, {k: res[k] for k in ("answer", "cypher", "citations", "rows")})

    def log_message(self, *a):
        pass
