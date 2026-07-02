.PHONY: fetch build query rdf neo4j test clean
N ?= 3000

# src/ layout, no install required: put the package on the path explicitly.
PY = PYTHONPATH=src python

fetch:            ## pull N records from openFDA into data/landing
	$(PY) -m supplygraph.cli fetch -n $(N)

build:            ## parse landing -> data/out/{nodes.csv,edges.csv,graph.jsonld}
	$(PY) -m supplygraph.cli build

query:            ## run sample analytics on the built graph
	$(PY) -m supplygraph.cli query

rdf:              ## load graph.jsonld into rdf, validate with shacl, run sparql
	$(PY) -m supplygraph.cli rdf

neo4j:            ## load nodes/edges csvs into neo4j, run cypher analytics (needs .[neo4j] + NEO4J_* env)
	$(PY) -m supplygraph.cli neo4j

test:             ## run unit tests
	pytest -q

clean:            ## remove generated output (keeps landing)
	rm -f data/out/*.csv data/out/*.jsonld
