"""Central config: paths, the source registry entry, and the ontology vocab IRI."""
import os

# --- source registry (one entry; add more connectors the same way) ---
API_LABEL = "https://api.fda.gov/drug/label.json"
PAGE_SIZE = 100                      # openFDA hard-caps limit at 100 per request
SOURCE_NAME = "openFDA drug label"
SOURCE_LICENSE = "https://open.fda.gov/license/"   # public, redistributable
TRUST_WEIGHT = 0.95                  # authoritative regulatory submission

# --- ontology namespace (terms map to schema.org in the JSON-LD context) ---
VOCAB = "https://w3id.org/supplygraph/schema#"

# --- paths ---
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LANDING_DIR = os.path.join(DATA, "landing")   # raw, immutable (bronze)
OUT_DIR = os.path.join(DATA, "out")           # neutral output (gold)
