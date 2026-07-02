"""tests for the neo4j consumer.

pure-logic tests (whitelist + query-builder) run with no db and no driver.
live-db tests need the neo4j driver and a reachable NEO4J_URI; skipped otherwise.
"""
import os

import pytest

from supplygraph import neo4j_load as nl


def test_label_whitelist_accepts_known():
    for lab in ("Company", "Product", "Part"):
        assert nl._check_label(lab) == lab


def test_label_whitelist_rejects_injection():
    for bad in ("Company) DETACH DELETE n //", "Drug", "", "company"):
        with pytest.raises(ValueError):
            nl._check_label(bad)


def test_rel_whitelist_accepts_known():
    for rel in ("MAKES", "CONTAINS"):
        assert nl._check_rel(rel) == rel


def test_rel_whitelist_rejects_injection():
    for bad in ("MAKES]->() DELETE r //", "SUPPLIES", "makes"):
        with pytest.raises(ValueError):
            nl._check_rel(bad)


def test_node_merge_cypher_interpolates_validated_label():
    q = nl.node_merge_cypher("Company")
    assert "MERGE (n:Company {id: row.id})" in q
    assert "$rows" in q


def test_edge_merge_cypher_uses_whitelisted_endpoints():
    q = nl.edge_merge_cypher("MAKES")
    assert "MATCH (s:Company {id: row.src})" in q
    assert "MATCH (d:Product {id: row.dst})" in q
    assert "MERGE (s)-[r:MAKES]->(d)" in q


def test_constraint_cypher_is_per_label_unique_on_id():
    q = nl.constraint_cypher("Part")
    assert "FOR (n:Part) REQUIRE n.id IS UNIQUE" in q


def test_builders_reject_bad_input():
    for fn in (nl.node_merge_cypher, nl.constraint_cypher):
        with pytest.raises(ValueError):
            fn("Nope")
    with pytest.raises(ValueError):
        nl.edge_merge_cypher("NOPE")


_NODES = ("node_id,label,name,stable_id\n"
          "co:acme,Company,Acme,\nndc:1,Product,Pill One,\n"
          "ndc:2,Product,Pill Two,\nunii:AAA,Part,Caffeine,AAA\n")
_EDGES = ("src,rel,dst,source,confidence,as_of,source_record\n"
          "co:acme,MAKES,ndc:1,openFDA drug label,0.9,20240101,spl-1\n"
          "co:acme,MAKES,ndc:2,openFDA drug label,0.7,20240101,spl-2\n"
          "ndc:1,CONTAINS,unii:AAA,openFDA drug label,1.0,20240101,spl-1\n"
          "ndc:2,CONTAINS,unii:AAA,openFDA drug label,1.0,20240101,spl-2\n")


@pytest.fixture
def live_session(tmp_path):
    neo4j = pytest.importorskip("neo4j")
    uri = os.environ.get("NEO4J_URI")
    if not uri:
        pytest.skip("NEO4J_URI unset; skipping live-db test")
    (tmp_path / "nodes.csv").write_text(_NODES)
    (tmp_path / "edges.csv").write_text(_EDGES)
    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
    try:
        driver = neo4j.GraphDatabase.driver(uri, auth=auth)
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"NEO4J_URI unreachable: {e}")
    with driver, driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n").consume()
        yield s, str(tmp_path)


def test_live_load_and_analytics(live_session):
    session, outdir = live_session
    n_nodes, n_edges = nl.load(session, outdir)
    assert (n_nodes, n_edges) == (4, 4)
    assert nl.top_makers(session) == [("Acme", 2)]
    assert nl.top_ingredients(session) == [("Caffeine", 2)]
    nl.load(session, outdir)
    assert nl.top_makers(session) == [("Acme", 2)]
