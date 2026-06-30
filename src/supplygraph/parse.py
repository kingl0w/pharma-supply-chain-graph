"""raw openfda record -> nodes + provenanced edges."""
from .config import SOURCE_NAME
from .resolve import resolve_company, resolve_ingredient


def _first(d, k):
    v = d.get(k)
    return v[0] if isinstance(v, list) and v else None


def claims_from(rec):
    o = rec.get("openfda") or {}
    ndc = _first(o, "product_ndc")
    maker = _first(o, "manufacturer_name")
    if not ndc or not maker:
        return {}, []

    name = _first(o, "brand_name") or _first(o, "generic_name") or ndc
    spl = _first(o, "spl_id") or rec.get("id") or ""
    as_of = rec.get("effective_time") or ""
    is_orig = bool((o.get("is_original_packager") or [False])[0])

    cid, cname, cstable = resolve_company(maker)
    prod = f"ndc:{ndc}"
    nodes = {cid: ("Company", cname, cstable), prod: ("Product", name, "")}

    make_conf = 0.9 if is_orig else 0.7   # lower when not the original packager
    edges = [(cid, "MAKES", prod, SOURCE_NAME, make_conf, as_of, spl)]

    subs = o.get("substance_name") or []
    uniis = o.get("unii") or []
    for i, sub in enumerate(subs):
        uid = uniis[i] if i < len(uniis) else None
        pid, conf = resolve_ingredient(sub, uid)
        nodes[pid] = ("Part", sub, uid or "")
        edges.append((prod, "CONTAINS", pid, SOURCE_NAME, conf, as_of, spl))

    return nodes, edges
