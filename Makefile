.PHONY: fetch build query test clean
N ?= 3000

fetch:            ## pull N records from openFDA into data/landing
	python -m supplygraph.cli fetch -n $(N)

build:            ## parse landing -> data/out/{nodes.csv,edges.csv,graph.jsonld}
	python -m supplygraph.cli build

query:            ## run sample analytics on the built graph
	python -m supplygraph.cli query

test:             ## run unit tests
	pytest -q

clean:            ## remove generated output (keeps landing)
	rm -f data/out/*.csv data/out/*.jsonld
