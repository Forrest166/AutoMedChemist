from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE_DIR = ROOT / "dist" / "AutoMedChemist_Portable"
DEFAULT_ZIP = ROOT / "AutoMedChemist_Portable.zip"
DEFAULT_MANIFEST = ROOT / "data" / "releases" / "native_portable_package_manifest.json"

INCLUDE_FILES = [
    "AutoMedChemist.exe",
    "run_native_ui.py",
    "run_app.py",
    "README.md",
    "requirements.txt",
    "pyproject.toml",
    "AutoMedChemist_Product_Update.pdf",
    "AutoMedChemist_Product_Update.pptx",
]

INCLUDE_DIRS = [
    "app",
    "src",
    "scripts",
    "data/rules",
    "data/substituents",
    "data/replacements",
    "data/mmp",
    "data/vendor",
    "data/profiles",
    "data/projects/demo",
    "docs/product_update_previews",
]

SKIP_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".db", ".zip"}
SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache"}


def _copy_dir(source: Path, target: Path) -> int:
    count = 0
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        if path.is_dir():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        count += 1
    return count


def _make_writable_and_retry(function, path, excinfo) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        function(path)
    except Exception:
        if isinstance(excinfo, tuple) and len(excinfo) > 1 and isinstance(excinfo[1], BaseException):
            raise excinfo[1]
        if isinstance(excinfo, BaseException):
            raise excinfo
        raise


def _rmtree_with_retry_handler(package_root: Path) -> None:
    try:
        shutil.rmtree(package_root, onexc=_make_writable_and_retry)
    except TypeError:
        shutil.rmtree(package_root, onerror=_make_writable_and_retry)


def _remove_existing_package(package_root: Path) -> None:
    if not package_root.exists():
        return
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            _rmtree_with_retry_handler(package_root)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
            if not package_root.exists():
                return
    if last_error is not None:
        raise last_error


def build_native_portable_package(
    *,
    package_dir: str | Path = DEFAULT_PACKAGE_DIR,
    zip_path: str | Path = DEFAULT_ZIP,
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict:
    package_root = Path(package_dir)
    zip_file = Path(zip_path)
    manifest_file = Path(manifest_path)
    package_root_resolved = package_root.resolve()
    dist_root = (ROOT / "dist").resolve()
    try:
        package_root_resolved.relative_to(dist_root)
    except ValueError as exc:
        raise ValueError("Portable package directory must stay under dist/.")
    _remove_existing_package(package_root)
    package_root.mkdir(parents=True, exist_ok=True)

    copied_files = 0
    missing: list[str] = []
    for rel in INCLUDE_FILES:
        source = ROOT / rel
        if source.exists():
            target = package_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_files += 1
        else:
            missing.append(rel)
    copied_dirs: dict[str, int] = {}
    for rel in INCLUDE_DIRS:
        source = ROOT / rel
        if source.exists():
            count = _copy_dir(source, package_root / rel)
            copied_dirs[rel] = count
            copied_files += count
        else:
            missing.append(rel)

    readme = package_root / "README_NATIVE_PACKAGE.txt"
    readme.write_text(
        "\n".join(
            [
                "AutoMedChemist Portable Native Package",
                "",
                "Launch AutoMedChemist.exe from this folder.",
                "For pipeline actions, keep Python with requirements installed or use the project .venv.",
                "The 4GB localmedchem.sqlite database is intentionally not bundled; keep it in the main workspace data folder when full ring-search data is needed.",
                "This package keeps external operational workflows out of scope.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    copied_files += 1

    if zip_file.exists():
        zip_file.unlink()
    with zipfile.ZipFile(zip_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in package_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(package_root.parent))

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if (package_root / "AutoMedChemist.exe").exists() and zip_file.exists() else "incomplete",
        "package_dir": str(package_root),
        "zip_path": str(zip_file),
        "zip_size_bytes": zip_file.stat().st_size if zip_file.exists() else 0,
        "copied_file_count": copied_files,
        "copied_dirs": copied_dirs,
        "missing": missing,
        "excluded_assets": ["data/localmedchem.sqlite", "data/releases/*", "*.sqlite", "*.zip"],
        "external_python_required_for_pipeline_actions": True,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a lightweight portable native AutoMedChemist package.")
    parser.add_argument("--package-dir", default=str(DEFAULT_PACKAGE_DIR))
    parser.add_argument("--zip-path", default=str(DEFAULT_ZIP))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args()
    manifest = build_native_portable_package(package_dir=args.package_dir, zip_path=args.zip_path, manifest_path=args.manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
