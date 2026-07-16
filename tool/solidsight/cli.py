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
    _add_build_flags(b)

    w = sub.add_parser("watch",
                       help="live mode: rebuild + refresh outputs whenever "
                            "the model (or a sibling .py) changes")
    _add_build_flags(w)
    w.add_argument("--poll", type=float, default=0.5,
                   help="seconds between file checks (default 0.5)")

    v = sub.add_parser("view",
                       help="interactive browser viewer (orbit, isolate, "
                            "sections, explode, measure) with live reload")
    _add_build_flags(v)
    v.add_argument("--port", type=int, default=8377,
                   help="HTTP port (default 8377; falls back to a free one)")
    v.add_argument("--no-watch", action="store_true",
                   help="serve the current build only, do not watch sources")
    v.add_argument("--poll", type=float, default=0.5,
                   help="seconds between file checks (default 0.5)")

    c = sub.add_parser("catalog", help="list the parametric parts catalog")
    c.add_argument("name", nargs="?", help="show full docs for one part")

    co = sub.add_parser("components",
                        help="search the offline real-world component "
                             "database (fasteners, bearings, motors ...)")
    cosub = co.add_subparsers(dest="cop", required=True)
    cos = cosub.add_parser("search", help="rank components against a query")
    cos.add_argument("query", nargs="+", help='e.g. "m4 socket head"')
    cos.add_argument("--json", action="store_true")
    coh = cosub.add_parser("show", help="datasheet + model call for one id")
    coh.add_argument("id")
    coh.add_argument("--json", action="store_true")

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

    asm = sub.add_parser("assembly",
                         help="BOM, per-axis play and a suggested assembly "
                              "sequence for a multi-part model")
    asm.add_argument("model", help="path to the .py model file")
    asm.add_argument("--json", action="store_true")

    ft = sub.add_parser("fit",
                        help="ISO 286 limits & fits: solidsight fit 8 H7 g6")
    ft.add_argument("nominal", type=float, help="nominal size in mm")
    ft.add_argument("hole", help="hole grade, H-basis (H6/H7/H8)")
    ft.add_argument("shaft", help="shaft grade (e/f/g/h/k/n/p + 6/7/8)")
    ft.add_argument("--json", action="store_true")

    ex = sub.add_parser("explain",
                        help="design review: what a check id means, the "
                             "evidence to gather, and the fix menu")
    ex.add_argument("check_id", nargs="?",
                    help="a check id from report.json (omit to list all)")

    rb = sub.add_parser("robot",
                        help="export declared joint()s as URDF (+SDF) with "
                             "real inertials and collision meshes")
    rb.add_argument("model", help="path to the .py model file")
    rb.add_argument("--out", default=None,
                    help="output directory (default: <model dir>/out)")
    rb.add_argument("--sdf", action="store_true", help="also write SDF 1.7")
    rb.add_argument("--density", type=float, default=1.24,
                    help="material density g/cm3 for mass/inertia "
                         "(default 1.24 = solid PLA)")

    dr = sub.add_parser("drawing",
                        help="technical drawing: dimensioned third-angle "
                             "multi-view PDF per part")
    dr.add_argument("model", help="path to the .py model file")
    dr.add_argument("--part", default=None, help="one named part only")
    dr.add_argument("--out", default=None,
                    help="output directory (default: <model dir>/out)")

    cv = sub.add_parser("convert",
                        help="convert between mesh formats "
                             "(stl/obj/ply/3mf/glb/off)")
    cv.add_argument("src", help="input mesh file")
    cv.add_argument("dst", help="output mesh file (format from extension)")

    _add_query_parser(sub)

    sub.add_parser("version", help="print version")

    args = parser.parse_args(argv)
    return _dispatch(parser, args)


def _add_build_flags(b) -> None:
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
    b.add_argument("--obj", action="store_true",
                   help="export OBJ per part + combined")
    b.add_argument("--glb", action="store_true",
                   help="export GLB per part + a combined scene that keeps "
                        "part names and colors")
    b.add_argument("--dxf", action="store_true",
                   help="export each --slice outline as DXF (2D CAD)")
    b.add_argument("--svg", action="store_true",
                   help="export each --slice outline as SVG")
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
    b.add_argument("--progress", action="store_true",
                   help="stream live per-stage progress lines to stderr "
                        "(model, metrics, pairs, renders, exports)")
    b.add_argument("--events", default=None, metavar="PATH",
                   help="stream structured NDJSON build events to a file "
                        "(one JSON object per line, written live)")


