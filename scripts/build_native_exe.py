from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the native AutoMedChemist desktop EXE.")
    parser.add_argument("--name", default="AutoMedChemist")
    parser.add_argument("--console", action="store_true", help="Keep a console attached for debugging.")
    args = parser.parse_args()

    dist_exe = ROOT / f"{args.name}.exe"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        args.name,
        "--paths",
        str(ROOT / "src"),
        "--hidden-import",
        "yaml",
        "--hidden-import",
        "PIL.ImageTk",
        "--distpath",
        str(ROOT),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build" / "pyinstaller"),
    ]
    if not args.console:
        command.append("--windowed")
    command.append(str(ROOT / "app" / "native_shell.py"))
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    report = {
        "status": "built" if proc.returncode == 0 and dist_exe.exists() else "failed",
        "exe_path": str(dist_exe),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    (ROOT / "data" / "releases").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "releases" / "native_exe_build_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    if (ROOT / "dist" / f"{args.name}.exe").exists() and not dist_exe.exists():
        shutil.copy2(ROOT / "dist" / f"{args.name}.exe", dist_exe)
    print(json.dumps({key: report[key] for key in ["status", "exe_path", "returncode"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
