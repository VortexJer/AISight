"""Regression tests — every test here pins a real bug found while
dogfooding. Run with: pytest tool/tests"""

import math
import time

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


# --- render: sliver triangles must not fake edges on flat faces ------------
# A disc with a complex engraving retriangulates its top face into long
# slivers; their normals tilt on float noise and drew phantom stripes
# across the flat top (found on examples/08-from-image).

def test_slivers_do_not_fake_edges_on_a_flat_face():
    from solidsight.render import _sound_faces
    disc = cylinder(h=4, d=90)
    star = polygon([(30 * math.cos(a), 30 * math.sin(a)) if i % 2 == 0 else
                    (12 * math.cos(a), 12 * math.sin(a))
                    for i, a in enumerate(
                        [j * math.pi / 10 for j in range(20)])])
    part = disc - star.extrude(2).translate(0, 0, 2.8)
    tm = part.to_trimesh()

    ok = _sound_faces(tm)
    normals = np.asarray(tm.face_normals, float)
    up = normals[:, 2] > 0.999                       # faces on the flat top
    # every sound top face agrees with +Z; the ones that do not are slivers
    tilted_sound = ok & (np.abs(normals[:, 2]) < 0.999) & \
        (np.asarray(tm.triangles, float)[:, :, 2].min(axis=1) > 3.99)
    assert up.sum() > 0
    assert tilted_sound.sum() == 0

    # and the filter must not reject honest geometry wholesale
    assert ok.mean() > 0.5
    assert _sound_faces(box(10, 10, 10).to_trimesh()).all()


def test_sound_face_filter_keeps_real_edges():
    # a gear's tooth flanks are real sharp edges and must survive
    from solidsight.render import _sound_faces
    g = parts.spur_gear(teeth=12, module=2, thickness=6)
    assert _sound_faces(g.to_trimesh()).mean() > 0.8


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


# --- rim breaks --------------------------------------------------------------

def test_chamfer_rim_removes_edge_material():
    cup = cylinder(h=30, d=40) - cylinder(h=30, d=34).translate(0, 0, 3)
    broken = cup.chamfer_rim(1.2)
    assert broken.volume < cup.volume - 10
    assert abs(broken.size[2] - cup.size[2]) < 1e-6   # height preserved
    assert len([s for s in broken.manifold.decompose()
                if s.volume() > 1e-9]) == 1


def test_round_rim_both_ends_single_shell():
    b = box(20, 20, 10).round_rim(2).round_rim(2, bottom=True)
    assert b.volume < 4000
    assert len([s for s in b.manifold.decompose() if s.volume() > 1e-9]) == 1


# --- ghost parts + swept insertion paths -------------------------------------

def test_ghost_measured_but_not_analyzed():
    from solidsight.assembly import expect
    sc = make_scene()
    sc.emit(box(20, 20, 10), name="body")
    sc.emit(box(5, 5, 30).translate(30, 0, 0), name="keepout", ghost=True)
    expect("keepout", "body", clearance=15)
    metrics, checks, pairs = analyze_scene(
        sc, ValidationOptions(mode="print-safe"))
    assert metrics["keepout"]["ghost"] is True
    assert "wall_thickness" not in metrics["keepout"]   # not print-analyzed
    by = {frozenset((p["a"], p["b"])): p for p in pairs}
    assert by[frozenset(("keepout", "body"))]["expectation"] == "met"
    # ghost must not trigger print-safe part checks (floating etc.)
    assert not any(c.get("part") == "keepout" for c in checks)


def test_swept_covers_travel():
    bar = box(4, 4, 4)
    path = parts.swept(bar, dz=-20)
    assert path.size[2] == pytest.approx(24, abs=0.01)
    assert path.volume > bar.volume * 4


# --- skill self-hosting -----------------------------------------------------

def test_skill_install_and_remove(tmp_path):
    from solidsight.skill_install import MARKER, install_skill
    dst = install_skill(tmp_path / "solidsight", quiet=True)
    assert (dst / "SKILL.md").exists()
    assert (dst / "references" / "design-language.md").exists()
    assert (dst / "domains" / "enclosures.md").exists()
    assert (dst / MARKER).read_text(encoding="utf-8").strip()


def test_skill_install_refreshes_removed_files(tmp_path):
    # installing over an older skill must not leave orphans behind
    from solidsight.skill_install import install_skill
    dst = install_skill(tmp_path / "solidsight", quiet=True)
    stale = dst / "domains" / "obsolete-playbook.md"
    stale.write_text("from a previous version", encoding="utf-8")
    install_skill(tmp_path / "solidsight", quiet=True)
    assert not stale.exists()


def test_packaged_skill_matches_repo_copy():
    # the wheel ships tool/solidsight/skill_data as a copy of /skill —
    # this guards against the two drifting apart
    from pathlib import Path
    base = Path(__file__).parents[1]          # tests -> solidsight/
    skill, pkg = base / "skill", base / "solidsight" / "skill_data"
    if not (skill / "SKILL.md").exists():
        pytest.skip("repo layout not present (installed package only)")
    rels = ["SKILL.md"]
    for sub in ("references", "domains"):
        rels += [f"{sub}/{p.name}" for p in (skill / sub).glob("*.md")]
    for rel in rels:
        assert (pkg / rel).exists(), f"skill_data/{rel} is missing"
        a = (skill / rel).read_text(encoding="utf-8")
        b = (pkg / rel).read_text(encoding="utf-8")
        assert a == b, f"skill_data/{rel} is out of sync with skill/{rel}"
    # and nothing extra shipped that the repo no longer has
    for sub in ("references", "domains"):
        shipped = {p.name for p in (pkg / sub).glob("*.md")}
        source = {p.name for p in (skill / sub).glob("*.md")}
        assert shipped == source, f"skill_data/{sub} has orphans: " \
                                  f"{shipped - source}"


# --- event streaming ---------------------------------------------------------

