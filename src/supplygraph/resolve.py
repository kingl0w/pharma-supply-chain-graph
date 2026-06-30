"""company + ingredient resolution to stable ids."""
import json
import os
import re

from .config import DATA

# 'doing business as' tail; keep the registered name before it. matches d.b.a., d/b/a/, dba, d b a
_DBA = re.compile(r"\bd\W?b\W?a\b.*$", re.I)

# split a suffix fused at a camelcase seam ("PharmaceuticalsInc"); case-sensitive so "Costco"/"Zinc" survive
_JAMMED_SUFFIX = re.compile(
    r"(?<=[a-z])(?=(?:Inc|Incorporated|LLC|Ltd|Corp|Corporation|PLC|GmbH)\b)"
)

# legal forms only; descriptors (pharmaceuticals, labs) stay, they distinguish the name
_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|gmbh|s\.?a|ag|n\.?v|plc|"
    r"private limited|limited|company)\b",
    re.I,
)

# fallback ids; prefer data/company_ids.json
KNOWN_IDS = {}

_IDS_PATH = os.path.join(DATA, "company_ids.json")


def _load_ids(path=_IDS_PATH):
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items()
            if isinstance(v, str) and v and not k.startswith("_")}


_IDS = _load_ids()


def stable_id_for(company_id, ids=None):
    table = _IDS if ids is None else ids
    return table.get(company_id) or KNOWN_IDS.get(company_id, "")


def resolve_company(name):
    base = _DBA.sub("", name).strip()
    base = re.sub(r"[.,]", "", base)     # before the split: a comma fuses "X,Inc." into "XInc"
    base = _JAMMED_SUFFIX.sub(" ", base)
    base = _SUFFIX.sub("", base)
    base = re.sub(r"\s+", " ", base).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    cid = f"co:{slug}"
    return cid, base or name, stable_id_for(cid)


def resolve_ingredient(substance, unii):
    if unii:
        return f"unii:{unii}", 1.0
    slug = re.sub(r"[^a-z0-9]+", "-", substance.lower()).strip("-")
    return f"sub:{slug}", 0.8
