from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


SOURCES = {
    "ertl_ring_replacements": "https://peter-ertl.com/molecular/data/rrr-data.txt",
    "ertl_natural_product_substituents": "https://peter-ertl.com/molecular/data/npsubstituents.txt",
    "ertl_4m_rings": "https://peter-ertl.com/molecular/data/rings.zip",
    "bajorath_top500_r_replacements": "https://zenodo.org/records/4741973/files/top500_R_replacements.xml?download=1",
    "bajorath_rgroup_readme": "https://zenodo.org/records/4741973/files/readme.txt?download=1",
    "shearer_drug_rings": "https://zenodo.org/api/records/6556752/files/full-drug-ring-download-2020-rich-taylor.txt/content",
    "shearer_clinical_rings": "https://zenodo.org/api/records/6556752/files/full-clinical-ring-download-2020-rich-taylor.txt/content",
}


FILENAMES = {
    "ertl_ring_replacements": "ertl_ring_replacements_rrr_data.txt",
    "ertl_natural_product_substituents": "ertl_natural_product_substituents.txt",
    "ertl_4m_rings": "ertl_4m_rings.zip",
    "bajorath_top500_r_replacements": "bajorath_top500_R_replacements.xml",
    "bajorath_rgroup_readme": "bajorath_rgroup_readme.txt",
    "shearer_drug_rings": "shearer_drug_ring_systems_2020.txt",
    "shearer_clinical_rings": "shearer_clinical_ring_systems_2020.txt",
}


def download(url: str, path: Path, force: bool = False, timeout: float = 90.0) -> dict:
    if path.exists() and not force:
        return {"path": str(path.resolve()), "url": url, "status": "cached", "size_bytes": path.stat().st_size}
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "AutoMedChemist/0.3"})
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return {
        "path": str(path.resolve()),
        "url": url,
        "status": "downloaded",
        "status_code": response.status_code,
        "size_bytes": len(response.content),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Download literature-backed ring, substituent, and R-group source files.")
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "raw" / "literature"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    results = []
    for key, url in SOURCES.items():
        results.append(download(url, out_dir / FILENAMES[key], force=args.force))

    report = {
        "download_count": len(results),
        "outputs": results,
    }
    report_path = out_dir / "literature_structure_download_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

