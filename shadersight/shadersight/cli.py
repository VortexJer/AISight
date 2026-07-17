"""shadersight CLI — shaders as mathematical systems."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .errors import ShaderSightError

_ASCII_FOLD = {ord(a): b for a, b in
               [("—", "-"), ("–", "-"), ("°", " deg"), ("·", "-"),
                ("…", "..."), ("×", "x"), ("→", "->"), ("≤", "<="),
                ("≥", ">=")]}


def _say(text: str, err: bool = False) -> None:
    print(text.translate(_ASCII_FOLD), file=sys.stderr if err else sys.stdout,
          flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="shadersight",
        description="Shader review for AI agents: a material or a node "
                    "graph in, exact physics + cost + preview out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("material",
                       help="test a PBR material's physics (energy, "
                            "reciprocity, positivity)")
    m.add_argument("--base-color", default="0.8,0.8,0.8",
                   help="R,G,B in 0..1 (default 0.8,0.8,0.8)")
    m.add_argument("--roughness", type=float, default=0.5)
    m.add_argument("--metallic", type=float, default=0.0)
    m.add_argument("--specular", type=float, default=0.5)
    m.add_argument("--quality", default="normal",
                   choices=["fast", "normal", "high"],
                   help="hemisphere integration resolution (default normal)")
    m.add_argument("--out", default="out")
    m.add_argument("--json", action="store_true")

    g = sub.add_parser("graph",
                       help="analyse a shader node graph (cycles, dead "
                            "nodes, cost)")
    g.add_argument("graph", help="a graph .json file")
    g.add_argument("--out", default="out")
    g.add_argument("--json", action="store_true")

    sub.add_parser("install-skill", help="(re)install the Claude Code skill")
    sub.add_parser("uninstall", help="remove the skill AND the package")
    sub.add_parser("version")

    args = p.parse_args(argv)
    if args.cmd not in ("install-skill", "uninstall"):
        from .skill_install import maybe_autoinstall
        maybe_autoinstall()

    try:
        if args.cmd == "version":
            _say(f"shadersight {__version__}")
            return 0
        if args.cmd == "install-skill":
            from .skill_install import install_skill
            install_skill()
            return 0
        if args.cmd == "uninstall":
            from .skill_install import uninstall
            return uninstall()
        if args.cmd == "material":
            return _material(args)
        return _graph(args)
    except ShaderSightError as e:
        _say(f"FAILED\n{e.render()}", err=True)
        return 1


def _material(args) -> int:
    from pathlib import Path

    from .brdf import Material
    from .errors import BadModelError
    from .report import inspect_material
    try:
        bc = tuple(float(v) for v in args.base_color.split(","))
    except ValueError:
        raise BadModelError(f"bad --base-color {args.base_color!r}",
                            suggestion="three numbers, e.g. 0.8,0.1,0.1")
    mat = Material(base_color=bc, roughness=args.roughness,
                   metallic=args.metallic, specular=args.specular)
    rep = inspect_material(mat, Path(args.out), quality=args.quality)
    out = rep.pop("_out_dir")
    if args.json:
        print(json.dumps(rep, indent=2))
        return 2 if rep["status"] == "failed" else 0

    mt = rep["material"]
    _say(f"shadersight material: {rep['status'].upper()}")
    _say(f"  material: base {mt['base_color']}, roughness {mt['roughness']}, "
         f"metallic {mt['metallic']} -> F0 {mt['f0']}, alpha {mt['alpha_ggx']}")
    e = rep["energy_conservation"]
    _say(f"  energy: max albedo {e['max_albedo']} at "
         f"{e['max_at_theta_deg']} deg -> "
         f"{'CONSERVES' if e['conserves_energy'] else 'VIOLATES'} "
         f"(grid {e['grid']['n_theta']}x{e['grid']['n_phi']}, "
         f"{e['grid']['n_views']} views)")
    r = rep["reciprocity"]
    _say(f"  reciprocity: max rel error {r['max_relative_error']} -> "
         f"{'OK' if r['reciprocal'] else 'BROKEN'}")
    _say(f"  positivity: min value {rep['positivity']['min_value']} -> "
         f"{'OK' if rep['positivity']['non_negative'] else 'NEGATIVE LOBE'}")
    _say(f"  furnace: loses {rep['furnace']['energy_lost'] * 100:.0f}% at "
         f"normal incidence (single-scatter GGX)")

    for c in [c for c in rep["checks"] if c["level"] == "fail"] + \
             [c for c in rep["checks"] if c["level"] == "warn"]:
        _say(f"  [{c['level'].upper()}] {c['message']}")
        if c.get("where"):
            _say(f"         where: {c['where']}")
        if c.get("try"):
            _say(f"         try:   {c['try']}")

    _say(f"  report: {out}/report.json")
    for f in rep["files"]["renders"]:
        _say(f"  render: {out}/{f}")
    _say("  NEXT: read the checks, then LOOK at albedo_curve.png (does it "
         "stay under the energy ceiling?) and preview.png.")
    return 2 if rep["status"] == "failed" else 0


def _graph(args) -> int:
    from pathlib import Path

    from .report import inspect_graph
    rep = inspect_graph(args.graph, Path(args.out))
    out = rep.pop("_out_dir")
    if args.json:
        print(json.dumps(rep, indent=2))
        return 2 if rep["status"] == "failed" else 0

    _say(f"shadersight graph: {rep['status'].upper()}")
    _say(f"  graph: {rep['name']} - {rep['nodes']} node(s), output "
         f"'{rep['output']}'")
    _say(f"  reachable: {rep['reachable_nodes']}/{rep['nodes']} nodes; "
         f"{len(rep['dead_nodes'])} dead, {len(rep['cycle_nodes'])} in cycles")
    c = rep["cost"]
    _say(f"  cost: ~{c['alu_equivalents']} ALU-equiv/pixel, "
         f"{c['texture_fetches']} texture fetch(es)"
         + (f" (top: {', '.join(list(c['by_type'])[:3])})"
            if c["by_type"] else ""))
    for chk in [c for c in rep["checks"] if c["level"] == "fail"] + \
               [c for c in rep["checks"] if c["level"] == "warn"]:
        _say(f"  [{chk['level'].upper()}] {chk['message']}")
        if chk.get("where"):
            _say(f"         where: {chk['where']}")
        if chk.get("try"):
            _say(f"         try:   {chk['try']}")
    _say(f"  report: {out}/report.json")
    return 2 if rep["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