def test_event_bus_stage_ordering_and_silence():
    from solidsight.events import EventBus
    bus = EventBus()
    seen: list[dict] = []
    # no sinks: emitting must be a silent no-op
    bus.emit("x", "start")
    bus.add_sink(seen.append)
    with bus.stage("render", total=2) as st:
        st.tick("view iso")
        st.tick("view top")
    statuses = [(e["stage"], e["status"]) for e in seen]
    assert statuses == [("render", "start"), ("render", "progress"),
                        ("render", "progress"), ("render", "done")]
    assert seen[1]["pct"] == 50.0 and seen[2]["pct"] == 100.0
    assert seen[3]["duration_s"] >= 0
    # a crashing sink must never break the build
    bus.add_sink(lambda ev: 1 / 0)
    bus.emit("x", "info")


def test_build_emits_events_and_stays_deterministic(tmp_path):
    from solidsight.events import BUS, ndjson_sink
    from solidsight.report import build_model
    model = tmp_path / "m.py"
    model.write_text("from solidsight import *\n"
                     "emit(box(10, 10, 10), name='cube')\n",
                     encoding="utf-8")
    sink = ndjson_sink(tmp_path / "events.ndjson")
    BUS.add_sink(sink)
    try:
        build_model(model, tmp_path / "a", views=["iso"])
    finally:
        BUS.clear_sinks()
        sink.close()
    build_model(model, tmp_path / "b", views=["iso"])
    import json as _json
    events = [_json.loads(line) for line in
              (tmp_path / "events.ndjson").read_text(
                  encoding="utf-8").splitlines()]
    stages = {e["stage"] for e in events}
    assert {"model", "metrics", "render", "export"} <= stages
    # events must never leak into the deterministic artifacts
    ra = (tmp_path / "a" / "report.json").read_bytes()
    rb = (tmp_path / "b" / "report.json").read_bytes()
    assert ra == rb
    assert b"events" not in ra


# --- watch mode ---------------------------------------------------------------

def test_watch_fingerprint_detects_real_change(tmp_path):
    from solidsight.runner import run_model
    from solidsight.watch import scene_fingerprint
    m = tmp_path / "m.py"
    m.write_text("from solidsight import *\n"
                 "emit(box(10, 10, 10), name='cube')\n", encoding="utf-8")
    fp1, parts1 = scene_fingerprint(run_model(m), {"mode": "free"})
    # cosmetic edit: same geometry -> same fingerprint
    m.write_text("from solidsight import *\n# a comment\n"
                 "emit(box(10, 10, 10), name='cube')\n", encoding="utf-8")
    fp2, _ = scene_fingerprint(run_model(m), {"mode": "free"})
    assert fp1 == fp2
    # real edit -> different fingerprint
    m.write_text("from solidsight import *\n"
                 "emit(box(10, 10, 11), name='cube')\n", encoding="utf-8")
    fp3, parts3 = scene_fingerprint(run_model(m), {"mode": "free"})
    assert fp1 != fp3
    assert parts1["cube"] != parts3["cube"]
    # same geometry but different build options -> different fingerprint
    fp4, _ = scene_fingerprint(run_model(m), {"mode": "print-safe"})
    assert fp3 != fp4


def test_watch_initial_build_and_export_reuse(tmp_path):
    from solidsight.report import build_model
    from solidsight.watch import run_watch
    m = tmp_path / "m.py"
    m.write_text("from solidsight import *\n"
                 "emit(box(10, 10, 10), name='cube')\n", encoding="utf-8")
    lines: list[str] = []
    rc = run_watch(m, dict(out_dir=tmp_path / "out", views=["iso"],
                           export_stl=True),
                   say=lines.append, max_builds=1)
    assert rc == 0
    stl = tmp_path / "out" / "stl" / "cube.stl"
    assert stl.exists()
    assert any("build #1" in ln for ln in lines)
    # unchanged part: the export file must be reused, not rewritten
    before = stl.stat().st_mtime_ns
    report = build_model(m, out_dir=tmp_path / "out", views=["iso"],
                         export_stl=True, unchanged_parts={"cube"})
    assert stl.stat().st_mtime_ns == before
    assert "stl/cube.stl" in report["files"]["exports"][0].replace("\\", "/")


# --- browser viewer -----------------------------------------------------------

def test_viewer_payload_structure(tmp_path):
    from solidsight.report import build_model
    from solidsight.runner import run_model
    from solidsight.viewer import scene_payload, write_viewer
    m = tmp_path / "m.py"
    m.write_text("from solidsight import *\n"
                 "emit(box(20, 10, 5), name='plate', color='#4a708b')\n"
                 "emit(box(6, 6, 20).translate(0, 0, 2), name='post')\n",
                 encoding="utf-8")
    scene = run_model(m)
    report = build_model(m, out_dir=tmp_path / "out", views=["iso"])
    payload, mesh_bin = scene_payload(scene, report)
    assert [p["name"] for p in payload["parts"]] == ["plate", "post"]
    p0 = payload["parts"][0]
    # geometry lives in mesh.bin now: JSON carries offsets only
    import numpy as _np
    pos = _np.frombuffer(mesh_bin, dtype="<f4", count=p0["pos_n"],
                         offset=p0["pos_off"])
    idx = _np.frombuffer(mesh_bin, dtype="<u4", count=p0["idx_n"],
                         offset=p0["idx_off"])
    assert len(pos) % 3 == 0 and len(idx) % 3 == 0
    assert idx.max() < len(pos) // 3
    assert len(mesh_bin) == sum(4 * (q["pos_n"] + q["idx_n"])
                                for q in payload["parts"])
    assert p0["com"] is not None and p0["volume"] == pytest.approx(1000)
    assert payload["pairs"][0]["status"] == "collision"  # post pierces plate
    assert payload["pairs"][0]["overlap_bbox"] is not None
    write_viewer(tmp_path / "v", payload, "abc123", mesh_bin)
    assert (tmp_path / "v" / "mesh.bin").read_bytes() == mesh_bin
    assert (tmp_path / "v" / "index.html").exists()
    assert (tmp_path / "v" / "three.module.min.js").exists()
    assert (tmp_path / "v" / "version.txt").read_text(
        encoding="utf-8") == "abc123"
    import json as _json
    again = _json.loads((tmp_path / "v" / "scene.json").read_text(
        encoding="utf-8"))
    assert again == _json.loads(_json.dumps(payload))  # deterministic JSON


