"""Design critique and cost estimation.

    solidsight critique model.py         # prioritized review, exact evidence
    solidsight cost model.py             # material + machine-time estimate
    solidsight cost model.py --process sla

critique = every validator finding, ordered by severity, each expanded
with the explain() knowledge base (meaning / evidence / fix menu) plus
the concrete numbers from THIS build. It ends with what is verifiably
GOOD about the design — an honest review names both.

cost = material mass x price + machine time x rate, per process, with
the uncertainty stated. Estimates, not quotes.
"""

from __future__ import annotations

# process profiles: (density g/cm3, material price eur/kg,
#                    machine rate eur/h, time model note)
PROCESSES = {
    "fdm": {"density": 1.24, "price_kg": 20.0, "rate_h": 1.0,
            "mm3_per_min": 600.0,
            "note": "solid PLA at 100% infill; slicer-dependent +-50%"},
    "fdm-petg": {"density": 1.27, "price_kg": 25.0, "rate_h": 1.0,
                 "mm3_per_min": 550.0,
                 "note": "solid PETG at 100% infill; +-50%"},
    "sla": {"density": 1.15, "price_kg": 60.0, "rate_h": 2.0,
            "mm3_per_min": 300.0,
            "note": "resin, solid; height-dominated in reality; +-60%"},
    "cnc-alu": {"density": 2.70, "price_kg": 8.0, "rate_h": 60.0,
                "mm3_per_min": 2000.0,
                "note": "billet 6061: stock = bbox, cost dominated by "
                        "machine time and setups; +-70%"},
}


def cost_estimate(scene, process: str = "fdm") -> dict:
    if process not in PROCESSES:
        from .errors import BadArgumentError
        raise BadArgumentError(
            f"unknown process {process!r}",
            suggestion="processes: " + ", ".join(sorted(PROCESSES)))
    p = PROCESSES[process]
    rows = []
    for part in scene.parts:
        if part.ghost:
            continue
        vol = part.solid.volume
        if process == "cnc-alu":
            lo, hi = part.solid.bbox
            stock = ((hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2]))
            mat_g = stock * p["density"] / 1000.0
            removed = max(stock - vol, 0.0)
            minutes = removed / p["mm3_per_min"] + 15.0    # + setup
        else:
            mat_g = vol * p["density"] / 1000.0
            minutes = vol / p["mm3_per_min"]
        mat_cost = mat_g / 1000.0 * p["price_kg"]
        machine_cost = minutes / 60.0 * p["rate_h"]
        rows.append({"part": part.name, "material_g": round(mat_g, 1),
                     "time_min": int(round(minutes)),
                     "material_eur": round(mat_cost, 2),
                     "machine_eur": round(machine_cost, 2),
                     "total_eur": round(mat_cost + machine_cost, 2)})
    return {"process": process, "note": p["note"], "parts": rows,
            "total_eur": round(sum(r["total_eur"] for r in rows), 2)}


def critique(scene, opts=None) -> dict:
    from .explain import explain
    from .validate import ValidationOptions, analyze_scene
    opts = opts or ValidationOptions(mode="print-safe")
    metrics, checks, pairs = analyze_scene(scene, opts)

    findings = []
    order = {"fail": 0, "warn": 1}
    for c in sorted((c for c in checks if c["level"] in order),
                    key=lambda c: (order[c["level"]], c["id"])):
        entry = {"level": c["level"], "id": c["id"],
                 "finding": c["message"], "where": c.get("where"),
                 "suggestion": c.get("suggestion")}
        e = explain(c["id"])
        if e:
            entry["meaning"] = e["meaning"]
            entry["fix_menu"] = e["fixes"]
        findings.append(entry)

    good = []
    for name, m in metrics.items():
        if m.get("ghost"):
            continue
        if m.get("watertight"):
            good.append(f"'{name}' is watertight, {m['shells']} shell(s)")
        w = (m.get("wall_thickness") or {}).get("min_mm")
        if w is not None and w >= opts.min_wall:
            good.append(f"'{name}' thinnest wall {w} mm "
                        f"(>= {opts.min_wall})")
        stab = m.get("stability") or {}
        if stab.get("status") == "stable":
            good.append(f"'{name}' stands stable as oriented")
    met = [p for p in pairs if p.get("expectation") == "met"]
    for p in met:
        good.append(f"declared spec MET: '{p['a']}' / '{p['b']}' "
                    f"({p.get('expected')})")

    return {"findings": findings, "verified_good": good,
            "verdict": ("REVISE" if any(f["level"] == "fail"
                                        for f in findings)
                        else "ACCEPTABLE" if findings else "CLEAN")}
