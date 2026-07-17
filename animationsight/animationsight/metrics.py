"""Motion as measurement.

Everything an animator judges by eye, computed exactly instead:
velocities and their derivatives, angular rates, balance against the
support polygon, contact events, foot sliding, ground penetration,
smoothness and loop continuity.

Conventions: positions in mm, time in seconds, angles in degrees.
The up axis is declared by the caller (BVH is usually Y-up) — nothing
here guesses it.
"""

from __future__ import annotations

import numpy as np

# Dempster's segment mass fractions (classical biomechanics, of total
# body mass). Applied by matching joint names; when the skeleton does
# not name things recognisably we fall back to uniform weights AND the
# report says so, because a COM from the wrong weights is a wrong COM.
SEGMENT_MASS = {
    "head": 0.081, "neck": 0.081,
    "hips": 0.142, "pelvis": 0.142, "spine": 0.139, "chest": 0.216,
    "abdomen": 0.139, "torso": 0.355,
    "shoulder": 0.028, "arm": 0.028, "upperarm": 0.028,
    "forearm": 0.016, "elbow": 0.016,
    "hand": 0.006, "wrist": 0.006,
    "thigh": 0.100, "upleg": 0.100, "hip": 0.100,
    "shin": 0.0465, "calf": 0.0465, "leg": 0.0465, "knee": 0.0465,
    "foot": 0.0145, "ankle": 0.0145, "toe": 0.0145,
}

# thresholds (mm, mm/s) — documented, not magic
CONTACT_HEIGHT_MM = 30.0      # a foot within this of the floor is down
CONTACT_SPEED_MMS = 120.0     # ... and moving slower than this
SLIDE_SPEED_MMS = 50.0        # horizontal speed while planted = sliding
PENETRATION_MM = 5.0          # below the floor by more than this = through it


def _axis_indices(up: str) -> tuple[int, tuple[int, int]]:
    """(vertical index, the two horizontal indices)."""
    k = {"x": 0, "y": 1, "z": 2}[up.lower()]
    return k, tuple(i for i in (0, 1, 2) if i != k)


def infer_floor(pos: np.ndarray, up: str) -> tuple[float, dict]:
    """Estimate the floor height from the motion itself.

    NOT the clip's lowest point: a foot that punches through the floor
    is exactly what we are looking for, and taking the minimum would
    silently redefine the floor as the bottom of the defect — making it
    undetectable. (That is not hypothetical; it is what the first
    version of this function did, and the injected 40 mm penetration in
    examples/01-walk vanished.)

    Instead: take the lowest point of the skeleton in each frame, and
    read a low percentile of that series. Anything standing on the floor
    parks that value at the floor for a large share of frames, while a
    defect (rare by nature) sits below the percentile and stays visible.
    """
    k, _h = _axis_indices(up)
    per_frame_min = pos[:, :, k].min(axis=1)
    floor = float(np.percentile(per_frame_min, 10.0))
    below = per_frame_min < floor - PENETRATION_MM
    return floor, {
        "method": "10th percentile of the per-frame lowest point",
        "clip_min_mm": round(float(per_frame_min.min()), 3),
        "frames_below_floor": int(below.sum()),
        "spread_mm": round(float(np.percentile(per_frame_min, 90.0)
                                 - floor), 2),
    }


def derivatives(pos: np.ndarray, dt: float) -> dict[str, np.ndarray]:
    """Velocity, acceleration and jerk from positions (F, J, 3).

    Central differences in the interior, one-sided at the ends: the
    endpoints are real samples, not padding, so they must not invent a
    zero derivative.
    """
    vel = np.gradient(pos, dt, axis=0)
    acc = np.gradient(vel, dt, axis=0)
    jerk = np.gradient(acc, dt, axis=0)
    return {"velocity": vel, "acceleration": acc, "jerk": jerk}


