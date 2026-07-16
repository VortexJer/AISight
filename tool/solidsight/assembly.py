"""Assembly helpers: bring several parts into one shared coordinate space.

An assembly file is a normal model file that uses place() instead of raw
emit(), pulling parts from other model files (from_model) or external meshes
(from_stl). Every build with 2+ parts automatically gets pairwise collision /
clearance analysis in report.json.

    from solidsight import *

    bracket = from_model("../bracket/model.py", "body")
    lid     = from_model("lid.py")            # single-part model
    motor   = from_stl("nema17.stl")

    place(bracket, name="bracket")
    place(motor, name="motor", at=(0, 0, 8), rotate=(0, 0, 90))
    place(lid, name="lid", at=(0, 0, 40))
"""

from __future__ import annotations

from pathlib import Path

from .errors import BadArgumentError, SceneError, fmt_num, fmt_vec
from .geom import Solid
from .scene import emit


def place(solid: Solid, name: str, at: tuple = (0, 0, 0),
          rotate: tuple = (0, 0, 0), color: str | None = None,
          ghost: bool = False, features: list | None = None) -> Solid:
    """Position a part in the assembly: rotate (degrees, X then Y then Z,
    around the origin), THEN translate by `at`. Registers it under `name`
    like emit() does, and returns the placed solid.

    ghost=True places a REFERENCE volume (keep-out zone, swept insertion
    path, connector envelope): fully measured in pairs[] / expect(), but
    rendered as an X-ray outline and excluded from prints, exports and
    material totals. Snap-fit note: flexible members interfere ON PURPOSE
    while inserting — sweep only the RIGID body as a ghost, and judge the
    flexible hook's interference DEPTH (in the overlap patches) against its
    allowed deflection instead of expecting zero contact."""
    if not isinstance(solid, Solid):
        raise BadArgumentError(
            f"place() got a {type(solid).__name__}, not a Solid",
            suggestion="from_model()/from_stl() return Solids; dicts from the "
                       'parts catalog need one entry picked, e.g. h["leaf_a"]')
    rx, ry, rz = rotate
    x, y, z = at
    placed = solid.rotate(rx, ry, rz).translate(x, y, z)
    return emit(placed, name=name, color=color, ghost=ghost,
                features=features)


def _resolve(path: str) -> Path:
    """Relative paths resolve against the model file that is executing."""
    from .scene import current_model_dir
    p = Path(path)
    base = current_model_dir()
    if not p.is_absolute() and base is not None:
        return base / p
    return p


def expect(a: str, b: str, clearance=None, status: str | None = None) -> None:
    """Declare the INTENDED relationship between two named parts — turns the
    pair analysis into a pass/fail spec test instead of numbers you have to
    judge by eye:

        expect("lid", "box", status="touching")        # meant to rest on it
        expect("gear_a", "gear_b", clearance=(0.15, 0.35))   # backlash band
        expect("card", "lid", clearance=0.5)           # at least 0.5 mm

    clearance: a float (minimum mm) or a (min, max) pair.
    status: "touching" (surfaces meant to contact) or "clear".
    The build FAILS (any mode) when reality violates a declared expectation;
    met expectations silence the generic touching/clearance advice."""
    from . import scene as scene_mod
    sc = scene_mod.current()
    if sc is None:
        raise SceneError(
            "expect() called outside a solidsight build",
            suggestion="use it inside a model/assembly file, after place()")
    if clearance is None and status is None:
        raise BadArgumentError(
            "expect() needs clearance= and/or status=",
            suggestion='e.g. expect("lid", "box", status="touching")')
    if status is not None and status not in ("touching", "clear"):
        raise BadArgumentError(
            f'expect() status must be "touching" or "clear", got {status!r}')
    lo = hi = None
    if clearance is not None:
        if isinstance(clearance, (int, float)):
            lo = float(clearance)
        else:
            lo = float(clearance[0])
            hi = float(clearance[1]) if len(clearance) > 1 else None
    sc.expectations.append({"a": str(a), "b": str(b), "min": lo, "max": hi,
                            "status": status})


