"""Generate the example graphs. Materials are made on the CLI, so the
only files needed are node graphs with known defects.

  clean_graph.json    a valid PBR graph: UVs -> textures -> a BRDF -> output
  broken_graph.json   the same idea with, by construction:
                        * a feedback cycle (mul <-> add)
                        * a dead noise branch not wired to the output
                        * a dangling reference to a node that does not exist
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent / "01-graphs"

CLEAN = {
    "name": "clean_pbr",
    "nodes": [
        {"id": "uv", "type": "uv", "inputs": {}},
        {"id": "albedo_tex", "type": "texture", "inputs": {"uv": "uv.out"}},
        {"id": "rough_tex", "type": "texture", "inputs": {"uv": "uv.out"}},
        {"id": "normal_tex", "type": "texture", "inputs": {"uv": "uv.out"}},
        {"id": "n", "type": "normal", "inputs": {"map": "normal_tex.out"}},
        {"id": "fres", "type": "fresnel", "inputs": {"normal": "n.out"}},
        {"id": "tint", "type": "multiply",
         "inputs": {"a": "albedo_tex.out", "b": 0.9}},
        {"id": "shade", "type": "brdf",
         "inputs": {"albedo": "tint.out", "roughness": "rough_tex.out",
                    "normal": "n.out", "fresnel": "fres.out"}},
        {"id": "out", "type": "output", "inputs": {"color": "shade.out"}},
    ],
    "output": "out",
}

BROKEN = {
    "name": "broken_pbr",
    "nodes": [
        {"id": "uv", "type": "uv", "inputs": {}},
        {"id": "tex", "type": "texture", "inputs": {"uv": "uv.out"}},
        # feedback cycle: mul needs add, add needs mul
        {"id": "mul", "type": "multiply",
         "inputs": {"a": "add.out", "b": "tex.out"}},
        {"id": "add", "type": "add", "inputs": {"a": "mul.out", "b": 0.5}},
        # dead branch: computed, never reaches the output
        {"id": "noise", "type": "fbm", "inputs": {"p": "uv.out"}},
        {"id": "warp", "type": "multiply",
         "inputs": {"a": "noise.out", "b": 2.0}},
        # dangling: 'missing' does not exist
        {"id": "out", "type": "output", "inputs": {"color": "missing.out"}},
    ],
    "output": "out",
}

if __name__ == "__main__":
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "clean_graph.json").write_text(json.dumps(CLEAN, indent=2),
                                           encoding="utf-8")
    (HERE / "broken_graph.json").write_text(json.dumps(BROKEN, indent=2),
                                            encoding="utf-8")
    print(f"wrote 2 graphs to {HERE}")