# --- universal formats ---------------------------------------------------------

def test_format_exports_and_roundtrip(tmp_path):
    from solidsight.report import build_model
    m = tmp_path / "m.py"
    m.write_text("from solidsight import *\n"
                 "emit(box(20, 10, 5), name='plate', color='#4a708b')\n"
                 "emit(cylinder(h=8, d=6).translate(40, 0, 0), name='pin')\n",
                 encoding="utf-8")
    report = build_model(m, out_dir=tmp_path / "out", views=["iso"],
                         export_obj=True, export_glb=True,
                         export_dxf=True, export_svg=True,
                         slices=[("z", 2.5)])
    exports = {e.replace("\\", "/") for e in report["files"]["exports"]}
    rel = {e.split("out/")[-1] for e in exports}
    assert {"obj/plate.obj", "obj/pin.obj", "obj/combined.obj",
            "glb/plate.glb", "glb/pin.glb", "glb/combined.glb",
            "dxf/slice_z_2p5.dxf", "svg/slice_z_2p5.svg"} <= rel

    import trimesh
    back = trimesh.load(str(tmp_path / "out" / "obj" / "plate.obj"),
                        force="mesh")
    assert back.is_watertight and back.volume == pytest.approx(1000, rel=1e-3)
    # combined GLB keeps the assembly structure: 2 named geometries
    sc = trimesh.load(str(tmp_path / "out" / "glb" / "combined.glb"))
    assert set(sc.geometry.keys()) == {"plate", "pin"}
    # from_mesh() reimports the GLB part
    m2 = tmp_path / "m2.py"
    m2.write_text("from solidsight import *\n"
                  "emit(from_mesh('out/glb/plate.glb'), name='again')\n",
                  encoding="utf-8")
    from solidsight.runner import run_model
    sc2 = run_model(m2)
    assert sc2.parts[0].solid.volume == pytest.approx(1000, rel=1e-3)


def test_convert_cli(tmp_path):
    from solidsight.cli import main
    import trimesh
    src = tmp_path / "cube.stl"
    trimesh.creation.box(extents=[10, 10, 10]).export(src)
    dst = tmp_path / "cube.obj"
    assert main(["convert", str(src), str(dst)]) == 0
    assert dst.exists()
    assert main(["convert", str(src), str(tmp_path / "cube.step")]) == 1


# --- engineering components catalog --------------------------------------------

def test_components_single_shell_and_exact_dims():
    cases = {
        "washer": parts.washer(5),                    # ISO 7089: 5.3/10/1.0
        "bearing": parts.bearing("608"),              # 8 x 22 x 7
        "shaft": parts.shaft(5, 60, flat=0.5),
        "pulley": parts.timing_pulley(20, bore=5),
        "spring": parts.spring(d=12, wire=1.6, length=30, coils=7),
        "nema17": parts.nema_motor(17),
        "servo": parts.micro_servo(),
        "extrusion": parts.extrusion_profile(80),
        "lead_screw": parts.lead_screw(8, 40),
        "rail": parts.linear_rail(60, size=9),
        "carriage": parts.linear_carriage(9),
        "chain": parts.cable_chain_link(),
    }
    for name, s in cases.items():
        shells = [p for p in s.manifold.decompose() if p.volume() > 1e-9]
        assert len(shells) == 1, f"{name} is {len(shells)} shells"
    w = cases["washer"]
    assert w.size[0] == pytest.approx(10, abs=0.01)       # OD
    assert w.size[2] == pytest.approx(1.0, abs=0.01)      # thickness
    b = cases["bearing"]
    assert b.size[0] == pytest.approx(22, abs=0.01)
    assert b.size[2] == pytest.approx(7, abs=0.01)
    n = cases["nema17"]
    assert n.size[0] == pytest.approx(42.3, abs=0.01)     # faceplate
    e = cases["extrusion"]
    assert e.size[0] == pytest.approx(20, abs=0.01)
    assert e.size[2] == pytest.approx(80, abs=0.01)
    # GT2 20T pulley: pitch diameter 20*2/pi = 12.73 -> flange od ~15.7
    p = cases["pulley"]
    assert p.size[0] == pytest.approx(20 * 2 / 3.14159 + 3, abs=0.1)


def test_component_determinism():
    a = parts.nema_motor(17).to_trimesh()
    b = parts.nema_motor(17).to_trimesh()
    assert np.array_equal(a.vertices, b.vertices)


# --- component database ---------------------------------------------------------

def test_component_db_search_and_instantiate():
    from solidsight.components_db import DATABASE, component, search
    hits = search("m4 socket head")
    assert hits and hits[0]["id"] == "iso4762_m4"
    hits = search("608 bearing")
    assert hits and hits[0]["id"] == "bearing_608"
    assert search("nema17")[0]["id"] == "nema17"
    # instantiation via parts.component with a free param
    s = component("iso4762_m4", length=16)
    assert s.size[2] == pytest.approx(20, abs=0.1)     # 16 shank + 4 head
    assert s.size[0] == pytest.approx(7.0, abs=0.2)    # exact ISO head od
    b = component("bearing_608")
    assert b.size[0] == pytest.approx(22, abs=0.01)
    # free param required -> actionable error
    from solidsight.errors import SolidsightError
    with pytest.raises(SolidsightError):
        component("iso4762_m4")
    with pytest.raises(SolidsightError):
        component("does_not_exist")
    # every db entry maps to a real catalog generator
    from solidsight import parts as P
    for e in DATABASE.values():
        assert hasattr(P, e["fn"]), e["id"]


def test_cap_screw_single_shell():
    s = parts.cap_screw(4, 16)
    shells = [p for p in s.manifold.decompose() if p.volume() > 1e-9]
    assert len(shells) == 1


# --- technical drawings ---------------------------------------------------------

