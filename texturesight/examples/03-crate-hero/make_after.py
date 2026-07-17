"""The hero crate AFTER the texturesight loop.

Same geometry, same atlas, same painted maps as the blind build —
`make_blind.py` is imported, not copied. Only the UV MAPPER is
rewritten, one fix per measured finding:

  uv-flipped-faces x148 (FAIL)
      The blind mapper matched a face's long axis to its region's long
      axis by TRANSPOSING (u,v) — a reflection, which mirrors the UV
      winding; and reversing a quad's 3D winding never touched its UV
      order. The after mapper rotates instead of transposing, then
      checks the SIGNED UV area of every face and mirrors it back if
      it is negative. Flips are impossible by construction.
  uv-stretch (p95 7.19:1, 328 faces over 2:1)
      The blind mapper normalised u and v independently, so every face
      was stretched to fill its region rect. The after mapper uses ONE
      scale for both axes: planar faces map conformally, anisotropy 1.
  texel-density 54x spread
      Every face filled its region regardless of physical size, so a
      3 cm latch got the texel rate of a 55 cm panel. The after mapper
      scales each region by its largest face's world extent and maps
      every face of the region at that same px/m.
  336 stacked islands / 336 shells
      Positions and UVs are welded on write (shared v/vt), so the OBJ
      carries real shells; repeated parts (posts, handles, chamfer
      trim) still share their region deliberately, trim-sheet style —
      that overlap is intent, and the README says so.

Run: python make_after.py  ->  crate_after.obj/.mtl (+ the same three
                               texture maps, re-exported)
"""

import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BLIND = os.path.join(HERE, "blind")

spec = importlib.util.spec_from_file_location(
    "make_blind", os.path.join(BLIND, "make_blind.py"))
B = importlib.util.module_from_spec(spec)
sys.modules["make_blind"] = B
spec.loader.exec_module(B)          # builds B.faces and the atlas B.A

TEX = B.TEX
PAD = 2.0


def _frame(f):
    """The same per-face projection frame the blind mapper chose."""
    if f["axsg"] is not None:
        return (np.array(B.UDIR[f["axsg"]], float),
                np.array(B.VDIR[f["axsg"]], float))
    vs = f["vs"]
    best = None
    for i in range(len(vs)):
        e = vs[(i + 1) % len(vs)] - vs[i]
        L = np.linalg.norm(e)
        if best is None or L > best[0]:
            best = (L, e / L)
    U = best[1]
    return U, np.cross(f["n"], U)


def face_uv(f):
    x0, y0, x1, y1 = B.A.regions[f["region"]]
    vs = f["vs"]
    U, V = _frame(f)
    us = np.array([np.dot(v, U) for v in vs])
    bs = np.array([np.dot(v, V) for v in vs])

    # orient the face's long axis onto the region's long axis by a
    # 90-degree ROTATION (u,b) -> (b,-u): a rotation keeps chirality,
    # the blind transpose was a reflection and mirrored 148 faces
    if ((y1 - y0) > (x1 - x0)) != \
            ((bs.max() - bs.min()) > (us.max() - us.min())):
        us, bs = bs.copy(), -us

    # ONE scale for both axes: the region's px/m, set by the largest
    # face of that region (precomputed) — conformal, uniform density
    S = REGION_SCALE[f["region"]]
    ru = (us.max() - us.min()) * S
    rb = (bs.max() - bs.min()) * S
    offx = x0 + PAD + ((x1 - x0 - 2 * PAD) - ru) / 2.0
    offy = y0 + PAD + ((y1 - y0 - 2 * PAD) - rb) / 2.0
    a = offx + (us - us.min()) * S
    b = offy + (rb - (bs - bs.min()) * S)          # V runs up the region
    u = a / TEX
    v = 1.0 - b / TEX

    # signed UV area must be positive (the mesh winding is CCW from
    # outside); mirror the face back if a frame choice reflected it
    area = 0.0
    for i in range(len(u)):
        j = (i + 1) % len(u)
        area += u[i] * v[j] - u[j] * v[i]
    if area < 0:
        cu = (u.max() + u.min()) / 2.0
        u = 2.0 * cu - u
    return list(zip(u, v))


