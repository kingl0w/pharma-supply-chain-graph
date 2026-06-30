"""Tests for the parse and resolve stages, against a real openFDA record."""
import json
import os

from supplygraph.parse import claims_from
from supplygraph.resolve import resolve_company, resolve_ingredient

HERE = os.path.dirname(__file__)


def _sample():
    with open(os.path.join(HERE, "sample_label.json")) as f:
        return json.load(f)["results"][0]


def test_resolve_company_strips_suffixes_and_dba():
    cid, name, stable = resolve_company("Rxhomeo Private Limited d.b.a. Rxhomeo, Inc")
    assert cid == "co:rxhomeo"
    assert stable == ""            # no authoritative id yet


def test_resolve_ingredient_prefers_unii():
    pid, conf = resolve_ingredient("SILICON DIOXIDE", "ETJ7Z6XBU4")
    assert pid == "unii:ETJ7Z6XBU4"
    assert conf == 1.0


def test_claims_from_real_record():
    nodes, edges = claims_from(_sample())
    assert nodes["co:rxhomeo"][0] == "Company"
    assert nodes["ndc:15631-0404"][0] == "Product"
    assert nodes["unii:ETJ7Z6XBU4"][0] == "Part"
    rels = {(s, r, o) for (s, r, o, *_rest) in edges}
    assert ("co:rxhomeo", "MAKES", "ndc:15631-0404") in rels
    assert ("ndc:15631-0404", "CONTAINS", "unii:ETJ7Z6XBU4") in rels
    # provenance present on every edge
    for e in edges:
        assert e[3] and e[5] is not None and e[6]  # source, as_of, source_record
