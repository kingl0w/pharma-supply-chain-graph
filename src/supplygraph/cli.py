"""cli entrypoint: python -m supplygraph.cli {fetch,build,query}."""
import argparse

from . import config, emit, openfda


def main():
    ap = argparse.ArgumentParser(prog="supplygraph",
                                 description="openFDA -> knowledge-graph data layer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="pull records into the landing zone")
    f.add_argument("-n", "--total", type=int, default=3000,
                   help="number of records to pull (default 3000)")
    f.add_argument("--no-trim", action="store_true",
                   help="keep full raw records instead of trimming to used fields")

    sub.add_parser("build", help="parse landing zone -> nodes/edges/jsonld")
    sub.add_parser("query", help="run sample analytics on the built graph")
    sub.add_parser("rdf", help="load graph.jsonld into rdf, validate (shacl), run sparql analytics")

    args = ap.parse_args()
    if args.cmd == "fetch":
        openfda.fetch(total=args.total, trim=not args.no_trim)
    elif args.cmd == "build":
        emit.build(config.LANDING_DIR)
    elif args.cmd == "query":
        from . import query
        query.run()
    elif args.cmd == "rdf":
        from . import rdf
        raise SystemExit(0 if rdf.run() else 1)


if __name__ == "__main__":
    main()
