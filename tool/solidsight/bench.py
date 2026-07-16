"""Benchmark runner: graded, deterministic design commissions.

A benchmark is a directory containing:

    prompt.md            the commission an agent receives
    reference.py         a model that PROVES the expectations are satisfiable
    expectations.json    machine-checkable assertions on the build report

Run the reference solutions (self-test) or grade an agent's solution:

    solidsight bench run                      # all, with references
    solidsight bench run 03-gear-pair
    solidsight bench run 03-gear-pair --solution my_gears.py

Assertion forms in expectations.json ("asserts" list):

    {"path": "parts.washer.shells", "equals": 1}
    {"path": "scene.total_volume_mm3", "between": [180, 260]}
    {"path": "status", "in": ["ok", "warnings"]}
    {"check_absent": "internal-cavity"}
    {"check_present": "internal-cavity"}
    {"pair": ["gear_a", "gear_b"], "status": "clear",
     "clearance_between": [0.05, 0.45]}

Top-level keys: "mode" (free|print-safe), "min_wall" (optional).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


def _lookup(report: dict, path: str):
    cur = report
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def grade(report: dict, spec: dict) -> list[dict]:
    """Evaluate every assertion; returns [{ok, text}]."""
    results = []

    def add(ok: bool, text: str) -> None:
        results.append({"ok": bool(ok), "text": text})

    for a in spec.get("asserts", []):
        if "path" in a:
            val = _lookup(report, a["path"])
            if "equals" in a:
                add(val == a["equals"], f"{a['path']} == {a['equals']!r} "
                                        f"(got {val!r})")
            elif "between" in a:
                lo, hi = a["between"]
                ok = isinstance(val, (int, float)) and lo <= val <= hi
                add(ok, f"{a['path']} in [{lo}, {hi}] (got {val!r})")
            elif "in" in a:
                add(val in a["in"], f"{a['path']} in {a['in']} (got {val!r})")
        elif "check_absent" in a:
            hit = [c for c in report["checks"] if c["id"] == a["check_absent"]]
            add(not hit, f"no '{a['check_absent']}' finding "
                         f"(got {len(hit)})")
        elif "check_present" in a:
            hit = [c for c in report["checks"]
                   if c["id"] == a["check_present"]]
            add(bool(hit), f"'{a['check_present']}' finding present")
        elif "pair" in a:
            pa, pb = a["pair"]
            entry = next((p for p in report.get("pairs", [])
                          if {p["a"], p["b"]} == {pa, pb}), None)
            if entry is None:
                add(False, f"pair {pa}/{pb} exists (parts missing?)")
                continue
            if "status" in a:
                add(entry["status"] == a["status"],
                    f"pair {pa}/{pb} status {a['status']} "
                    f"(got {entry['status']})")
            if "clearance_between" in a:
                lo, hi = a["clearance_between"]
                c = entry.get("min_clearance_mm")
                ok = c is not None and lo <= c <= hi
                add(ok, f"pair {pa}/{pb} clearance in [{lo}, {hi}] "
                        f"(got {c!r})")
    return results


def run_benchmark(bench_dir: Path, solution: Path | None = None) -> dict:
    from .report import build_model
    spec = json.loads((bench_dir / "expectations.json"
                       ).read_text(encoding="utf-8"))
    model = solution or (bench_dir / "reference.py")
    with tempfile.TemporaryDirectory() as td:
        report = build_model(
            model, out_dir=Path(td), views=["iso"],
            mode=spec.get("mode", "free"),
            min_wall=spec.get("min_wall", 1.2))
    results = grade(report, spec)
    passed = all(r["ok"] for r in results)
    return {"benchmark": bench_dir.name, "model": str(model),
            "passed": passed, "results": results}


def run_all(bench_root: Path, only: str | None, solution: Path | None,
            say, as_json: bool = False) -> int:
    dirs = sorted(d for d in bench_root.iterdir()
                  if d.is_dir() and (d / "expectations.json").exists())
    if only:
        dirs = [d for d in dirs if d.name == only]
        if not dirs:
            say(f"no benchmark named {only!r} in {bench_root}", err=True)
            return 1
    if solution and len(dirs) != 1:
        say("--solution grades ONE benchmark; name it", err=True)
        return 1
    out = []
    ok_all = True
    for d in dirs:
        from .errors import SolidsightError
        try:
            res = run_benchmark(d, solution)
        except SolidsightError as e:
            res = {"benchmark": d.name, "passed": False,
                   "results": [{"ok": False,
                                "text": f"build failed: {e}"}]}
        out.append(res)
        ok_all &= res["passed"]
        if not as_json:
            say(f"{'PASS' if res['passed'] else 'FAIL'}  {d.name}")
            for r in res["results"]:
                mark = "ok " if r["ok"] else "XXX"
                say(f"      [{mark}] {r['text']}")
    if as_json:
        print(json.dumps(out, indent=2))
    return 0 if ok_all else 1
