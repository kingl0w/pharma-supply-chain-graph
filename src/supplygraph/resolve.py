"""Entity resolution. The make-or-break component.

Companies: normalize the labeler string to a stable slug id, then resolve to an
authoritative external id (LEI or Wikidata QID) via a local mapping file.
Ingredients: UNII is already a stable government identifier, so resolution is
near-free; fall back to a name slug.
"""
import json
import os
import re

from .config import DATA

# 'doing business as' alias tail. Real pulls use many separators: d.b.a., d/b/a/,
# "dba", "d b a". \W? lets one non-word char (dot, slash, space) sit between the
# letters. We KEEP the registered name BEFORE the alias (the legal entity) and drop
# everything from the d/b/a onward: "Conopco d/b/a/ Unilever" -> "Conopco".
_DBA = re.compile(r"\bd\W?b\W?a\b.*$", re.I)

# Incorporation suffix fused onto the previous word at a camelCase seam, e.g.
# "PharmaceuticalsInc" (often produced when a "Pharmaceuticals,Inc." comma is
# stripped). Case-sensitive, with a lowercase->Uppercase boundary, so we split only
# a real seam and never a name that merely ends in the letters ("Costco", "Zinc").
# Only the unambiguous incorporation tokens belong here.
_JAMMED_SUFFIX = re.compile(
    r"(?<=[a-z])(?=(?:Inc|Incorporated|LLC|Ltd|Corp|Corporation|PLC|GmbH)\b)"
)

# Legal-entity / incorporation forms only. Industry descriptors (pharmaceuticals,
# laboratories, labs) are deliberately NOT here: they distinguish the name
# ("NuCare Pharmaceuticals" != a bare "NuCare"), they are not a legal suffix.
_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|gmbh|s\.?a|ag|n\.?v|plc|"
    r"private limited|limited|company)\b",
    re.I,
)

# In-code fallback ids. Prefer data/company_ids.json for new entries.
KNOWN_IDS = {
    # "co:pfizer": "765980TFWHQUEX7C5293",   # example LEI
}

_IDS_PATH = os.path.join(DATA, "company_ids.json")


def _load_ids(path=_IDS_PATH):
    """Load co:<slug> -> authoritative id from the mapping file. Keys starting with
    '_' are documentation and ignored; non-string values are dropped. Missing or
    invalid file => empty mapping (the pipeline still runs, just without ids)."""
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items()
            if isinstance(v, str) and v and not k.startswith("_")}


_IDS = _load_ids()


def stable_id_for(company_id, ids=None):
    """Authoritative external id (LEI or Wikidata QID) for a resolved company id,
    or '' when unknown. File mapping wins; falls back to in-code KNOWN_IDS."""
    table = _IDS if ids is None else ids
    return table.get(company_id) or KNOWN_IDS.get(company_id, "")


def resolve_company(name):
    """Return (company_id, clean_name, stable_id)."""
    base = _DBA.sub("", name).strip()            # drop 'd/b/a ...' alias tail
    # Strip punctuation BEFORE the jam-splitter: a comma with no following space
    # ("Pharmaceuticals,Inc.") otherwise fuses into "PharmaceuticalsInc" only AFTER
    # the splitter ran, hiding the seam. Order matters here.
    base = re.sub(r"[.,]", "", base)
    base = _JAMMED_SUFFIX.sub(" ", base)         # "PharmaceuticalsInc" -> "Pharmaceuticals Inc"
    base = _SUFFIX.sub("", base)
    base = re.sub(r"\s+", " ", base).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    cid = f"co:{slug}"
    return cid, base or name, stable_id_for(cid)


def resolve_ingredient(substance, unii):
    """Return (part_id, confidence). UNII present => authoritative => 1.0."""
    if unii:
        return f"unii:{unii}", 1.0
    slug = re.sub(r"[^a-z0-9]+", "-", substance.lower()).strip("-")
    return f"sub:{slug}", 0.8
