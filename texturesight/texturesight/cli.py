"""texturesight CLI — UV and texture review as measurement."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .errors import TextureSightError

_ASCII_FOLD = {ord(a): b for a, b in
               [("—", "-"), ("–", "-"), ("°", " deg"), ("·", "-"),
                ("…", "..."), ("×", "x"), ("→", "->")]}


def _say(text: str, err: bool = False) -> None:
    print(text.translate(_ASCII_FOLD), file=sys.stderr if err else sys.stdout,
          flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="texturesight",
        description="UV and texture review for AI agents: a mesh and its "
                    "maps in, exact measurements + evidence renders out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inspect",
                       help="audit a mesh's UVs and/or its texture maps")
    i.add_argument("--mesh", default=None, help="an unwrapped .obj")
    i.add_argument("--texture", action="append", default=[], metavar="IMG",
                   help="a texture map (repeatable)")
    i.add_argument("--kind", default="auto",
                   choices=["auto", "albedo", "normal", "roughness",
                            "metallic", "ao", "height"],
                   help="what the textures are (default: guess from the "
                        "filename, and the report says it guessed)")
    i.add_argument("--texture-px", type=int, default=1024,
                   help="texture size to compute texel density against "
                        "(default 1024)")
    i.add_argument("--out", default="out", help="output dir (default: ./out)")
    i.add_argument("--json", action="store_true")

    df = sub.add_parser("diff",
                        help="what changed between two inspect outputs")
    df.add_argument("a", help="the 'before' out dir (with report.json)")
    df.add_argument("b", help="the 'after' out dir")

    sub.add_parser("install-skill", help="(re)install the Claude Code skill")
    sub.add_parser("uninstall", help="remove the skill AND the package")
    sub.add_parser("version")

    args = p.parse_args(argv)

    if args.cmd not in ("install-skill", "uninstall"):
        from .skill_install import maybe_autoinstall
        maybe_autoinstall()

    try:
        if args.cmd == "version":
            _say(f"texturesight {__version__}")
            return 0
        if args.cmd == "install-skill":
            from .skill_install import install_skill
            install_skill()
            return 0
        if args.cmd == "uninstall":
            from .skill_install import uninstall
            return uninstall()
        if args.cmd == "diff":
            return _diff(args)
        return _inspect(args)
    except TextureSightError as e:
        _say(f"FAILED\n{e.render()}", err=True)
        return 1


def _diff(args) -> int:
    import json as _json
    from pathlib import Path

    from .report import diff_reports
    reps = []
    for d in (args.a, args.b):
        p = Path(d) / "report.json"
        if not p.exists():
            _say(f"FAILED\ndiff-error: no report.json in {d}\n"
                 f"  try:   run `texturesight inspect ... --out {d}` first",
                 err=True)
            return 1
        reps.append(_json.loads(p.read_text(encoding="utf-8")))
    for line in diff_reports(*reps):
        _say(line)
    return 0


def _inspect(args) -> int:
    from pathlib import Path

    from .report import inspect
    if not args.mesh and not args.texture:
        _say("FAILED\nargument-error: nothing to inspect\n"
             "  try:   --mesh model.obj and/or --texture albedo.png",
             err=True)
        return 1

    rep = inspect(args.mesh, args.texture, Path(args.out),
                  texture_px=args.texture_px, kind=args.kind)
    out = rep.pop("_out_dir")
    if args.json:
        print(json.dumps(rep, indent=2))
        return 2 if rep["status"] == "failed" else 0

    _say(f"texturesight inspect: {rep['status'].upper()}")
    if "uv" in rep:
        u = rep["uv"]
        m, d = u["mesh"], u["texel_density"]
        _say(f"  mesh: {m['source']} - {m['faces']} faces, "
             f"{m['uv_coords']} uvs, material(s): {', '.join(m['materials'])}")
        if "px_per_unit" in d:
            _say(f"  texel density @ {u['assumed_texture_px']}px: "
                 f"{d['px_per_unit']['area_weighted_mean']} px/unit mean "
                 f"({d['px_per_unit']['p2']}..{d['px_per_unit']['p98']}), "
                 f"spread {d['spread_ratio']}x")
        a = u["distortion"]["anisotropy"]
        _say(f"  distortion: anisotropy median {a['median']}, p95 "
             f"{a['p95']}, max {a['max']}; "
             f"{u['distortion']['flipped_face_count']} flipped face(s)")
        i_, pk = u["islands"], u["packing"]
        _say(f"  layout: {i_['uv_islands']} island(s) over "
             f"{i_['mesh_shells']} mesh shell(s), {i_['seam_edges']} seam "
             f"edge(s) ({i_['seam_length_3d']} of 3D length)")
        _say(f"  packing: {pk['utilization'] * 100:.0f}% of the UV square "
             f"used, {pk['overlap_cells']} overlap cell(s)")

    for t in rep.get("textures", []):
        b = t["basics"]
        _say(f"  texture: {b['name']} - {b['size_px'][0]}x{b['size_px'][1]}"
             f", {b['channels']}ch, kind={t['kind']} ({t['kind_source']})"
             + ("" if b["power_of_two"] else "  [not power-of-two]"))
        tl = t["tiling"]
        _say(f"      tiling: {'YES' if tl['tiles'] else 'NO'} "
             f"(h {tl['horizontal']['ratio']}x, v {tl['vertical']['ratio']}x "
             f"vs its own interior)")
        if "normal_map" in t:
            n = t["normal_map"]
            _say(f"      normal: |n| mean {n['unit_length']['mean']}, "
                 f"Z mean {n['z_channel']['mean']}, green looks like "
                 f"{n['green_convention']['likely']}")
        if "channel" in t:
            c = t["channel"]
            _say(f"      values: {c['min']}..{c['max']} (p1 "
                 f"{c['percentiles']['p1']}, p99 {c['percentiles']['p99']}), "
                 f"{c['distinct_levels_of_256']}/256 levels used")

    for chk in [c for c in rep["checks"] if c["level"] == "fail"] + \
               [c for c in rep["checks"] if c["level"] == "warn"]:
        _say(f"  [{chk['level'].upper()}] {chk['message']}")
        if chk.get("where"):
            _say(f"         where: {chk['where']}")
        if chk.get("try"):
            _say(f"         try:   {chk['try']}")

    _say(f"  report: {out}/report.json")
    for r in rep["files"]["renders"]:
        _say(f"  render: {out}/{r}")
    if rep["files"]["renders"]:
        _say("  NEXT: LOOK at uv_layout.png (red = flipped, orange = "
             "stretched) and uv_density.png, then read report.json.")
    return 2 if rep["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