def _add_query_parser(sub) -> None:
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

    qd = qsub.add_parser("distance", parents=[common],
                         help="exact minimum distance between two parts")
    qd.add_argument("a", help="first part name")
    qd.add_argument("b", help="second part name")

    qv = qsub.add_parser("voxels", parents=[common],
                         help="boolean voxel grid + sealed-cavity detection")
    qv.add_argument("--res", type=float, default=None,
                    help="voxel size in mm (default: max dimension / 64)")
    qv.add_argument("--layer", default=None,
                    help="print one Z layer as ASCII (index or 'all')")


def _dispatch(parser, args) -> int:
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
    if args.command == "convert":
        return _convert(Path(args.src), Path(args.dst))
    if args.command == "assembly":
        return _assembly(args)
    if args.command == "fit":
        from .fits import fit
        try:
            res = fit(args.nominal, args.hole, args.shaft)
        except SolidsightError as e:
            _say(f"FIT FAILED\n{e.render()}", err=True)
            return 1
        if args.json:
            print(json.dumps(res, indent=2))
            return 0
        _say(f"fit {args.nominal:g} {args.hole}/{args.shaft}: "
             f"{res['type'].upper()}")
        _say(f"  hole:  {res['hole']}")
        _say(f"  shaft: {res['shaft']}")
        _say(f"  clearance: {res['clearance_min_mm']} .. "
             f"{res['clearance_max_mm']} mm "
             + ("(negative = interference)"
                if res['clearance_min_mm'] < 0 else ""))
        _say(f"  note: {res['printing_note']}")
        return 0
    if args.command == "explain":
        from .explain import all_ids, explain
        if not args.check_id:
            _say("check ids: " + ", ".join(all_ids()))
            return 0
        e = explain(args.check_id)
        if e is None:
            _say(f"no explanation for {args.check_id!r}. Known: "
                 + ", ".join(all_ids()), err=True)
            return 1
        _say(f"{args.check_id}")
        _say(f"  meaning:  {e['meaning']}")
        _say(f"  evidence: {e['evidence']}")
        for i, f in enumerate(e["fixes"], 1):
            _say(f"  fix {i}:    {f}")
        return 0
    if args.command == "robot":
        from .robot import export_urdf
        from .runner import run_model
        model = Path(args.model)
        try:
            scene = run_model(model)
            export_urdf(scene,
                        Path(args.out) if args.out else model.parent / "out",
                        model.name, density=args.density, sdf=args.sdf,
                        say=_say)
            return 0
        except SolidsightError as e:
            _say(f"ROBOT EXPORT FAILED\n{e.render()}", err=True)
            return 1
    if args.command == "drawing":
        from .drawings import run_drawing
        model = Path(args.model)
        try:
            return run_drawing(model,
                               Path(args.out) if args.out
                               else model.parent / "out",
                               args.part, say=_say)
        except SolidsightError as e:
            _say(f"DRAWING FAILED\n{e.render()}", err=True)
            return 1
    if args.command == "catalog":
        return _catalog(args.name)
    if args.command == "components":
        return _components(args)
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
    if args.command == "watch":
        return _watch(args)
    if args.command == "view":
        return _view(args)
    parser.print_help()
    return 0


# ---------------------------------------------------------------------------

def _attach_sinks(args):
    """Wire --progress / --events sinks; returns the ndjson sink or None."""
    ndjson = None
    if getattr(args, "progress", False):
        from .events import BUS, console_sink
        BUS.add_sink(console_sink())
    if getattr(args, "events", None):
        from .events import BUS, ndjson_sink
        Path(args.events).parent.mkdir(parents=True, exist_ok=True)
        ndjson = ndjson_sink(args.events)
        BUS.add_sink(ndjson)
    return ndjson


def _parse_build_kwargs(args) -> dict | None:
    """Shared by build/watch: turn CLI flags into build_model kwargs.
    Returns None (after printing the error) on a malformed flag."""
    model = Path(args.model)
    slices = []
    for s in args.slice:
        try:
            axis, val = s.split("=", 1)
            slices.append((axis.strip().lower(), float(val)))
        except ValueError:
            _say(f"BUILD FAILED\nbad --slice {s!r}\n  try: --slice z=5",
                 err=True)
            return None

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
            return None

    return dict(
        out_dir=Path(args.out) if args.out else model.parent / "out",
        mode="print-safe" if args.print_safe else "free",
        views=[v.strip() for v in args.views.split(",") if v.strip()],
        turntable=args.turntable,
        slices=slices,
        only_parts=([p.strip() for p in args.part.split(",")]
                    if args.part else None),
        export_stl=args.stl,
        export_3mf=args.threemf,
        export_obj=args.obj,
        export_glb=args.glb,
        export_dxf=args.dxf,
        export_svg=args.svg,
        size=args.size,
        min_wall=args.min_wall,
        max_overhang=args.max_overhang,
        allow_multiple_shells=args.allow_multiple_shells,
        exploded=args.exploded,
        focus=focus,
    )