def test_drawing_circle_detection_and_pdf(tmp_path):
    from solidsight.drawings import draw_sheet, find_circles, hole_table
    make_scene()
    plate = box(40, 30, 6)
    plate = plate - parts.hole(5, 8).translate(10, 5, 6) \
                  - parts.hole(5, 8).translate(-10, -5, 6)
    tm = plate.to_trimesh()
    circles = find_circles(tm)
    fives = [c for c in circles if abs(c["d"] - 5) < 0.2]
    assert len(fives) >= 2                     # both drilled rims found
    # the rectangular outline must NOT be reported as a circle
    assert not any(c["d"] > 30 for c in circles)
    holes = hole_table(circles, tm.extents)
    thru = [h for h in holes if abs(h["d"] - 5) < 0.2 and h["thru"]]
    assert len(thru) == 2                      # paired rims -> THRU holes
    draw_sheet("plate", tm, tmp_path / "plate.pdf", "m.py", "test")
    pdf = (tmp_path / "plate.pdf").read_bytes()
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000
    assert b"CreationDate" not in pdf          # deterministic sheet


def test_drawing_hidden_lines(tmp_path):
    from solidsight.drawings import view_edges
    # a block with a lug BEHIND it (as seen from the front): the lug's
    # edges must classify as hidden
    make_scene()
    solid = box(30, 10, 20) + box(10, 10, 10).translate(0, 10, 5)
    d = view_edges(solid.to_trimesh(), "front", res=500)
    assert len(d["visible"]) > 0 and len(d["hidden"]) > 0


# --- robotics export -------------------------------------------------------------

def test_urdf_export_masses_and_tree(tmp_path):
    import xml.etree.ElementTree as ET
    from solidsight.robot import export_urdf, joint
    sc = make_scene()
    sc.emit(box(60, 60, 10), name="base")
    sc.emit(box(10, 40, 8).translate(0, 15, 10), name="arm")
    joint("base", "arm", type="revolute", axis=(0, 0, 1),
          origin=(0, 0, 10), limits=(-90, 90))
    export_urdf(sc, tmp_path, "bot.py", density=1.24,
                say=lambda *a, **k: None)
    root = ET.parse(tmp_path / "robot" / "bot.urdf").getroot()
    links = {l.get("name"): l for l in root.findall("link")}
    assert set(links) == {"base", "arm"}
    # analytic check: 60x60x10 mm PLA plate = 44.64 g
    m = float(links["base"].find("inertial/mass").get("value"))
    assert m == pytest.approx(0.04464, rel=1e-3)
    # analytic inertia of a solid cuboid about COM: m(b^2+c^2)/12 (SI)
    ixx = float(links["base"].find("inertial/inertia").get("ixx"))
    expected = m * (0.060 ** 2 + 0.010 ** 2) / 12
    assert ixx == pytest.approx(expected, rel=1e-3)
    j = root.find("joint")
    assert j.get("type") == "revolute"
    import math as _m
    assert float(j.find("limit").get("lower")) == pytest.approx(
        _m.radians(-90))
    assert (tmp_path / "robot" / "meshes" / "arm_collision.stl").exists()


def test_urdf_tree_validation_errors(tmp_path):
    from solidsight.errors import SolidsightError
    from solidsight.robot import export_urdf, joint
    sc = make_scene()
    sc.emit(box(10, 10, 10), name="a")
    sc.emit(box(10, 10, 10).translate(20, 0, 0), name="b")
    sc.emit(box(10, 10, 10).translate(40, 0, 0), name="c")
    joint("a", "b")                       # c left floating -> second root
    with pytest.raises(SolidsightError, match="ONE root"):
        export_urdf(sc, tmp_path, "bot.py", say=lambda *a, **k: None)
    joint("a", "c")
    export_urdf(sc, tmp_path, "bot.py", say=lambda *a, **k: None)  # now ok


# --- assembly intelligence + reasoning API ---------------------------------------

def test_bom_groups_identical_parts():
    from solidsight.bom import assembly_sequence, axis_play, bom
    from solidsight.assembly import pair_analysis
    sc = make_scene()
    leg = cylinder(h=30, d=8)
    sc.emit(box(80, 40, 5).translate(0, 0, 30), name="table")
    for i, (x, y) in enumerate([(-30, -12), (30, -12), (-30, 12), (30, 12)]):
        sc.emit(leg.translate(x, y, 0), name=f"leg_{i}")
    rows = bom(sc)
    legs = [r for r in rows if r["count"] == 4]
    assert len(legs) == 1 and sorted(legs[0]["names"]) == \
        ["leg_0", "leg_1", "leg_2", "leg_3"]
    pairs, _ = pair_analysis(sc)
    seq = assembly_sequence(sc, pairs)
    assert seq[0]["part"].startswith("leg")      # legs start at z=0
    assert seq[-1]["part"] == "table" or any(
        s["part"] == "table" and "registers" in s["note"] for s in seq)
    play = axis_play(sc)
    assert play["z"]["total_play_mm"] == pytest.approx(0, abs=0.01)


def test_iso_fits_textbook_values():
    from solidsight.fits import fit
    r = fit(8, "H7", "g6")                       # classic slide fit
    assert r["type"] == "clearance"
    assert r["clearance_min_mm"] == pytest.approx(0.005, abs=1e-4)
    assert r["clearance_max_mm"] == pytest.approx(0.029, abs=1e-4)
    r = fit(22, "H7", "p6")                      # press fit
    assert r["type"] == "interference"
    r = fit(10, "H7", "k6")
    assert r["type"] == "transition"
    from solidsight.errors import SolidsightError
    with pytest.raises(SolidsightError):
        fit(8, "G7", "g6")                       # only H-basis holes
    with pytest.raises(SolidsightError):
        fit(500, "H7", "g6")                     # out of table


def test_explain_covers_every_emitted_check_id():
    from solidsight.explain import EXPLANATIONS
    core_ids = {"thin-wall", "internal-cavity", "multiple-shells",
                "not-watertight", "overhang", "parts-overlap",
                "expectation-violated", "union-touching",
                "noop-difference", "floating", "unstable"}
    assert core_ids <= set(EXPLANATIONS)
    for e in EXPLANATIONS.values():
        assert e["meaning"] and e["fixes"]


# --- plugin system ---------------------------------------------------------------

