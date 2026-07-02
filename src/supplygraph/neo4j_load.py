"""neo4j consumer: read the neutral csvs, load into neo4j via the official driver.

named neo4j_load, not neo4j: `import neo4j` must resolve to the installed driver;
a local neo4j.py would shadow it. reads data/out/nodes.csv + edges.csv (not the
jsonld), writes with parameterized idempotent merge in batched transactions (no
server-side load csv). connection from env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD.
this is a consumer layer; the core pipeline stays stdlib-only, driver in the
optional `neo4j` extra.
"""
import csv
import os

from .config import OUT_DIR

# neo4j cannot parameterize labels or rel types; they are interpolated, so they
# must be whitelisted first. RELS also pins each rel's endpoint labels.
LABELS = {"Company", "Product", "Part"}
RELS = {"MAKES": ("Company", "Product"), "CONTAINS": ("Product", "Part")}

BATCH = 1000


def _check_label(label):
    if label not in LABELS:
        raise ValueError(f"label not in whitelist {sorted(LABELS)}: {label!r}")
    return label


def _check_rel(rel):
    if rel not in RELS:
        raise ValueError(f"rel not in whitelist {sorted(RELS)}: {rel!r}")
    return rel


def constraint_cypher(label):
    _check_label(label)
    return f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"


def node_merge_cypher(label):
    _check_label(label)
    return (f"UNWIND $rows AS row "
            f"MERGE (n:{label} {{id: row.id}}) "
            f"SET n.name = row.name, n.stable_id = row.stable_id")


def edge_merge_cypher(rel):
    _check_rel(rel)
    src, dst = RELS[rel]
    return (f"UNWIND $rows AS row "
            f"MATCH (s:{src} {{id: row.src}}) "
            f"MATCH (d:{dst} {{id: row.dst}}) "
            f"MERGE (s)-[r:{rel}]->(d) "
            f"SET r.source = row.source, r.confidence = row.confidence, "
            f"r.as_of = row.as_of, r.source_record = row.source_record")


# mirror query.py / rdf.py: distinct products per maker / ingredient, count desc then name
MAKERS = ("MATCH (c:Company)-[:MAKES]->(p:Product) "
          "RETURN coalesce(c.name, c.id) AS name, count(DISTINCT p) AS n "
          "ORDER BY n DESC, name LIMIT $limit")
INGREDIENTS = ("MATCH (p:Product)-[:CONTAINS]->(part:Part) "
               "RETURN coalesce(part.name, part.id) AS name, count(DISTINCT p) AS n "
               "ORDER BY n DESC, name LIMIT $limit")


def _read_nodes(outdir):
    by_label = {}
    with open(os.path.join(outdir, "nodes.csv"), newline="") as f:
        for r in csv.DictReader(f):
            _check_label(r["label"])
            by_label.setdefault(r["label"], []).append(
                {"id": r["node_id"], "name": r["name"], "stable_id": r["stable_id"]})
    return by_label


def _read_edges(outdir):
    by_rel = {}
    with open(os.path.join(outdir, "edges.csv"), newline="") as f:
        for r in csv.DictReader(f):
            _check_rel(r["rel"])
            by_rel.setdefault(r["rel"], []).append({
                "src": r["src"], "dst": r["dst"], "source": r["source"],
                "confidence": float(r["confidence"]),
                "as_of": r["as_of"], "source_record": r["source_record"]})
    return by_rel


def _batches(rows):
    for i in range(0, len(rows), BATCH):
        yield rows[i:i + BATCH]


def load(session, outdir=OUT_DIR):
    nodes = _read_nodes(outdir)
    for label in nodes:
        session.run(constraint_cypher(label))
    for label, rows in nodes.items():
        q = node_merge_cypher(label)
        for batch in _batches(rows):
            session.execute_write(lambda tx, b=batch: tx.run(q, rows=b).consume())
    edges = _read_edges(outdir)
    for rel, rows in edges.items():
        q = edge_merge_cypher(rel)
        for batch in _batches(rows):
            session.execute_write(lambda tx, b=batch: tx.run(q, rows=b).consume())
    n_nodes = sum(len(v) for v in nodes.values())
    n_edges = sum(len(v) for v in edges.values())
    return n_nodes, n_edges


def top_makers(session, limit=10):
    return [(r["name"], r["n"]) for r in session.run(MAKERS, limit=limit)]


def top_ingredients(session, limit=10):
    return [(r["name"], r["n"]) for r in session.run(INGREDIENTS, limit=limit)]


def run(outdir=OUT_DIR):
    from neo4j import GraphDatabase
    uri = os.environ.get("NEO4J_URI")
    if not uri:
        raise SystemExit("set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD to load Neo4j")
    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
    with GraphDatabase.driver(uri, auth=auth) as driver:
        with driver.session() as session:
            n_nodes, n_edges = load(session, outdir)
            print(f"loaded {n_nodes} nodes, {n_edges} edges into {uri}")
            print("\nTop makers by product count:")
            for name, n in top_makers(session):
                print(f"  {n:4d}  {name}")
            print("\nMost common active ingredients:")
            for name, n in top_ingredients(session):
                print(f"  {n:4d}  {name}")
    return True
