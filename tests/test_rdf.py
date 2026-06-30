"""tests for the rdf consumer (load + shacl + sparql)."""
import os

import pytest

pytest.importorskip("rdflib")
pytest.importorskip("pyshacl")

from supplygraph import emit, rdf

_NODES = {
    "co:acme": ("Company", "Acme", ""),
    "ndc:1": ("Product", "Pill One", ""),
    "ndc:2": ("Product", "Pill Two", ""),
    "unii:AAA": ("Part", "Caffeine", "AAA"),
}
_EDGES = [
    ("co:acme", "MAKES", "ndc:1", "openFDA drug label", 0.9, "20240101", "spl-1"),
    ("co:acme", "MAKES", "ndc:2", "openFDA drug label", 0.7, "20240101", "spl-2"),
    ("ndc:1", "CONTAINS", "unii:AAA", "openFDA drug label", 1.0, "20240101", "spl-1"),
    ("ndc:2", "CONTAINS", "unii:AAA", "openFDA drug label", 1.0, "20240101", "spl-2"),
]


def _fixture(tmp_path, nodes=_NODES, edges=_EDGES):
    emit.write_jsonld(nodes, edges, outdir=str(tmp_path))
    return rdf.load(os.path.join(str(tmp_path), "graph.jsonld"))


def test_fixture_conforms_and_queries(tmp_path):
    g = _fixture(tmp_path)
    conforms, report = rdf.validate(g)
    assert conforms, report
    assert rdf.top_makers(g) == [("Acme", 2)]
    assert rdf.top_ingredients(g) == [("Caffeine", 2)]


def test_rejects_out_of_range_confidence(tmp_path):
    edges = [("co:acme", "MAKES", "ndc:1", "openFDA drug label", 1.5, "20240101", "spl-1")]
    g = _fixture(tmp_path, nodes={"co:acme": ("Company", "Acme", ""), "ndc:1": ("Product", "P", "")}, edges=edges)
    conforms, _ = rdf.validate(g)
    assert not conforms
