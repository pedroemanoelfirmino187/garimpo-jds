"""Executa a suíte offline do JDS e produz um relatório simples."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "quality_report.txt"

cmd = [sys.executable, "-m", "pytest", "-q"]
proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
text = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
REPORT.write_text(text, encoding="utf-8")
print(text)
print(f"Relatório: {REPORT}")
sys.exit(proc.returncode)
