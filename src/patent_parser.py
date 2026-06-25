from __future__ import annotations

import re

from .chemistry import canonicalize_smiles
from .ingestion import candidate_id_for, infer_classes, infer_connection_type, infer_direction_tags, infer_property_tags, infer_risk


SMILES_TOKEN_RE = re.compile(r"(?P<smiles>\[\*:1\][A-Za-z0-9@+\-\[\]\(\)=#$\\/%.]+)")


def _candidate_from_smiles(smiles: str, source_name: str, source_record_id: str | None = None) -> dict | None:
    try:
        canonical = canonicalize_smiles(smiles)
    except Exception:
        return None
    connection_type = infer_connection_type(smiles)
    name = f"Patent parsed motif {canonical}"
    classes = infer_classes(name, smiles, connection_type)
    risk = infer_risk(name, smiles, classes)
    if any(token in canonical for token in ["C=C", "C#C", "CCl"]):
        risk_tags = set(risk.get("risk_tags") or [])
        risk_tags.update({"reactive_alert", "advanced_only"})
        risk["risk_tags"] = sorted(risk_tags)
        risk["default_enabled"] = False
    advanced = "advanced_only" in set(risk.get("risk_tags") or [])
    return {
        "candidate_id": candidate_id_for(canonical, "surechembl_parsed"),
        "name": name,
        "short_name": canonical,
        "smiles": smiles,
        "canonical_smiles": canonical,
        "source_type": "surechembl_parsed",
        "source_name": source_name,
        "source_record_id": source_record_id or canonical,
        "reference": "https://www.api.surechembl.org/",
        "connection_type": connection_type,
        "class": classes,
        "direction_tags": infer_direction_tags(smiles, classes),
        "property_tags": infer_property_tags(smiles, classes),
        "risk": risk,
        "priority": {
            "mvp": not advanced,
            "common_medchem": not advanced,
            "advanced_only": advanced,
            "default_rank": 155 if advanced else 125,
        },
        "candidate_status": "staged",
        "review_tier": "advanced_only" if advanced else "needs_medchem_review",
    }


def extract_surechembl_candidates(payloads: list[dict]) -> list[dict]:
    candidates: dict[str, dict] = {}
    for payload in payloads:
        source_name = str(payload.get("source_name") or "SureChEMBL")
        source_record_id = str(payload.get("schembl_id") or payload.get("id") or payload.get("source_record_id") or "")
        explicit = payload.get("candidates") or payload.get("compounds") or []
        for item in explicit:
            if isinstance(item, dict) and item.get("smiles"):
                smiles = item["smiles"]
                if "[*:1]" not in smiles:
                    continue
                candidate = _candidate_from_smiles(smiles, source_name, str(item.get("id") or source_record_id or smiles))
                if candidate:
                    candidate.update({key: value for key, value in item.items() if key not in candidate and value is not None})
                    candidates[candidate["candidate_id"]] = candidate
        text = "\n".join(str(payload.get(key) or "") for key in ["text_preview", "abstract", "description", "claims", "payload_text"])
        for match in SMILES_TOKEN_RE.finditer(text):
            candidate = _candidate_from_smiles(match.group("smiles"), source_name, source_record_id or "text_preview")
            if candidate:
                candidates[candidate["candidate_id"]] = candidate
    return list(candidates.values())

