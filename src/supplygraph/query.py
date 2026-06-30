"""sample analytics over the built graph."""
import csv
import os
from collections import Counter, defaultdict

from .config import OUT_DIR


def run(outdir=OUT_DIR):
    npath = os.path.join(outdir, "nodes.csv")
    epath = os.path.join(outdir, "edges.csv")
    if not (os.path.exists(npath) and os.path.exists(epath)):
        raise SystemExit("no built graph found; run `build` first")
    nodes = {r["node_id"]: r for r in csv.DictReader(open(npath))}
    edges = list(csv.DictReader(open(epath)))
    nm = lambda i: nodes[i]["name"] if i in nodes else i

    makers = defaultdict(set)
    contains = defaultdict(set)
    for e in edges:
        if e["rel"] == "MAKES":
            makers[e["src"]].add(e["dst"])
        elif e["rel"] == "CONTAINS":
            contains[e["dst"]].add(e["src"])

    print("Top makers by product count:")
    for co, ps in sorted(makers.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {len(ps):4d}  {nm(co)}")

    print("\nMost common active ingredients:")
    for ing, ps in sorted(contains.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {len(ps):4d}  {nm(ing)}")

    mix = Counter("confirmed" if float(e["confidence"]) == 1.0 else "lower" for e in edges)
    print(f"\nNodes: {len(nodes)}   Edges: {len(edges)}   {dict(mix)}")
