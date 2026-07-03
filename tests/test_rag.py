"""tests for the graph-rag consumer.

pure-logic tests (guards, limit, schema hint) run with no db and no llm.
the e2e test mocks llm.chat and the neo4j session, so it needs neither.
the live test needs the neo4j driver, a reachable NEO4J_URI, and LLM_BASE_URL;
skipped otherwise so `make test` stays green with nothing running.
"""
import os

import pytest

from supplygraph import rag


# --- read-only guard ------------------------------------------------------

def test_is_read_only_accepts_match_return():
    assert rag.is_read_only("MATCH (c:Company)-[:MAKES]->(p:Product) RETURN c.name")


@pytest.mark.parametrize("clause", [
    "CREATE (n:Company {id: 'x'})",
    "MATCH (c:Company) SET c.name = 'x'",
    "MATCH (n) DELETE n",
    "MATCH (n) DETACH DELETE n",
    "MATCH (c:Company) REMOVE c.name",
    "MERGE (n:Company {id: 'x'})",
    "DROP CONSTRAINT foo",
    "FOREACH (x IN [1] | CREATE (:N))",
    "LOAD CSV FROM 'file:///x.csv' AS row CREATE (:N)",
    "MATCH (c:Company) CALL apoc.create.node(['N'], {}) YIELD node RETURN node",
])
def test_is_read_only_rejects_write_clause(clause):
    assert not rag.is_read_only(clause)
    with pytest.raises(ValueError):
        rag.assert_read_only(clause)


def test_assert_read_only_rejects_injection():
    with pytest.raises(ValueError):
        rag.assert_read_only("MATCH (n) DETACH DELETE n")


# --- ensure_limit ---------------------------------------------------------

def test_ensure_limit_appends_when_missing():
    out = rag.ensure_limit("MATCH (n) RETURN n")
    assert out == "MATCH (n) RETURN n LIMIT 50"


def test_ensure_limit_appends_custom_default():
    assert rag.ensure_limit("MATCH (n) RETURN n", default=5).endswith("LIMIT 5")


def test_ensure_limit_preserves_existing():
    q = "MATCH (n) RETURN n LIMIT 10"
    assert rag.ensure_limit(q) == q


def test_ensure_limit_strips_trailing_semicolon():
    assert rag.ensure_limit("MATCH (n) RETURN n;") == "MATCH (n) RETURN n LIMIT 50"


# --- schema grounding -----------------------------------------------------

def test_cypher_prompt_includes_schema_labels():
    prompt = rag._cypher_prompt("anything")
    for token in ("Company", "Product", "Part", "MAKES", "CONTAINS", "source_record"):
        assert token in prompt
    assert "anything" in prompt


def test_strip_fences_removes_markdown():
    assert rag._strip_fences("```cypher\nMATCH (n) RETURN n\n```") == "MATCH (n) RETURN n"


# --- e2e with mocks (no llm, no db) ---------------------------------------

class _FakeTx:
    def __init__(self, rows):
        self.rows = rows

    def run(self, cypher, **kw):
        return [type("R", (), {"data": lambda self, d=r: d})() for r in self.rows]


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.ran = None

    def execute_read(self, fn):
        return fn(_FakeTx(self.rows))


def test_answer_returns_dict_with_citations(monkeypatch):
    rows = [
        {"product": "Advil", "ingredient": "Ibuprofen", "source_record": "spl-1"},
        {"product": "Advil PM", "ingredient": "Ibuprofen", "source_record": "spl-2"},
        {"product": "Advil Dup", "ingredient": "Ibuprofen", "source_record": "spl-1"},
    ]
    replies = iter([
        "MATCH (p:Product)-[c:CONTAINS]->(part:Part) RETURN p.name, c.source_record",
        "Advil and Advil PM contain Ibuprofen (source_record spl-1, spl-2).",
    ])
    monkeypatch.setattr("supplygraph.llm.chat", lambda *a, **k: next(replies))

    res = rag.answer("what contains ibuprofen?", _FakeSession(rows))

    assert res["question"] == "what contains ibuprofen?"
    assert res["rows"] == rows
    assert res["citations"] == ["spl-1", "spl-2"]   # distinct, order-preserving
    assert "Ibuprofen" in res["answer"]
    assert res["cypher"].endswith("LIMIT 50")        # ensure_limit applied


def test_answer_empty_rows_has_no_citations(monkeypatch):
    replies = iter([
        "MATCH (p:Product) WHERE p.name = 'nope' RETURN p.name",
        "The graph has no data for this question.",
    ])
    monkeypatch.setattr("supplygraph.llm.chat", lambda *a, **k: next(replies))

    res = rag.answer("does nonexistdrug exist?", _FakeSession([]))
    assert res["rows"] == []
    assert res["citations"] == []


# --- live (needs driver + reachable neo4j + llm) --------------------------

def test_live_answer():
    pytest.importorskip("neo4j")
    if not (os.environ.get("NEO4J_URI") and os.environ.get("LLM_BASE_URL")):
        pytest.skip("set NEO4J_URI and LLM_BASE_URL to run the live rag test")
    import neo4j
    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
    try:
        driver = neo4j.GraphDatabase.driver(os.environ["NEO4J_URI"], auth=auth)
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"NEO4J_URI unreachable: {e}")
    with driver, driver.session() as s:
        res = rag.answer("which companies make the most products?", s)
    assert set(res) == {"question", "cypher", "rows", "answer", "citations"}
    assert rag.is_read_only(res["cypher"])
