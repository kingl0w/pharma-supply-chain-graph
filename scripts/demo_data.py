"""snapshot data/out csvs into public/graph-data.json for the static demo page.

compact on purpose: nodes as [id, label, name, stable_id], edges as [src_idx,
dst_idx, rel, confidence, as_of, source_record] with integer indexes into the
node list (source is omitted: it is the constant "openFDA drug label"). run via
`make demo-data` after `make build`; the output is a committed site asset, not
pipeline output.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "graph-data.json"


def main():
    with open(ROOT / "data/out/nodes.csv", newline="", encoding="utf-8") as f:
        nodes = [[r["node_id"], r["label"], r["name"], r["stable_id"]]
                 for r in csv.DictReader(f)]
    idx = {n[0]: i for i, n in enumerate(nodes)}
    with open(ROOT / "data/out/edges.csv", newline="", encoding="utf-8") as f:
        edges = [[idx[r["src"]], idx[r["dst"]], r["rel"], float(r["confidence"]),
                  r["as_of"], r["source_record"]]
                 for r in csv.DictReader(f)]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"nodes": nodes, "edges": edges}, separators=(",", ":")),
                   encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, "
          f"{len(nodes)} nodes, {len(edges)} edges)")


if __name__ == "__main__":
    main()