def from_model(path: str, part: str | None = None) -> Solid:
    """Load a named part from another solidsight model file. Relative paths
    resolve against the calling model file's directory. With part=None the
    model must emit exactly one part."""
    from .runner import run_model
    p = _resolve(path)
    scene = run_model(p)
    if part is None:
        if len(scene.parts) != 1:
            names = ", ".join(pp.name for pp in scene.parts)
            raise SceneError(
                f"{p.name} emits {len(scene.parts)} parts; say which one",
                where=f"available: {names}",
                suggestion=f'from_model("{path}", "{scene.parts[0].name}")')
        return scene.parts[0].solid
    return scene.get(part).solid


def from_mesh(path: str) -> Solid:
    """Import an external mesh (STL/OBJ/PLY/3MF/GLB/OFF) as a Solid. The
    mesh must be watertight — solidsight will not guess at holes.
    (`from_stl` is the historical alias; both accept every format.)"""
    return from_stl(path)


def from_stl(path: str) -> Solid:
    """Import an external STL/OBJ/3MF/PLY/GLB mesh as a Solid. The mesh must
    be watertight — solidsight will not guess at holes."""
    import numpy as np
    import trimesh
    from manifold3d import Manifold, Mesh

    p = _resolve(path)
    if not p.exists():
        raise BadArgumentError(f"mesh file not found: {p}",
                               suggestion="check the path (relative paths "
                                          "resolve against the model file)")
    try:
        tm = trimesh.load(str(p), force="mesh")
    except Exception as e:
        raise BadArgumentError(
            f"could not read {p.name}: {e}",
            suggestion="supported formats: STL, OBJ, PLY, 3MF, GLB") from e
    if tm.is_empty or len(tm.faces) == 0:
        raise BadArgumentError(f"{p.name} contains no triangles")
    tm.merge_vertices()
    if not tm.is_watertight:
        broken = tm.edges_sorted[trimesh.grouping.group_rows(
            tm.edges_sorted, require_count=1)] if len(tm.edges_sorted) else []
        raise BadArgumentError(
            f"{p.name} is not watertight ({len(broken)} boundary edges) — "
            "it cannot become a solid",
            suggestion="repair it first (e.g. Meshmixer/Blender 'make "
                       "manifold'), or re-export with merged vertices")
    mesh = Mesh(
        vert_properties=np.asarray(tm.vertices, dtype=np.float32),
        tri_verts=np.asarray(tm.faces, dtype=np.uint32))
    m = Manifold(mesh)
    if m.is_empty():
        raise BadArgumentError(
            f"{p.name} could not be converted into a solid "
            f"(status: {m.status()})",
            suggestion="the mesh may self-intersect or have inverted "
                       "normals; repair and re-export")
    solid = Solid(m, f"from_stl({p.name})")
    if solid.volume < 0:
        solid = Solid(Manifold(Mesh(
            vert_properties=np.asarray(tm.vertices, dtype=np.float32),
            tri_verts=np.asarray(tm.faces[:, ::-1], dtype=np.uint32))),
            f"from_stl({p.name})")
    return solid


# ---------------------------------------------------------------------------
# pairwise analysis (used by the report on every multi-part build)
# ---------------------------------------------------------------------------

