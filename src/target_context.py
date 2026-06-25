from __future__ import annotations

import re


TARGET_FAMILY_ALIASES = {
    "protein kinase": "kinase",
    "tyrosine kinase": "kinase",
    "serine threonine kinase": "kinase",
    "serine/threonine kinase": "kinase",
    "gpcr": "gpcr",
    "g protein coupled receptor": "gpcr",
    "g-protein-coupled receptor": "gpcr",
    "ion channel": "ion_channel",
    "nuclear receptor": "nuclear_receptor",
    "protease": "protease",
    "peptidase": "protease",
    "transporter": "transporter",
    "cytochrome p450": "cyp",
    "cyp450": "cyp",
    "phosphodiesterase": "pde",
}

TARGET_FAMILY_PATTERNS = [
    (re.compile(r"\bkinase\b", re.I), "kinase"),
    (re.compile(r"\b(gpcr|g[\s-]?protein[\s-]?coupled receptor)\b", re.I), "gpcr"),
    (re.compile(r"\bion channel\b|\bchannel\b", re.I), "ion_channel"),
    (re.compile(r"\bnuclear receptor\b|\breceptor\b", re.I), "receptor"),
    (re.compile(r"\bprotease\b|\bpeptidase\b", re.I), "protease"),
    (re.compile(r"\btransporter\b", re.I), "transporter"),
    (re.compile(r"\bcytochrome p450\b|\bcyp\d", re.I), "cyp"),
    (re.compile(r"\bphosphodiesterase\b|\bpde\d", re.I), "pde"),
    (re.compile(r"\bhdac\b|histone deacetylase", re.I), "hdac"),
    (re.compile(r"\bbromodomain\b|\bbrd\d", re.I), "bromodomain"),
]

ASSAY_TYPE_ALIASES = {
    "pIC50": "IC50",
    "IC 50": "IC50",
    "EC 50": "EC50",
    "Ki": "KI",
    "Kd": "KD",
    "MIC90": "MIC90",
    "MIC50": "MIC50",
}

ENDPOINT_ALIASES = {
    "activity": "potency",
    "bioactivity": "potency",
    "ic50": "potency",
    "ec50": "potency",
    "ki": "potency",
    "kd": "potency",
    "mic": "antibacterial_potency",
    "mic50": "antibacterial_potency",
    "mic90": "antibacterial_potency",
    "clearance": "metabolic_stability",
    "clint": "metabolic_stability",
    "microsomal stability": "metabolic_stability",
    "hLM": "metabolic_stability",
    "solubility": "solubility",
    "logd": "lipophilicity",
    "logp": "lipophilicity",
    "permeability": "permeability",
    "efflux": "permeability",
}


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def _slug(value: str | None) -> str | None:
    text = _compact(value)
    if not text:
        return None
    return re.sub(r"\s+", "_", text)


def normalize_target_family(value: str | None) -> str | None:
    text = _compact(value)
    if not text:
        return None
    left = text.split("|", 1)[0].strip()
    if left in TARGET_FAMILY_ALIASES:
        return TARGET_FAMILY_ALIASES[left]
    for pattern, family in TARGET_FAMILY_PATTERNS:
        if pattern.search(left):
            return family
    if left.startswith("chembl"):
        return left.upper()
    return _slug(left)


def normalize_assay_type(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text in ASSAY_TYPE_ALIASES:
        return ASSAY_TYPE_ALIASES[text]
    compact = re.sub(r"[^a-zA-Z0-9]+", "", text).upper()
    return ASSAY_TYPE_ALIASES.get(compact, compact)


def normalize_endpoint_group(
    value: str | None,
    *,
    assay_type: str | None = None,
    assay_name: str | None = None,
) -> str | None:
    for raw in [value, assay_type, assay_name]:
        text = _compact(raw)
        if not text:
            continue
        if text in ENDPOINT_ALIASES:
            return ENDPOINT_ALIASES[text]
        for key, endpoint in ENDPOINT_ALIASES.items():
            if key in text:
                return endpoint
    return _slug(value) or _slug(assay_type) or _slug(assay_name)


def standardize_target_context(context: dict | None) -> dict:
    context = context or {}
    target_family_raw = context.get("target_family")
    assay_type_raw = context.get("assay_type") or context.get("standard_type")
    endpoint_raw = context.get("endpoint_group") or context.get("endpoint")
    assay_name = context.get("assay_name")
    target_family = normalize_target_family(target_family_raw)
    assay_type = normalize_assay_type(assay_type_raw)
    endpoint_group = normalize_endpoint_group(endpoint_raw, assay_type=assay_type, assay_name=assay_name)
    return {
        **context,
        "target_family_raw": target_family_raw,
        "assay_type_raw": assay_type_raw,
        "endpoint_group_raw": endpoint_raw,
        "target_family": target_family or "",
        "assay_type": assay_type or "",
        "endpoint_group": endpoint_group or "",
    }
