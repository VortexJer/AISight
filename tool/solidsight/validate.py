"""Quantitative validation: everything an agent can check WITHOUT eyes.

Produces per-part metrics (volume, area, bbox, center of mass, shells,
watertightness, minimum wall thickness, overhangs) and a list of checks with
pass/warn/fail levels, concrete locations and suggestions.

Two modes:
- "free"       (default): metrics are reported, nothing is enforced.
- "print-safe": manifold + single shell + wall thickness + overhang limits
                are enforced for FDM/resin printing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .errors import fmt_num, fmt_vec
from .scene import Part, Scene


@dataclass
class ValidationOptions:
    mode: str = "free"                # "free" | "print-safe"
    min_wall: float = 1.2             # mm, print-safe wall floor
    max_overhang: float = 50.0        # degrees from vertical, print-safe
    thickness_samples: int = 600      # rays cast per part
    allow_multiple_shells: bool = False


def check(level: str, id_: str, message: str, part: str | None = None,
          where: str | None = None, suggestion: str | None = None) -> dict:
    return {"id": id_, "level": level, "part": part, "message": message,
            "where": where, "suggestion": suggestion}


def analyze_scene(scene: Scene, opts: ValidationOptions,
                  skip_pairs: bool = False
                  ) -> tuple[dict, list[dict], list[dict]]:
    """Returns (parts_metrics, checks, pairs). pairs holds the assembly
    collision/clearance analysis for every combination of named parts."""
    checks: list[dict] = []
    metrics: dict[str, dict] = {}

    for w in scene.warnings:
        checks.append(check("warn", w["code"], w["message"],
                            where=w.get("where"),
                            suggestion=w.get("suggestion")))

    from .events import BUS
    part_stage = BUS.stage("metrics", total=len(scene.parts))
    part_stage.__enter__()
    for part in scene.parts:
        if part.ghost:
            part_stage.tick(f"part '{part.name}' (ghost)")
            lo, hi = part.solid.bbox
            metrics[part.name] = {
                "ghost": True,
                "volume_mm3": round(part.solid.volume, 3),
                "bbox": {"min": _r3(lo), "max": _r3(hi),
                         "size": _r3(part.solid.size)},
                "color": part.color,
                "note": "reference volume: measured in pairs[], excluded "
                        "from print checks, exports and material totals",
            }
            continue
        m, cs = _analyze_part(part, opts)
        if part.features:
            m["features"] = part.features
        metrics[part.name] = m
        checks.extend(cs)
        part_stage.tick(f"part '{part.name}'")
    part_stage.__exit__(None, None, None)

    if skip_pairs:
        if scene.expectations:
            checks.append(check(
                "fail", "expectation-skipped",
                "--skip-pairs was passed but the model declares expect() "
                "specs — they cannot be verified",
                suggestion="drop --skip-pairs, or remove the expect() "
                           "declarations"))
        return metrics, checks, []
    from .assembly import pair_analysis
    pairs, pair_checks = pair_analysis(scene, mode=opts.mode)
    checks.extend(pair_checks)
    return metrics, checks, pairs


# ---------------------------------------------------------------------------

def _analyze_part(part: Part, opts: ValidationOptions) -> tuple[dict, list[dict]]:
    checks: list[dict] = []
    solid = part.solid
    mesh = solid.to_trimesh()
    lo, hi = solid.bbox
    ps = opts.mode == "print-safe"

    # decompose() also returns sealed cavities as NEGATIVE-volume components;
    # "shells" means actual solid pieces, cavities are reported separately
    shells = [s for s in solid.manifold.decompose() if s.volume() > 1e-9]
    n_shells = len(shells)
    watertight = bool(mesh.is_watertight)
    com = mesh.center_mass if watertight else mesh.centroid

    # ray casting and overhang stats run on a simplified mesh (0.02 mm
    # tolerance) — same answers, far fewer triangles on threads/fillets
    from .geom import Solid as _S
    lite = _S(solid.manifold.simplify(0.02)).to_trimesh()
    thickness = _wall_thickness(lite, opts.thickness_samples)
    overhang = _overhangs(lite, opts.max_overhang)
    voids = _internal_voids(solid, mesh, n_shells)

    metrics = {
        "volume_mm3": round(solid.volume, 3),
        "surface_area_mm2": round(solid.area, 3),
        "bbox": {"min": _r3(lo), "max": _r3(hi), "size": _r3(solid.size)},
        "center_of_mass": _r3(com),
        "triangles": int(len(mesh.faces)),
        "shells": n_shells,
        "watertight": watertight,
        "genus": (int(solid.manifold.genus())
                  if len(solid.manifold.decompose()) == 1 else None),
        "wall_thickness": thickness,
        "overhangs": overhang,
        "internal_voids": voids,
        "print_estimate": {
            "material_g_pla": round(solid.volume * 0.00124, 1),
            "material_g_petg": round(solid.volume * 0.00127, 1),
            "rough_time_min": int(round(solid.volume / 600)),
            "note": "solid part at 100% infill; time is +-50%, "
                    "slicer-dependent",
        },
        "stability": _stability(mesh, lo, com),
        "color": part.color,
    }

    if not watertight:
        checks.append(check(
            "fail", "not-watertight",
            f'part "{part.name}" is not watertight (open surface)',
            part=part.name,
            suggestion="this should not happen with solidsight primitives — "
                       "rebuild the part step by step and report which "
                       "operation breaks it"))

    if n_shells > 1:
        boxes = "; ".join(
            f"piece {i + 1} at {fmt_vec(s.bounding_box()[:3])}.."
            f"{fmt_vec(s.bounding_box()[3:])}, {fmt_num(s.volume())} mm3"
            for i, s in enumerate(shells[:4]))
        more = f" (+{n_shells - 4} more)" if n_shells > 4 else ""
        level = "fail" if ps and not opts.allow_multiple_shells else "warn"
        checks.append(check(
            level, "multiple-shells",
            f'part "{part.name}" is {n_shells} disconnected pieces, not one '
            f"solid", part=part.name, where=boxes + more,
            suggestion="pieces must overlap (not just touch) to fuse in a "
                       "union; extend one into the other by ~0.1 mm. If "
                       "separate pieces are intentional, emit() them as "
                       "separate named parts, or pass --allow-multiple-shells"))

    tmin = thickness["min_mm"]
    if tmin is not None:
        spot = thickness["at"]
        inspect_cmd = _inspect_cmd(spot, r=max(8.0, tmin * 6))
        if ps and tmin < opts.min_wall:
            checks.append(check(
                "fail", "thin-wall",
                f'part "{part.name}" has a {fmt_num(tmin)} mm wall — below '
                f"the {fmt_num(opts.min_wall)} mm print-safe minimum",
                part=part.name,
                where=f"thinnest point near {fmt_vec(spot)}",
                suggestion="thicken that region, or lower --min-wall if your "
                           f"printer really handles it. Inspect: {inspect_cmd}"))
        elif not ps and tmin < 0.4:
            checks.append(check(
                "warn", "thin-wall",
                f'part "{part.name}" has a {fmt_num(tmin)} mm wall — thinner '
                f"than any printer/CNC can produce",
                part=part.name,
                where=f"thinnest point near {fmt_vec(spot)}",
                suggestion="probably an accidental sliver from a boolean. "
                           f"Inspect: {inspect_cmd}"))

    if voids["count"] > 0:
        if voids["voids"]:
            v0 = voids["voids"][0]
            detail = f' (largest ~{fmt_num(v0["volume_mm3"])} mm3)'
            where = (f"largest cavity bbox {v0['bbox']['min']}.."
                     f"{v0['bbox']['max']} (voxel resolution "
                     f"{voids['res_mm']} mm)")
            z_mid = (v0["bbox"]["min"][2] + v0["bbox"]["max"][2]) / 2
        else:
            detail = " (smaller than the inspection voxel grid)"
            where = "run `solidsight query <model> voxels --res 0.3` to locate it"
            z_mid = (lo[2] + hi[2]) / 2
        checks.append(check(
            "fail" if ps else "warn", "internal-cavity",
            f'part "{part.name}" contains {voids["count"]} sealed internal '
            f'cavit{"y" if voids["count"] == 1 else "ies"}{detail} that no '
            f"opening reaches — the outside render looks solid",
            part=part.name, where=where,
            suggestion="resin/powder cannot drain and FDM cannot print a "
                       "sealed roof; add a drain hole or remove the void. "
                       "Inspect it with: solidsight query <model> section "
                       f"z={fmt_num(z_mid)} — if the void is intentional, "
                       "build with --free"))

    if overhang["area_mm2"] > 0 and ps:
        checks.append(check(
            "warn", "overhang",
            f'part "{part.name}" has {fmt_num(overhang["area_mm2"])} mm2 of '
            f"faces steeper than {fmt_num(opts.max_overhang)} deg overhang "
            f'(worst: {fmt_num(overhang["max_deg"])} deg)',
            part=part.name,
            where=f"worst face near {fmt_vec(overhang['worst_at'])}",
            suggestion="reorient the part, chamfer the underside (45 deg "
                       "cones under bosses), or accept support material. "
                       "Flat roofs spanning an opening wall-to-wall (port "
                       "slots, windows) are BRIDGES and usually print fine "
                       "despite this warning. Inspect: "
                       f"{_inspect_cmd(overhang['worst_at'], r=12)}"))

    st = metrics["stability"]
    if st["standing"] is False:
        checks.append(check(
            "warn", "unstable",
            f'part "{part.name}" will TIP OVER standing on its base: the '
            f"center of mass projects {fmt_num(-st['com_margin_mm'])} mm "
            f"OUTSIDE the footprint",
            part=part.name,
            where=f"center of mass {fmt_vec(com)}; footprint spans the "
                  f"contact at z={fmt_num(lo[2])}",
            suggestion="widen the base, add feet, or shift mass toward the "
                       "footprint center"))
    elif (st["standing"] and st["com_margin_mm"] is not None
          and st["com_margin_mm"] < max(2.0, 0.04 * float(hi[2] - lo[2]))):
        checks.append(check(
            "warn", "barely-stable",
            f'part "{part.name}" is barely stable: the center of mass sits '
            f"only {fmt_num(st['com_margin_mm'])} mm inside the footprint "
            f"edge",
            part=part.name,
            suggestion="a nudge will tip it; widen the base or lower the "
                       "center of mass"))

    if ps:
        if lo[2] < -0.05:
            checks.append(check(
                "warn", "below-plate",
                f'part "{part.name}" extends {fmt_num(-lo[2])} mm below Z=0 '
                f"(the build plate)", part=part.name,
                suggestion="finish the part with .on_ground() or translate "
                           "it up"))
        elif lo[2] > 0.05:
            checks.append(check(
                "warn", "floating",
                f'part "{part.name}" floats {fmt_num(lo[2])} mm above the '
                f"build plate", part=part.name,
                suggestion="use .on_ground() unless it is meant to sit on "
                           "another part"))

    return metrics, checks


# ---------------------------------------------------------------------------
# wall thickness: built on the shared ray engine in query.py
# ---------------------------------------------------------------------------

def _wall_thickness(mesh, n_samples: int) -> dict:
    """Inward-normal ray thickness, built on the SAME ray engine as
    `solidsight query` (query.TriangleSet). A measurement only counts when
    the exit face roughly OPPOSES the entry face (dot < -0.8): near concave
    corners (thread roots, pocket edges) the inward ray exits through the
    adjacent face at a tiny distance, but that wedge is backed by bulk
    material and is not a wall."""
    from .query import TriangleSet
    faces = np.asarray(mesh.faces)
    if len(faces) == 0:
        return {"min_mm": None, "at": None, "samples": 0,
                "method": "inward-normal-ray"}
    ts = TriangleSet(mesh)
    # deterministic subsample: evenly spaced face indices
    n = min(n_samples, len(faces))
    idx = np.unique(np.linspace(0, len(faces) - 1, n).round().astype(int))
    tri = mesh.triangles[idx]                    # (n, 3, 3)
    origins = tri.mean(axis=1)                   # face centers
    normals = np.asarray(mesh.face_normals)[idx]
    eps = 1e-4
    dist, tri_hit = ts.first_exit(origins - normals * eps, -normals)
    valid = np.isfinite(dist) & (tri_hit >= 0)
    if valid.any():
        exit_normals = ts.normals[np.where(tri_hit >= 0, tri_hit, 0)]
        opposing = np.einsum("ij,ij->i", exit_normals, normals) < -0.8
        valid &= opposing
    if not valid.any():
        return {"min_mm": None, "at": None, "samples": int(len(idx)),
                "method": "inward-normal-ray"}
    dist = dist + eps

    # A candidate reading only counts as a WALL if:
    #  (1) there is AIR just past the exit (folded-surface slivers from
    #      twisted extrusions read near-zero but material continues), and
    #  (2) it is not a TAPER: knife wedges (thread chamfer feathers, blade
    #      edges) thin out to zero by construction — that is geometry, not a
    #      wall defect. Plates have antiparallel faces; wedges do not, and
    #      re-measuring a little way along the wedge reads much thicker.
    order = np.argsort(np.where(valid, dist, np.inf), kind="stable")
    probe_dir = np.array([[0.577350269, 0.211324865, 0.788675134]])
    probe_dir /= np.linalg.norm(probe_dir)
    k = -1
    for cand in order[:60]:
        if not valid[cand]:
            break
        n1 = normals[cand]
        d0 = float(dist[cand])
        # (1) air beyond the exit?
        probe = (origins[cand] - n1 * d0 - n1 * 0.05)[None, :]
        if len(ts.cast(probe, probe_dir)[0]) % 2 == 1:
            continue                    # material continues: surface fold
        n2 = ts.normals[tri_hit[cand]]
        if float(n1 @ n2) < -0.995:
            k = int(cand)               # parallel faces: a true wall
            break
        # (2) wedge? re-measure 0.8 mm to each side, perpendicular to the
        # wedge edge but along the entry surface
        edge = np.cross(n1, n2)
        edge /= max(np.linalg.norm(edge), 1e-12)
        u = np.cross(edge, n1)
        side_o = np.stack([origins[cand] + u * 0.8 - n1 * eps,
                           origins[cand] - u * 0.8 - n1 * eps])
        side_d, _tri = ts.first_exit(side_o, np.stack([-n1, -n1]))
        grown = np.where(np.isfinite(side_d), side_d, np.inf).max()
        if grown < 1.8 * d0 + 0.15:
            k = int(cand)               # stays thin along the surface: wall
            break
        # else: thickens fast -> taper edge, skip this candidate
    if k < 0:
        return {"min_mm": None, "at": None, "samples": int(len(idx)),
                "method": "inward-normal-ray",
                "note": "only taper edges found (wedges thinning to zero "
                        "by construction); no plate-like wall measured"}
    return {"min_mm": round(float(dist[k]), 3),
            "at": _r3(origins[k]),
            "samples": int(len(idx)),
            "method": "inward-normal-ray"}


# ---------------------------------------------------------------------------
# static stability: does the part stand on its footprint?
# ---------------------------------------------------------------------------

def _stability(mesh, lo, com) -> dict:
    """For parts resting on the plate: is the center of mass over the base?
    com_margin_mm > 0: distance from the COM projection to the nearest
    footprint edge (bigger = more stable); < 0: it will tip."""
    z0 = float(lo[2])
    if z0 > 0.5:      # floating/stacked part: standing is not evaluable
        return {"standing": None, "com_margin_mm": None,
                "note": "part does not rest on the build plate"}
    verts = np.asarray(mesh.vertices)
    base = verts[verts[:, 2] < z0 + 0.5][:, :2]
    if len(base) < 3:
        return {"standing": None, "com_margin_mm": None,
                "note": "contact region too small to evaluate"}
    try:
        from scipy.spatial import ConvexHull
        hull = ConvexHull(base)
    except Exception:
        return {"standing": None, "com_margin_mm": None,
                "note": "footprint is degenerate (a line or point)"}
    # hull.equations: A @ p + b <= 0 inside; margin = -max(A @ com + b)
    p = np.array([float(com[0]), float(com[1])])
    margin = float(-(hull.equations[:, :2] @ p + hull.equations[:, 2]).max())
    return {"standing": bool(margin > 0), "com_margin_mm": round(margin, 2)}


# ---------------------------------------------------------------------------
# internal cavities: exact topological test, voxel localization on demand
# ---------------------------------------------------------------------------

def _internal_voids(solid, mesh, n_shells: int) -> dict:
    """For a manifold solid, (surface components) - (solid components) is
    EXACTLY the number of sealed internal cavities. Counting components is
    cheap (union-find on face adjacency); only when cavities exist do we pay
    for a voxel pass to locate and measure them."""
    comps = _surface_components(mesh)
    cavities = comps - n_shells
    if cavities <= 0:
        return {"count": 0, "res_mm": None, "voids": []}
    from .query import find_voids, voxelize
    from .geom import Solid as _S
    lite = _S(solid.manifold.simplify(0.1))
    vox = voxelize(lite, res=max(max(solid.size) / 48, 0.1))
    located = find_voids(vox)
    return {"count": int(cavities), "res_mm": vox["res_mm"],
            "voids": located[:3]}


def _surface_components(mesh) -> int:
    adj = np.asarray(mesh.face_adjacency)
    n = len(mesh.faces)
    if n == 0:
        return 0
    parent = np.arange(n)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in adj:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[ra] = rb
    return len({find(i) for i in range(n)})


# ---------------------------------------------------------------------------

def _overhangs(mesh, threshold_deg: float) -> dict:
    """Faces steeper than threshold (degrees from vertical, 90 = ceiling),
    excluding faces resting on the build plate."""
    normals = np.asarray(mesh.face_normals)
    areas = np.asarray(mesh.area_faces)
    centers = mesh.triangles.mean(axis=1)
    nz = normals[:, 2]
    down = nz < -1e-6
    overhang_deg = np.degrees(np.arcsin(np.clip(-nz, 0, 1)))
    z_min = float(mesh.bounds[0][2])
    on_plate = centers[:, 2] < z_min + 0.25
    bad = down & ~on_plate & (overhang_deg > threshold_deg)
    if not bad.any():
        return {"max_deg": 0.0, "area_mm2": 0.0, "worst_at": None,
                "threshold_deg": threshold_deg}
    worst = int(np.argmax(np.where(bad, overhang_deg, -1)))
    return {"max_deg": round(float(overhang_deg[worst]), 1),
            "area_mm2": round(float(areas[bad].sum()), 2),
            "worst_at": _r3(centers[worst]),
            "threshold_deg": threshold_deg}


def _r3(v) -> list[float]:
    return [round(float(x), 3) for x in v]


def _inspect_cmd(at, r: float) -> str:
    """Ready-to-run close-up command for a reported location."""
    x, y, z = (round(float(v), 1) for v in at)
    return (f"solidsight build <model> --views iso,iso_back "
            f"--focus {x},{y},{z},{round(float(r), 1)} "
            f"--slice z={z} --out out_focus")