def _build(args) -> int:
    from .report import build_model
    mode = "print-safe" if args.print_safe else "free"
    ndjson = _attach_sinks(args)
    kwargs = _parse_build_kwargs(args)
    if kwargs is None:
        return 1

    try:
        report = build_model(model_path=Path(args.model), **kwargs)
    finally:
        if ndjson is not None:
            ndjson.close()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report)

    if report["status"] == "failed" and mode == "print-safe":
        return 2
    return 0


def _watch(args) -> int:
    from .watch import run_watch
    ndjson = _attach_sinks(args)
    kwargs = _parse_build_kwargs(args)
    if kwargs is None:
        return 1
    try:
        return run_watch(Path(args.model), kwargs, say=_say,
                         poll_s=args.poll)
    finally:
        if ndjson is not None:
            ndjson.close()


def _view(args) -> int:
    from .viewer import run_view
    ndjson = _attach_sinks(args)
    kwargs = _parse_build_kwargs(args)
    if kwargs is None:
        return 1
    try:
        return run_view(Path(args.model), kwargs, say=_say, port=args.port,
                        watch=not args.no_watch, poll_s=args.poll)
    except SolidsightError as e:
        _say(f"VIEW FAILED\n{e.render()}", err=True)
        return 1
    finally:
        if ndjson is not None:
            ndjson.close()


def _print_summary(report: dict) -> None:
    _say(f"solidsight build: {report['status'].upper()}  "
          f"(mode: {report['mode']})")
    sc = report["scene"]
    _say(f"  scene: {sc['part_count']} part(s), "
          f"{sc['size'][0]} x {sc['size'][1]} x {sc['size'][2]} mm, "
          f"{sc['total_volume_mm3']} mm3")
    for name, p in report["parts"].items():
        if p.get("ghost"):
            _say(f"  part '{name}': GHOST reference volume, "
                 f"{p['volume_mm3']} mm3")
            continue
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

    if args.op == "distance":
        pa, pb = scene.get(args.a).solid, scene.get(args.b).solid
        inter = pa.manifold ^ pb.manifold
        vol = float(inter.volume())
        if vol > 1e-3:
            bb = inter.bounding_box()
            res = {"a": args.a, "b": args.b, "status": "collision",
                   "overlap_volume_mm3": round(vol, 3),
                   "overlap_bbox": {
                       "min": [round(float(v), 3) for v in bb[:3]],
                       "max": [round(float(v), 3) for v in bb[3:]]}}
        else:
            diag = max(scene.combined().size) * 2 + 1
            gap = round(float(pa.manifold.min_gap(pb.manifold, diag)), 4)
            res = {"a": args.a, "b": args.b,
                   "status": "touching" if gap <= 0.05 else "clear",
                   "min_distance_mm": gap}
        if args.json:
            print(json.dumps(res, indent=2))
        elif res["status"] == "collision":
            _say(f"'{args.a}' and '{args.b}' COLLIDE: "
                 f"{res['overlap_volume_mm3']} mm3 of overlap at "
                 f"{res['overlap_bbox']['min']}..{res['overlap_bbox']['max']}")
        else:
            _say(f"'{args.a}' <-> '{args.b}': {res['status']}, minimum "
                 f"distance {res['min_distance_mm']} mm")
        return 0

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
    """Compare two build outputs: per-part geometry deltas, checks that
    appeared or disappeared, and pixel differences between matching renders."""
    reports, render_dirs = [], []
    for p in (path_a, path_b):
        if p.is_dir():
            p = p / "report.json"
        if not p.exists():
            _say(f"DIFF FAILED\nno report at {p}\n"
                 "  try: point at an out/ dir or its report.json", err=True)
            return 1
        reports.append(json.loads(p.read_text(encoding="utf-8")))
        render_dirs.append(p.parent / "renders")
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

    da, db = render_dirs
    if da.is_dir() and db.is_dir():
        shared = sorted({f.name for f in da.glob("*.png")}
                        & {f.name for f in db.glob("*.png")})
        for name in shared:
            try:
                import numpy as np
                from PIL import Image
                ia = np.asarray(Image.open(da / name).convert("RGB"), int)
                ib = np.asarray(Image.open(db / name).convert("RGB"), int)
                if ia.shape != ib.shape:
                    _say(f"  render {name}: different sizes")
                    continue
                changed = (np.abs(ia - ib).max(axis=2) > 8).mean() * 100
                _say(f"  render {name}: "
                     + ("identical" if changed == 0
                        else f"{changed:.1f}% of pixels differ"))
            except Exception as e:
                _say(f"  render {name}: could not compare ({e})")
    return 0


