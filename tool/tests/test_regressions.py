"""Regression tests — every test here pins a real bug found while
dogfooding. Run with: pytest tool/tests"""

import math

import numpy as np
import pytest

from solidsight import box, cylinder, parts, polygon, stroke, union
from solidsight import scene as _scene_mod
from solidsight.scene import Scene
from solidsight.validate import ValidationOptions, analyze_scene


def make_scene():
    sc = Scene()
    _scene_mod.activate(sc)
    return sc


def teardown_function(_fn):
    _scene_mod.deactivate()


# --- threads: chamfer envelope must not split the thread into 2 shells ----

def test_thread_is_single_shell():
    t = parts.iso_thread(8, 20)
    shells = [s for s in t.manifold.decompose() if s.volume() > 1e-9]
    assert len(shells) == 1


# --- ray parity: shared triangle edges must count as ONE crossing ---------

def test_ray_through_shared_edge_counts_once():
    from solidsight.query import raycast
    b = box(10, 10, 10)
    # (0,0) is exactly on the cube's face diagonal -> edge-coincident hits
    res = raycast(b, (0, 0, -5), (0, 0, 1))
    assert res["crossings"] == 2
    assert len(res["material_segments"]) == 1
    assert res["material_segments"][0]["thickness_mm"] == pytest.approx(10)


# --- sealed cavities: decompose returns them as negative-volume pieces ----

def test_sealed_cavity_detected_and_shells_not_confused():
    sc = make_scene()
    block = box(20, 20, 20) - box(10, 10, 10).translate(0, 0, 5)
    sc.emit(block, name="block")
    metrics, checks, _pairs = analyze_scene(
        sc, ValidationOptions(mode="print-safe"))
    assert metrics["block"]["shells"] == 1          # NOT 2
    assert metrics["block"]["internal_voids"]["count"] == 1
    assert any(c["id"] == "internal-cavity" and c["level"] == "fail"
               for c in checks)


# --- union-touching: fires on coplanar contact, NOT on interleaved cutters -

def test_union_touching_warns_on_coplanar_stack():
    sc = make_scene()
    a = box(10, 10, 5)
    b = box(10, 10, 5).translate(0, 0, 5)   # exactly stacked, zero overlap
    _ = a + b
    assert any(w["code"] == "union-touching" for w in sc.warnings)


def test_union_interleaved_cutters_no_false_positive():
    sc = make_scene()
    outer = union(box(2, 10, 5).translate(-4, 0, 0),
                  box(2, 10, 5).translate(4, 0, 0))
    inner = box(2, 10, 5)                   # inside outer's bbox, not touching
    _ = outer + inner
    assert not any(w["code"] == "union-touching" for w in sc.warnings)


# --- wall thickness: no false 0 mm at concave V-grooves (thread roots) ----

def test_thread_thickness_no_false_zero():
    sc = make_scene()
    sc.emit(parts.iso_thread(8, 12), name="rod")
    metrics, _checks, _ = analyze_scene(sc, ValidationOptions(mode="free"))
    tmin = metrics["rod"]["wall_thickness"]["min_mm"]
    assert tmin is None or tmin > 0.5


# --- wall metric: real 0.5 mm cutter-skin must still be found -------------

def test_thin_skin_detected():
    sc = make_scene()
    skin = box(20, 20, 5) - cylinder(h=7, d=10).translate(0, -4.5, -1)
    sc.emit(skin, name="p")
    metrics, _c, _p = analyze_scene(sc, ValidationOptions(mode="free"))
    assert 0.4 < metrics["p"]["wall_thickness"]["min_mm"] < 0.6


# --- renderer: crease-split must not blend normals across 90-deg edges ----
# (trimesh removed Trimesh.smoothed(); a silent fallback averaged normals
# across creases and produced fan-shading artifacts on flat floors)

