from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import initialize_database, insert_api_health_checks  # noqa: E402


DEFAULT_ENDPOINTS = [
    {
        "source_name": "PubChem PUG-REST",
        "endpoint_url": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/aspirin/cids/JSON",
        "verify": True,
    },
    {
        "source_name": "ChEMBL",
        "endpoint_url": "https://www.ebi.ac.uk/chembl/api/data/molecule.json?limit=1",
        "verify": True,
    },
    {
        "source_name": "SureChEMBL",
        "endpoint_url": "https://www.surechembl.org/",
        "verify": True,
    },
]


def check_id(source_name: str, endpoint_url: str, checked_at: str) -> str:
    digest = hashlib.sha1(f"{source_name}:{endpoint_url}:{checked_at}".encode("utf-8")).hexdigest()[:16]
    return f"API-{digest.upper()}"


def probe_endpoint(endpoint: dict, timeout: float) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    status_code = None
    error = ""
    ok = False
    try:
        response = requests.get(
            endpoint["endpoint_url"],
            timeout=timeout,
            verify=endpoint.get("verify", True),
            headers={"User-Agent": "AutoMedChemist/0.2"},
        )
        status_code = response.status_code
        ok = 200 <= response.status_code < 400
        if not ok:
            error = response.text[:500]
    except Exception as exc:
        error = str(exc)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "check_id": check_id(endpoint["source_name"], endpoint["endpoint_url"], checked_at),
        "source_name": endpoint["source_name"],
        "endpoint_url": endpoint["endpoint_url"],
        "checked_at": checked_at,
        "ok": ok,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "error": error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe external source APIs used by the data ingestion pipeline.")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "api_health_report.json"))
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--allow-insecure-surechembl", action="store_true")
    args = parser.parse_args()

    endpoints = [dict(endpoint) for endpoint in DEFAULT_ENDPOINTS]
    if args.allow_insecure_surechembl:
        for endpoint in endpoints:
            if endpoint["source_name"] == "SureChEMBL":
                endpoint["verify"] = False

    checks = [probe_endpoint(endpoint, timeout=args.timeout) for endpoint in endpoints]
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "check_count": len(checks),
        "ok_count": sum(1 for item in checks if item["ok"]),
        "error_count": sum(1 for item in checks if not item["ok"]),
        "checks": checks,
    }

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_api_health_checks(conn, checks)
        finally:
            conn.close()

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

