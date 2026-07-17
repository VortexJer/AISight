"""Assemble the deterministic shader report."""

from __future__ import annotations

import json
from pathlib import Path

from . import brdf as B
from .graph import analyze_graph, parse_graph


def _check(id_, level, message, where=None, suggestion=None) -> dict:
    c = {"id": id_, "level": level, "message": message}
    if where:
        c["where"] = where
    if suggestion:
        c["try"] = suggestion
    return c


def analyze_material(mat: B.Material, quality: str = "normal") -> dict:
    nt, npph = {"fast": (32, 64), "normal": (64, 128),
                "high": (128, 256)}[quality]
    energy = B.energy_conservation(mat, nt, npph)
    recip = B.reciprocity(mat)
    pos = B.positivity(mat)
    furnace = B.furnace_residual(mat, nt, npph)

    checks: list[dict] = []
    if not energy["conserves_energy"]:
        checks.append(_check(
            "energy-not-conserved", "fail",
            f"the material reflects {energy['max_albedo']}x the light it "
            f"receives at {energy['max_at_theta_deg']} deg",
            where=f"directional albedo peaks at "
                  f"theta={energy['max_at_theta_deg']} deg",
            suggestion="a passive surface cannot emit energy: lower the "
                       "base colour or specular, or check the F/D/G "
                       "normalisation - most often the D term is not "
                       "normalised so its hemisphere integral exceeds 1"))
    if not recip["reciprocal"]:
        checks.append(_check(
            "not-reciprocal", "fail",
            f"f(wi,wo) != f(wo,wi): relative error up to "
            f"{recip['max_relative_error']}",
            where=f"worst at wi={recip['worst_pair']['wi']}, "
                  f"wo={recip['worst_pair']['wo']}",
            suggestion="Helmholtz reciprocity is a physical law; a term "
                       "that treats the view and light directions "
                       "asymmetrically (a common 'fake fresnel' mistake) "
                       "breaks it and looks wrong from half the angles"))
    if not pos["non_negative"]:
        checks.append(_check(
            "negative-brdf", "fail",
            f"the BRDF goes negative (min {pos['min_value']})",
            where=f"{pos['negative_samples']} sampled direction(s)",
            suggestion="a negative BRDF subtracts light and punches black "
                       "holes into the shading: check for a sign slip or "
                       "an over-eager energy-compensation term"))
    if furnace["energy_lost"] > 0.15:
        checks.append(_check(
            "high-energy-loss", "warn",
            f"the material loses {furnace['energy_lost'] * 100:.0f}% of its "
            f"energy at this roughness (single-scatter GGX)",
            where="normal-incidence white furnace",
            suggestion="EXPECTED for rough surfaces with single-scatter "
                       "GGX, not a bug: rough metals look too dark without "
                       "a multi-scatter term. Add one if it matters, or "
                       "accept it"))

    fails = [c for c in checks if c["level"] == "fail"]
    return {
        "status": ("failed" if fails else
                   ("warnings" if checks else "ok")),
        "material": {"name": mat.name,
                     "base_color": [round(float(v), 4) for v in mat.base_color],
                     "roughness": mat.roughness, "metallic": mat.metallic,
                     "specular": mat.specular,
                     "f0": [round(float(v), 4) for v in mat.f0],
                     "alpha_ggx": round(mat.alpha, 5)},
        "energy_conservation": energy,
        "reciprocity": recip,
        "positivity": pos,
        "furnace": furnace,
        "checks": checks,
    }


def inspect_material(mat: B.Material, out_dir: Path,
                     quality: str = "normal") -> dict:
    from .render import render_albedo_curve, render_sphere
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rep = analyze_material(mat, quality=quality)

    render_sphere(mat, out / "preview.png")
    render_albedo_curve(rep["energy_conservation"], out / "albedo_curve.png")

    fails = [c for c in rep["checks"] if c["level"] == "fail"]
    rep["status"] = "failed" if fails else ("warnings" if rep["checks"]
                                            else "ok")
    rep["files"] = {"report": "report.json",
                    "renders": ["preview.png", "albedo_curve.png"]}
    (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n",
                                     encoding="utf-8")
    rep["_out_dir"] = str(out)
    return rep


def inspect_graph(path: str | Path, out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    g = parse_graph(path)
    rep = analyze_graph(g)
    fails = [c for c in rep["checks"] if c["level"] == "fail"]
    rep["status"] = "failed" if fails else ("warnings" if rep["checks"]
                                            else "ok")
    rep["files"] = {"report": "report.json"}
    (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n",
                                     encoding="utf-8")
    rep["_out_dir"] = str(out)
    return rep
