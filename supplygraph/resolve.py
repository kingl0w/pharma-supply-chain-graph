"""Entity resolution. The make-or-break component.

Companies: normalize the labeler string to a stable slug id, and (TODO) resolve to
an authoritative LEI or Wikidata QID. Ingredients: UNII is already a stable
government identifier, so resolution is near-free; fall back to a name slug.
"""
import re

_DBA = re.compile(r"\b(d\.?b\.?a\.?|dba)\b.*$", re.I)
_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|gmbh|s\.?a|ag|n\.?v|plc|"
    r"private limited|limited|company|pharmaceuticals?|laboratories|labs)\b",
    re.I,
)

# Plug authoritative ids here as you resolve the biggest labelers.
# key = resolved company id, value = LEI or Wikidata QID string.
KNOWN_IDS = {
    # "co:pfizer": "765980TFWHQUEX7C5293",   # example LEI
}


def resolve_company(name):
    """Return (company_id, clean_name, stable_id)."""
    base = _DBA.sub("", name).strip()           # drop 'd.b.a. ...' alias tail
    base = re.sub(r"[.,]", "", base)
    base = _SUFFIX.sub("", base)
    base = re.sub(r"\s+", " ", base).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    cid = f"co:{slug}"
    return cid, base or name, KNOWN_IDS.get(cid, "")


def resolve_ingredient(substance, unii):
    """Return (part_id, confidence). UNII present => authoritative => 1.0."""
    if unii:
        return f"unii:{unii}", 1.0
    slug = re.sub(r"[^a-z0-9]+", "-", substance.lower()).strip("-")
    return f"sub:{slug}", 0.8
