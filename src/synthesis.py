from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_SYNTHESIS_ROUTES_PATH = Path(__file__).resolve().parents[2] / "data" / "vendor" / "synthesis_route_templates.yaml"


def load_synthesis_routes(path: str | Path | None = None) -> list[dict]:
    route_path = Path(path) if path is not None else DEFAULT_SYNTHESIS_ROUTES_PATH
    if not route_path.exists():
        return []
    with route_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("routes") or [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported synthesis route shape: {route_path}")


def match_synthesis_routes(substituent: dict, site_type: str | None, routes: list[dict]) -> list[dict]:
    classes = set(substituent.get("class") or [])
    direction_tags = set(substituent.get("direction_tags") or [])
    risk_tags = set((substituent.get("risk") or {}).get("risk_tags") or [])
    matches = []
    for route in routes:
        route_classes = set(route.get("match_classes") or [])
        route_directions = set(route.get("match_direction_tags") or [])
        route_sites = set(route.get("match_site_types") or [])
        blocked_risks = set(route.get("blocked_risk_tags") or [])
        if route_classes and not classes.intersection(route_classes):
            continue
        if route_directions and not direction_tags.intersection(route_directions):
            continue
        if route_sites and site_type and site_type not in route_sites:
            continue
        score = float(route.get("score", 50.0))
        if risk_tags.intersection(blocked_risks):
            score -= 20.0
        matches.append({**route, "matched_score": max(0.0, min(100.0, score))})
    matches.sort(key=lambda row: row.get("matched_score", 0.0), reverse=True)
    return matches


def score_synthesis_route(substituent: dict, site_type: str | None, routes: list[dict]) -> float | None:
    matches = match_synthesis_routes(substituent, site_type, routes)
    if not matches:
        return None
    return float(matches[0]["matched_score"])


def route_summary(substituent: dict, site_type: str | None, routes: list[dict]) -> dict | None:
    matches = match_synthesis_routes(substituent, site_type, routes)
    if not matches:
        return None
    top = matches[0]
    return {
        "template_id": top.get("template_id"),
        "name": top.get("name"),
        "routine_level": top.get("routine_level"),
        "route_confidence": top.get("route_confidence"),
        "score": top.get("matched_score"),
        "notes": top.get("notes"),
    }


def validate_synthesis_routes(routes: list[dict]) -> dict:
    issues = []
    seen = set()
    for route in routes:
        template_id = route.get("template_id")
        if not template_id:
            issues.append({"severity": "error", "check": "route_template_id", "message": "Missing template_id", "item_id": None})
        elif template_id in seen:
            issues.append({"severity": "error", "check": "route_duplicate_id", "message": "Duplicate template_id", "item_id": template_id})
        seen.add(template_id)
        for field in ["name", "routine_level", "score"]:
            if route.get(field) in {None, ""}:
                issues.append({"severity": "error", "check": "route_required_field", "message": f"Missing {field}", "item_id": template_id})
        try:
            score = float(route.get("score"))
            if score < 0 or score > 100:
                issues.append({"severity": "error", "check": "route_score_range", "message": "score must be between 0 and 100", "item_id": template_id})
        except (TypeError, ValueError):
            issues.append({"severity": "error", "check": "route_score_numeric", "message": "score must be numeric", "item_id": template_id})
    return {
        "route_count": len(routes),
        "error_count": sum(1 for issue in issues if issue["severity"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
        "issues": issues,
    }

