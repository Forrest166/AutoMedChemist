from __future__ import annotations

import argparse
from pathlib import Path


POWERSHELL_LAUNCHER = """$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (Test-Path ".venv\\Scripts\\python.exe") {
  $Python = ".venv\\Scripts\\python.exe"
} else {
  $Python = "python"
}
& $Python run_app.py
"""


BAT_LAUNCHER = """@echo off
setlocal
cd /d "%~dp0\\.."
if exist ".venv\\Scripts\\python.exe" (
  ".venv\\Scripts\\python.exe" run_app.py
) else (
  python run_app.py
)
"""


def write_launchers(output_dir: str | Path) -> list[Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ps1 = out / "LocalMedChemLauncher.ps1"
    bat = out / "LocalMedChemLauncher.bat"
    ps1.write_text(POWERSHELL_LAUNCHER, encoding="utf-8")
    bat.write_text(BAT_LAUNCHER, encoding="utf-8")
    return [ps1, bat]


def main() -> None:
    parser = argparse.ArgumentParser(description="Write simple non-developer launchers for the native AutoMedChemist app.")
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()
    for path in write_launchers(args.output_dir):
        print(path.resolve())


if __name__ == "__main__":
    main()
