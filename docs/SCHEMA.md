# Supply Graph Ontology Spec v0.1

Status: draft. Scope: drug labeling and ingredient relationships, seeded from
openFDA drug label records. One source so far (openFDA `drug/label.json`).

## 1. Purpose

Represent which companies (labelers) make drug products and which active
ingredients those products contain, with explicit provenance and confidence on
every assertion, so the graph can answer dependency, concentration, and risk
questions and distinguish authoritative identifiers (NDC, UNII) from inferred
name matches.

## 2. Namespaces

```
@prefix sg:     <https://w3id.org/supplygraph/schema#> .   # ontology terms
@prefix :       <https://w3id.org/supplygraph/id/> .       # individuals (nodes)
@prefix schema: <https://schema.org/> .                    # vocab alignment
@prefix wdt:    <http://www.wikidata.org/prop/direct/> .   # property alignment
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:    <http://www.w3.org/2002/07/owl#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
@prefix sh:     <http://www.w3.org/ns/shacl#> .
```

Swap the base IRI before publishing. Node IRIs reuse the CSV `node_id` verbatim,
mapping the `prefix:` separator to `prefix_` for a legal IRI local name, e.g.
`co:pfizer` -> `:co_pfizer`, `ndc:0069-0150` -> `:ndc_0069-0150`,
`unii:R16CO5Y76E` -> `:unii_R16CO5Y76E`. The CSV stays the source of truth and the
mapping is mechanical.

## 3. Classes

| Class        | Meaning                                              | schema.org           |
|--------------|------------------------------------------------------|----------------------|
| `sg:Company` | The drug labeler (`manufacturer_name` on the label). | `schema:Organization`|
| `sg:Product` | A drug product, identified by NDC (`product_ndc`).   | `schema:Product`     |
| `sg:Part`    | An active ingredient, identified by UNII where known.| `schema:Substance`   |

Parts are first-class nodes, not literals, because an ingredient is shared across
many products and carries its own stable government identifier (UNII).

## 4. Object properties (edge types)

Two relationships. The drug label does not distinguish design / fabrication /
supply, so there is no such split here — only who makes the product and what it
contains.

| Property      | Domain       | Range        | Meaning                                  | Wikidata          |
|---------------|--------------|--------------|------------------------------------------|-------------------|
| `sg:makes`    | `sg:Company` | `sg:Product` | The labeler makes / markets the product. | `wdt:P176` (manufacturer) |
| `sg:contains` | `sg:Product` | `sg:Part`    | The product contains the ingredient.     | `wdt:P527` (has part), `wdt:P186` (made from material) |

## 5. Datatype properties

| Property      | Domain       | Range        | Notes                                       |
|---------------|--------------|--------------|---------------------------------------------|
| `sg:name`     | any node     | `xsd:string` | Display label (`schema:name`).              |
| `sg:stableId` | `sg:Company` | `xsd:string` | External id: LEI or Wikidata QID (see 7).   |
| `sg:unii`     | `sg:Part`    | `xsd:string` | UNII code, the FDA ingredient identifier.   |

In `nodes.csv` the `stable_id` column carries the company external id for Company
rows and the UNII for Part rows; it is empty for Product rows.

## 6. Provenance (the core discipline)

Every makes / contains assertion carries four qualifiers: `sg:source`,
`sg:confidence`, `sg:asOf`, `sg:sourceRecord`. This is non-optional. An edge
without provenance is invalid (enforced in SHACL, section 9). As implemented:

- `source` = `"openFDA drug label"` (the source registry name).
- `confidence` = per section 8.
- `asOf` = the label's `effective_time`.
- `sourceRecord` = the SPL id (`spl_id`) — the citation back to the exact submission.

`edges.csv` columns: `src, rel, dst, source, confidence, as_of, source_record`.

Recommended RDF encoding: RDF-star (supported by Fuseki / TDB2 and SPARQL-star).

