"""Audit the blind agent's material set with shadersight.

The blind side (blind/) was authored by a cold-context agent with no
tools — numpy-free, render-free, from memory. This script runs the SAME
commission's deliverables through the tool: every material through
`shadersight material`, the car-paint node graph through
`shadersight graph`. Whatever it finds, it finds; the README reports it
either way.

Run: python audit_blind.py     -> audit/<name>/, audit/graph/
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
BLIND = HERE / "blind"
AUDIT = HERE / "audit"


def run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "shadersight.cli"] + args,
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main() -> None:
    AUDIT.mkdir(exist_ok=True)
    mats = json.loads((BLIND / "materials_blind.json")
                      .read_text(encoding="utf-8"))["materials"]
    summary = []
    for name, m in mats.items():
        args = ["material",
                "--base-color", ",".join(str(v) for v in m["base_color"]),
                "--roughness", str(m["roughness"]),
                "--metallic", str(m.get("metallic", 0.0)),
                "--out", str(AUDIT / name)]
        if "specular" in m:
            args += ["--specular", str(m["specular"])]
        code, out = run(args)
        rep = json.loads((AUDIT / name / "report.json")
                         .read_text(encoding="utf-8"))
        e = rep["energy_conservation"]
        summary.append((name, rep["status"], e["max_albedo"]))
        print(f"{name:14s} {rep['status']:8s} max albedo {e['max_albedo']}",
              flush=True)

    code, out = run(["graph", str(BLIND / "carpaint_graph_blind.json"),
                     "--out", str(AUDIT / "graph")])
    print(out.strip(), flush=True)

    failed = [n for n, s, _ in summary if s == "failed"]
    print(f"\naudit: {len(summary)} materials, "
          f"{len(failed)} failed ({', '.join(failed) or 'none'})",
          flush=True)


if __name__ == "__main__":
    main()
