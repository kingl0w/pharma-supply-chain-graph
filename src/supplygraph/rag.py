"""graph-rag consumer: plain-english question -> cypher -> grounded, cited answer.

flow: text_to_cypher (llm) -> assert_read_only + ensure_limit (guards) ->
run_cypher (read transaction, one syntax-retry) -> compose_answer (llm, rows only).

layered safety: the guard rejects any write clause *before* execution, and
execute_read makes the db itself refuse writes even if the guard is bypassed.
answers are grounded: the model answers from the returned rows only and cites the
source_record behind every fact. deferred imports keep the rag extra optional and
`make test` green without the neo4j driver installed.
"""
import json
import os
import re

# --- schema grounding (few-shot) ------------------------------------------

SCHEMA_HINT = """Graph schema (Neo4j):
Nodes:
  (:Company {id, name, stable_id})   // drug labeler
  (:Product {id, name, stable_id})   // a drug product, identified by NDC
  (:Part    {id, name, stable_id})   // an active ingredient, identified by UNII
Relationships (each carries provenance: source, confidence, as_of, source_record):
  (:Company)-[:MAKES]->(:Product)
  (:Product)-[:CONTAINS]->(:Part)
Part.name and Product.name are stored UPPERCASE. Always match names
case-insensitively with toLower(x.name) CONTAINS '<lowercase term>'; never use
exact equality or a {name: '...'} map filter.
Do not add a category-word filter on the product name (e.g. requiring the name to
contain "sunscreen") unless the user explicitly asks to filter by product name.
When a question filters on related-node properties (e.g. ingredient names), also
RETURN those matched values (e.g. a.name, b.name) so the evidence appears in the rows.
For a fact question about a specific product, ingredient, or maker, RETURN the
relationship's source_record so the answer can be cited. For an aggregate/count
question, omit source_record and return only the counts."""

EXAMPLES = [
    ("Which companies make the most products?",
     "MATCH (c:Company)-[:MAKES]->(p:Product) "
     "RETURN c.name AS company, count(DISTINCT p) AS products "
     "ORDER BY products DESC LIMIT 10"),
    ("What ingredients does ibuprofen contain?",
     "MATCH (p:Product)-[c:CONTAINS]->(part:Part) "
     "WHERE toLower(p.name) CONTAINS 'ibuprofen' "
     "RETURN DISTINCT p.name AS product, part.name AS ingredient, "
     "c.source_record AS source_record, c.confidence AS confidence"),
    ("What sunscreens contain both avobenzone and octocrylene?",
     "MATCH (p:Product)-[c1:CONTAINS]->(a:Part), (p)-[:CONTAINS]->(b:Part) "
     "WHERE toLower(a.name) CONTAINS 'avobenzone' "
     "AND toLower(b.name) CONTAINS 'octocrylene' "
     "RETURN DISTINCT p.name AS product, a.name AS ingredient_1, "
     "b.name AS ingredient_2, c1.source_record AS source_record"),
    ("Which products contain caffeine?",
     "MATCH (p:Product)-[c:CONTAINS]->(part:Part) "
     "WHERE toLower(part.name) CONTAINS 'caffeine' "
     "RETURN p.name AS product, c.source_record AS source_record"),
    ("What does Pfizer make?",
     "MATCH (c:Company)-[m:MAKES]->(p:Product) "
     "WHERE toLower(c.name) CONTAINS 'pfizer' "
     "RETURN p.name AS product, m.source_record AS source_record, m.confidence AS confidence"),
]

# --- read-only guard ------------------------------------------------------

# word-boundary match on write clauses. this also flags writing procedures,
# whose names carry these verbs (apoc.create.*, apoc.*.delete, *.setProperty).
# execute_read is the second layer: the db refuses writes even if this misses.
_WRITE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b", re.I)
_HAS_LIMIT = re.compile(r"\bLIMIT\b\s+\d+", re.I)


def is_read_only(cypher):
    return not _WRITE.search(cypher or "")


def assert_read_only(cypher):
    if not is_read_only(cypher):
        raise ValueError(f"refusing non-read-only cypher: {cypher!r}")


def ensure_limit(cypher, default=50):
    """append a LIMIT to bound result size, unless the query already has one."""
    if _HAS_LIMIT.search(cypher):
        return cypher
    return f"{cypher.rstrip().rstrip(';').rstrip()} LIMIT {default}"


# --- llm steps ------------------------------------------------------------

def _strip_fences(text):
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    return t


def _cypher_prompt(question):
    shots = "\n".join(f"Q: {q}\nCypher: {c}" for q, c in EXAMPLES)
    return f"{SCHEMA_HINT}\n\nExamples:\n{shots}\n\nQ: {question}\nCypher:"