def angular_velocity(rot: np.ndarray, dt: float) -> np.ndarray:
    """Per-joint angular speed in deg/s, from (F, J, 3, 3) rotations.

    The rotation from frame f to f+1 is R_{f+1} @ R_f^T; its angle comes
    from the trace. This is the true geodesic angle — decomposing into
    Euler rates would depend on the channel order and gimbal state.
    """
    F = rot.shape[0]
    rel = rot[1:] @ np.swapaxes(rot[:-1], -1, -2)
    trace = np.trace(rel, axis1=-2, axis2=-1)
    ang = np.degrees(np.arccos(np.clip((trace - 1.0) / 2.0, -1.0, 1.0)))
    speed = ang / dt
    # F-1 intervals -> F samples: repeat the last so shapes line up with
    # positions (and say nothing new about the final frame)
    return np.concatenate([speed, speed[-1:]], axis=0) if F > 1 else speed


def _weights(names: list[str]) -> tuple[np.ndarray, bool]:
    """Per-joint mass weights and whether they are anthropometric."""
    w = np.zeros(len(names))
    matched = 0
    for i, n in enumerate(names):
        key = n.lower().replace("_", "").replace(".", "")
        hit = None
        for token, frac in SEGMENT_MASS.items():
            if token in key:
                # prefer the longest matching token ("upperarm" over "arm")
                if hit is None or len(token) > len(hit[0]):
                    hit = (token, frac)
        if hit:
            w[i] = hit[1]
            matched += 1
    if matched < max(3, len(names) // 4):
        return np.ones(len(names)) / len(names), False
    total = w.sum()
    if total <= 0:
        return np.ones(len(names)) / len(names), False
    return w / total, True


def center_of_mass(pos: np.ndarray,
                   names: list[str]) -> tuple[np.ndarray, bool]:
    """(F, 3) COM trajectory, and whether real segment masses were used."""
    w, anthropometric = _weights(names)
    return np.einsum("fjc,j->fc", pos, w), anthropometric


def contacts(pos: np.ndarray, names: list[str], dt: float,
             up: str, floor_mm: float) -> dict:
    """Which foot-like joints are planted, when, and are they sliding.

    Foot sliding is the classic animation defect and the clearest case
    for measuring instead of watching: a planted foot that drifts
    horizontally reads as 'skating' but is nearly invisible frame by
    frame — and it is exact arithmetic here.
    """
    k, (h1, h2) = _axis_indices(up)
    feet = [i for i, n in enumerate(names)
            if any(t in n.lower() for t in ("foot", "toe", "ankle"))]
    vel = np.gradient(pos, dt, axis=0)
    speed = np.linalg.norm(vel, axis=2)
    h_speed = np.hypot(vel[:, :, h1], vel[:, :, h2])
    height = pos[:, :, k] - floor_mm

    out = {"foot_joints": [names[i] for i in feet], "events": [],
           "planted": {}, "sliding": []}
    if not feet:
        out["note"] = ("no foot/toe/ankle joints found by name: contact "
                       "and balance analysis was skipped")
        return out

    for i in feet:
        down = (height[:, i] < CONTACT_HEIGHT_MM) & \
               (speed[:, i] < CONTACT_SPEED_MMS)
        out["planted"][names[i]] = down

        # contact events: rising/falling edges of the planted signal
        edges = np.diff(down.astype(int))
        for f in np.nonzero(edges == 1)[0]:
            out["events"].append({"frame": int(f + 1), "joint": names[i],
                                  "event": "plant",
                                  "t_s": round(float((f + 1) * dt), 4)})
        for f in np.nonzero(edges == -1)[0]:
            out["events"].append({"frame": int(f + 1), "joint": names[i],
                                  "event": "lift",
                                  "t_s": round(float((f + 1) * dt), 4)})

        # sliding: planted AND drifting horizontally
        slide = down & (h_speed[:, i] > SLIDE_SPEED_MMS)
        if slide.any():
            frames = np.nonzero(slide)[0]
            out["sliding"].append({
                "joint": names[i],
                "frames": [int(f) for f in frames],
                "worst_frame": int(frames[np.argmax(h_speed[frames, i])]),
                "peak_speed_mm_s": round(float(h_speed[frames, i].max()), 2),
                "total_slip_mm": round(float(
                    (h_speed[frames, i] * dt).sum()), 2),
            })
    out["events"].sort(key=lambda e: (e["frame"], e["joint"]))
    return out


def balance(pos: np.ndarray, names: list[str], com: np.ndarray,
            contact: dict, up: str) -> dict:
    """COM against the support polygon, per frame.

    With one contact the 'polygon' is a point and every pose is
    technically unbalanced — so we report the horizontal distance from
    the COM to the support, and flag only what exceeds a foot-sized
    margin. Dynamic motion is SUPPOSED to be out of balance (that is
    what running is); this measures how far, not whether it is wrong.
    """
    _k, (h1, h2) = _axis_indices(up)
    planted = contact.get("planted", {})
    if not planted:
        return {"note": "no contacts: balance not evaluated",
                "frames_outside_support": []}

    idx = {n: i for i, n in enumerate(names)}
    F = pos.shape[0]
    dist = np.full(F, np.nan)
    n_support = np.zeros(F, dtype=int)

    for f in range(F):
        pts = [pos[f, idx[n], [h1, h2]] for n, d in planted.items() if d[f]]
        n_support[f] = len(pts)
        if not pts:
            continue
        P = np.array(pts)
        c = com[f, [h1, h2]]
        if len(P) == 1:
            dist[f] = float(np.linalg.norm(c - P[0]))
        else:
            # distance to the support segment/polygon (feet are few:
            # the segment between the two extremes is the support base)
            a, b = P[0], P[-1]
            ab = b - a
            L2 = float(ab @ ab)
            t = 0.0 if L2 == 0 else float(np.clip((c - a) @ ab / L2, 0, 1))
            dist[f] = float(np.linalg.norm(c - (a + t * ab)))

    airborne = [int(f) for f in np.nonzero(n_support == 0)[0]]
    valid = ~np.isnan(dist)
    return {
        "com_to_support_mm": {
            "max": round(float(np.nanmax(dist)), 2) if valid.any() else None,
            "mean": round(float(np.nanmean(dist)), 2) if valid.any() else None,
            "at_frame": (int(np.nanargmax(dist)) if valid.any() else None),
        },
        "airborne_frames": airborne,
        "airborne_ratio": round(len(airborne) / F, 4),
        "note": ("distance from the COM's ground projection to the support "
                 "base; large values in flight//dynamic frames are expected "
                 "- read them with airborne_frames"),
    }


def penetration(pos: np.ndarray, names: list[str], up: str,
                floor_mm: float) -> list[dict]:
    """Joints that go through the floor — never intentional, easy to
    miss by eye when it is a few mm for a few frames."""
    k, _h = _axis_indices(up)
    depth = floor_mm - pos[:, :, k]
    out = []
    for j in range(pos.shape[1]):
        bad = depth[:, j] > PENETRATION_MM
        if bad.any():
            frames = np.nonzero(bad)[0]
            out.append({
                "joint": names[j],
                "frames": [int(f) for f in frames],
                "worst_frame": int(frames[np.argmax(depth[frames, j])]),
                "max_depth_mm": round(float(depth[frames, j].max()), 2),
            })
    return sorted(out, key=lambda d: -d["max_depth_mm"])


def smoothness(deriv: dict, names: list[str], dt: float) -> dict:
    """Jerk statistics + pops.

    A 'pop' is a single-frame spike in acceleration: the signature of a
    bad key, a wrong tangent or a splice. It is one frame long, which is
    exactly why nobody catches it watching at speed.

    The z-score's MAD is floored at a fraction of the CLIP's overall
    acceleration scale: a joint that holds still for most of the clip
    has MAD ~ 0, and dividing by it declared every keyframe of a
    blocking pass to be a million-sigma event (a jump clip reported 154
    'pops'). A spike must be extreme FOR THE CLIP, not merely nonzero
    for a mostly-static joint.
    """
    jerk = np.linalg.norm(deriv["jerk"], axis=2)          # (F, J)
    acc = np.linalg.norm(deriv["acceleration"], axis=2)
    rms = np.sqrt((jerk ** 2).mean(axis=0))

    pops = []
    med = np.median(acc, axis=0)
    mad = np.median(np.abs(acc - med), axis=0)
    clip_scale = float(np.median(np.abs(acc - np.median(acc))))
    mad = np.maximum(mad, max(0.10 * clip_scale, 1e-6))
    for j in range(acc.shape[1]):
        z = (acc[:, j] - med[j]) / (1.4826 * mad[j])      # robust z-score
        spikes = np.nonzero(z > 12.0)[0]
        for f in spikes:
            pops.append({"frame": int(f), "joint": names[j],
                         "t_s": round(float(f * dt), 4),
                         "accel_mm_s2": round(float(acc[f, j]), 1),
                         "robust_z": round(float(z[f]), 1)})
    pops.sort(key=lambda p: -p["robust_z"])

    # Cluster by frame: a pose SNAP hits many joints in the same frame,
    # and 154 per-joint entries for what is really 5 global snaps buries
    # the signal (found dogfooding a blocking-pass jump). One event per
    # frame-neighbourhood, with how many joints it hit.
    events: list[dict] = []
    for p in sorted(pops, key=lambda p: p["frame"]):
        # a snap's spikes span the 2-3 frames of its acceleration kick;
        # the window is anchored at the cluster START so successive
        # snaps cannot daisy-chain into one blob covering half the clip
        if events and p["frame"] - events[-1]["frames"][0] <= 2:
            ev = events[-1]
            ev["frames"] = sorted(set(ev["frames"] + [p["frame"]]))
            ev["_joints"].add(p["joint"])
            if p["robust_z"] > ev["worst"]["robust_z"]:
                ev["worst"] = p
        else:
            events.append({"frames": [p["frame"]], "_joints": {p["joint"]},
                           "worst": dict(p)})
    for ev in events:
        w = ev["worst"]
        ev["joints_hit"] = len(ev["_joints"])
        ev["kind"] = "pose snap" if ev["joints_hit"] >= 4 else "joint pop"
        ev["t_s"] = w["t_s"]
        ev["worst_joint"] = w["joint"]
        ev["worst_accel_mm_s2"] = w["accel_mm_s2"]
        ev["worst_robust_z"] = w["robust_z"]
        del ev["worst"], ev["_joints"]
    events.sort(key=lambda e: -e["worst_robust_z"])

    worst = int(np.argmax(rms))
    return {
        "jerk_rms_mm_s3": {names[j]: round(float(rms[j]), 1)
                           for j in range(len(names))},
        "roughest_joint": names[worst],
        "roughest_jerk_rms_mm_s3": round(float(rms[worst]), 1),
        "pops": events[:12],
        "pop_count": len(events),
        "raw_spike_count": len(pops),
        "note": ("a pop is a single-frame acceleration spike (robust "
                 "z > 12, MAD floored at 10% of the clip's own scale), "
                 "clustered by frame: a 'pose snap' hits many joints at "
                 "once (blocking pass or splice), a 'joint pop' is one "
                 "bad key"),
    }


G_MM_S2 = 9810.0


def ballistics(com: np.ndarray, airborne_frames: list[int], dt: float,
               up: str) -> dict:
    """During flight, the COM has no choice: gravity is the only force,
    so its height must follow a parabola at -9.81 m/s^2. An animator
    breaks this constantly — too slow reads as 'floaty', too fast as
    'heavy' — and nobody can SEE 0.68 g; they just feel something is
    off. It is a least-squares fit, so measure it.

    Also a free sanity check on --unit: an effective gravity of ~0.1 g
    or ~10 g usually means the declared unit is wrong, not that the
    animation is.
    """
    k, _h = _axis_indices(up)
    spans: list[tuple[int, int]] = []
    if airborne_frames:
        start = prev = airborne_frames[0]
        for f in airborne_frames[1:]:
            if f == prev + 1:
                prev = f
                continue
            spans.append((start, prev))
            start = prev = f
        spans.append((start, prev))

    out = []
    for a, b in spans:
        n = b - a + 1
        if n < 5:
            continue                       # too short to fit a parabola
        t = np.arange(n) * dt
        h = com[a:b + 1, k]
        coef = np.polyfit(t, h, 2)         # h = c2 t^2 + c1 t + c0
        eff_g = -2.0 * float(coef[0])
        resid = float(np.sqrt(np.mean(
            (np.polyval(coef, t) - h) ** 2)))
        out.append({
            "frames": [int(a), int(b)],
            "duration_s": round(n * dt, 4),
            "apex_rise_mm": round(float(h.max() - h[0]), 1),
            "effective_gravity_mm_s2": round(eff_g, 1),
            "gravity_ratio": round(eff_g / G_MM_S2, 3),
            "fit_rms_mm": round(resid, 2),
        })
    return {
        "flights": out,
        "note": ("effective gravity from a parabola fit to the COM "
                 "height over each airborne span; 1.0 = physical, "
                 "<0.75 reads floaty, >1.3 reads heavy. ~0.1 or ~10 "
                 "usually means --unit is wrong"),
    }


def loop_continuity(pos: np.ndarray, deriv: dict, names: list[str],
                    up: str) -> dict:
    """How well the clip loops.

    Two conventions exist and both are correct, so the gap alone means
    nothing:

      * OVERLAP: the last frame duplicates the first (gap ~ 0);
      * FULL:    the last frame is one step BEFORE the first, because
                 playback wraps N-1 -> 0 (gap ~ one frame of motion).

    Judging against zero reports every correctly authored full-loop as
    broken — a false positive, and false positives are how a tool loses
    the right to be believed. So the gap is compared against the clip's
    own median per-frame motion, and 'discontinuous' means the seam
    jumps by MORE than a normal frame does.
    """
    _k, _h = _axis_indices(up)
    first, last = pos[0], pos[-1]
    travel = last[0] - first[0]              # root travel: not a defect
    gap = np.linalg.norm((last - travel) - first, axis=1)

    # what one frame of motion looks like in this clip
    step = np.linalg.norm(np.diff(pos, axis=0), axis=2)      # (F-1, J)

    typical_max = float(np.median(step.max(axis=1)))

    worst = int(np.argmax(gap))
    g = float(gap.max())
    if g <= max(2.0, 0.25 * typical_max):
        kind, cleanly = "overlap (last frame duplicates the first)", True
    elif g <= 2.0 * max(typical_max, 1.0):
        kind, cleanly = "full (last frame is one step before the first)", True
    else:
        kind, cleanly = "discontinuous", False

    # velocity continuity across the seam, measured the way the clip
    # would actually play: wrap around instead of a one-sided difference
    # at the ends (which is a measurement artifact, not a defect)
    dt_pos = np.concatenate([pos[-1:], pos, pos[:1]], axis=0)
    dt_pos[0] -= travel                       # unwrap the root at the seam
    dt_pos[-1] += travel
    wrapped_v = (dt_pos[2:] - dt_pos[:-2]) / 2.0
    vgap = np.linalg.norm(wrapped_v[-1] - wrapped_v[0], axis=1)

    return {
        "pose_gap_mm": {"max": round(g, 2), "mean": round(float(gap.mean()), 2),
                        "worst_joint": names[worst]},
        "typical_frame_motion_mm": round(typical_max, 2),
        "velocity_gap_mm_frame": {
            "max": round(float(vgap.max()), 2),
            "worst_joint": names[int(np.argmax(vgap))]},
        "root_travel_mm": [round(float(v), 2) for v in travel],
        "convention": kind,
        "loops_cleanly": bool(cleanly),
        "note": ("the seam gap is judged against this clip's own median "
                 "per-frame motion, because a full loop is SUPPOSED to "
                 "differ from frame 0 by one step; root travel is removed"),
    }


def peaks(deriv: dict, ang: np.ndarray, names: list[str],
          dt: float) -> dict:
    """Per-joint peak magnitudes — the numbers an animator quotes."""
    out = {}
    speed = np.linalg.norm(deriv["velocity"], axis=2)
    acc = np.linalg.norm(deriv["acceleration"], axis=2)
    for j, n in enumerate(names):
        fs = int(np.argmax(speed[:, j]))
        out[n] = {
            "peak_speed_mm_s": round(float(speed[fs, j]), 1),
            "peak_speed_frame": fs,
            "peak_accel_mm_s2": round(float(acc[:, j].max()), 1),
            "peak_angular_deg_s": round(float(ang[:, j].max()), 1),
        }
    return out