def pair_analysis(scene, mode: str = "free",
                  touch_tol: float = 0.05) -> tuple[list[dict], list[dict]]:
    """For every pair of named parts: collision (overlap bbox + volume + a
    concrete move suggestion) or minimum clearance between their surfaces.
    Returns (pairs, checks)."""
    from .validate import check

    pairs: list[dict] = []
    checks: list[dict] = []
    parts = scene.parts
    ps = mode == "print-safe"

    exps = {frozenset((e["a"], e["b"])): e for e in scene.expectations}
    seen_exp: set[frozenset] = set()
    part_names = {p.name for p in parts}
    for e in scene.expectations:
        missing = {e["a"], e["b"]} - part_names
        if missing:
            checks.append(check(
                "fail", "expectation-unknown-part",
                "expect() references unknown part(s): "
                + ", ".join(sorted(repr(m) for m in missing)),
                where=f"emitted parts: {', '.join(sorted(part_names)) or '(none)'}",
                suggestion="match expect() names to the emit()/place() names"))
            seen_exp.add(frozenset((e["a"], e["b"])))

    if len(parts) < 2:
        return pairs, checks

    from .events import BUS
    n_pairs = len(parts) * (len(parts) - 1) // 2
    pair_stage = BUS.stage("pairs", total=n_pairs)
    pair_stage.__enter__()

    diag = max(scene.combined().size) * 2 + 1

    def _exp_text(e) -> str:
        bits = []
        if e["status"]:
            bits.append(e["status"])
        if e["min"] is not None and e["max"] is not None:
            bits.append(f"clearance {fmt_num(e['min'])}..{fmt_num(e['max'])} mm")
        elif e["min"] is not None:
            bits.append(f"clearance >= {fmt_num(e['min'])} mm")
        return " and ".join(bits)

    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            a, b = parts[i], parts[j]
            inter = a.solid.manifold ^ b.solid.manifold
            vol = float(inter.volume())
            if vol > 1e-3:
                bb = inter.bounding_box()
                pieces = [p for p in inter.decompose() if p.volume() > 1e-3]
                patch_boxes = [p.bounding_box() for p in pieces[:4]]
                if len(pieces) > 1:
                    # several separate contact patches: the part is OVERSIZED
                    # (it pokes into the other on multiple sides), moving it
                    # would only trade one patch for another
                    depths = [min(pb[3] - pb[0], pb[4] - pb[1], pb[5] - pb[2])
                              for pb in patch_boxes]
                    ax_of = [int(min(range(3), key=lambda k:
                                     (pb[3 + k] - pb[k]))) for pb in patch_boxes]
                    axis_name = "xyz"[max(set(ax_of), key=ax_of.count)]
                    shrink = 2 * max(depths)
                    suggestion = (
                        f"the overlap is {len(pieces)} separate patches — "
                        f"'{b.name}' is oversized rather than misplaced: "
                        f"shrink it {fmt_num(shrink + 0.2)} mm in {axis_name} "
                        f"(and keep 0.2+ mm of real clearance), or rework "
                        f"the joint")
                    where = "; ".join(
                        f"patch {i + 1} at {fmt_vec(pb[:3])}..{fmt_vec(pb[3:])}"
                        for i, pb in enumerate(patch_boxes))
                else:
                    # minimum translation of b (per axis) that separates the
                    # part bounding boxes — an honest "how far to move"
                    (alo, ahi), (blo, bhi) = a.solid.bbox, b.solid.bbox
                    moves = [min(ahi[k] - blo[k], bhi[k] - alo[k])
                             for k in range(3)]
                    axis = int(min(range(3), key=lambda k: moves[k]))
                    axis_name = "xyz"[axis]
                    move = moves[axis]
                    b_size = b.solid.size[axis]
                    if move > 0.4 * b_size:
                        # moving that far means "take it out" — the part
                        # probably does not fit where it is
                        mid = (bb[2] + bb[5]) / 2
                        suggestion = (
                            f"'{b.name}' does not fit here: clearing "
                            f"'{a.name}' needs {fmt_num(move + 0.1)} mm of "
                            f"travel in {axis_name} ({fmt_num(b_size)} mm "
                            f"part). Shrink '{b.name}' where it presses into "
                            f"'{a.name}', and render --slice z={fmt_num(mid)} "
                            f"through the overlap to see the contact")
                    else:
                        suggestion = (
                            f"move '{b.name}' {fmt_num(move + 0.1)} mm along "
                            f"{axis_name}, or shrink one part there")
                    where = (f"overlap bbox x {fmt_num(bb[0])}..{fmt_num(bb[3])}, "
                             f"y {fmt_num(bb[1])}..{fmt_num(bb[4])}, "
                             f"z {fmt_num(bb[2])}..{fmt_num(bb[5])}")
                exp = exps.get(frozenset((a.name, b.name)))
                entry = {
                    "a": a.name, "b": b.name, "status": "collision",
                    "overlap_volume_mm3": round(vol, 3),
                    "overlap_bbox": {
                        "min": [round(float(v), 3) for v in bb[:3]],
                        "max": [round(float(v), 3) for v in bb[3:]]},
                    "overlap_patches": [
                        {"min": [round(float(v), 3) for v in pb[:3]],
                         "max": [round(float(v), 3) for v in pb[3:]]}
                        for pb in patch_boxes],
                    "min_clearance_mm": None,
                    "suggestion": suggestion,
                }
                if exp is not None:
                    seen_exp.add(frozenset((a.name, b.name)))
                    entry["expected"] = _exp_text(exp)
                    entry["expectation"] = "violated"
                    checks.append(check(
                        "fail", "expectation-violated",
                        f'pair "{a.name}" / "{b.name}" was declared '
                        f"'{_exp_text(exp)}' but the parts COLLIDE "
                        f"({fmt_num(vol)} mm3 of overlap)",
                        where=where, suggestion=suggestion))
                pairs.append(entry)
                mid = [(bb[k] + bb[3 + k]) / 2 for k in range(3)]
                r_focus = max(8.0, max(bb[3 + k] - bb[k] for k in range(3)))
                from .validate import _inspect_cmd
                checks.append(check(
                    "fail" if ps else "warn", "parts-overlap",
                    f'parts "{a.name}" and "{b.name}" occupy the same space '
                    f"({fmt_num(vol)} mm3 of overlap"
                    + (f" in {len(pieces)} patches)" if len(pieces) > 1 else ")"),
                    where=where,
                    suggestion=suggestion + "; separate parts must never "
                                            "intersect. Inspect: "
                    + _inspect_cmd(mid, r=r_focus)))
            else:
                gap = float(a.solid.manifold.min_gap(b.solid.manifold, diag))
                gap = round(gap, 3)
                touching = gap <= touch_tol
                entry = {
                    "a": a.name, "b": b.name,
                    "status": "touching" if touching else "clear",
                    "overlap_volume_mm3": 0.0,
                    "overlap_bbox": None,
                    "min_clearance_mm": gap,
                    "suggestion": None if not touching else
                        f"surfaces are {fmt_num(gap)} mm apart — parts that "
                        "must slide or snap need real clearance (0.15-0.3 mm "
                        "printed); if they should be one rigid piece, union "
                        "them into a single part",
                }
                exp = exps.get(frozenset((a.name, b.name)))
                if exp is not None:
                    seen_exp.add(frozenset((a.name, b.name)))
                    entry["expected"] = _exp_text(exp)
                    problems = []
                    if exp["status"] == "touching" and not touching:
                        problems.append(f"expected touching, but the gap is "
                                        f"{fmt_num(gap)} mm")
                    if exp["status"] == "clear" and touching:
                        problems.append("expected clear, but the surfaces "
                                        "touch")
                    if exp["min"] is not None and gap < exp["min"] - 1e-9:
                        problems.append(f"clearance {fmt_num(gap)} mm is "
                                        f"below the declared minimum "
                                        f"{fmt_num(exp['min'])} mm")
                    if exp["max"] is not None and gap > exp["max"] + 1e-9:
                        problems.append(f"clearance {fmt_num(gap)} mm exceeds "
                                        f"the declared maximum "
                                        f"{fmt_num(exp['max'])} mm")
                    if problems:
                        entry["expectation"] = "violated"
                        checks.append(check(
                            "fail", "expectation-violated",
                            f'pair "{a.name}" / "{b.name}" violates its '
                            f"declared spec: " + "; ".join(problems),
                            where=f"declared: {_exp_text(exp)}; measured "
                                  f"clearance {fmt_num(gap)} mm",
                            suggestion="adjust the geometry until the "
                                       "declared relationship holds, or fix "
                                       "the expect() if the intent changed"))
                    else:
                        entry["expectation"] = "met"
                        entry["suggestion"] = None   # intent declared and met
                pairs.append(entry)
            pair_stage.tick(f"'{a.name}' vs '{b.name}': "
                            f"{pairs[-1]['status']}")
    pair_stage.__exit__(None, None, None)

    for key, e in exps.items():
        if key not in seen_exp and not ({e["a"], e["b"]} - part_names):
            # both parts exist but the pair loop never saw them: can only
            # happen with a==b
            checks.append(check(
                "fail", "expectation-self-pair",
                f"expect() needs two DIFFERENT parts, got '{e['a']}' twice",
                suggestion="declare expectations between distinct parts"))
    return pairs, checks
