"""The same commission WITH the tool in the loop.

Eight production materials plus a layered car-paint node graph. Where a
measured preset exists, use it (the presets carry spectrophotometer F0
values); where it doesn't, author the material and let the tool verify
it before it ships. The car-paint graph keeps the blind version's
structure — two BRDF lobes under a fresnel clear coat, which the audit
confirmed is sound — but bakes the procedural flake pattern
(fbm + voronoi, 320 of its 436 ALU/pixel) into a single texture fetch.

Run: python make_after.py    -> after/<name>/, after/graph/,
                                after/carpaint_graph_after.json,
                                gold diff (blind vs preset)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
AFTER = HERE / "after"
AUDIT = HERE / "audit"

# preset name where one exists, else the authored recipe
MATERIALS: dict[str, dict] = {
    "gold": {"preset": "gold", "roughness": 0.18},
    "aluminum": {"preset": "aluminum", "roughness": 0.22},
    "copper": {"preset": "copper", "roughness": 0.16},
    "skin": {"preset": "skin", "roughness": 0.45},
    "snow": {"preset": "snow", "roughness": 0.35},
    "red_car_paint": {"base_color": (0.45, 0.015, 0.02), "roughness": 0.12,
                      "metallic": 0.0, "specular": 1.0},
    "black_rubber": {"preset": "rubber", "roughness": 0.82},
    "gray_plastic": {"preset": "plastic", "base_color": (0.5, 0.5, 0.5),
                     "roughness": 0.55},
}


def run(args: list[str]) -> str:
    r = subprocess.run([sys.executable, "-m", "shadersight.cli"] + args,
                       capture_output=True, text=True)
    if r.returncode not in (0, 1):        # 1 = warnings, still a report
        raise SystemExit(f"shadersight {' '.join(args)} failed:\n"
                         f"{r.stdout}{r.stderr}")
    return r.stdout


def carpaint_graph() -> dict:
    """The blind graph with its 320-ALU procedural flake chain baked
    into one 100-ALU texture fetch (mask in .r, height in .g)."""
    return {"name": "carpaint_after", "output": "n15", "nodes": [
        {"id": "n1", "type": "uv", "inputs": {}},
        {"id": "n2", "type": "texture", "inputs": {"uv": "n1.out"},
         "comment": "baked flake map: voronoi^8 mask in R, fbm height in G"},
        {"id": "n3", "type": "constant",
         "inputs": {"value": [0.45, 0.015, 0.02]}},
        {"id": "n4", "type": "constant",
         "inputs": {"value": [0.85, 0.83, 0.88]}},
        {"id": "n5", "type": "mix",
         "inputs": {"a": "n3.out", "b": "n4.out", "factor": "n2.r"}},
        {"id": "n6", "type": "normal", "inputs": {}},
        {"id": "n7", "type": "multiply", "inputs": {"a": "n2.g", "b": 0.12}},
        {"id": "n8", "type": "add", "inputs": {"a": "n6.out", "b": "n7.out"}},
        {"id": "n9", "type": "normalize", "inputs": {"a": "n8.out"}},
        {"id": "n10", "type": "mix",
         "inputs": {"a": 0.35, "b": 0.15, "factor": "n2.r"}},
        {"id": "n11", "type": "brdf",
         "inputs": {"base_color": "n5.out", "roughness": "n10.out",
                    "metallic": "n2.r", "normal": "n9.out"}},
        {"id": "n12", "type": "brdf",
         "inputs": {"base_color": [1.0, 1.0, 1.0], "roughness": 0.04,
                    "metallic": 0.0, "normal": "n6.out"}},
        {"id": "n13", "type": "fresnel",
         "inputs": {"normal": "n6.out", "ior": 1.5}},
        {"id": "n14", "type": "clamp",
         "inputs": {"a": "n13.out", "min": 0.0, "max": 1.0}},
        {"id": "n15", "type": "mix",
         "inputs": {"a": "n11.out", "b": "n12.out", "factor": "n14.out"}},
    ]}


def main() -> None:
    AFTER.mkdir(exist_ok=True)
    for name, rec in MATERIALS.items():
        args = ["material", "--out", str(AFTER / name)]
        if "preset" in rec:
            args += ["--preset", rec["preset"]]
        for k, flag in (("base_color", "--base-color"),
                        ("roughness", "--roughness"),
                        ("metallic", "--metallic"),
                        ("specular", "--specular")):
            if k in rec:
                v = rec[k]
                v = ",".join(str(x) for x in v) if isinstance(v, tuple) else v
                args += [flag, str(v)]
        out = run(args)
        line = next(ln for ln in out.splitlines() if "energy:" in ln)
        print(f"{name:14s} {line.strip()}", flush=True)

    gpath = AFTER / "carpaint_graph_after.json"
    gpath.write_text(json.dumps(carpaint_graph(), indent=1),
                     encoding="utf-8")
    print(run(["graph", str(gpath), "--out", str(AFTER / "graph")]).strip(),
          flush=True)

    # the receipts: is the blind gold the measured gold? diff says.
    if (AUDIT / "gold").exists():
        print(run(["diff", str(AUDIT / "gold"), str(AFTER / "gold")]).strip(),
              flush=True)


if __name__ == "__main__":
    main()