def test_plugins_isolation_and_checks(tmp_path):
    import solidsight.plugins as PL
    from solidsight.report import build_model

    api = PL.PluginAPI("testplug")
    api.add_validator("envelope", lambda scene: [
        {"message": f"scene has {len(scene.parts)} part(s)"}])
    api.add_validator("boom", lambda scene: 1 / 0)      # must not crash
    api.add_exporter("manifest", lambda scene, out: ["x"])
    old = PL._registry
    PL._registry = [api]
    try:
        m = tmp_path / "m.py"
        m.write_text("from solidsight import *\n"
                     "emit(box(10, 10, 10), name='cube')\n",
                     encoding="utf-8")
        report = build_model(m, out_dir=tmp_path / "out", views=["iso"])
        ids = [c["id"] for c in report["checks"]]
        assert "plugin-testplug-envelope" in ids       # validator ran
        assert "plugin-error" in ids                   # crash -> warning
        assert report["status"] != "failed"            # never fails a build
    finally:
        PL._registry = old


# --- benchmark suite --------------------------------------------------------------

def test_bench_grader_logic():
    from solidsight.bench import grade
    report = {"status": "ok", "scene": {"part_count": 2},
              "parts": {"a": {"shells": 1}},
              "pairs": [{"a": "a", "b": "b", "status": "clear",
                         "min_clearance_mm": 0.2}],
              "checks": [{"id": "overhang"}]}
    spec = {"asserts": [
        {"path": "status", "in": ["ok", "warnings"]},
        {"path": "parts.a.shells", "equals": 1},
        {"path": "scene.part_count", "between": [1, 3]},
        {"check_absent": "internal-cavity"},
        {"check_present": "overhang"},
        {"pair": ["a", "b"], "status": "clear",
         "clearance_between": [0.1, 0.3]},
    ]}
    results = grade(report, spec)
    assert all(r["ok"] for r in results)
    bad = grade(report, {"asserts": [{"path": "parts.a.shells",
                                      "equals": 2}]})
    assert not bad[0]["ok"]


def test_bench_fast_references(tmp_path):
    # the two fastest benchmarks self-test in CI; the full suite runs
    # via `solidsight bench run` (see benchmarks/README.md)
    from pathlib import Path
    from solidsight.bench import run_benchmark
    root = Path(__file__).parents[1] / "benchmarks"
    if not root.is_dir():
        pytest.skip("benchmarks live in the repo, not the wheel")
    for name in ("01-washer", "05-cavity-trap"):
        res = run_benchmark(root / name)
        assert res["passed"], res["results"]


# --- semantic feature metadata ----------------------------------------------------

def test_emit_features_reach_the_report(tmp_path):
    from solidsight.report import build_model
    m = tmp_path / "m.py"
    m.write_text(
        "from solidsight import *\n"
        "p = box(30, 20, 6) - parts.hole(5, 8).translate(10, 0, 6)\n"
        "emit(p, name='plate', features=[\n"
        "    {'type': 'hole', 'd': 5, 'at': [10, 0, 6], 'thru': True}])\n",
        encoding="utf-8")
    report = build_model(m, out_dir=tmp_path / "out", views=["iso"])
    feats = report["parts"]["plate"]["features"]
    assert feats == [{"type": "hole", "d": 5, "at": [10, 0, 6],
                      "thru": True}]
    # malformed features -> actionable SceneError
    m.write_text("from solidsight import *\n"
                 "emit(box(5, 5, 5), name='p', features=['hole'])\n",
                 encoding="utf-8")
    from solidsight.errors import SolidsightError
    with pytest.raises(SolidsightError, match="type"):
        build_model(m, out_dir=tmp_path / "out2", views=["iso"])


# --- critique + cost --------------------------------------------------------------

def test_critique_and_cost():
    from solidsight.review import cost_estimate, critique
    sc = make_scene()
    hollow = box(30, 30, 30) - box(20, 20, 20).translate(0, 0, 5)
    sc.emit(hollow, name="trap")
    res = critique(sc)
    assert res["verdict"] == "REVISE"
    cavity = [f for f in res["findings"] if f["id"] == "internal-cavity"]
    assert cavity and cavity[0]["fix_menu"]          # explain() attached
    assert any("watertight" in g for g in res["verified_good"])
    est = cost_estimate(sc, "fdm")
    # 30^3 - 20^3 = 19000 mm3 -> 23.6 g PLA
    assert est["parts"][0]["material_g"] == pytest.approx(23.6, abs=0.5)
    cnc = cost_estimate(sc, "cnc-alu")
    assert cnc["parts"][0]["material_g"] == pytest.approx(72.9, abs=1)
    from solidsight.errors import SolidsightError
    with pytest.raises(SolidsightError):
        cost_estimate(sc, "laser")


# --- motion inspection ------------------------------------------------------------

def test_motion_finds_the_blocked_arc():
    from solidsight.motion import inspect_motion
    from solidsight.robot import joint
    sc = make_scene()
    sc.emit(box(60, 60, 5), name="base")
    # arm rotating about Z at the origin; a post stands in its path at +X
    sc.emit(box(40, 8, 5).translate(15, 0, 5), name="arm")
    sc.emit(cylinder(h=20, d=10).translate(25, 25, 0), name="post")
    joint("base", "arm", type="revolute", axis=(0, 0, 1),
          origin=(0, 0, 5), limits=(0, 90))
    reports = inspect_motion(sc, steps=6)
    r = reports[0]
    assert r["joint"] == "base_to_arm"
    hit_posts = [s for s in r["collisions"]
                 if any(h["part"] == "post" for h in s["hits"])]
    assert hit_posts, "the arm must hit the post around 45 deg"
    assert any(abs(s["value"] - 45) < 16 for s in hit_posts)
    assert 0.0 in r["free_positions"]        # start is clear of the post
    # non-principal axis -> actionable error
    from solidsight.errors import SolidsightError
    sc2 = make_scene()
    sc2.emit(box(10, 10, 10), name="a")
    sc2.emit(box(10, 10, 10).translate(20, 0, 0), name="b")
    joint("a", "b", type="revolute", axis=(1, 1, 0), origin=(0, 0, 0),
          limits=(0, 90))
    with pytest.raises(SolidsightError, match="principal"):
        inspect_motion(sc2)


# --- BOM rows must identify parts, not dump construction trees ------------
# `solidsight assembly` printed 300-char nested desc() strings as line
# items ("difference(difference(rounded_box(... minus snap_slot(w=8))").

