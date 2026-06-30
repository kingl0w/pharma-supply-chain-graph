"""Tests for the parse and resolve stages, against a real openFDA record."""
import json
import os

import pytest

from supplygraph import resolve
from supplygraph.parse import claims_from
from supplygraph.resolve import (
    _load_ids,
    resolve_company,
    resolve_ingredient,
    stable_id_for,
)

HERE = os.path.dirname(__file__)


def _sample():
    with open(os.path.join(HERE, "sample_label.json")) as f:
        return json.load(f)["results"][0]


def test_resolve_company_strips_suffixes_and_dba():
    cid, name, stable = resolve_company("Rxhomeo Private Limited d.b.a. Rxhomeo, Inc")
    assert cid == "co:rxhomeo"
    assert stable == ""            # no authoritative id yet


# raw labeler strings exactly as they appear in the pull -> (expected id, clean name).
# Fed verbatim to resolve_company, the same entry point parse.py uses.
COMPANY_IDS = [
    ("Conopco d/b/a/ Unilever", "co:conopco", "Conopco"),             # slash d/b/a; keep entity before alias
    ("NuCare Pharmaceuticals,Inc.", "co:nucare-pharmaceuticals", "NuCare Pharmaceuticals"),  # real raw form: comma, no space
    ("NuCare PharmaceuticalsInc", "co:nucare-pharmaceuticals", "NuCare Pharmaceuticals"),    # already-fused variant
    ("Bryant Ranch Prepack", "co:bryant-ranch-prepack", "Bryant Ranch Prepack"),
    ("A-S Medication Solutions", "co:a-s-medication-solutions", "A-S Medication Solutions"),
    ("Rxhomeo Private Limited d.b.a. Rxhomeo, Inc", "co:rxhomeo", "Rxhomeo"),
]


@pytest.mark.parametrize("name,want_id,want_name", COMPANY_IDS)
def test_company_normalization(name, want_id, want_name):
    cid, clean, _stable = resolve_company(name)
    assert cid == want_id
    assert clean == want_name


def test_stable_id_lookup_and_default():
    ids = {"co:foo": "765980TFWHQUEX7C5293"}
    assert stable_id_for("co:foo", ids) == "765980TFWHQUEX7C5293"
    assert stable_id_for("co:missing", ids) == ""


def test_resolve_company_populates_stable_id(monkeypatch):
    monkeypatch.setattr(resolve, "_IDS", {"co:nucare-pharmaceuticals": "Q123456"})
    assert resolve_company("NuCare Pharmaceuticals,Inc.")[2] == "Q123456"


def test_load_ids_ignores_doc_and_nonstring(tmp_path):
    p = tmp_path / "company_ids.json"
    p.write_text('{"_README": "docs", "co:x": "Q1", "co:bad": 5}')
    assert _load_ids(str(p)) == {"co:x": "Q1"}


def test_seed_file_is_valid():
    ids = _load_ids()  # the shipped data/company_ids.json
    assert ids and all(k.startswith("co:") and isinstance(v, str) for k, v in ids.items())


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
