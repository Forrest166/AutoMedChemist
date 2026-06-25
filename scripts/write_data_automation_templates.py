from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def _powershell_script(root: Path, python_exe: str, chunk_size: int, max_chunks: int) -> str:
    return f"""$ErrorActionPreference = "Stop"
$Root = "{root}"
$Python = "{python_exe}"
Set-Location $Root
& $Python scripts\\import_ertl_ring_chunks.py --chunk-size {chunk_size} --max-chunks {max_chunks}
& $Python scripts\\build_data_foundation_report.py --no-checksums
"""


def _task_xml(root: Path, ps1_path: Path, task_name: str, start_time: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{escape(task_name)}: import Ertl ring chunks and refresh the LocalMedChem data foundation.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{escape(start_time)}</StartBoundary>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File "{escape(str(ps1_path))}"</Arguments>
      <WorkingDirectory>{escape(str(root))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Windows Task Scheduler templates for data-foundation refresh jobs.")
    parser.add_argument("--output-dir", default=str(ROOT / "dist" / "tasks"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--chunk-size", type=int, default=10000)
    parser.add_argument("--max-chunks", type=int, default=1)
    parser.add_argument("--task-name", default="LocalMedChem_ErtlRingChunk")
    parser.add_argument("--start-time", default="2026-05-14T02:30:00")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ps1_path = output_dir / f"{args.task_name}.ps1"
    xml_path = output_dir / f"{args.task_name}.xml"
    ps1_path.write_text(
        _powershell_script(ROOT.resolve(), args.python, args.chunk_size, args.max_chunks),
        encoding="utf-8",
    )
    xml_path.write_text(
        _task_xml(ROOT.resolve(), ps1_path.resolve(), args.task_name, args.start_time),
        encoding="utf-16",
    )
    summary = {
        "task_name": args.task_name,
        "powershell_path": str(ps1_path.resolve()),
        "task_xml_path": str(xml_path.resolve()),
        "chunk_size": args.chunk_size,
        "max_chunks": args.max_chunks,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