def test_bom_item_is_a_label_not_a_construction_tree():
    from solidsight.bom import bom
    sc = make_scene()
    from solidsight import rounded_box
    composed = (rounded_box(50, 34, 24, r=3)
                - box(44, 28, 21).translate(0, 0, 2)
                - cylinder(h=30, d=6))
    sc.emit(composed, name="box")
    sc.emit(parts.bearing(name="608"), name="brg")
    rows = {r["names"][0]: r for r in bom(sc)}

    # a user-composed solid is identified by its NAME + size, not its tree
    assert rows["box"]["item"] == "custom part"
    assert rows["box"]["size_mm"] == [50.0, 34.0, 24.0]
    assert "difference(" in rows["box"]["desc"]      # tree still traceable

    # catalog provenance survives as the item label
    assert rows["brg"]["item"].startswith("bearing")
    assert "(" in rows["brg"]["item"]


# --- joints carry a real name (URDF/SDF + motion --joint) -----------------
# joints were identified only as "<parent>_to_<child>": a ROS consumer
# wants "shoulder_pan", and `motion --joint` had no other handle.

def test_joint_name_defaults_and_overrides():
    from solidsight.motion import _jname
    sc = make_scene()
    sc.emit(box(20, 20, 5), name="base")
    sc.emit(box(10, 10, 40), name="link1")
    sc.emit(box(8, 8, 30), name="link2")

    from solidsight.robot import joint
    joint("base", "link1", type="revolute", axis=(0, 0, 1),
          origin=(0, 0, 5), limits=(-90, 90))                 # default name
    joint("link1", "link2", type="revolute", axis=(0, 1, 0),
          origin=(0, 0, 45), limits=(0, 120), name="elbow")   # declared

    assert _jname(sc.joints[0]) == "base_to_link1"
    assert _jname(sc.joints[1]) == "elbow"


def test_duplicate_joint_names_are_rejected():
    from solidsight.errors import BadArgumentError
    from solidsight.robot import joint
    sc = make_scene()
    sc.emit(box(20, 20, 5), name="base")
    sc.emit(box(10, 10, 40), name="link1")
    joint("base", "link1", type="revolute", axis=(0, 0, 1),
          origin=(0, 0, 5), limits=(-90, 90), name="j")
    with pytest.raises(BadArgumentError):
        joint("base", "link1", type="revolute", axis=(0, 1, 0),
              origin=(0, 0, 5), limits=(-90, 90), name="j")


def test_urdf_and_sdf_use_the_declared_joint_name(tmp_path):
    import xml.etree.ElementTree as ET

    from solidsight.robot import export_urdf, joint
    sc = make_scene()
    sc.emit(box(20, 20, 5), name="base")
    sc.emit(box(10, 10, 40).translate(0, 0, 5), name="link1")
    joint("base", "link1", type="revolute", axis=(0, 0, 1),
          origin=(0, 0, 5), limits=(-90, 90), name="shoulder_pan")
    export_urdf(sc, tmp_path, "arm.py", sdf=True, say=lambda *_a, **_k: None)

    urdf = ET.parse(tmp_path / "robot" / "arm.urdf").getroot()
    assert [j.get("name") for j in urdf.findall("joint")] == ["shoulder_pan"]
    sdf = ET.parse(tmp_path / "robot" / "arm.sdf").getroot()
    assert [j.get("name") for j in sdf.iter("joint")] == ["shoulder_pan"]


# --- CLI output must not sit in a buffer when redirected ------------------
# Agents run `watch`/`view` redirected to a log, never on a tty. Python
# block-buffers a non-tty stdout, so the log stayed EMPTY while the loop
# ran (i.e. forever) until _say() started flushing.

def test_cli_output_flushes_when_not_a_tty(tmp_path):
    import subprocess
    import sys
    model = tmp_path / "m.py"
    model.write_text("from solidsight import *\n"
                     "emit(box(10, 10, 10), name='cube')\n", encoding="utf-8")
    log = tmp_path / "out.log"
    # a build that never exits on its own: watch. Kill it, then read the
    # log — anything written before the kill must already be on disk.
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen(
            [sys.executable, "-m", "solidsight.cli", "watch", str(model),
             "--views", "iso", "--out", str(tmp_path / "out")],
            stdout=fh, stderr=subprocess.STDOUT)
        try:
            deadline = time.time() + 90
            while time.time() < deadline:
                if "watching" in log.read_text(encoding="utf-8", errors="replace"):
                    break
                time.sleep(0.5)
        finally:
            p.kill()
            p.wait(timeout=30)
    text = log.read_text(encoding="utf-8", errors="replace")
    assert "build #1" in text, f"nothing flushed before the kill: {text!r}"
    assert "watching" in text


