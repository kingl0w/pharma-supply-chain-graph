# Data Sourcing Architecture v0.1

How the supply graph acquires, normalizes, resolves, and provenances data in a
production-grade way. The hand-entered iPhone 16 Pro seed was schema validation
scaffolding. This subsystem replaces it. Manual entry becomes just one connector
among many.

## 1. Principle

Sourcing is a standing subsystem, not a one-time import. Every fact in the graph
must trace back to a retained source record, an extraction run, and a timestamp,
so any triple can be re-derived, audited, or invalidated when a source changes.
Provenance is not a column. It is the backbone.

## 2. Source registry (config as data)

Each source is a declarative record: id, tier, license, format, access method,
refresh cadence, coverage, and a trust weight that feeds edge confidence. New
sources are added as config, not code paths.

### Tier A: free, structured, authoritative. Build these first.

| Source | What it gives | License | Notes |
|--------|---------------|---------|-------|
| GLEIF (LEI) | Canonical legal entity ids + hierarchy | Open / CC0 | The backbone for entity resolution. |
| Wikidata | Company/product/part nodes, manufacturer (P176), has part(s) (P527), made from material (P186) | CC0 | Seeds nodes + stable QIDs, SPARQL endpoint. |
| SEC EDGAR | 10-K customer concentration (>~10% revenue), Risk Factors, conflict minerals (Form SD) | Public domain | Free full-text search + API. Buyer/supplier edges from filings. |
| Vendor supplier lists | Direct tier-1 suppliers + factory locations | Published PDF (facts) | Apple publishes its top 200 suppliers, ~98% of direct spend, with locations. Others publish similar. |
| FCC filings | Device internal photos / IDs at launch | Public domain | Useful for part identification corroboration. |

### Tier B: free, unstructured. Scrape with care, check license per source.

| Source | What it gives | License caution |
|--------|---------------|-----------------|
| iFixit teardowns | Die-marking part identification | Creative Commons, noncommercial. Verify before any commercial use. |
| Earnings call transcripts / PR | Design wins, named partnerships | Source-dependent. Quote sparingly, store facts not text. |
| Trade press | Supplier changes, qualification news | Source-dependent. |

### Tier C: commercial, licensed. Evaluate only if the product justifies the cost.

| Source | What it gives | Reality |
|--------|---------------|---------|
| S&P Panjiva | ~2B shipment records, ~9M companies, bill-of-lading buyer/supplier edges from US CBP + ~20 countries | Licensed. Cannot redistribute raw. Most literal supplier->buyer signal for physical goods. |
| Bloomberg SPLC | ~900k supply chain relationships, ~200k quantified with revenue/cost % | Terminal-gated. Built from filings, transcripts, analyst estimates. |
| Z2Data / SiliconExpert | Part-level: 1B+ parts, 150k+ suppliers, compliance (RoHS, REACH, conflict minerals) | Licensed. Strong for the part tier and obsolescence/risk. |
| TechInsights | Deep teardown BOMs | Paid, proprietary. The gold standard for full BOMs. |
| ImportGenius / ImportYeti | Bill-of-lading access, lower cost tiers | Coverage and terms vary; ImportYeti has had a free tier. |

## 3. The licensing distinction that drives design

Bills of lading are public record, but the aggregated databases built on them
(Panjiva and similar) are licensed and cannot be redistributed. Facts are not
copyrightable, but a specific compilation or PDF can be. Practical rule:

- Tier A: ingest and redistribute freely.
- Tier B: extract facts, store provenance, do not republish source text; confirm
  noncommercial-only sources stay internal if the product is commercial.
- Tier C: use under license, store derived facts with a source reference, never
  expose raw licensed records downstream.

This is why the canonical store holds facts plus a source pointer, not source
copies, for anything past Tier A.

## 4. Pipeline

```
 source registry
       |
  [connector]      per-source extract, isolated, idempotent
       |
  landing zone     raw, immutable, append-only (bronze)
       |           original bytes + fetch metadata, partitioned by source+date
  [parser]         source-specific -> canonical staging claim
       |
  staging          {claim_type, subject_raw, object_raw, fields, source_ref} (silver)
       |
  [entity resolution]  subject/object strings -> canonical entity ids
       |               blocking -> candidate scoring -> auto-merge | review queue
  [ontology mapping]   claim -> RDF-star triples, aligned to schema.org/Wikidata
       |
  [SHACL gate]     validate; quarantine failures
       |
  curated store    Fuseki / TDB2, queryable (gold)
       |
  lineage graph    PROV-O: each triple -> extraction activity -> source record
```

Run mode is batch on a per-source cadence, not streaming. Supply relationships
change on the order of months, so scheduled incremental refresh is correct and far
simpler to operate. Each connector is idempotent and re-runnable.

## 5. Entity resolution (the make-or-break component)

A dedicated service, not an afterthought. Canonical entity registry keyed on LEI
where available, Wikidata QID otherwise. Pipeline per incoming entity string:

1. Normalize (legal suffixes, casing, transliteration).
2. Block on cheap keys (name prefix, country, ticker) to limit comparisons.
3. Score candidates (string similarity + attribute agreement).
4. Auto-merge above a high threshold, send mid-confidence to a review queue,
   create a new node below.
5. Record the resolution decision and its evidence in lineage.

"Bosch", "Robert Bosch GmbH", and "Bosch Sensortec" must converge to the right
nodes, with the subsidiary relationship preserved, not flattened. Getting this
wrong silently corrupts every downstream query, so it is gated and reviewable.

## 6. Conflict resolution and confidence

Sources will disagree. Do not overwrite. Keep every assertion with its own
provenance, and compute a canonical view by combining source trust weight with
extraction certainty. When a teardown die marking (high) contradicts a press
release (low), the graph holds both and the canonical answer follows the weighted
score. Disagreement is queryable, not hidden.

Confidence scale stays as defined in SCHEMA.md section 8. Source trust weight is a
registry property, so re-weighting a source is a config change that re-scores its
edges on next build.

## 7. Provenance and lineage

Adopt PROV-O. Every curated triple links to a `prov:Activity` (the extraction run,
with code version and timestamp) and a `prov:Entity` (the retained source record).
This makes three things possible: audit ("why does the graph claim this"),
re-derivation (rebuild gold from bronze after a parser fix), and invalidation
(retract everything from a source found to be wrong).

## 8. Observability

Per source: freshness against an SLA, records ingested, extraction error rate,
share of entities auto-resolved vs queued. Graph-level: node/edge counts, coverage
by product and by part tier, fraction of edges at each confidence level. These are
queries against the lineage graph, so the monitoring is data, not bolted-on.

## 9. Build order

1. Stand up landing zone + lineage + one Tier A connector end to end (Wikidata or
   GLEIF), proving the whole pipeline on the easiest legal source.
2. Add SEC EDGAR and vendor supplier lists. Now you have free, authoritative,
   redistributable buyer/supplier and tier-1 edges.
3. Add iFixit teardown extraction for the part tier, license-checked.
4. Only then evaluate a Tier C commercial source, justified by a concrete gap the
   free tiers cannot fill (deep BOMs, shipment-level buyer/supplier).

The seed connector (manual CSV) stays valid throughout as the Tier B fallback for
facts no automated source yet covers.

## 10. Open questions

- Hosting the landing zone on Hserver1 (object storage or just partitioned disk)
  vs external. Volume is small until Tier C.
- Entity resolution review queue: build minimal UI, or CLI-driven approve/reject
  to start. CLI first.
- Whether to model PROV lineage in the same triple store or a separate graph.
