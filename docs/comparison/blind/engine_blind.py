"""Inline-4 engine block, generated blind from engineering knowledge.

Units: mm.  Coordinate system:
  X = crank axis (front of engine at -X, rear at +X)
  Y = transverse (thrust axis)
  Z = vertical, crank centerline at Z=0, deck face at Z=+220

Nominal engine: 2.0 L four -- 86 mm bore, 94 mm bore spacing, closed deck.

Only numpy + trimesh are used.  Booleans run on trimesh's manifold engine.
"""

import numpy as np
import trimesh
from trimesh.creation import box, cylinder
from trimesh.transformations import translation_matrix, rotation_matrix

ENGINE = "manifold"

# ----------------------------------------------------------------- helpers
def T(x, y, z):
    return translation_matrix([x, y, z])

def BX(x0, x1, y0, y1, z0, z1):
    """Axis-aligned box from min/max corners."""
    ext = [x1 - x0, y1 - y0, z1 - z0]
    ctr = [(x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0]
    return box(extents=ext, transform=T(*ctr))

def CZ(r, z0, z1, x=0.0, y=0.0, sec=64):
    """Cylinder along Z."""
    return cylinder(radius=r, height=z1 - z0, sections=sec,
                    transform=T(x, y, (z0 + z1) / 2.0))

def CX(r, x0, x1, y=0.0, z=0.0, sec=64):
    """Cylinder along X."""
    m = T((x0 + x1) / 2.0, y, z) @ rotation_matrix(np.pi / 2.0, [0, 1, 0])
    return cylinder(radius=r, height=x1 - x0, sections=sec, transform=m)

def CY(r, y0, y1, x=0.0, z=0.0, sec=64):
    """Cylinder along Y."""
    m = T(x, (y0 + y1) / 2.0, z) @ rotation_matrix(-np.pi / 2.0, [1, 0, 0])
    return cylinder(radius=r, height=y1 - y0, sections=sec, transform=m)

def union(meshes):
    return trimesh.boolean.union(meshes, engine=ENGINE)

def difference(meshes):
    return trimesh.boolean.difference(meshes, engine=ENGINE)

# ------------------------------------------------------------- parameters
BORE_D      = 86.0                      # cylinder bore
BORE_R      = BORE_D / 2.0
PITCH       = 94.0                      # bore spacing
BORE_X      = [-1.5 * PITCH, -0.5 * PITCH, 0.5 * PITCH, 1.5 * PITCH]
MAIN_X      = [-2 * PITCH, -PITCH, 0.0, PITCH, 2 * PITCH]   # 5 main bearings

DECK_Z      = 220.0                     # deck face height above crank CL
BLOCK_XEND  = 205.0                     # front/rear faces at +/-205
UPPER_HW    = 65.0                      # upper block half width
CASE_HW     = 85.0                      # crankcase half width
PAN_Z       = -45.0                     # oil pan rail face
CASE_TOP    = 95.0                      # crankcase casting top (overlaps upper)
UPPER_BOT   = 85.0                      # upper block bottom (overlap for union)

LINER_R     = 50.0                      # cylinder wall outer radius (siamese)
JACKET_R    = 58.0                      # water jacket outer radius
JACKET_Z0   = 110.0                     # jacket floor
JACKET_Z1   = 212.0                     # jacket roof -> 8 mm closed deck plate

BULK_T      = 18.0                      # main bearing bulkhead thickness
SKIRT_IN    = 73.0                      # crankcase inner wall (12 mm skirts)
TUNNEL_R    = 30.0                      # crank tunnel / main bearing bore

# ------------------------------------------------------ 1. base castings
parts = []

# Upper block (cylinder barrel section)
parts.append(BX(-BLOCK_XEND, BLOCK_XEND, -UPPER_HW, UPPER_HW, UPPER_BOT, DECK_Z))
# Crankcase
parts.append(BX(-BLOCK_XEND, BLOCK_XEND, -CASE_HW, CASE_HW, PAN_Z, CASE_TOP))

# Engine mount bosses: 3 per side on the crankcase walls at Z=60
MOUNT_X = [-120.0, 0.0, 120.0]
for mx in MOUNT_X:
    parts.append(CY(15.0, 70.0, 96.0, x=mx, z=60.0))     # right side
    parts.append(CY(15.0, -96.0, -70.0, x=mx, z=60.0))   # left side

# Front nose boss and rear main seal boss on the crank axis
parts.append(CX(50.0, -212.0, -193.0, y=0.0, z=0.0, sec=96))
parts.append(CX(50.0, 193.0, 212.0, y=0.0, z=0.0, sec=96))

solid = union(parts)

# ----------------------------------------------- 2. carve the water jacket
jackets = [CZ(JACKET_R, JACKET_Z0, JACKET_Z1, x=bx, sec=96) for bx in BORE_X]
solid = difference([solid] + jackets)

# ------------------------- 3. add back cylinder walls + head-bolt columns
adds = []
# Siamese cylinder walls standing in the jacket, tied into deck and base
for bx in BORE_X:
    adds.append(CZ(LINER_R, 102.0, 218.0, x=bx, sec=96))
# 10 head-bolt bosses (columns through the jacket) at the bulkhead stations
HB_Y = 34.0
hb_xy = [(mx, s * HB_Y) for mx in MAIN_X for s in (+1, -1)]
for hx, hy in hb_xy:
    adds.append(CZ(11.0, 100.0, 216.0, x=hx, y=hy, sec=48))
solid = union([solid] + adds)

# ------------------------------------------------------------ 4. cutters
cuts = []

# Cylinder bores (through deck, opening into the crankcase)
for bx in BORE_X:
    cuts.append(CZ(BORE_R, 83.0, 235.0, x=bx, sec=128))

# Crankcase bays between the five bulkheads
h = BULK_T / 2.0
bays = [(MAIN_X[i] + h, MAIN_X[i + 1] - h) for i in range(4)]
for x0, x1 in bays:
    cuts.append(BX(x0, x1, -SKIRT_IN, SKIRT_IN, -60.0, 90.0))

# Main-cap parting face: everything below Z=0 between the skirts is cap territory
cuts.append(BX(-BLOCK_XEND - 5, BLOCK_XEND + 5, -72.5, 72.5, -60.0, 0.0))

# Crank tunnel: half-bores in the bulkheads, seal openings front and rear
cuts.append(CX(TUNNEL_R, -220.0, 220.0, y=0.0, z=0.0, sec=96))

# Head-bolt holes, blind into the bosses
for hx, hy in hb_xy:
    cuts.append(CZ(6.0, 130.0, 235.0, x=hx, y=hy, sec=32))

# Main bearing cap bolt holes, up into each bulkhead from the cap face
for mx in MAIN_X:
    for s in (+1, -1):
        cuts.append(CZ(5.5, -70.0, 45.0, x=mx, y=s * 32.0, sec=32))

# Engine mount tapped holes (blind, do not break into the crankcase)
for mx in MOUNT_X:
    cuts.append(CY(5.0, 77.0, 100.0, x=mx, z=60.0, sec=32))
    cuts.append(CY(5.0, -100.0, -77.0, x=mx, z=60.0, sec=32))

# Coolant transfer holes through the closed deck into the jacket (2 per bore)
for bx in BORE_X:
    for s in (+1, -1):
        cuts.append(CZ(4.0, 205.0, 235.0, x=bx, y=s * 54.0, sec=32))

# Longitudinal oil galleries, drilled full length below the jacket floor
for gy in (-52.0, 52.0):
    cuts.append(CX(7.0, -220.0, 220.0, y=gy, z=100.0, sec=48))

# Vertical main-bearing oil feed drillings from the left gallery down each bulkhead
for mx in MAIN_X:
    cuts.append(CZ(4.0, 20.0, 106.0, x=mx, y=-52.0, sec=32))

# Oil pan rail bolt holes (blind, up into the rails)
for px in (-150.0, -50.0, 50.0, 150.0):
    for s in (+1, -1):
        cuts.append(CZ(3.5, -55.0, -25.0, x=px, y=s * 79.0, sec=32))

solid = difference([solid] + cuts)

# ------------------------------------------------------------- 5. export
import os
out_dir = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(out_dir, "engine_blind.stl")
solid.export(out_path)

print("watertight:", solid.is_watertight)
print("volume_mm3:", solid.volume)
print("bounds:", solid.bounds.tolist())