def test_crease_split_cube_normals_axis_aligned():
    from solidsight.render import _crease_split
    tm = box(10, 10, 10).to_trimesh()
    _verts, _faces, normals = _crease_split(tm, math.radians(30))
    assert np.abs(normals).max(axis=1).min() > 1 - 1e-6


# --- polygon: silent self-intersection must warn --------------------------

def test_self_intersecting_polygon_warns():
    sc = make_scene()
    _ = polygon([(0, 0), (10, 10), (10, 0), (0, 10)])   # bowtie
    assert any(w["code"] == "self-intersecting-polygon" for w in sc.warnings)


# --- collision report: oversized part -> patches + shrink suggestion ------

def test_multi_patch_collision_reports_oversized():
    from solidsight.assembly import pair_analysis
    sc = make_scene()
    walls = union(box(2, 30, 20).translate(-14, 0, 0),
                  box(2, 30, 20).translate(14, 0, 0))
    sc.emit(walls, name="walls")
    sc.emit(box(29, 20, 10, ).translate(0, 0, 5), name="bar")
    pairs, checks = pair_analysis(sc, mode="free")
    col = [p for p in pairs if p["status"] == "collision"][0]
    assert len(col["overlap_patches"]) == 2
    assert "oversized" in col["suggestion"]


# --- determinism: same construction, identical mesh ------------------------

def test_gear_deterministic():
    a = parts.spur_gear(2, 20, 8, bore=6)
    b = parts.spur_gear(2, 20, 8, bore=6)
    ma, mb = a.to_trimesh(), b.to_trimesh()
    assert np.array_equal(ma.vertices, mb.vertices)
    assert np.array_equal(ma.faces, mb.faces)


# --- new helpers stay sane --------------------------------------------------

def test_hex_grid_cuts_material():
    plate = box(60, 40, 3)
    vented = plate - parts.hex_grid(50, 30, 5, cell=7, wall=2).translate(0, 0, -1)
    assert vented.volume < plate.volume
    assert len([s for s in vented.manifold.decompose()
                if s.volume() > 1e-9]) == 1


def test_stroke_single_region():
    sk = stroke([(0, 0), (10, 0), (20, 6), (28, 14)], width=4)
    solid = sk.extrude(3)
    assert len([s for s in solid.manifold.decompose()
                if s.volume() > 1e-9]) == 1


def test_hole_counterbore_geometry():
    block = box(30, 30, 20)
    cut = block - parts.hole(6, 12, counterbore=(10, 5)).translate(0, 0, 20)
    import math as m
    removed = block.volume - cut.volume
    expected = m.pi * (3 ** 2) * 12 + m.pi * (5 ** 2 - 3 ** 2) * 5
    assert abs(removed - expected) / expected < 0.01   # 64-segment circles
    assert len([s for s in cut.manifold.decompose() if s.volume() > 1e-9]) == 1


def test_aim_directions():
    h = parts.hole(4, 10, through_margin=1)
    for direction, axis, sign in (("+x", 0, +1), ("-x", 0, -1),
                                  ("+y", 1, +1), ("-y", 1, -1),
                                  ("-z", 2, -1), ("+z", 2, +1)):
        lo, hi = h.aim(direction).bbox
        deep_end = hi[axis] if sign > 0 else lo[axis]
        assert abs(deep_end - sign * 10) < 1e-6, direction


def test_tube_path_single_shell():
    pts = [(0, 0, 0), (0, 0, 10), (5, 0, 15), (12, 0, 16)]
    t = parts.tube_path(pts, d=6)
    assert len([s for s in t.manifold.decompose() if s.volume() > 1e-9]) == 1


# --- declared assembly expectations ----------------------------------------

