from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


def _load_manifest(path: str | Path) -> dict:
    p = Path(path)
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as archive:
            return json.loads(archive.read("release_bundle_manifest.json").decode("utf-8"))
    return json.loads(p.read_text(encoding="utf-8"))


def compare_manifests(base: dict, head: dict) -> dict:
    base_files = {item["path"]: item for item in base.get("files", [])}
    head_files = {item["path"]: item for item in head.get("files", [])}
    added = sorted(set(head_files) - set(base_files))
    removed = sorted(set(base_files) - set(head_files))
    changed = sorted(path for path in set(base_files).intersection(head_files) if base_files[path].get("sha256") != head_files[path].get("sha256"))
    risk_level = "high" if removed else "medium" if len(changed) > 75 or len(added) > 25 else "low"
    return {
        "base_created_at": base.get("created_at"),
        "head_created_at": head.get("created_at"),
        "base_file_count": len(base_files),
        "head_file_count": len(head_files),
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "risk_level": risk_level,
        "added": added,
        "removed": removed,
        "changed": [
            {
                "path": path,
                "base_size_bytes": base_files[path].get("size_bytes"),
                "head_size_bytes": head_files[path].get("size_bytes"),
                "base_sha256": base_files[path].get("sha256"),
                "head_sha256": head_files[path].get("sha256"),
            }
            for path in changed
        ],
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Release Manifest Diff",
        "",
        f"- Base created at: `{report.get('base_created_at')}`",
        f"- Head created at: `{report.get('head_created_at')}`",
        f"- Risk level: `{report.get('risk_level')}`",
        f"- Added: `{report.get('added_count')}`",
        f"- Changed: `{report.get('changed_count')}`",
        f"- Removed: `{report.get('removed_count')}`",
        "",
    ]
    for key in ["added", "removed"]:
        if report.get(key):
            lines.extend([f"## {key.title()}", ""])
            for path in report[key][:100]:
                lines.append(f"- `{path}`")
            lines.append("")
    if report.get("changed"):
        lines.extend(["## Changed", ""])
        for row in report["changed"][:100]:
            lines.append(f"- `{row.get('path')}`")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two LocalMedChem release bundle manifests or zip bundles.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--markdown-out", default=None)
    args = parser.parse_args()
    report = compare_manifests(_load_manifest(args.base), _load_manifest(args.head))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.markdown_out:
        out = Path(args.markdown_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
