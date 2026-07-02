# supply-graph

A data layer that turns public source data into a provenanced knowledge graph,
emitted in a store-neutral format so the same output feeds an RDF triple store,
Neo4j, and a RAG endpoint with no reprocessing.

First source: openFDA drug labels. The graph models
`Company --MAKES--> Product --CONTAINS--> Part`, where every edge carries its
source, a confidence score, an as-of date, and the exact source record id. That
provenance is the point: downstream answers can cite where each fact came from.

## Why it is built this way

The processing (fetch, clean, resolve, provenance) is the portable value. The
output is neutral (`nodes.csv`, `edges.csv`, `graph.jsonld`), so adapting to a new
target store is a thin loader, not a rebuild. See `docs/DATA_SOURCING.md` for the
production sourcing design and `docs/SCHEMA.md` for the ontology.

## Quickstart

```bash
# (optional) raise the openFDA rate limit
export OPENFDA_API_KEY=your_key

# pull data on a host that can reach api.fda.gov
make fetch N=3000

# build the neutral output into data/out/
make build

# sanity-check
make query

# load into RDF, SHACL-validate, run SPARQL analytics (no server)
pip install -e ".[rdf]"
make rdf

# load the same CSVs into Neo4j, run Cypher analytics
pip install -e ".[neo4j]"
export NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=your_pw
make neo4j

# tests (no network needed)
pip install -e ".[dev]"
make test
```

The core pipeline uses only the Python standard library. `pytest` is the only
dev dependency. The RDF consumer (`make rdf`) adds `rdflib` + `pyshacl`, scoped to
the optional `rdf` extra; the Neo4j consumer (`make neo4j`) adds the official
`neo4j` driver in the optional `neo4j` extra. Each consumer is independent and the
core install stays dependency-free. The two consumers read different artifacts of
the same build — RDF reads `graph.jsonld`, Neo4j reads `nodes.csv` + `edges.csv` —
and print the same analytics, proving the neutral output is store-portable.

## Output

- `data/out/nodes.csv`  one row per Company / Product / Part, with a stable id slot
- `data/out/edges.csv`  one row per relationship, with full provenance columns
- `data/out/graph.jsonld`  the same graph as RDF-ready JSON-LD, schema.org-aligned,
  with each assertion reified so provenance is first-class

## Structure

```
src/supplygraph/  pipeline package (connector, parse, resolve, emit, query, cli, rdf, neo4j_load)
shapes/           SHACL shapes for the RDF consumer
cypher/           commented Cypher practice queries for the Neo4j consumer
docs/             SCHEMA.md (ontology) and DATA_SOURCING.md (sourcing architecture)
data/landing/     raw immutable source pages (gitignored)
data/out/         generated neutral output (gitignored)
tests/            unit tests over a real sample record
pyproject.toml    project metadata, console script, and pytest config
```

## Status and roadmap

Data layer is complete: connector, parse, entity resolution with a stable-id hook,
neutral output, CLI, tests. Consumer 1 (RDF) is in: `make rdf` loads the JSON-LD into
rdflib, validates it against the `shapes/` SHACL contract, and runs SPARQL analytics
locally (no server). Consumer 2 (Neo4j) is in: `make neo4j` loads `nodes.csv` +
`edges.csv` into Neo4j via the official driver and runs the same analytics in Cypher
(the portability proof). Next: a RAG endpoint that answers questions and cites the
source record behind every fact.

## Data source and license

openFDA data is public (US government) and redistributable; each landing page
records the license link. Do not rely on this data for medical decisions.
