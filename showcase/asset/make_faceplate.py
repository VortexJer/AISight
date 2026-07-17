"""Vigia's game-asset face plate: a 40x30 panel with the eye aperture,
unwrapped into two islands (panel ring + eye bezel). Written twice:
the broken version has the BEZEL island's winding flipped - the classic
mirrored-normal-map bug - and packed at half density.
Run: python make_faceplate.py
"""
from pathlib import Path

def build(broken: bool) -> str:
    L = ["# vigia face plate", "usemtl faceplate"]
    V, T, F = [], [], []
    def quad(c3, uv):
        vi = []
        for c in c3: V.append(c); vi.append(len(V))
        ti = []
        for u in uv: T.append(u); ti.append(len(T))
        F.append((vi, ti))
    # panel: 4 quads around the eye aperture (a 12x12 hole at centre)
    # panel 40 wide, eye aperture 12
    ring = [
        [(-20,-15,0),(20,-15,0),(20,-6,0),(-20,-6,0)],     # bottom band
        [(-20,6,0),(20,6,0),(20,15,0),(-20,15,0)],         # top band
        [(-20,-6,0),(-6,-6,0),(-6,6,0),(-20,6,0)],         # left band
        [(6,-6,0),(20,-6,0),(20,6,0),(6,6,0)],             # right band
    ]
    slots = [(0.03,0.03),(0.03,0.40),(0.03,0.77),(0.52,0.03)]
    for c3,(ox,oy) in zip(ring, slots):
        w = (c3[1][0]-c3[0][0])/40*0.45
        h = (c3[2][1]-c3[1][1])/30*0.45
        quad(c3, [(ox,oy),(ox+w,oy),(ox+w,oy+h),(ox,oy+h)])
    # eye bezel: one quad ring simplified as a single quad island
    s = 0.10 if broken else 0.20
    uv = [(0.55,0.45),(0.55+s,0.45),(0.55+s,0.45+s),(0.55,0.45+s)]
    if broken:
        uv = uv[::-1]                       # flipped winding
    quad([(-6,-6,1.5),(6,-6,1.5),(6,6,1.5),(-6,6,1.5)], uv)
    for v in V: L.append(f"v {v[0]} {v[1]} {v[2]}")
    for t in T: L.append(f"vt {t[0]:.4f} {t[1]:.4f}")
    for vi,ti in F: L.append("f " + " ".join(f"{a}/{b}" for a,b in zip(vi,ti)))
    return "\n".join(L) + "\n"

here = Path(__file__).parent
(here/"faceplate_broken.obj").write_text(build(True), encoding="utf-8")
(here/"faceplate_fixed.obj").write_text(build(False), encoding="utf-8")
print("faceplates written")
