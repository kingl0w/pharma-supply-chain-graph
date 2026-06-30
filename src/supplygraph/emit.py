"""build neutral output: nodes.csv, edges.csv, graph.jsonld."""
import csv
import glob
import json
import os

from .config import OUT_DIR, VOCAB
from .parse import claims_from


def collect(landing):
    nodes, edges, recs = {}, [], 0
    for p in sorted(glob.glob(os.path.join(landing, "openfda_label_*.json"))):
        with open(p) as f:
            page = json.load(f)
        for rec in page.get("results", []):
            recs += 1
            n, e = claims_from(rec)
            nodes.update(n)
            edges.extend(e)
    return nodes, edges, recs


def write_csv(nodes, edges, outdir=OUT_DIR):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "nodes.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "label", "name", "stable_id"])
        for nid, (lab, nm, st) in nodes.items():
            w.writerow([nid, lab, nm, st])
    with open(os.path.join(outdir, "edges.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["src", "rel", "dst", "source", "confidence", "as_of", "source_record"])
        for row in edges:
            w.writerow(row)


def write_jsonld(nodes, edges, outdir=OUT_DIR):
    os.makedirs(outdir, exist_ok=True)
    context = {
        "@vocab": VOCAB,
        "schema": "https://schema.org/",
        "name": "schema:name",
        "stableId": "schema:identifier",
        "Company": "schema:Organization",
        "Product": "schema:Product",
    }
    graph = []
    for nid, (lab, nm, st) in nodes.items():
        obj = {"@id": nid, "@type": lab, "name": nm}
        if st:
            obj["stableId"] = st
        graph.append(obj)
    # edges as reified assertions so provenance is first-class
    for (s, rel, o, src, conf, asof, rec) in edges:
        graph.append({
            "@id": f"_:stmt-{s}-{rel}-{o}",
            "@type": "Assertion",
            "subject": {"@id": s},
            "predicate": rel,
            "object": {"@id": o},
            "source": src,
            "confidence": conf,
            "asOf": asof,
            "sourceRecord": rec,
        })
    doc = {"@context": context, "@graph": graph}
    with open(os.path.join(outdir, "graph.jsonld"), "w") as f:
        json.dump(doc, f, indent=2)


def build(landing, outdir=OUT_DIR):
    nodes, edges, recs = collect(landing)
    write_csv(nodes, edges, outdir)
    write_jsonld(nodes, edges, outdir)
    print(f"parsed {recs} records -> {len(nodes)} nodes, {len(edges)} edges")
    print(f"wrote {outdir}/nodes.csv, edges.csv, graph.jsonld")
    return nodes, edges
