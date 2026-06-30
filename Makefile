.PHONY: fetch build query test clean
N ?= 3000

# src/ layout, no install required: put the package on the path explicitly.
PY = PYTHONPATH=src python

fetch:            ## pull N records from openFDA into data/landing
	$(PY) -m supplygraph.cli fetch -n $(N)

build:            ## parse landing -> data/out/{nodes.csv,edges.csv,graph.jsonld}
	$(PY) -m supplygraph.cli build

query:            ## run sample analytics on the built graph
	$(PY) -m supplygraph.cli query

test:             ## run unit tests
	pytest -q

clean:            ## remove generated output (keeps landing)
	rm -f data/out/*.csv data/out/*.jsonld
