"""animationsight CLI — animation review as measurement."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .errors import AnimationSightError

_ASCII_FOLD = {ord(a): b for a, b in
               [("—", "-"), ("–", "-"), ("°", " deg"),
                ("·", "-"), ("…", "..."), ("×", "x"),
                ("→", "->")]}


def _say(text: str, err: bool = False) -> None:
    print(text.translate(_ASCII_FOLD), file=sys.stderr if err else sys.stdout,
          flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="animationsight",
        description="Animation review for AI agents: a clip in, exact "
                    "motion measurements + evidence renders out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--unit", default="cm",
                        choices=["mm", "cm", "m", "in"],
                        help="what the file's numbers mean (BVH does not "
                             "say; mocap is usually cm)")
    common.add_argument("--up", default="y", choices=["x", "y", "z"],
                        help="vertical axis (BVH convention is y)")
    common.add_argument("--floor", type=float, default=None, metavar="MM",
                        help="floor height (default: inferred robustly - "
                             "the 10th percentile of the per-frame lowest "
                             "point, so a penetration cannot hide itself)")

    i = sub.add_parser("inspect", parents=[common],
                       help="measure a clip: report.json + evidence frames")
    i.add_argument("clip", help="path to a .bvh file")
    i.add_argument("--out", default=None, help="output dir (default: ./out)")
    i.add_argument("--frames", type=int, default=6,
                   help="evenly spaced frames to render (flagged frames "
                        "are always added on top; default 6)")
    i.add_argument("--view", default="side",
                   choices=["side", "front", "top"])
    i.add_argument("--size", type=int, default=640)
    i.add_argument("--kind", default="auto",
                   choices=["auto", "oneshot", "loop"],
                   help="declare the intent: 'oneshot' (jump, hit, "
                        "gesture) silences the loop-seam check, 'loop' "
                        "keeps it strict, 'auto' reports with a caveat")
    i.add_argument("--json", action="store_true",
                   help="full report JSON on stdout")

    d = sub.add_parser("diff", parents=[common],
                       help="what changed between two takes")
    d.add_argument("a")
    d.add_argument("b")

    t = sub.add_parser("track", parents=[common],
                       help="print one joint's per-frame numbers")
    t.add_argument("clip")
    t.add_argument("joint")
    t.add_argument("--json", action="store_true")

    sub.add_parser("install-skill", help="(re)install the Claude Code skill")
    sub.add_parser("uninstall", help="remove the skill AND the package")
    sub.add_parser("version")

    args = p.parse_args(argv)

    if args.cmd not in ("install-skill", "uninstall"):
        from .skill_install import maybe_autoinstall
        maybe_autoinstall()

    try:
        return _dispatch(args)
    except AnimationSightError as e:
        _say(f"FAILED\n{e.render()}", err=True)
        return 1


def _dispatch(args) -> int:
    if args.cmd == "version":
        _say(f"animationsight {__version__}")
        return 0
    if args.cmd == "install-skill":
        from .skill_install import install_skill
        install_skill()
        return 0
    if args.cmd == "uninstall":
        from .skill_install import uninstall
        return uninstall()
    if args.cmd == "inspect":
        return _inspect(args)
    if args.cmd == "diff":
        return _diff(args)
    if args.cmd == "track":
        return _track(args)
    return 1


def _inspect(args) -> int:
    from .report import inspect_clip
    rep = inspect_clip(args.clip, out_dir=args.out, unit=args.unit,
                       up=args.up, floor_mm=args.floor,
                       n_frames=args.frames, view=args.view,
                       size=args.size, kind=args.kind, say=_say)
    out = rep.pop("_out_dir")
    if args.json:
        print(json.dumps(rep, indent=2))
        return 2 if rep["status"] == "failed" else 0

    c = rep["clip"]
    _say(f"animationsight inspect: {rep['status'].upper()}")
    _say(f"  clip: {c['source']} - {c['frames']} frames @ {c['fps']} fps "
         f"({c['duration_s']}s), {c['joints']} joints, {c['unit']}, "
         f"up={c['up_axis']}")
    if c["floor_inferred"]:
        fe = c["floor_estimate"]
        extra = ""
        if fe.get("frames_below_floor"):
            extra = f", {fe['frames_below_floor']} frame(s) below it"
        _say(f"  floor: {c['floor_mm']} mm  (inferred: {fe['method']}"
             f"{extra})")
    else:
        _say(f"  floor: {c['floor_mm']} mm  (declared)")
    com = rep["com"]
    _say(f"  COM height: {com['height_mm']['min']}..{com['height_mm']['max']}"
         f" mm (mean {com['height_mm']['mean']})"
         + ("" if com["anthropometric_weights"]
            else "   [UNIFORM weights - joint names unrecognised]"))
    ct = rep["contacts"]
    if ct["foot_joints"]:
        _say(f"  contacts: {len(ct['events'])} plant/lift event(s) on "
             f"{', '.join(ct['foot_joints'])}")
    b = rep["balance"]
    if b.get("com_to_support_mm", {}).get("max") is not None:
        _say(f"  balance: COM up to {b['com_to_support_mm']['max']} mm from "
             f"the support base; airborne {b['airborne_ratio'] * 100:.0f}% "
             f"of frames")
    s = rep["smoothness"]
    _say(f"  smoothness: roughest joint '{s['roughest_joint']}' "
         f"(jerk RMS {s['roughest_jerk_rms_mm_s3']} mm/s3), "
         f"{s['pop_count']} pop(s)")
    for fl in rep["ballistics"]["flights"]:
        _say(f"  flight: frames {fl['frames'][0]}..{fl['frames'][1]} "
             f"({fl['duration_s']}s, apex +{fl['apex_rise_mm']} mm) -> "
             f"{fl['gravity_ratio']}x gravity")
    lp = rep["loop"]
    _say(f"  loop: {'CLEAN' if lp['loops_cleanly'] else 'DISCONTINUOUS'} "
         f"- {lp['convention']}; seam gap {lp['pose_gap_mm']['max']} mm vs "
         f"{lp['typical_frame_motion_mm']} mm in a normal frame")

    for chk in [c for c in rep["checks"] if c["level"] == "fail"] + \
               [c for c in rep["checks"] if c["level"] == "warn"]:
        _say(f"  [{chk['level'].upper()}] {chk['message']}")
        if chk.get("where"):
            _say(f"         where: {chk['where']}")
        if chk.get("try"):
            _say(f"         try:   {chk['try']}")

    _say(f"  report: {out}/report.json")
    for f in rep["files"]["frames"]:
        _say(f"  frame:  {out}/{f}")
    for t in rep["files"]["tracks"]:
        _say(f"  track:  {out}/{t}")
    for a_ in rep["files"].get("flight_arcs", []):
        _say(f"  arc:    {out}/{a_}  (ghosted flight + measured arc vs 1 g)")
    _say("  NEXT: LOOK at the flagged frames and the tracks, then read "
         "report.json checks.")
    return 2 if rep["status"] == "failed" else 0


def _diff(args) -> int:
    from .bvh import parse_bvh
    from .report import analyze, diff_reports
    reps = []
    for path in (args.a, args.b):
        clip = parse_bvh(path, unit=args.unit)
        r = analyze(clip, up=args.up, floor_mm=args.floor)
        r.pop("_arrays")
        reps.append(r)
    for line in diff_reports(*reps):
        _say(line)
    return 0


def _track(args) -> int:
    import numpy as np

    from .bvh import forward_kinematics, parse_bvh
    from .metrics import derivatives
    clip = parse_bvh(args.clip, unit=args.unit)
    if args.joint not in clip.names:
        from .errors import BadArgumentError
        raise BadArgumentError(
            f"no joint named {args.joint!r}",
            where=f"skeleton: {', '.join(clip.names)}",
            suggestion="use one of those names")
    pos, _rot = forward_kinematics(clip)
    j = clip.names.index(args.joint)
    d = derivatives(pos, clip.frame_time)
    speed = np.linalg.norm(d["velocity"][:, j], axis=1)
    rows = [{"frame": int(f), "t_s": round(f * clip.frame_time, 4),
             "pos_mm": [round(float(v), 2) for v in pos[f, j]],
             "speed_mm_s": round(float(speed[f]), 2)}
            for f in range(clip.n_frames)]
    if args.json:
        print(json.dumps({"joint": args.joint, "samples": rows}, indent=2))
        return 0
    _say(f"track '{args.joint}' - {clip.n_frames} frames @ {clip.fps:.1f} fps")
    _say("  frame     t_s        x        y        z    speed_mm_s")
    for r in rows:
        x, y, z = r["pos_mm"]
        _say(f"  {r['frame']:5d}  {r['t_s']:7.3f}  {x:7.1f}  {y:7.1f}  "
             f"{z:7.1f}  {r['speed_mm_s']:10.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
