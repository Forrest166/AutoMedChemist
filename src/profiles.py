from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_PROFILE_DIR = Path(__file__).resolve().parents[2] / "data" / "profiles"


def load_scoring_profile(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def list_scoring_profiles(profile_dir: str | Path | None = None) -> list[dict]:
    directory = Path(profile_dir) if profile_dir is not None else DEFAULT_PROFILE_DIR
    if not directory.exists():
        return []
    profiles = []
    for path in sorted(directory.rglob("*.yaml")):
        profile = load_scoring_profile(path)
        if isinstance(profile.get("profiles"), list):
            for item in profile.get("profiles") or []:
                if isinstance(item, dict) and item.get("profile_id"):
                    item = dict(item)
                    item["_path"] = str(path)
                    profiles.append(item)
            continue
        if not profile.get("profile_id"):
            continue
        profile["_path"] = str(path)
        profiles.append(profile)
    return profiles


def profile_weights(profile: dict | None) -> dict:
    return dict((profile or {}).get("score_weights") or {})
