"""Generate the jump example: a standing long-jump, twice.

A full little scene, not a pose test: crouch, drive forward and up,
a travelling ballistic flight, landing absorb 60 cm ahead, recovery to
stand. Written twice:

  jump_floaty.bvh   the flight keeps the same forward travel and the
                    same apex but hangs in the air ~35% too long — the
                    "make it read better" edit every animator has made.
                    Effective gravity ~0.55 g.
  jump_fixed.bvh    the airtime physics demands for that apex
                    (T = 2*sqrt(2h/g)): 1.0 g.

Every still frame of both clips is identical in pose terms; only the
TIMING of the flight differs. That is exactly why the defect is
invisible to inspection and obvious to measurement — and why
inspect renders flight_0_arc.png (ghosted poses + measured COM arc vs
the 1 g reference shape) for any clip with a flight.

Run: python make_jump.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from make_clips import ANKLE_H, HIERARCHY, JOINTS, leg_ik  # noqa: E402

FPS = 30.0
G_CM = 981.0
STAND, CROUCH, LAND_LOW = 78.0, 60.0, 66.0
APEX_RISE = 32.0                 # cm above standing, at the COM peak
JUMP_DIST = 60.0                 # forward travel during flight, cm


def build(floaty: bool) -> str:
    t_settle, t_crouch, t_launch = 0.30, 0.45, 0.12
    t_land, t_absorb, t_recover = 0.10, 0.25, 0.45
    t_air_phys = 2.0 * math.sqrt(2.0 * APEX_RISE / G_CM)      # 0.511 s
    t_air = t_air_phys * (1.35 if floaty else 1.0)

    T = t_settle + t_crouch + t_launch + t_air + t_land + t_absorb \
        + t_recover
    n = int(round(T * FPS))
    z_take = 0.0                                  # takeoff position
    z_land = JUMP_DIST

    def state(t: float):
        """(hip_y, hip_z, phase) at time t."""
        if t < t_settle:
            return STAND, 0.0, "ground"
        t -= t_settle
        if t < t_crouch:
            s = t / t_crouch
            return STAND - (STAND - CROUCH) * math.sin(
                math.pi * s / 2), 0.0, "ground"
        t -= t_crouch
        if t < t_launch:
            s = t / t_launch
            # drive up and slightly forward, ready to leave the ground
            return CROUCH + (STAND - CROUCH) * s, z_take + 4.0 * s, "ground"
        t -= t_launch
        if t < t_air:
            s = t / t_air
            hy = STAND + 4.0 * APEX_RISE * s * (1.0 - s)
            hz = (z_take + 4.0) + (z_land - z_take - 4.0) * s
            return hy, hz, "air"
        t -= t_air
        if t < t_land:
            s = t / t_land
            return STAND - (STAND - LAND_LOW) * s, z_land, "ground"
        t -= t_land
        if t < t_absorb:
            return LAND_LOW, z_land, "ground"
        t -= t_absorb
        s = min(t / t_recover, 1.0)
        return LAND_LOW + (STAND - LAND_LOW) * math.sin(
            math.pi * s / 2), z_land, "ground"

    rows = []
    for f in range(n):
        t = f / FPS
        hy, hz, phase = state(t)
        air = phase == "air"
        # arms: back in the crouch, thrown up in flight, settling after
        if t < t_settle + t_crouch:
            arm = -45.0
        elif air:
            arm = 65.0
        else:
            arm = -10.0
        vals = {"Hips": [0.0, hy, hz, 0, 0, 0],
                "Spine": [0, 8 if t < t_settle + t_crouch else
                          (-6 if air else 0), 0],
                "Chest": [0, 2, 0], "Neck": [0, 0, 0], "Head": [0, 0, 0]}
        for s_ in ("Left", "Right"):
            vals[f"{s_}UpperArm"] = [0, arm, 0]
            vals[f"{s_}Forearm"] = [0, -15, 0]
            vals[f"{s_}Hand"] = [0, 0, 0]
        for s_ in ("Left", "Right"):
            if air:
                # tuck, then reach for the landing in the last third
                sflight = 0.0
                # recompute flight fraction for the reach
                t_in = t - (t_settle + t_crouch + t_launch)
                sflight = max(0.0, min(t_in / t_air, 1.0))
                if sflight < 0.66:
                    vals[f"{s_}Thigh"] = [0, -70, 0]
                    vals[f"{s_}Shin"] = [0, 85, 0]
                    vals[f"{s_}Foot"] = [0, -15, 0]
                else:
                    vals[f"{s_}Thigh"] = [0, -35, 0]
                    vals[f"{s_}Shin"] = [0, 25, 0]
                    vals[f"{s_}Foot"] = [0, 10, 0]
            else:
                th, sh = leg_ik(hy, hz, ANKLE_H, hz + 4.0)
                vals[f"{s_}Thigh"] = [0, th, 0]
                vals[f"{s_}Shin"] = [0, sh, 0]
                vals[f"{s_}Foot"] = [0, -(th + sh), 0]
        row = []
        for name, _nch in JOINTS:
            row += vals[name]
        rows.append(" ".join(f"{v:.4f}" for v in row))

    return "\n".join([HIERARCHY, "MOTION", f"Frames: {n}",
                      f"Frame Time: {1.0 / FPS:.6f}"] + rows) + "\n"


if __name__ == "__main__":
    here = Path(__file__).parent
    (here / "jump_floaty.bvh").write_text(build(True), encoding="utf-8")
    (here / "jump_fixed.bvh").write_text(build(False), encoding="utf-8")
    t_phys = 2.0 * math.sqrt(2.0 * APEX_RISE / G_CM)
    print(f"apex +{APEX_RISE} cm, travel {JUMP_DIST} cm")
    print(f"floaty airtime {t_phys * 1.35:.3f} s (needs {t_phys:.3f} at 1 g)")
