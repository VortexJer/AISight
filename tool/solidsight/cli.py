"""solidsight CLI.

    solidsight build model.py [--print-safe] [--out DIR] [--views ...]
    solidsight catalog [PART]
    solidsight version
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

from . import __version__
from .errors import SolidsightError

_ASCII_FOLD = str.maketrans({"—": "-", "–": "-", "°": " deg", "·": "|",
                             "…": "...", "×": "x"})


def _say(text: str, err: bool = False) -> None:
    """Print with non-ASCII punctuation folded away so output survives any
    Windows console codepage an agent might read it through."""
    print(text.translate(_ASCII_FOLD), file=sys.stderr if err else sys.stdout)


def main(argv: list[str] | None = None) -> int:
    import logging
    logging.getLogger("trimesh").setLevel(logging.ERROR)
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(
        prog="solidsight",
        description="3D design tool for AI agents: code in, renders + "
                    "validation report out.")
    sub = parser.add_subparsers(dest="command")

    b = sub.add_parser("build", help="build a model file: geometry -> "
                                     "renders + report.json (+ STL)")
    b.add_argument("model", help="path to the .py model file")
    mode = b.add_mutually_exclusive_group()
    mode.add_argument("--print-safe", action="store_true",
                      help="enforce 3D-printability: single shell, wall "
                           "thickness, overhang warnings")
    mode.add_argument("--free", action="store_true",
                      help="exploration mode (default): report metrics, "
                           "enforce nothing")
    b.add_argument("--out", default=None,
                   help="output directory (default: <model dir>/out)")
    b.add_argument("--views", default="iso,front,right,top",
                   help="comma list of iso,iso_back,front,back,left,right,"
                        "top,bottom (default: iso,front,right,top)")
    b.add_argument("--turntable", type=int, default=0, metavar="N",
                   help="also render N frames orbiting the model")
    b.add_argument("--slice", action="append", default=[], metavar="AXIS=MM",
                   help="render a cross-section, e.g. --slice z=5 "
                        "(repeatable)")
    b.add_argument("--part", default=None,
                   help="build only these named parts (comma list)")
    b.add_argument("--stl", action="store_true",
                   help="export binary STL per part + combined")
    b.add_argument("--3mf", dest="threemf", action="store_true",
                   help="export 3MF per part + combined (units + colors "
                        "aware format)")
    b.add_argument("--exploded", action="store_true",
                   help="also render an exploded view of multi-part scenes")
    b.add_argument("--focus", default=None, metavar="X,Y,Z,R",
                   help="zoom every view onto a sphere of radius R around "
                        "the point (X,Y,Z) — inspect one feature up close")
    b.add_argument("--size", type=int, default=900,
                   help="render size in pixels (default 900)")
    b.add_argument("--min-wall", type=float, default=1.2,
                   help="print-safe minimum wall thickness in mm (default 1.2)")
    b.add_argument("--max-overhang", type=float, default=50.0,
                   help="print-safe overhang warning threshold in degrees "
                        "from vertical (default 50)")
    b.add_argument("--allow-multiple-shells", action="store_true",
                   help="print-safe: do not fail parts made of several "
                        "disconnected pieces")
    b.add_argument("--json", action="store_true",
                   help="print the full report JSON to stdout")

    c = sub.add_parser("catalog", help="list the parametric parts catalog")
    c.add_argument("name", nargs="?", help="show full docs for one part")

    df = sub.add_parser("diff",
                        help="compare two build reports: what did my change "
                             "actually change?")
    df.add_argument("report_a", help="path to the OLD report.json")
    df.add_argument("report_b", help="path to the NEW report.json")

    isk = sub.add_parser("install-skill",
                         help="(re)install the Claude Code skill into "
                              "~/.claude/skills/solidsight")
    isk.add_argument("--dir", default=None,
                     help="alternative skills directory")
    sub.add_parser("uninstall",
                   help="remove the Claude Code skill AND the solidsight "
                        "package")

    q = sub.add_parser(
        "query",
        help="exact spatial queries on a model: point/ray/section/voxels")
    q.add_argument("model", help="path to the .py model file")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--part", default=None,
                        help="query one named part (default: whole scene)")
    common.add_argument("--json", action="store_true",
                        help="machine output instead of text/ASCII")
    qsub = q.add_subparsers(dest="op", required=True)

    qp = qsub.add_parser("point", parents=[common],
                         help="INSIDE / OUTSIDE / ON_SURFACE for one point")
    qp.add_argument("x", type=float)
    qp.add_argument("y", type=float)
    qp.add_argument("z", type=float)
    qp.add_argument("--tol", type=float, default=1e-3,
                    help="ON_SURFACE tolerance in mm (default 0.001)")

    qr = qsub.add_parser("ray", parents=[common],
                         help="all surface crossings along a ray")
    for name in ("ox", "oy", "oz", "dx", "dy", "dz"):
        qr.add_argument(name, type=float)

    qs = qsub.add_parser("section", parents=[common],
                         help="ASCII INSIDE/OUTSIDE grid at a cut plane")
    qs.add_argument("plane", help="AXIS=VALUE, e.g. z=4 or x=-10")
    qs.add_argument("--res", type=float, default=None,
                    help="cell size in mm (default: auto ~78 columns)")

    qv = qsub.add_parser("voxels", parents=[common],
                         help="boolean voxel grid + sealed-cavity detection")
    qv.add_argument("--res", type=float, default=None,
                    help="voxel size in mm (default: max dimension / 64)")
    qv.add_argument("--layer", default=None,
                    help="print one Z layer as ASCII (index or 'all')")

    sub.add_parser("version", help="print version")

    args = parser.parse_args(argv)

    from .skill_install import install_skill, maybe_autoinstall, uninstall
    if args.command == "install-skill":
        install_skill(Path(args.dir) if args.dir else None)
        return 0
    if args.command == "uninstall":
        return uninstall()
    maybe_autoinstall()   # self-host the skill on machines with Claude Code

    if args.command == "version":
        print(f"solidsight {__version__}")
        return 0
    if args.command == "diff":
        return _diff(Path(args.report_a), Path(args.report_b))
    if args.command == "catalog":
        return _catalog(args.name)
    if args.command == "query":
        try:
            return _query(args)
        except SolidsightError as e:
            _say(f"QUERY FAILED\n{e.render()}", err=True)
            return 1
    if args.command == "build":
        try:
            return _build(args)
        except SolidsightError as e:
            _say(f"BUILD FAILED\n{e.render()}", err=True)
            return 1
    parser.print_help()
    return 0


# ---------------------------------------------------------------------------

def _build(args) -> int:
    from .report import build_model
    mode = "print-safe" if args.print_safe else "free"
    model = Path(args.model)
    out_dir = Path(args.out) if args.out else model.parent / "out"

    slices = []
    for s in args.slice:
        try:
            axis, val = s.split("=", 1)
            slices.append((axis.strip().lower(), float(val)))
        except ValueError:
            _say(f"BUILD FAILED\nbad --slice {s!r}\n  try: --slice z=5",
                 err=True)
            return 1

    focus = None
    if args.focus:
        try:
            focus = tuple(float(v) for v in args.focus.split(","))
            if len(focus) != 4 or focus[3] <= 0:
                raise ValueError
        except ValueError:
            _say(f"BUILD FAILED\nbad --focus {args.focus!r}\n"
                 "  try: --focus 70,43,24,25  (X,Y,Z and a positive radius)",
                 err=True)
            return 1

    report = build_model(
        model_path=model,
        out_dir=out_dir,
        mode=mode,
        views=[v.strip() for v in args.views.split(",") if v.strip()],
        turntable=args.turntable,
        slices=slices,
        only_parts=[p.strip() for p in args.part.split(",")] if args.part else None,
        export_stl=args.stl,
        export_3mf=args.threemf,
        size=args.size,
        min_wall=args.min_wall,
        max_overhang=args.max_overhang,
        allow_multiple_shells=args.allow_multiple_shells,
        exploded=args.exploded,
        focus=focus,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report)

    if report["status"] == "failed" and mode == "print-safe":
        return 2
    return 0


def _print_summary(report: dict) -> None:
    _say(f"solidsight build: {report['status'].upper()}  "
          f"(mode: {report['mode']})")
    sc = report["scene"]
    _say(f"  scene: {sc['part_count']} part(s), "
          f"{sc['size'][0]} x {sc['size'][1]} x {sc['size'][2]} mm, "
          f"{sc['total_volume_mm3']} mm3")
    for name, p in report["parts"].items():
        t = p["wall_thickness"]["min_mm"]
        _say(f"  part '{name}': vol {p['volume_mm3']} mm3, "
              f"{p['shells']} shell(s), min wall "
              f"{t if t is not None else 'n/a'} mm")
    for pr in report.get("pairs", []):
        if pr["status"] != "collision":
            exp = ""
            if pr.get("expectation"):
                exp = (f"  [spec {pr['expectation'].upper()}: "
                       f"{pr.get('expected')}]")
            _say(f"  pair '{pr['a']}' <-> '{pr['b']}': {pr['status']}, "
                 f"clearance {pr['min_clearance_mm']} mm{exp}")
    fails = [c for c in report["checks"] if c["level"] == "fail"]
    warns = [c for c in report["checks"] if c["level"] == "warn"]
    for chk in fails + warns:
        _say(f"  [{chk['level'].upper()}] {chk['message']}")
        if chk.get("where"):
            _say(f"         where: {chk['where']}")
        if chk.get("suggestion"):
            _say(f"         try:   {chk['suggestion']}")
    _say(f"  report:  {report['files']['report']}")
    for r in report["files"]["renders"]:
        _say(f"  render:  {r}")
    for r in report["files"].get("exports", []):
        _say(f"  export:  {r}")
    _say("  NEXT: open the renders and LOOK at them (Read tool), then read "
          "report.json checks.")


def _query(args) -> int:
    from . import query as Q
    from .runner import run_model

    scene = run_model(Path(args.model))
    if args.part:
        solid = scene.get(args.part).solid
        scope = f"part '{args.part}'"
    elif len(scene.parts) == 1:
        solid = scene.parts[0].solid
        scope = f"part '{scene.parts[0].name}'"
    else:
        solid = scene.combined()
        scope = f"scene ({len(scene.parts)} parts merged; use --part for one)"

    if args.op == "point":
        res = Q.classify_point(solid, args.x, args.y, args.z, tol=args.tol)
        res["scope"] = scope
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            _say(f"point ({args.x}, {args.y}, {args.z}) is {res['result']}  "
                 f"(distance to surface {res['distance_to_surface_mm']} mm) "
                 f"— {scope}")
        return 0

    if args.op == "ray":
        res = Q.raycast(solid, (args.ox, args.oy, args.oz),
                        (args.dx, args.dy, args.dz))
        res["scope"] = scope
        if args.json:
            print(json.dumps(res, indent=2))
            return 0
        _say(f"ray from ({args.ox}, {args.oy}, {args.oz}) along "
             f"({args.dx}, {args.dy}, {args.dz}) — {scope}")
        _say(f"  crossings: {res['crossings']}"
             + ("  (origin starts INSIDE the material)"
                if res["origin_inside"] else ""))
        for h in res["hits"]:
            what = "ENTER" if h["entering"] else "EXIT "
            _say(f"  {what} at t={h['t_mm']} mm  point {tuple(h['point'])}")
        for s in res["material_segments"]:
            _say(f"  material from t={s['from_mm']} to t={s['to_mm']}  "
                 f"(thickness {s['thickness_mm']} mm)")
        if res.get("note"):
            _say(f"  note: {res['note']}")
        return 0

    if args.op == "section":
        try:
            axis, val = args.plane.split("=", 1)
            axis, val = axis.strip().lower(), float(val)
        except ValueError:
            _say("QUERY FAILED\nbad plane spec\n  try: section z=4", err=True)
            return 1
        res = Q.section_grid(solid, axis, val, res=args.res)
        res["scope"] = scope
        if args.json:
            print(json.dumps(res, indent=2))
            return 0
        _say(f"section {axis}={val} — {scope}")
        _say(f"  cell {res['cell_mm']} mm | cols = {res['cols_axis']} "
             f"(min at left) | rows = {res['rows_axis']} (max at top)")
        for row in res["grid"]:
            _say("  " + row)
        return 0

    if args.op == "voxels":
        vox = Q.voxelize(solid, res=args.res)
        voids = Q.find_voids(vox)
        nx, ny, nz = vox["shape"]
        if args.json and args.layer is None:
            out = dict(vox)
            out["grid"] = [[[int(v) for v in col] for col in plane]
                           for plane in vox["grid"].transpose(2, 1, 0)]
            out["grid_order"] = "grid[z_layer][y_row][x_col], 1 = material"
            out["internal_voids"] = voids
            out["scope"] = scope
            print(json.dumps(out))
            return 0
        _say(f"voxels — {scope}")
        _say(f"  grid {nx} x {ny} x {nz} at {vox['res_mm']} mm/voxel, "
             f"{vox['filled_voxels']} filled "
             f"(~{vox['filled_volume_mm3']} mm3)")
        if voids:
            for v in voids:
                _say(f"  SEALED CAVITY: ~{v['volume_mm3']} mm3 at bbox "
                     f"{v['bbox']['min']}..{v['bbox']['max']}")
        else:
            _say("  no sealed internal cavities at this resolution")
        if args.layer is not None:
            layers = (range(nz) if args.layer == "all"
                      else [int(args.layer)])
            z0 = vox["origin"][2]
            for k in layers:
                if not (0 <= k < nz):
                    _say(f"  layer {k} out of range 0..{nz - 1}", err=True)
                    return 1
                _say(f"  layer z={round(z0 + (k + 0.5) * vox['res_mm'], 3)} "
                     f"mm (index {k}):")
                plane = vox["grid"][:, :, k]
                for j in range(ny - 1, -1, -1):
                    _say("  " + "".join("#" if plane[i, j] else "."
                                        for i in range(nx)))
        return 0
    return 1


def _diff(path_a: Path, path_b: Path) -> int:
    """Compare two report.json files: per-part geometry deltas and checks
    that appeared or disappeared."""
    reports = []
    for p in (path_a, path_b):
        if p.is_dir():
            p = p / "report.json"
        if not p.exists():
            _say(f"DIFF FAILED\nno report at {p}\n"
                 "  try: point at an out/ dir or its report.json", err=True)
            return 1
        reports.append(json.loads(p.read_text(encoding="utf-8")))
    a, b = reports

    _say(f"diff: {a['model']} [{a['status']}] -> {b['model']} [{b['status']}]")
    names_a, names_b = set(a["parts"]), set(b["parts"])
    for name in sorted(names_b - names_a):
        _say(f"  + part '{name}' added")
    for name in sorted(names_a - names_b):
        _say(f"  - part '{name}' removed")
    for name in sorted(names_a & names_b):
        pa, pb = a["parts"][name], b["parts"][name]
        lines = []
        dv = pb["volume_mm3"] - pa["volume_mm3"]
        if abs(dv) > 1e-3:
            lines.append(f"volume {pa['volume_mm3']} -> {pb['volume_mm3']} "
                         f"({'+' if dv > 0 else ''}{round(dv, 3)} mm3)")
        sa, sb = pa["bbox"]["size"], pb["bbox"]["size"]
        if sa != sb:
            lines.append(f"size {sa} -> {sb}")
        wa = pa["wall_thickness"]["min_mm"]
        wb = pb["wall_thickness"]["min_mm"]
        if wa != wb:
            lines.append(f"min wall {wa} -> {wb} mm")
        if pa["shells"] != pb["shells"]:
            lines.append(f"shells {pa['shells']} -> {pb['shells']}")
        va = pa.get("internal_voids", {}).get("count", 0)
        vb = pb.get("internal_voids", {}).get("count", 0)
        if va != vb:
            lines.append(f"internal cavities {va} -> {vb}")
        if lines:
            _say(f"  part '{name}': " + "; ".join(lines))
        else:
            _say(f"  part '{name}': unchanged")

    def keyed(checks):
        return {(c["id"], c.get("part"), c["message"]): c for c in checks}
    ka, kb = keyed(a["checks"]), keyed(b["checks"])
    for k in sorted(kb.keys() - ka.keys(), key=str):
        c = kb[k]
        _say(f"  NEW  [{c['level'].upper()}] {c['message']}")
    for k in sorted(ka.keys() - kb.keys(), key=str):
        c = ka[k]
        _say(f"  GONE [{c['level'].upper()}] {c['message']}")
    if not (kb.keys() - ka.keys()) and not (ka.keys() - kb.keys()):
        _say("  checks: no differences")
    return 0


def _catalog(name: str | None) -> int:
    from .parts import CATALOG
    if name:
        fn = CATALOG.get(name)
        if fn is None:
            print(f"no part named {name!r}. Available: "
                  + ", ".join(sorted(CATALOG)), file=sys.stderr)
            return 1
        _say(f"parts.{name}{inspect.signature(fn)}\n")
        _say(inspect.getdoc(fn) or "")
        return 0
    print("solidsight parametric parts catalog "
          "(use in models as parts.<name>(...)):\n")
    for key in CATALOG:
        fn = CATALOG[key]
        doc = (inspect.getdoc(fn) or "").splitlines()[0]
        _say(f"  parts.{key}{inspect.signature(fn)}")
        _say(f"      {doc}\n")
    print("Full docs for one part: solidsight catalog <name>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
