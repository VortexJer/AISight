# One-piece coupe bodywork by station lofting (Vantage-2024 proportions).
# The whole outer skin is ONE loft_sections() solid: hood, fenders,
# greenhouse and decklid are the same 34-point template evaluated at 12
# stations - no box-on-top cabin.
from solidsight import *

# ---- datums (mm) ----------------------------------------------------------
L, W, H, WB = 4465.0, 1942.0, 1273.0, 2704.0
X0, X1 = -L / 2, L / 2                    # nose .. tail
FA = X0 + 850                             # front axle
RA = FA + WB                              # rear axle
CLEAR = 120.0                             # ground clearance
WHEEL_D, WHEEL_W = 680.0, 305.0
ARCH_D = 750.0


def station(y_body, z_belt, y_green, z_top, z_floor=CLEAR,
            rocker_in=60.0, belt_bulge=40.0, crown=0.5):
    """One cross-section half-template, mirrored to a closed polygon.
    y_body: half width at the beltline. z_belt: beltline height.
    y_green: half width where the 'greenhouse' region starts (on hood
    stations this is just where the top surface begins to crown).
    z_top: centerline top height. crown: 0..1 fullness of the top arc."""
    pts = []
    yb = y_body - rocker_in
    # bottom: center -> rocker (flat floor, small turn-up at the rocker)
    pts += [(0.0, z_floor), (yb * 0.55, z_floor), (yb, z_floor + 25)]
    # body side: rocker up to the beltline with barrel bulge (widest at
    # ~55% of the side height), tucking back in at the shoulder
    zs = z_floor + 25
    for t in (0.3, 0.55, 0.8, 1.0):
        z = zs + (z_belt - zs) * t
        bulge = belt_bulge * (1 - (t - 0.55) ** 2 / 0.45 ** 2)
        pts.append((yb + max(0.0, bulge), z))
    # shoulder: inboard run to the greenhouse/top (concave corner)
    pts.append((y_green, z_belt + 18))
    # top region (glass or hood): elliptical tumblehome arc ending
    # tangent-horizontal at the centerline (no tent peak)
    import math as _m
    zb = z_belt + 18
    for deg in (18, 38, 58, 76, 90):
        th = _m.radians(deg)
        y = y_green * _m.cos(th)
        z = zb + (z_top - zb) * (_m.sin(th) ** (1.0 + 0.8 * crown))
        pts.append((y, z))
    half = pts
    mirrored = [(-y, z) for (y, z) in reversed(half[1:-1])]
    return half + mirrored


# ---- stations nose -> tail -------------------------------------------------
# (x, half width, beltline z, greenhouse half width, top z, crown)
S = [
    (X0 + 8,    620, 520,  480, 585, 0.9),    # splitter lip
    (X0 + 120,  810, 600,  600, 700, 0.8),    # nose, grille face
    (X0 + 420,  905, 740,  650, 800, 0.65),    # ahead of front arch
    (FA,        950, 830,  640, 878, 0.55),    # front axle: fender peak
    (FA + 450,  930, 845,  615, 905, 0.55),    # hood mid
    (FA + 900,  920, 860,  600, 960, 0.6),    # cowl / windshield base
    (FA + 1350, 915, 890,  585, 1250, 0.5),  # A-pillar / roof rise
    (FA + 1750, 920, 900,  560, H,    0.5),  # roof crown (over seats)
    (RA - 250,  955, 910,  520, 1215, 0.55),   # C-pillar, haunch swell
    (RA,        971, 920,  400, 1105, 0.6),   # rear axle: widest haunch
    (RA + 500,  940, 930,  520, 1000, 0.75),  # decklid / spoiler lip
    (X1 - 8,    850, 880,  560, 955, 0.85),   # tail face
]
secs = [station(yb, zb, yg, zt, crown=cr) for (_x, yb, zb, yg, zt, cr) in S]
xs = [s[0] for s in S]
body = parts.loft_sections(secs, xs)

# ---- carve ----------------------------------------------------------------
WHEEL_Z = WHEEL_D / 2   # tyres touch the ground
arch = (cylinder(h=2600, d=ARCH_D)
        .translate(0, 0, -1300).aim("+y"))       # centered, spans both sides
for xa in (FA, RA):
    body = body - arch.translate(xa, 0, WHEEL_Z)

emit(body, name="body", color="#1b4d3e", material="glossy")

wheel = (cylinder(h=WHEEL_W, d=WHEEL_D)
         .translate(0, 0, -WHEEL_W / 2).aim("+y"))   # centered on its axle
TRACK_HALF = 740.0
for xa in (FA, RA):
    for side in (-1, 1):
        emit(wheel.translate(xa, side * TRACK_HALF, WHEEL_Z),
             name=f"wheel_{'fr' if xa == FA else 'rr'}"
                  f"_{'l' if side < 0 else 'r'}",
             color="#17181a", material="matte")