def _assembly(args) -> int:
    from .assembly import pair_analysis
    from .bom import assembly_sequence, axis_play, bom
    from .runner import run_model
    try:
        scene = run_model(Path(args.model))
        pairs, _checks = pair_analysis(scene)
        rows = bom(scene)
        play = axis_play(scene)
        seq = assembly_sequence(scene, pairs)
    except SolidsightError as e:
        _say(f"ASSEMBLY FAILED\n{e.render()}", err=True)
        return 1
    if args.json:
        print(json.dumps({"bom": rows, "axis_play": play,
                          "sequence": seq}, indent=2))
        return 0
    _say("BILL OF MATERIALS")
    for r in rows:
        ghost = "  (ghost/reference)" if r["ghost"] else ""
        _say(f"  {r['count']} x {r['item']}  "
             f"[{', '.join(r['names'])}]  "
             f"{r['grams_pla_each']} g PLA each{ghost}")
    _say("AXIS PLAY (bbox gaps between consecutive parts)")
    for axis, d in play.items():
        gaps = "; ".join(f"{g['after']} -> {g['before']}: {g['gap_mm']} mm"
                         for g in d["gaps"]) or "none"
        _say(f"  {axis}: total {d['total_play_mm']} mm  ({gaps})")
    _say("SUGGESTED SEQUENCE (bottom-up heuristic; check the exploded "
         "render)")
    for s in seq:
        _say(f"  {s['step']}. {s['part']} — {s['note']}")
    return 0


def _components(args) -> int:
    from .components_db import DATABASE, make_expression, search
    if args.cop == "search":
        hits = search(" ".join(args.query))
        if args.json:
            print(json.dumps(hits, indent=2))
            return 0
        if not hits:
            _say("no matches. Try broader words (e.g. 'bearing', 'm4', "
                 "'nema17', 'pulley', 'rail').", err=True)
            return 1
        for e in hits:
            _say(f"  {e['id']:20s} {e['name']}  [{e['standard']}]")
            _say(f"  {'':20s} -> {make_expression(e)}"
                 + (f"   | {e['note']}" if e["note"] else ""))
        return 0
    if args.cop == "show":
        e = DATABASE.get(args.id)
        if e is None:
            hits = search(args.id.replace("_", " "), limit=3)
            _say(f"no component {args.id!r}."
                 + (" Close: " + ", ".join(h["id"] for h in hits)
                    if hits else ""), err=True)
            return 1
        if args.json:
            print(json.dumps(e, indent=2))
            return 0
        _say(f"{e['id']}: {e['name']}  [{e['standard']}]")
        _say(f"  kind: {e['kind']}")
        if e["note"]:
            _say(f"  dims: {e['note']}")
        for k, v in e["free_params"].items():
            _say(f"  free: {k} — {v}")
        _say(f"  model: {make_expression(e)}")
        _say(f'  or:    parts.component("{e["id"]}"'
             + (", length=...)" if "length" in e["free_params"] else ")"))
        return 0
    return 1


def _convert(src: Path, dst: Path) -> int:
    """Mesh format conversion via trimesh (STEP/IGES need a BREP kernel —
    out of core scope; a plugin can register them)."""
    import trimesh
    brep = {".step", ".stp", ".iges", ".igs"}
    if src.suffix.lower() in brep or dst.suffix.lower() in brep:
        _say("CONVERT FAILED\nSTEP/IGES are BREP formats - the mesh kernel "
             "cannot read or write them faithfully\n"
             "  try: a BREP tool (FreeCAD, build123d) or a solidsight "
             "plugin that registers a STEP exporter", err=True)
        return 1
    if not src.exists():
        _say(f"CONVERT FAILED\nno such file: {src}", err=True)
        return 1
    try:
        mesh = trimesh.load(str(src), force="mesh")
        if mesh.is_empty or len(mesh.faces) == 0:
            raise ValueError("no triangles in input")
        dst.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(dst))
    except Exception as e:
        _say(f"CONVERT FAILED\n{type(e).__name__}: {e}\n"
             "  try: supported formats are stl, obj, ply, 3mf, glb, off",
             err=True)
        return 1
    _say(f"converted {src.name} -> {dst}  "
         f"({len(mesh.faces)} triangles, watertight: {mesh.is_watertight})")
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
