"""Assemble the deterministic clip report.

Same rules as solidsight's: relative paths, no timestamps, findings that
carry `where` and a `try:`. The report is the product; the renders are
evidence for what it says.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import metrics as M
from .bvh import forward_kinematics, parse_bvh
from .metrics import G_MM_S2 as G
from .render import render_frames, render_track


def _check(id_, level, message, where=None, suggestion=None) -> dict:
    c = {"id": id_, "level": level, "message": message}
    if where:
        c["where"] = where
    if suggestion:
        c["try"] = suggestion
    return c


def analyze(clip, up: str = "y", floor_mm: float | None = None,
            kind: str = "auto") -> dict:
    """Every measurement for one clip. Pure: no files touched.

    kind: "oneshot" silences the loop check (a jump is not supposed to
    loop), "loop" keeps it, "auto" reports it with the caveat. The tool
    cannot know the intent; the caller can, so let them declare it.
    """
    pos, rot = forward_kinematics(clip)
    names = clip.names
    dt = clip.frame_time

    k, _h = M._axis_indices(up)
    if floor_mm is None:
        # mocap is rarely authored at exactly 0, so the floor is
        # estimated — robustly, so that a penetration defect cannot
        # define the floor and hide itself (see infer_floor)
        floor_mm, floor_info = M.infer_floor(pos, up)
        floor_inferred = True
    else:
        floor_inferred = False
        floor_info = {"method": "declared by the caller"}

    deriv = M.derivatives(pos, dt)
    ang = M.angular_velocity(rot, dt)
    com, anthropometric = M.center_of_mass(pos, names)
    contact = M.contacts(pos, names, dt, up, floor_mm)
    bal = M.balance(pos, names, com, contact, up)
    pen = M.penetration(pos, names, up, floor_mm)
    smooth = M.smoothness(deriv, names, dt)
    loop = M.loop_continuity(pos, deriv, names, up)
    pk = M.peaks(deriv, ang, names, dt)
    ball = M.ballistics(com, bal.get("airborne_frames", []), dt, up)

    checks: list[dict] = []
    for s in contact.get("sliding", []):
        checks.append(_check(
            "foot-sliding", "warn",
            f"'{s['joint']}' slides while planted: {s['total_slip_mm']} mm "
            f"over {len(s['frames'])} frame(s)",
            where=f"worst at frame {s['worst_frame']}, "
                  f"{s['peak_speed_mm_s']} mm/s horizontal",
            suggestion="pin the foot over the contact: match the root's "
                       "forward speed to the stride, or add an IK "
                       "constraint on the planted frames"))
    for p in pen:
        checks.append(_check(
            "ground-penetration", "fail",
            f"'{p['joint']}' goes {p['max_depth_mm']} mm through the floor",
            where=f"worst at frame {p['worst_frame']}, "
                  f"{len(p['frames'])} frame(s) affected",
            suggestion="raise the root or re-key the limb over those "
                       "frames; a floor contact should stop AT the floor"))
    if smooth["pop_count"]:
        w = smooth["pops"][0]
        snaps = sum(1 for e in smooth["pops"] if e["kind"] == "pose snap")
        checks.append(_check(
            "motion-pop", "warn",
            f"{smooth['pop_count']} discontinuity event(s)"
            + (f" ({snaps} full pose snap(s) - a blocking pass or splice)"
               if snaps else "")
            + f"; worst is a {w['kind']} at frame {w['frames'][0]}",
            where=f"t={w['t_s']}s, {w['joints_hit']} joint(s) hit, worst "
                  f"'{w['worst_joint']}' at {w['worst_accel_mm_s2']} mm/s2 "
                  f"(robust z {w['worst_robust_z']})",
            suggestion="a pose snap needs inbetweens/easing at that "
                       "frame; a single joint pop is one bad key or "
                       "tangent"))
    for fl in ball["flights"]:
        r = fl["gravity_ratio"]
        if r < 0.1 or r > 8.0:
            checks.append(_check(
                "gravity-unit-suspect", "warn",
                f"flight at frames {fl['frames']} decelerates at "
                f"{r:.2f}x gravity - that is not an animation style, "
                f"that is probably the wrong --unit",
                where=f"effective g {fl['effective_gravity_mm_s2']} mm/s2",
                suggestion="check --unit (mocap is usually cm); a 10x "
                           "ratio is exactly one metric prefix"))
        elif r < 0.75:
            checks.append(_check(
                "floaty-flight", "warn",
                f"flight at frames {fl['frames']} falls at {r:.2f}x "
                f"gravity: it will read as floaty",
                where=f"apex +{fl['apex_rise_mm']} mm over "
                      f"{fl['duration_s']}s; at 1 g that apex takes "
                      f"{2.83 * (max(fl['apex_rise_mm'], 0.1) / G) ** 0.5:.2f}s "
                      f"of airtime",
                suggestion="physics fixes it two ways: shorten the "
                           "airtime to match the apex, or raise the apex "
                           "to match the airtime (T = 2*sqrt(2h/g)); or "
                           "accept the stylised float and say so"))
        elif r > 1.3:
            checks.append(_check(
                "heavy-flight", "warn",
                f"flight at frames {fl['frames']} falls at {r:.2f}x "
                f"gravity: it will read as heavy/rushed",
                where=f"apex +{fl['apex_rise_mm']} mm over "
                      f"{fl['duration_s']}s",
                suggestion="lengthen the airtime or raise the apex to "
                           "match 1 g, or accept the stylisation and "
                           "say so"))

    if not loop["loops_cleanly"] and kind != "oneshot":
        checks.append(_check(
            "loop-discontinuity", "warn",
            f"the seam jumps {loop['pose_gap_mm']['max']} mm, far more "
            f"than a normal frame ({loop['typical_frame_motion_mm']} mm)",
            where=f"worst joint '{loop['pose_gap_mm']['worst_joint']}' "
                  f"(root travel removed)",
            suggestion="if the clip is meant to loop, match the last frame "
                       "to one step before the first; if it is a one-shot, "
                       "ignore this"))
    if not anthropometric:
        checks.append(_check(
            "com-weights-unknown", "warn",
            "joint names were not recognisable, so the COM uses UNIFORM "
            "weights instead of segment masses",
            where=f"skeleton: {', '.join(names[:6])}...",
            suggestion="rename joints to conventional ones (hips, spine, "
                       "thigh, shin, foot...) or read balance as indicative"))

    status = "failed" if any(c["level"] == "fail" for c in checks) else \
        ("warnings" if checks else "ok")

    return {
        "status": status,
        "clip": {
            "source": clip.source, "frames": clip.n_frames,
            "fps": round(clip.fps, 4), "duration_s": round(clip.duration_s, 4),
            "joints": len(names), "unit": clip.unit, "up_axis": up,
            "floor_mm": round(floor_mm, 3),
            "floor_inferred": floor_inferred,
            "floor_estimate": floor_info,
        },
        "skeleton": {"root": clip.root.name, "joint_names": names},
        "com": {
            "anthropometric_weights": anthropometric,
            # the full trajectory goes to com_trajectory.csv, not here: a
            # 1000-frame clip would put 3000 floats into a report meant
            # to be READ; the numbers a reader acts on are the summary
            "trajectory_file": "com_trajectory.csv",
            "height_mm": {"min": round(float(com[:, k].min()), 2),
                          "max": round(float(com[:, k].max()), 2),
                          "mean": round(float(com[:, k].mean()), 2)},
        },
        "ballistics": ball,
        "kind": kind,
        "peaks": pk,
        "contacts": {
            "foot_joints": contact.get("foot_joints", []),
            "events": contact.get("events", []),
            "sliding": contact.get("sliding", []),
            "note": contact.get("note"),
        },
        "balance": bal,
        "penetration": pen,
        "smoothness": smooth,
        "loop": loop,
        "checks": checks,
        "_arrays": {"pos": pos, "com": com, "deriv": deriv, "ang": ang,
                    "floor": floor_mm},   # dropped before writing
    }


def inspect_clip(path: str | Path, out_dir: Path | None = None,
                 unit: str = "cm", up: str = "y",
                 floor_mm: float | None = None, n_frames: int = 6,
                 view: str = "side", size: int = 640,
                 kind: str = "auto", say=print) -> dict:
    """Parse, measure, render the evidence, write report.json."""
    clip = parse_bvh(path, unit=unit)
    rep = analyze(clip, up=up, floor_mm=floor_mm, kind=kind)
    arrays = rep.pop("_arrays")
    out = Path(out_dir) if out_dir else Path(path).parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    frames_dir = out / "frames"

    # the full COM trajectory, exact, one row per frame
    com_rows = ["frame,t_s,x_mm,y_mm,z_mm"]
    for f, p in enumerate(arrays["com"]):
        com_rows.append(f"{f},{f * clip.frame_time:.4f},"
                        + ",".join(f"{float(v):.2f}" for v in p))
    (out / "com_trajectory.csv").write_text("\n".join(com_rows) + "\n",
                                            encoding="utf-8")

    pos, com = arrays["pos"], arrays["com"]
    names = clip.names

    # which frames to render: evenly spaced, PLUS every frame a finding
    # points at (the evidence must be visible, not merely nearby)
    picks = set(np.linspace(0, clip.n_frames - 1, num=max(2, n_frames),
                            dtype=int).tolist())
    marks: dict[int, list[int]] = {}
    idx = {n: i for i, n in enumerate(names)}
    for s in rep["contacts"]["sliding"]:
        picks.add(s["worst_frame"])
        marks.setdefault(s["worst_frame"], []).append(idx[s["joint"]])
    for p in rep["penetration"]:
        picks.add(p["worst_frame"])
        marks.setdefault(p["worst_frame"], []).append(idx[p["joint"]])
    for p in rep["smoothness"]["pops"][:3]:
        f = p["frames"][0]
        picks.add(f)
        marks.setdefault(f, []).append(idx[p["worst_joint"]])

    written = render_frames(clip, pos, com, frames_dir,
                            sorted(picks), up, arrays["floor"],
                            view=view, size=size, marks=marks)

    # tracks: COM height always; a foot's height/speed when we have feet
    k, (h1, h2) = M._axis_indices(up)
    tracks = []
    render_track(com[:, k] - arrays["floor"], out / "track_com_height.png",
                 f"{clip.source} — COM height above floor", "mm",
                 clip.frame_time)
    tracks.append("track_com_height.png")

    feet = rep["contacts"]["foot_joints"]
    if feet:
        fj = idx[feet[0]]
        vel = arrays["deriv"]["velocity"]
        hs = np.hypot(vel[:, fj, h1], vel[:, fj, h2])
        slide_frames = [f for s in rep["contacts"]["sliding"]
                        if s["joint"] == feet[0] for f in s["frames"]]
        render_track(hs, out / "track_foot_speed.png",
                     f"{feet[0]} — horizontal speed (slides marked)",
                     "mm/s", clip.frame_time, marks=slide_frames)
        tracks.append("track_foot_speed.png")

    rep["files"] = {
        "report": "report.json",
        "frames": [f"frames/{n}" for n in written],
        "tracks": tracks,
    }
    (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n",
                                     encoding="utf-8")
    rep["_out_dir"] = str(out)
    return rep


def diff_reports(a: dict, b: dict) -> list[str]:
    """What changed between two takes — the numbers, not an impression."""
    lines = [f"diff: {a['clip']['source']} [{a['status']}] -> "
             f"{b['clip']['source']} [{b['status']}]"]
    ca, cb = a["clip"], b["clip"]
    if (ca["frames"], ca["fps"]) != (cb["frames"], cb["fps"]):
        lines.append(f"  timing: {ca['frames']} frames @ {ca['fps']} fps -> "
                     f"{cb['frames']} @ {cb['fps']}")

    na = set(a["skeleton"]["joint_names"])
    nb = set(b["skeleton"]["joint_names"])
    if na != nb:
        if nb - na:
            lines.append(f"  joints ADDED: {', '.join(sorted(nb - na))}")
        if na - nb:
            lines.append(f"  joints GONE:  {', '.join(sorted(na - nb))}")

    for name in sorted(na & nb):
        pa, pb = a["peaks"][name], b["peaks"][name]
        d = pb["peak_speed_mm_s"] - pa["peak_speed_mm_s"]
        if abs(d) > max(1.0, 0.05 * max(pa["peak_speed_mm_s"], 1.0)):
            lines.append(
                f"  '{name}': peak speed {pa['peak_speed_mm_s']} -> "
                f"{pb['peak_speed_mm_s']} mm/s ({d:+.1f})")

    ida = {(c["id"], c["message"]) for c in a["checks"]}
    idb = {(c["id"], c["message"]) for c in b["checks"]}
    for cid, msg in sorted(idb - ida, key=str):
        lines.append(f"  NEW  [{cid}] {msg}")
    for cid, msg in sorted(ida - idb, key=str):
        lines.append(f"  GONE [{cid}] {msg}")
    if len(lines) == 1:
        lines.append("  no differences worth reporting")
    return lines