def test_view_starts_before_the_model_exists(tmp_path):
    """The live preview is a screen FIRST: `view missing.py` must serve
    a waiting placeholder (spinner) immediately and hot-switch to the
    scene when the file appears and builds. User: 'sigue sin ensenar
    el live preview'."""
    import json
    import subprocess
    import sys
    import time
    model = tmp_path / "late_model.py"
    proc = subprocess.Popen(
        [sys.executable, "-m", "solidsight.cli", "view", str(model),
         "--no-open", "--poll", "0.2", "--port", "0"],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    scene_json = tmp_path / "out" / "viewer" / "scene.json"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not scene_json.exists():
            time.sleep(0.2)
        assert scene_json.exists(), "no placeholder served"
        d = json.loads(scene_json.read_text(encoding="utf-8"))
        assert d["status"] == "waiting" and d["parts"] == []
        model.write_text("from solidsight import *\n"
                         "emit(box(10, 10, 5), name='late')\n",
                         encoding="utf-8")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            d = json.loads(scene_json.read_text(encoding="utf-8"))
            if d["status"] != "waiting":
                break
            time.sleep(0.3)
        assert [p["name"] for p in d["parts"]] == ["late"]
    finally:
        proc.kill()


def test_emit_material_reaches_viewer_and_glb(tmp_path):
    """emit(material=...) is the part's visual finish: preset resolved,
    carried in the viewer payload and the GLB's PBR material."""
    from solidsight.scene import MATERIALS, Scene, activate, deactivate
    from solidsight.geom import box
    from solidsight.viewer import scene_payload
    import pytest as _pytest
    from solidsight.errors import SceneError

    sc = Scene()
    activate(sc)
    try:
        sc.emit(box(10, 10, 5), name="body", material="chrome")
        sc.emit(box(5, 5, 5), name="window",
                material={"opacity": 0.4, "roughness": 0.05})
        with _pytest.raises(SceneError):
            sc.emit(box(2, 2, 2), name="bad", material="vibranium")
    finally:
        deactivate()
    assert sc.parts[0].material == MATERIALS["chrome"]
    assert sc.parts[1].material["opacity"] == 0.4

    report = {"model": "m", "mode": "free", "status": "ok",
              "scene": {"bbox": {"min": [0, 0, 0], "max": [1, 1, 1]},
                        "size": [1, 1, 1]},
              "parts": {}, "checks": []}
    pay, _bin = scene_payload(sc, report)
    assert pay["parts"][0]["material"]["metallic"] == 1.0

    from solidsight.report import _export_glb_scene
    import trimesh
    glb = tmp_path / "s.glb"
    _export_glb_scene(sc.parts, glb)
    back = trimesh.load(glb)
    mats = {g.visual.material.name: g.visual.material
            for g in back.geometry.values()}
    assert float(mats["body"].metallicFactor) == 1.0
    alpha = float(mats["window"].baseColorFactor[3])
    if alpha > 1.0:                       # GLTF loaders return uint8 0..255
        alpha /= 255.0
    assert alpha < 1.0


def test_loft_sections_handles_concave_stations():
    """The car-body tool: a concave (shoulder-notched) section lofted
    straight must keep its concavity exactly — hull-based loft() would
    bloat across it. Volume is exact for a prism."""
    from solidsight.parts import loft_sections
    sec = [(-50, 0), (50, 0), (50, 40), (20, 40), (20, 60), (-20, 60),
           (-20, 40), (-50, 40)]
    s = loft_sections([sec, sec], [0.0, 100.0])
    assert abs(s.volume - 480000.0) < 1.0
    assert s.to_trimesh().is_watertight


def test_loft_sections_rejects_mismatched_point_counts():
    from solidsight.parts import loft_sections
    from solidsight.errors import BadArgumentError
    import pytest as _pytest
    tri = [(0, 0), (10, 0), (0, 10)]
    quad = [(0, 0), (10, 0), (10, 10), (0, 10)]
    with _pytest.raises(BadArgumentError):
        loft_sections([tri, quad], [0.0, 10.0])


def test_viewer_falls_back_when_the_port_is_taken(tmp_path):
    """Two viewers must never share a URL. The second one probes the
    requested port, finds it owned (on Windows SO_REUSEADDR would have
    let it bind anyway and the browser would keep reading the stale
    server) and serves on the next free port, saying so.
    User: 'el viewer deberia comprobar automaticamente si puede usar
    ese port y sino usar otro libre'."""
    from solidsight.viewer import serve_viewer, write_viewer
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    for d in (a_dir, b_dir):
        write_viewer(d, {"status": "waiting", "parts": []}, "waiting-0")
    lines_a, lines_b = [], []
    first = serve_viewer(a_dir, 0, lines_a.append)     # any free port
    port = first.server_address[1]
    try:
        second = serve_viewer(b_dir, port, lines_b.append)
        try:
            assert second.server_address[1] != port
            assert any("in use" in ln for ln in lines_b), lines_b
        finally:
            second.shutdown()
            second.server_close()
    finally:
        first.shutdown()
        first.server_close()


def test_image_outline_refuses_a_photo_instead_of_hanging(tmp_path):
    """A photograph traces into thousands of texture contours; the old
    behaviour was a sketch that took ~40 s to extrude into ~800k
    triangles and dragged every later boolean. It must be refused with
    the numbers and a remedy. User: 'se atasca muchisimo cuando mira
    fotos'."""
    import numpy as np
    from PIL import Image
    from solidsight.errors import SolidsightError
    from solidsight.vision import image_outline
    rng = np.random.default_rng(7)
    noise = rng.integers(0, 255, size=(900, 1200), dtype=np.uint8)
    p = tmp_path / "photo.png"
    Image.fromarray(noise, mode="L").save(p)
    with pytest.raises(SolidsightError) as e:
        image_outline(str(p), width=400)
    msg = e.value.render()
    assert "shredded" in msg and "contours" in msg
    assert "min_area=" in msg and "profile_read" in msg


def test_image_outline_still_traces_a_clean_drawing(tmp_path):
    """The guard must not touch the real case: a flat two-tone shape
    traces as before, and the trace_px cap keeps its size exact."""
    import numpy as np
    from PIL import Image
    from solidsight.vision import image_outline
    img = np.full((2400, 3200), 255, dtype=np.uint8)   # over trace_px
    img[600:1800, 800:2400] = 0                        # one black rect
    p = tmp_path / "flat.png"
    Image.fromarray(img, mode="L").save(p)
    sk = image_outline(str(p), width=320.0)            # 0.1 mm per px
    rings = sk.cross_section.to_polygons()
    assert len(rings) == 1
    xs = [pt[0] for pt in rings[0]]
    ys = [pt[1] for pt in rings[0]]
    assert (max(xs) - min(xs)) == pytest.approx(160.0, abs=1.0)
    assert (max(ys) - min(ys)) == pytest.approx(120.0, abs=1.0)


def test_viewer_geometry_is_binary_not_json(tmp_path):
    """A 100k-triangle scene used to be a 22 MB scene.json rebuilt in
    Python loops on every save. Geometry must ride in mesh.bin and the
    JSON must stay small. User: 'el viewer es super lento'."""
    from solidsight.report import build_model
    from solidsight.runner import run_model
    from solidsight.viewer import scene_payload, write_viewer
    import json as _json
    m = tmp_path / "m.py"
    m.write_text("from solidsight import *\n"
                 "emit(sphere(r=20, segments=120), name='ball')\n",
                 encoding="utf-8")
    scene = run_model(m)
    report = build_model(m, out_dir=tmp_path / "out", views=["iso"],
                         skip_pairs=True)
    payload, mesh_bin = scene_payload(scene, report)
    js = _json.dumps(payload)
    assert "positions" not in js and "indices" not in js
    assert len(mesh_bin) > 20 * len(js)          # bytes are where it went
    write_viewer(tmp_path / "v", payload, "fp1", mesh_bin)
    # version.txt is the reload trigger: it must land after the geometry
    assert (tmp_path / "v" / "mesh.bin").stat().st_mtime_ns <= \
           (tmp_path / "v" / "version.txt").stat().st_mtime_ns


def test_empty_views_means_render_nothing(tmp_path):
    """`views=[]` must render NOTHING. `views = views or [...]` treated
    an empty list as "unset" and quietly rendered the four default
    views, which is what kept the viewer's light build at 42 s."""
    from solidsight.report import build_model
    m = tmp_path / "m.py"
    m.write_text("from solidsight import *\nemit(box(10, 10, 10), name='b')\n",
                 encoding="utf-8")
    rep = build_model(m, out_dir=tmp_path / "out", views=[], skip_pairs=True)
    assert rep["files"]["renders"] == []
    assert list((tmp_path / "out" / "renders").glob("*.png")) == []
    rep2 = build_model(m, out_dir=tmp_path / "out2", skip_pairs=True)
    assert len(rep2["files"]["renders"]) == 4     # None still means default


def test_light_build_skips_the_expensive_metrics(tmp_path):
    """The live viewer needs geometry, not 600-ray wall probes: light
    builds must keep bbox/volume/triangles and drop the rest, which is
    what took 12.3 s of a 138k-triangle bottle's 42 s rebuild."""
    from solidsight.report import build_model
    m = tmp_path / "m.py"
    m.write_text("from solidsight import *\n"
                 "emit(sphere(r=15, segments=64), name='ball')\n",
                 encoding="utf-8")
    light = build_model(m, out_dir=tmp_path / "l", views=[], light=True,
                        skip_pairs=True)["parts"]["ball"]
    full = build_model(m, out_dir=tmp_path / "f", views=[],
                       skip_pairs=True)["parts"]["ball"]
    assert light["light"] is True
    assert light["volume_mm3"] == full["volume_mm3"]
    assert light["triangles"] == full["triangles"]
    for heavy in ("wall_thickness", "overhangs", "internal_voids",
                  "shells", "genus", "stability"):
        assert heavy not in light, heavy
        assert heavy in full, heavy


def test_declared_opacity_survives_the_xray_toggle():
    """The viewer forced opacity=1 on every non-ghost part whenever the
    option panel was touched, wiping emit(material={'opacity':...}).
    User: 'nuestro viewer no interpreta transparencia'."""
    from pathlib import Path
    html = (Path(__file__).parents[1] / "solidsight" / "viewer_assets"
            / "index.html").read_text(encoding="utf-8")
    assert "declaredOpacity" in html
    assert "mat.opacity = opts.xray ? 0.35 : 1;" not in html
    # and the packaged asset must be the same file the repo ships
    pkg = (Path(__file__).parents[1] / "solidsight" / "viewer_assets"
           / "index.html")
    assert pkg.exists()


def test_closing_the_window_frees_the_port(tmp_path):
    """A closed viewer window used to leave a process holding its port
    forever, so the next `view` landed on 8378 while the human stared at
    a stale window. The page beacons /bye on pagehide; the server stops
    and releases the port. A RELOAD also beacons, so a request inside
    the grace period must cancel the shutdown.
    User: 'si yo cierro una ventana del viewer libere el port y tal'."""
    import time as _t
    import urllib.request as _u
    from solidsight.viewer import _port_is_free, serve_viewer, \
        watch_for_window_close, write_viewer
    d = tmp_path / "v"
    write_viewer(d, {"status": "waiting", "parts": []}, "waiting-0")
    stopped = []
    httpd = serve_viewer(d, 0, lambda *_: None)
    port = httpd.server_address[1]
    watch_for_window_close(httpd, lambda *_: None,
                           lambda: (stopped.append(True), httpd.shutdown()))
    url = f"http://127.0.0.1:{port}"
    _u.urlopen(f"{url}/version.txt", timeout=3).read()      # a window opens
    # a reload: bye, then a poll inside the grace -> must survive
    _u.urlopen(_u.Request(f"{url}/bye", data=b"", method="POST"), timeout=3)
    _t.sleep(1.0)
    _u.urlopen(f"{url}/version.txt", timeout=3).read()
    _t.sleep(2.0)
    assert not stopped, "a reload must not stop the viewer"
    # now the window really closes
    _u.urlopen(_u.Request(f"{url}/bye", data=b"", method="POST"), timeout=3)
    for _ in range(120):
        if stopped:
            break
        _t.sleep(0.25)
    assert stopped, "closing the window must stop the server"
    httpd.server_close()
    # "free" = a new viewer can take it back. Probe exactly the way
    # serve_viewer does: a raw bind() calls a TIME_WAIT port busy on
    # macOS/Linux even though the server (SO_REUSEADDR) can have it.
    assert _port_is_free(port), "the port must be usable again"


def test_touching_transparent_parts_do_not_z_fight():
    """A glass part sitting flush against a solid one shares its face, and a
    shared face rasterises to the same depth on both -> the seam flickered
    while orbiting. Two guards: the depth range now follows the model instead
    of a fixed 0.1 -> 100000 frustum, and see-through parts carry a polygon
    offset so the tie is always broken the same way.
    User: 'a veces parpadea si 2 piezas estan pegadas y una es transparente'."""
    from pathlib import Path
    html = (Path(__file__).parents[1] / "solidsight" / "viewer_assets"
            / "index.html").read_text(encoding="utf-8")
    assert "biasDepth" in html
    assert "polygonOffset" in html
    # the frustum is computed, not hard-coded wide open
    assert "camera.near = Math.max(" in html
    assert "camera.far = sph.r" in html
    # and the bias is re-decided on the x-ray toggle, not only at build time
    assert "biasDepth(mat, mat.opacity < 1, rank)" in html
