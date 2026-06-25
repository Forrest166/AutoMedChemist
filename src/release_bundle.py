from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_RELEASE_PATTERNS = [
    "README.md",
    "run_app.py",
    "app/*.py",
    "src/localmedchem/*.py",
    "scripts/*.py",
    "docs/*.md",
    "dist/*.ps1",
    "dist/*.bat",
    "dist/tasks/*",
    "data/localmedchem.sqlite",
    "data/rules/*.yaml",
    "data/vendor/*.yaml",
    "data/vendor/*.csv",
    "data/mmp/*.yaml",
    "data/seeds/*.yaml",
    "data/replacements/*.yaml",
    "data/replacements/*.csv",
    "data/rings/*.yaml",
    "data/substituents/*.yaml",
    "data/substituents/*.json",
    "data/substituents/*.md",
    "data/substituents/*.csv",
    "data/releases/*.json",
    "data/releases/*.md",
    "data/releases/*.sha256",
    "data/projects/demo/*.json",
    "data/projects/demo/*.csv",
    "data/projects/demo/*.md",
    "data/projects/demo/*.sdf",
    "data/projects/demo/route_batches/*.json",
    "data/projects/demo/route_batches/*.csv",
    "data/projects/demo/ci_default/*.csv",
    "data/projects/demo/ci_default/*.sdf",
    "data/projects/demo/ci_default/route_batches/*.json",
    "data/projects/demo/ci_default/route_batches/*.csv",
    "data/projects/demo/ci_basic_amine/*.csv",
    "data/projects/demo/ci_basic_amine/*.sdf",
    "data/projects/demo/ci_basic_amine/route_batches/*.json",
    "data/projects/demo/ci_basic_amine/route_batches/*.csv",
    "data/profiles/*.yaml",
    "data/profiles/calibrated/*.yaml",
]


def _is_post_bundle_checksum_artifact(root_path: Path, path: Path) -> bool:
    rel = path.relative_to(root_path).as_posix()
    return rel == "data/releases/latest_release_checksum.json" or (
        rel.startswith("data/releases/localmedchem_release_") and rel.endswith(".zip.sha256")
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_release_files(root: str | Path, patterns: list[str] | None = None) -> list[Path]:
    root_path = Path(root).resolve()
    files = []
    seen = set()
    for pattern in patterns or DEFAULT_RELEASE_PATTERNS:
        for path in root_path.glob(pattern):
            if not path.is_file():
                continue
            if _is_post_bundle_checksum_artifact(root_path, path.resolve()):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files, key=lambda path: path.as_posix())


def create_release_bundle(
    root: str | Path,
    output_zip: str | Path,
    *,
    patterns: list[str] | None = None,
    extra_metadata: dict | None = None,
) -> dict:
    root_path = Path(root).resolve()
    out_path = Path(output_zip)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    files = collect_release_files(root_path, patterns=patterns)
    created_at = datetime.now(timezone.utc).isoformat()
    manifest_files = []
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            rel = path.resolve().relative_to(root_path).as_posix()
            archive.write(path, rel)
            manifest_files.append(
                {
                    "path": rel,
                    "size_bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
        manifest = {
            "created_at": created_at,
            "file_count": len(manifest_files),
            "files": manifest_files,
            "metadata": extra_metadata or {},
        }
        archive.writestr("release_bundle_manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return {
        "created_at": created_at,
        "bundle_path": str(out_path.resolve()),
        "bundle_sha256": file_sha256(out_path),
        "bundle_size_bytes": out_path.stat().st_size,
        "file_count": len(manifest_files),
        "files": manifest_files,
        "metadata": extra_metadata or {},
    }


def write_release_bundle_checksum(bundle_path: str | Path, output_path: str | Path | None = None) -> dict:
    bundle = Path(bundle_path)
    digest = file_sha256(bundle)
    out = Path(output_path) if output_path is not None else bundle.with_suffix(bundle.suffix + ".sha256")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"{digest}  {bundle.name}\n", encoding="utf-8")
    return {
        "bundle_path": str(bundle.resolve()),
        "checksum_path": str(out.resolve()),
        "sha256": digest,
        "algorithm": "sha256",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def write_latest_release_checksum_report(bundle_path: str | Path, output_path: str | Path | None = None) -> dict:
    bundle = Path(bundle_path)
    report = write_release_bundle_checksum(bundle)
    out = Path(output_path) if output_path is not None else bundle.parent / "latest_release_checksum.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def verify_release_bundle(bundle_path: str | Path, extract_dir: str | Path | None = None) -> dict:
    bundle = Path(bundle_path)
    target_dir = Path(extract_dir) if extract_dir is not None else bundle.with_suffix("")
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(target_dir)
    manifest_path = target_dir / "release_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    issues = []
    for item in manifest.get("files", []):
        path = target_dir / item["path"]
        if not path.exists():
            issues.append({"path": item["path"], "message": "missing"})
            continue
        digest = file_sha256(path)
        if digest != item.get("sha256"):
            issues.append({"path": item["path"], "message": "sha256_mismatch"})
    return {
        "bundle_path": str(bundle.resolve()),
        "bundle_sha256": file_sha256(bundle),
        "extract_dir": str(target_dir.resolve()),
        "file_count": manifest.get("file_count"),
        "verified_count": (manifest.get("file_count") or 0) - len(issues),
        "ok": not issues,
        "issues": issues,
    }


def write_release_bundle_report(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