def text_to_cypher(question):
    from . import llm
    out = llm.chat([
        {"role": "system", "content": "You translate a question into ONE read-only "
         "Cypher query for the given schema. Output ONLY the Cypher query: no prose, "
         "no explanation, no markdown fences."},
        {"role": "user", "content": _cypher_prompt(question)},
    ])
    return _strip_fences(out)


def _fix_cypher(cypher, error):
    from . import llm
    out = llm.chat([
        {"role": "system", "content": "Fix the Cypher query. Output ONLY the "
         "corrected read-only Cypher: no prose, no markdown."},
        {"role": "user", "content": f"{SCHEMA_HINT}\n\nQuery:\n{cypher}\n\n"
         f"Neo4j returned this error:\n{error}\n\nCorrected Cypher:"},
    ])
    return _strip_fences(out)


NO_DATA = "The graph has no data for this question."


def compose_answer(question, rows):
    if not rows:                       # empty-check in code, consistent with _citations
        return NO_DATA
    from . import llm
    return llm.chat([
        {"role": "system", "content": "You answer strictly from the provided graph "
         "rows and cite the source_record ids behind each fact. You never invent "
         "drugs, companies, or ingredients that are not present in the rows."},
        {"role": "user", "content":
            f"Question: {question}\n\nRows returned from the graph (JSON):\n"
            f"{json.dumps(rows, indent=2)}\n\nThese {len(rows)} row(s) are the result "
            "set of a query that already applied every filter in the question, so each "
            "row satisfies the question by construction. Treat the rows as authoritative "
            "matches: do not re-verify the condition against columns that may not be "
            "present. Answer by listing or summarizing the returned rows and cite the "
            "source_record value(s). Do not claim there is no data."},
    ])


# --- execution ------------------------------------------------------------

def _read(session, cypher):
    return session.execute_read(lambda tx: [r.data() for r in tx.run(cypher)])


def run_cypher(session, cypher):
    """run cypher in a read transaction; one llm retry on a syntax error.

    returns (final_cypher, rows) so callers cite the query that actually ran.
    """
    try:
        from neo4j.exceptions import CypherSyntaxError
    except ImportError:  # rag extra not installed; nothing to catch specially
        class CypherSyntaxError(Exception):
            pass
    assert_read_only(cypher)
    bounded = ensure_limit(cypher)
    try:
        return bounded, _read(session, bounded)
    except CypherSyntaxError as e:
        fixed = ensure_limit(_fix_cypher(bounded, str(e)))
        assert_read_only(fixed)
        return fixed, _read(session, fixed)


def _citations(rows):
    seen = []
    for r in rows:
        sr = r.get("source_record") if isinstance(r, dict) else None
        if sr and sr not in seen:
            seen.append(sr)
    return seen


def answer(question, session):
    cypher, rows = run_cypher(session, text_to_cypher(question))
    rows = list(rows)                  # materialize once; both consumers read this list
    return {"question": question, "cypher": cypher, "rows": rows,
            "answer": compose_answer(question, rows), "citations": _citations(rows)}


def _driver():
    from neo4j import GraphDatabase
    uri = os.environ.get("NEO4J_URI")
    if not uri:
        raise SystemExit("set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD to query the graph")
    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
    return GraphDatabase.driver(uri, auth=auth)


def run(question):
    with _driver() as driver, driver.session() as session:
        res = answer(question, session)
    print(res["answer"])
    print("\n--- Cypher ---\n" + res["cypher"])
    print("\n--- Citations ---")
    for c in res["citations"]:
        print(f"  {c}")
    if not res["citations"]:
        print("  (none)")
    return res


def serve(host="127.0.0.1", port=8000):
    """minimal stdlib endpoint: POST /ask {"question": "..."} and GET /health.

    reuses one neo4j driver across requests; this is what the web demo calls.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    driver = _driver()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send(*(200, {"status": "ok"}) if self.path == "/health"
                       else (404, {"error": "not found"}))

        def do_POST(self):
            if self.path != "/ask":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                question = json.loads(self.rfile.read(length) or b"{}")["question"]
            except (ValueError, KeyError, TypeError):
                self._send(400, {"error": 'POST JSON {"question": "..."}'})
                return
            try:
                with driver.session() as session:
                    res = answer(question, session)
            except Exception as e:  # surface llm/db failures as 500, keep serving
                self._send(500, {"error": str(e)})
                return
            self._send(200, {k: res[k] for k in ("answer", "cypher", "citations", "rows")})

        def log_message(self, *a):
            pass

    server = HTTPServer((host, port), Handler)
    print(f"serving on http://{host}:{port}  (POST /ask, GET /health)")
    try:
        server.serve_forever()
    finally:
        driver.close()
