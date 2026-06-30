"""paths, source registry, ontology vocab iri."""
import os

API_LABEL = "https://api.fda.gov/drug/label.json"
PAGE_SIZE = 100                      # openfda caps limit at 100
SOURCE_NAME = "openFDA drug label"
SOURCE_LICENSE = "https://open.fda.gov/license/"
TRUST_WEIGHT = 0.95

VOCAB = "https://w3id.org/supplygraph/schema#"

# src/supplygraph/config.py -> repo root is 3 levels up
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
LANDING_DIR = os.path.join(DATA, "landing")   # raw, immutable
OUT_DIR = os.path.join(DATA, "out")           # generated
