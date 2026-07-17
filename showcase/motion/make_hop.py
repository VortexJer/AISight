"""Vigia's hop — its idle animation, written twice.

The robot is rigid (no legs): it crouches on its base, springs, flies as
one body, lands. FootL/FootR are its base pads, counter-animated during
the crouch so they stay planted on the floor (which is what makes the
contact analysis meaningful).

  hop_floaty.bvh  flight stretched 1.4x: the "cute" edit. ~0.5 g.
  hop_fixed.bvh   T = 2*sqrt(2h/g) for the same apex: 1 g.

Run: python make_hop.py
"""

from __future__ import annotations

import math
from pathlib import Path

FPS = 30.0
G_CM = 981.0
STAND = 40.0                     # body centre height, cm... it is a robot
CROUCH = 34.0
APEX = 14.0                      # cm of hop

HIER = """HIERARCHY
ROOT Body
{
  OFFSET 0 0 0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT Head
  {
    OFFSET 0 26 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET 0 8 0
    }
  }
  JOINT ArmL
  {
    OFFSET 10 6 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET 8 0 0
    }
  }
  JOINT ArmR
  {
    OFFSET -10 6 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET -8 0 0
    }
  }
  JOINT FootL
  {
    OFFSET 6 -18 0
    CHANNELS 3 Xposition Yposition Zposition
    End Site
    {
      OFFSET 0 -4 0
    }
  }
  JOINT FootR
  {
    OFFSET -6 -18 0
    CHANNELS 3 Xposition Yposition Zposition
    End Site
    {
      OFFSET 0 -4 0
    }
  }
}
"""


def build(floaty: bool) -> str:
    t_settle, t_crouch, t_launch = 0.4, 0.35, 0.1
    t_land, t_recover = 0.1, 0.5
    t_air = 2.0 * math.sqrt(2.0 * APEX / G_CM) * (1.4 if floaty else 1.0)
    T = t_settle + t_crouch + t_launch + t_air + t_land + t_recover
    n = int(round(T * FPS))

    def body_y(t):
        if t < t_settle:
            return STAND, True
        t -= t_settle
        if t < t_crouch:
            return STAND - (STAND - CROUCH) * math.sin(
                math.pi * (t / t_crouch) / 2), True
        t -= t_crouch
        if t < t_launch:
            return CROUCH + (STAND - CROUCH) * (t / t_launch), True
        t -= t_launch
        if t < t_air:
            s = t / t_air
            return STAND + 4.0 * APEX * s * (1.0 - s), False
        t -= t_air
        if t < t_land:
            return STAND - 4.0 * (t / t_land) * (1 - t / t_land) * 4.0, True
        t -= t_land
        return STAND - 4.0 * math.cos(math.pi * min(t / t_recover, 1.0) / 2) \
            * 0.0, True

    rows = []
    for f in range(n):
        t = f / FPS
        y, grounded = body_y(t)
        air = not grounded
        arm = 15.0 * math.sin(2 * math.pi * t * 0.5) if not air else -50.0
        head_tilt = -8.0 if air else 0.0
        # feet: counter the body's dip while grounded (stay planted);
        # rigid with the body in flight
        foot_dy = (STAND - y) if grounded else 0.0
        row = [0.0, y, 0.0, 0.0, 0.0, 0.0,          # Body
               0.0, head_tilt, 0.0,                  # Head
               0.0, 0.0, arm,                        # ArmL
               0.0, 0.0, -arm,                       # ArmR
               0.0, foot_dy, 0.0,                    # FootL (positions)
               0.0, foot_dy, 0.0]                    # FootR
        rows.append(" ".join(f"{v:.4f}" for v in row))

    return "\n".join([HIER, "MOTION", f"Frames: {n}",
                      f"Frame Time: {1.0 / FPS:.6f}"] + rows) + "\n"


if __name__ == "__main__":
    here = Path(__file__).parent
    (here / "hop_floaty.bvh").write_text(build(True), encoding="utf-8")
    (here / "hop_fixed.bvh").write_text(build(False), encoding="utf-8")
    t = 2.0 * math.sqrt(2.0 * APEX / G_CM)
    print(f"apex {APEX} cm; physical airtime {t:.3f}s, floaty {t * 1.4:.3f}s")
