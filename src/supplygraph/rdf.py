"""rdf consumer: load graph.jsonld, validate with shacl, run sparql analytics.

uses rdflib + pyshacl. this is the rdf consumer layer; the core pipeline stays stdlib-only.
"""
import os

import rdflib
from pyshacl import validate as _shacl

from .config import OUT_DIR, ROOT

GRAPH = os.path.join(OUT_DIR, "graph.jsonld")
SHAPES = os.path.join(ROOT, "shapes", "supplygraph.shacl.ttl")

_PREFIXES = """
PREFIX sg: <https://w3id.org/supplygraph/schema#>
PREFIX schema: <https://schema.org/>"""

# count distinct products per maker, mirroring query.py top makers
_MAKERS = _PREFIXES + '''
SELECT ?name (COUNT(DISTINCT ?prod) AS ?n) WHERE {
  ?a sg:predicate "MAKES" ; sg:subject ?co ; sg:object ?prod .
  OPTIONAL { ?co schema:name ?nm }
  BIND(COALESCE(?nm, STR(?co)) AS ?name)
} GROUP BY ?co ?name ORDER BY DESC(?n) ?name LIMIT __N__'''

# count distinct products per ingredient, mirroring query.py most common ingredients
_INGREDIENTS = _PREFIXES + '''
SELECT ?name (COUNT(DISTINCT ?prod) AS ?n) WHERE {
  ?a sg:predicate "CONTAINS" ; sg:object ?part ; sg:subject ?prod .
  OPTIONAL { ?part schema:name ?nm }
  BIND(COALESCE(?nm, STR(?part)) AS ?name)
} GROUP BY ?part ?name ORDER BY DESC(?n) ?name LIMIT __N__'''


def load(path=GRAPH):
    g = rdflib.Graph()
    g.parse(path, format="json-ld")
    return g


def validate(graph, shapes=SHAPES):
    conforms, _report_graph, report_text = _shacl(graph, shacl_graph=shapes, inference="none")
    return conforms, report_text


def _rows(graph, query, limit):
    res = graph.query(query.replace("__N__", str(int(limit))))
    return [(str(r.name), int(r.n)) for r in res]


def top_makers(graph, limit=10):
    return _rows(graph, _MAKERS, limit)


def top_ingredients(graph, limit=10):
    return _rows(graph, _INGREDIENTS, limit)


def run(path=GRAPH, shapes=SHAPES):
    g = load(path)
    print(f"loaded {len(g)} triples from {path}")
    conforms, report = validate(g, shapes)
    print(f"SHACL conforms: {conforms}")
    if not conforms:
        print(report)
    print("\nTop makers by product count:")
    for name, n in top_makers(g):
        print(f"  {n:4d}  {name}")
    print("\nMost common active ingredients:")
    for name, n in top_ingredients(g):
        print(f"  {n:4d}  {name}")
    return conforms