def test_expectation_met_and_violated():
    from solidsight.assembly import expect, pair_analysis
    sc = make_scene()
    sc.emit(box(20, 20, 10), name="base")
    sc.emit(box(10, 10, 5).translate(0, 0, 10), name="top")     # touching
    sc.emit(box(5, 5, 5).translate(30, 0, 0), name="far")       # 15 clear
    expect("top", "base", status="touching")                    # met
    expect("far", "base", clearance=(20, 30))                   # violated
    pairs, checks = pair_analysis(sc, mode="free")
    by = {frozenset((p["a"], p["b"])): p for p in pairs}
    assert by[frozenset(("top", "base"))]["expectation"] == "met"
    assert by[frozenset(("far", "base"))]["expectation"] == "violated"
    assert any(c["id"] == "expectation-violated" and c["level"] == "fail"
               for c in checks)


def test_expectation_unknown_part_fails():
    from solidsight.assembly import expect, pair_analysis
    sc = make_scene()
    sc.emit(box(10, 10, 10), name="only")
    expect("only", "ghost", clearance=1)
    _pairs, checks = pair_analysis(sc, mode="free")
    assert any(c["id"] == "expectation-unknown-part" for c in checks)


# --- freeform + lofts + curved text ------------------------------------------

def test_loft_rejects_concave_profile():
    from solidsight import circle
    star = polygon([(10, 0), (2, 2), (0, 10), (-2, 2), (-10, 0),
                    (-2, -2), (0, -10), (2, -2)])
    with pytest.raises(Exception) as e:
        parts.loft([circle(d=20), star], [0, 10])
    assert "convex" in str(e.value)


def test_loft_single_shell():
    from solidsight import circle, ngon
    f = parts.loft([circle(d=40), ngon(6, d=28), circle(d=16)], [0, 30, 55])
    assert len([s for s in f.manifold.decompose() if s.volume() > 1e-9]) == 1


def test_wrapped_text_engraves():
    pot = cylinder(h=40, d=60)
    engraved = pot - parts.wrapped_text("AB", d=60, size=10).translate(0, 0, 20)
    assert engraved.volume < pot.volume - 5


def test_warp_deterministic_and_bulges():
    import math as m

    def bulge(x, y, z):
        s = 1 + 0.2 * m.sin(m.pi * z / 40)
        return x * s, y * s, z
    a = cylinder(h=40, d=30).refine(2).warp(bulge)
    b = cylinder(h=40, d=30).refine(2).warp(bulge)
    assert a.volume == b.volume
    assert a.size[0] > 30.5           # it actually bulged


# --- stability ---------------------------------------------------------------

def test_stability_detects_tippy_part():
    sc = make_scene()
    # heavy head on a tiny off-center foot: COM far outside the footprint
    tippy = (box(4, 4, 2)
             + box(30, 30, 6).translate(12, 0, 1.5))
    sc.emit(tippy.on_ground(), name="tippy")
    metrics, checks, _ = analyze_scene(sc, ValidationOptions(mode="free"))
    st = metrics["tippy"]["stability"]
    assert st["standing"] is False
    assert any(c["id"] == "unstable" for c in checks)


# --- skill self-hosting -----------------------------------------------------

def test_skill_install_and_remove(tmp_path):
    from solidsight.skill_install import MARKER, install_skill
    dst = install_skill(tmp_path / "solidsight", quiet=True)
    assert (dst / "SKILL.md").exists()
    assert (dst / "references" / "design-language.md").exists()
    assert (dst / MARKER).read_text(encoding="utf-8").strip()


def test_packaged_skill_matches_repo_copy():
    # the wheel ships tool/solidsight/skill_data as a copy of /skill —
    # this guards against the two drifting apart
    from pathlib import Path
    repo = Path(__file__).parents[2]          # tool/tests -> repo root
    skill, pkg = repo / "skill", repo / "tool" / "solidsight" / "skill_data"
    if not (skill / "SKILL.md").exists():
        pytest.skip("repo layout not present (installed package only)")
    for rel in ["SKILL.md"] + [f"references/{p.name}"
                               for p in (skill / "references").glob("*.md")]:
        a = (skill / rel).read_text(encoding="utf-8")
        b = (pkg / rel).read_text(encoding="utf-8")
        assert a == b, f"skill_data/{rel} is out of sync with skill/{rel}"