def _region_scales():
    """px per meter for each region: its largest face fills it."""
    ext = {}
    for f in B.faces:
        U, V = _frame(f)
        us = np.array([np.dot(v, U) for v in f["vs"]])
        bs = np.array([np.dot(v, V) for v in f["vs"]])
        ru, rb = us.max() - us.min(), bs.max() - bs.min()
        x0, y0, x1, y1 = B.A.regions[f["region"]]
        if ((y1 - y0) > (x1 - x0)) != (rb > ru):
            ru, rb = rb, ru
        w, h = x1 - x0 - 2 * PAD, y1 - y0 - 2 * PAD
        s = min(w / max(ru, 1e-9), h / max(rb, 1e-9))
        ext[f["region"]] = min(ext.get(f["region"], 1e9), s)
    return ext


REGION_SCALE = _region_scales()


def write_obj():
    """Welded export: shared positions and shared UVs, real shells."""
    vmap, tmap = {}, {}
    vlist, tlist = [], []
    rows = []
    tris = 0
    cur = None
    for f in B.faces:
        if f["part"] != cur:
            rows.append("g %s" % f["part"])
            cur = f["part"]
        uvs = face_uv(f)
        vi, ti = [], []
        for v, (u, vv) in zip(f["vs"], uvs):
            kv = (round(v[0], 6), round(v[1], 6), round(v[2], 6))
            if kv not in vmap:
                vmap[kv] = len(vlist) + 1
                vlist.append("v %.5f %.5f %.5f" % kv)
            vi.append(vmap[kv])
            kt = (round(u, 6), round(vv, 6))
            if kt not in tmap:
                tmap[kt] = len(tlist) + 1
                tlist.append("vt %.5f %.5f" % kt)
            ti.append(tmap[kt])
        m = len(f["vs"])
        for t in range(1, m - 1):
            rows.append("f " + " ".join(
                "%d/%d" % (vi[q], ti[q]) for q in (0, t, t + 1)))
            tris += 1

    with open(os.path.join(HERE, "crate_after.obj"), "w") as o:
        o.write("# Hero sci-fi supply crate -- texturesight-audited build\n")
        o.write("mtllib crate_after.mtl\no crate_hero\nusemtl crate_mat\n")
        o.write("\n".join(vlist) + "\n")
        o.write("\n".join(tlist) + "\n")
        o.write("\n".join(rows) + "\n")
    with open(os.path.join(HERE, "crate_after.mtl"), "w") as o:
        o.write("newmtl crate_mat\nKa 1 1 1\nKd 1 1 1\nKs 0.2 0.2 0.2\n"
                "Ns 64\nd 1.0\nillum 2\n"
                "map_Kd crate_albedo.png\nmap_Pr crate_roughness.png\n"
                "map_Bump -bm 1.0 crate_normal.png\nnorm crate_normal.png\n")
    return tris, len(vlist), len(tlist)


def main():
    from PIL import Image
    tris, nv, nt = write_obj()
    # the SAME painted maps, re-exported beside the after mesh
    B.paint_all()
    nrm = B.build_normal()
    Image.fromarray(np.clip(B.ALB + 0.5, 0, 255).astype(np.uint8),
                    "RGB").save(os.path.join(HERE, "crate_albedo.png"))
    Image.fromarray(np.clip(nrm * 255.0 + 0.5, 0, 255).astype(np.uint8),
                    "RGB").save(os.path.join(HERE, "crate_normal.png"))
    Image.fromarray(np.clip(B.RGH * 255.0 + 0.5, 0, 255).astype(np.uint8),
                    "L").save(os.path.join(HERE, "crate_roughness.png"))
    print("crate_after.obj: %d tris, %d welded verts, %d welded uvs"
          % (tris, nv, nt))
    dens = sorted(REGION_SCALE.items(), key=lambda kv: kv[1])
    print("region px/m: min %s %.0f, max %s %.0f (%.1fx spread)"
          % (dens[0][0], dens[0][1], dens[-1][0], dens[-1][1],
             dens[-1][1] / dens[0][1]))


if __name__ == "__main__":
    main()