```
<< :co_pfizer sg:makes :ndc_0069-0150 >>
    sg:source       "openFDA drug label" ;
    sg:confidence   0.9 ;
    sg:asOf         "20240101" ;
    sg:sourceRecord "<spl_id>" .
```

In the JSON-LD output each edge is reified as an `Assertion` node
(`subject` / `predicate` / `object` + `source` / `confidence` / `asOf` /
`sourceRecord`) so provenance is first-class and RAG-friendly. Fallback for plain
RDF 1.1: standard reification with `rdf:Statement`. Pick one and keep it consistent.

## 7. Identity and entity resolution

Mint one node per real-world entity, with a stable external id to defend against
duplicates as the dataset grows:

- Company: the labeler string is normalized (drop `d.b.a.` alias tails, legal
  suffixes, punctuation) to a slug id `co:<slug>`. Attach an authoritative external
  id — LEI preferred, Wikidata QID acceptable — via `KNOWN_IDS` in `resolve.py`.
  Empty until backfilled; backfill the biggest labelers before scaling.
- Part: UNII is already a stable government identifier, so resolution is near-free
  (`unii:<UNII>`). Fall back to a name slug `sub:<slug>` only when the record carries
  no UNII.

When the same company appears from two sources under different names, both resolve
to the node whose `sg:stableId` matches.

## 8. Confidence scale

The pipeline assigns confidence mechanically from the record:

| Value | Edge       | Meaning                                                           |
|-------|------------|-------------------------------------------------------------------|
| 1.0   | `contains` | UNII present — authoritative ingredient identifier.               |
| 0.9   | `makes`    | `is_original_packager` is true — labeler is the original packager. |
| 0.8   | `contains` | No UNII — ingredient matched by name slug only.                   |
| 0.7   | `makes`    | `is_original_packager` is false — labeler may relabel, not make.   |

A `contains` edge to a `sub:` part (no UNII) is a deliberate "known unknown": valid
and queryable, flagged by its lower confidence, not an error.

## 9. SHACL validation (sketch)

```
sg:CompanyShape a sh:NodeShape ;
    sh:targetClass sg:Company ;
    sh:property [ sh:path sg:name ; sh:minCount 1 ] .

sg:MakesShape a sh:NodeShape ;
    sh:targetSubjectsOf sg:makes ;
    sh:class sg:Company .          # only companies make products

sg:ContainsShape a sh:NodeShape ;
    sh:targetSubjectsOf sg:contains ;
    sh:class sg:Product .          # only products contain parts

sg:ProvenanceShape a sh:NodeShape ;
    sh:targetObjectsOf sg:confidence ;
    sh:datatype xsd:decimal ;
    sh:minInclusive 0.0 ; sh:maxInclusive 1.0 .
```

Every provenance-bearing edge must validate: confidence in [0,1], a non-empty
source, an asOf date, a source record. Run SHACL on each ingest before merging.

## 10. CSV to triples mapping

`nodes.csv` row (`node_id, label, name, stable_id`) -> one node with `rdf:type`
(from `label`) + datatype properties. `edges.csv` row
(`src, rel, dst, source, confidence, as_of, source_record`) -> one object-property
triple, wrapped in an RDF-star annotation carrying source / confidence / asOf /
sourceRecord. A ~30 line converter emits the `.ttl`; the CSVs stay the editable
source, the Turtle is generated.

## 11. Open questions

- Inactive ingredients / excipients: openFDA exposes active substances; inactive
  ingredients arrive as free text, not UNII-coded. Model them later or skip?
- One product, many NDCs: a drug can carry several `product_ndc` values across
  packagings. Mint one Product per NDC (current behavior) or merge to a product
  concept? Defer until a query forces the answer.
- Labeler vs. true manufacturer: `is_original_packager` lets us flag relabelers
  (confidence 0.7), but does not name the contract manufacturer. Out of scope until
  a source provides it.
- Backfill LEIs / Wikidata QIDs for the top labelers before adding a second source.
