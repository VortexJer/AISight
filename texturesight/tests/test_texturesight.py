"""Tests for texturesight.

The example assets are synthetic on purpose: every defect is injected by
examples/make_assets.py with a known magnitude, so these tests assert
the measurements find exactly that — and that the clean reference stays
clean, which is the half that keeps the tool trustworthy.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from texturesight import analyze_texture, analyze_uv, parse_obj
from texturesight.errors import BadMeshError
from texturesight.images import (channel_stats, compression_artifacts,
                                 load_image, normal_map, tiling_seams)
from texturesight.uv import _uv_jacobian_svd

EX = Path(__file__).parents[1] / "examples" / "01-cube"


@pytest.fixture(scope="module")
def clean():
    return parse_obj(EX / "cube_clean.obj")


@pytest.fixture(scope="module")
def broken():
    return parse_obj(EX / "cube_broken.obj")


# --- OBJ parsing -----------------------------------------------------------

def test_parses_quads_into_triangles(clean):
    assert clean.n_faces == 12          # 6 quads fan-triangulated
    assert len(clean.verts) == 24
    assert clean.groups == {"cube": pytest.approx(np.arange(12))} or \
        list(clean.groups) == ["cube"]


def test_mesh_without_uvs_is_rejected(tmp_path):
    p = tmp_path / "nouv.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    with pytest.raises(BadMeshError) as ei:
        parse_obj(p)
    assert "UV" in str(ei.value)
    assert "unwrapped" in str(ei.value.suggestion)


def test_missing_file_says_so(tmp_path):
    with pytest.raises(BadMeshError):
        parse_obj(tmp_path / "ghost.obj")


# --- the UV Jacobian: the maths everything else rests on -------------------

def test_uniform_scale_is_conformal(clean):
    """A square UV island on a square face is a pure scale: anisotropy
    is exactly 1. Transposing the tangent-basis matrix reports it as
    2.618:1 instead, which is the bug this pins."""
    smax, smin = _uv_jacobian_svd(clean)
    assert np.allclose(smax / smin, 1.0, atol=1e-9)


def test_known_anisotropy_is_measured_exactly(broken):
    """make_assets.py squashes one face's UVs to 1/4 in u: 4.0:1."""
    rep = analyze_uv(broken)
    rep.pop("_arrays")
    assert rep["distortion"]["anisotropy"]["max"] == pytest.approx(4.0,
                                                                   abs=0.01)


def test_texel_density_is_uniform_on_the_clean_cube(clean):
    rep = analyze_uv(clean, texture_px=1024)
    rep.pop("_arrays")
    d = rep["texel_density"]
    assert d["spread_ratio"] == pytest.approx(1.0, abs=0.001)
    # 0.32 UV units over a 1-unit face at 1024 px = 327.68 px/unit
    assert d["px_per_unit"]["area_weighted_mean"] == pytest.approx(327.68,
                                                                   abs=0.1)


def test_texel_density_scales_with_texture_size(clean):
    a = analyze_uv(clean, texture_px=1024)
    b = analyze_uv(clean, texture_px=2048)
    a.pop("_arrays"), b.pop("_arrays")
    assert (b["texel_density"]["px_per_unit"]["area_weighted_mean"]
            == pytest.approx(
                2 * a["texel_density"]["px_per_unit"]["area_weighted_mean"],
                rel=1e-6))


# --- the clean reference stays clean ---------------------------------------

def test_clean_cube_has_no_findings(clean):
    rep = analyze_uv(clean)
    rep.pop("_arrays")
    assert [c["id"] for c in rep["checks"]] == []


def test_clean_cube_islands_match_its_shells(clean):
    rep = analyze_uv(clean)
    rep.pop("_arrays")
    i = rep["islands"]
    assert i["uv_islands"] == 6
    assert i["mesh_shells"] == 6        # the faces are not welded
    assert i["seam_edges"] == 0


# --- every injected UV defect is found -------------------------------------

def test_finds_the_flipped_face(broken):
    rep = analyze_uv(broken)
    rep.pop("_arrays")
    assert rep["distortion"]["flipped_face_count"] == 2      # one quad
    assert any(c["id"] == "uv-flipped-faces" and c["level"] == "fail"
               for c in rep["checks"])


def test_finds_the_density_hole(broken):
    """One island was scaled to 1/3, so density there is 1/3."""
    rep = analyze_uv(broken, texture_px=1024)
    rep.pop("_arrays")
    d = rep["texel_density"]
    assert d["spread_ratio"] == pytest.approx(3.0, abs=0.05)
    assert d["px_per_unit"]["min"] == pytest.approx(327.68 / 3, abs=0.5)
    assert any(c["id"] == "texel-density-uneven" for c in rep["checks"])


def test_finds_uvs_outside_the_square(broken):
    rep = analyze_uv(broken)
    rep.pop("_arrays")
    assert rep["packing"]["faces_outside_0_1"] == 2
    assert any(c["id"] == "uv-out-of-bounds" for c in rep["checks"])


def test_winding_majority_decides_what_flipped_means(clean):
    """Flipping EVERY face is a winding convention, not 12 defects."""
    m = parse_obj(EX / "cube_clean.obj")
    m.tri_uv = m.tri_uv[:, ::-1].copy()
    rep = analyze_uv(m)
    rep.pop("_arrays")
    assert rep["distortion"]["flipped_face_count"] == 0


# --- textures --------------------------------------------------------------

def test_tiling_texture_tiles_and_seamed_one_does_not():
    ok = tiling_seams(load_image(EX / "tile_clean.png"))
    bad = tiling_seams(load_image(EX / "tile_seam.png"))
    assert ok["tiles"] is True
    assert bad["tiles"] is False
    # the seam is huge relative to the texture's own variation
    assert bad["vertical"]["ratio"] > 10.0


def test_seam_test_is_relative_not_absolute():
    """A noisy texture with a large absolute edge difference still
    tiles; a smooth gradient with a small one does not. Judging the
    absolute difference gets both backwards."""
    rng = np.random.default_rng(3)
    noise = rng.random((64, 64, 3))                # tiles: wraps fine
    ramp = np.tile(np.linspace(0, 1, 64), (64, 1))[:, :, None] \
        .repeat(3, axis=2)                          # does NOT tile in x
    assert tiling_seams(noise)["horizontal"]["tiles"] is True
    assert tiling_seams(ramp)["horizontal"]["tiles"] is False


def test_valid_normal_map_passes():
    r = analyze_texture(EX / "normal_ok.png")
    nm = r["normal_map"]
    assert nm["unit_length"]["ok"] is True
    assert nm["unit_length"]["mean"] == pytest.approx(1.0, abs=0.01)
    assert nm["z_channel"]["ok"] is True
    assert not [c for c in r["checks"] if c["level"] == "fail"]


def test_srgb_mangled_normal_map_fails():
    """make_assets.py gamma-encodes one map: the vectors stop being unit
    length, which is silent in a viewport and fatal to the lighting."""
    r = analyze_texture(EX / "normal_bad.png")
    nm = r["normal_map"]
    assert nm["unit_length"]["ok"] is False
    assert nm["unit_length"]["mean"] > 1.1
    assert any(c["id"] == "normal-not-unit-length" and c["level"] == "fail"
               for c in r["checks"])


def test_normal_convention_is_identified():
    """make_assets.py authors an OpenGL (+Y up) dome."""
    nm = normal_map(load_image(EX / "normal_ok.png"))
    assert nm["green_convention"]["likely"].startswith("OpenGL")
    # and flipping green must flip the verdict
    img = load_image(EX / "normal_ok.png").copy()
    img[:, :, 1] = 1.0 - img[:, :, 1]
    assert normal_map(img)["green_convention"]["likely"].startswith("DirectX")


def test_quantised_data_map_is_caught():
    r = analyze_texture(EX / "rough_banded.png")
    assert r["channel"]["distinct_levels_of_256"] < 12
    assert any(c["id"] == "map-quantised" for c in r["checks"])


def test_constant_map_is_called_out(tmp_path):
    from PIL import Image
    p = tmp_path / "rough_flat.png"
    Image.fromarray(np.full((64, 64), 128, dtype=np.uint8), "L").save(p)
    r = analyze_texture(p)
    assert r["channel"]["is_constant"] is True
    assert any(c["id"] == "map-is-constant" for c in r["checks"])


def test_banding_is_not_reported_as_codec_blocking():
    """A posterised gradient correlates with the block grid on ONE axis.
    A codec's grid is square, so both axes must agree — otherwise every
    quantised map gets accused of being a JPEG."""
    ca = compression_artifacts(load_image(EX / "rough_banded.png"))
    assert ca["block_8"]["blocking"] is False


def test_flat_image_is_not_blocky(tmp_path):
    """An interior gradient of ~0 divides into a huge ratio; the
    visibility floor is what stops that from being 'blocking'."""
    flat = np.full((64, 64, 3), 0.5)
    ca = compression_artifacts(flat)
    assert ca["block_8"]["blocking"] is False


def test_kind_is_guessed_from_the_filename_and_says_so():
    r = analyze_texture(EX / "normal_ok.png")
    assert r["kind"] == "normal"
    assert r["kind_source"] == "filename"
    r2 = analyze_texture(EX / "normal_ok.png", kind="albedo")
    assert r2["kind_source"] == "declared"


def test_channel_stats_report_wasted_range():
    img = np.full((32, 32, 1), 0.5)
    img[:16] = 0.55
    st = channel_stats(img, "roughness")
    assert st["range_used"] < 0.1
    assert st["is_constant"] is False


# --- report / CLI ----------------------------------------------------------

def test_report_is_deterministic(clean):
    import json
    a = analyze_uv(clean)
    b = analyze_uv(parse_obj(EX / "cube_clean.obj"))
    a.pop("_arrays"), b.pop("_arrays")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_cli_exit_codes(tmp_path):
    def run(mesh, out):
        return subprocess.run(
            [sys.executable, "-m", "texturesight.cli", "inspect",
             "--mesh", str(mesh), "--out", str(out)],
            capture_output=True, text=True)

    ok = run(EX / "cube_clean.obj", tmp_path / "a")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert (tmp_path / "a" / "uv_layout.png").exists()
    assert (tmp_path / "a" / "report.json").exists()

    bad = run(EX / "cube_broken.obj", tmp_path / "b")
    assert bad.returncode == 2
    assert "inverted UV winding" in bad.stdout


def test_cli_needs_something_to_inspect(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "texturesight.cli", "inspect",
         "--out", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 1
    assert "nothing to inspect" in r.stderr


def test_skill_installs(tmp_path):
    from texturesight.skill_install import MARKER, install_skill
    dst = install_skill(tmp_path / "texturesight", quiet=True)
    assert (dst / "SKILL.md").exists()
    assert (dst / MARKER).read_text(encoding="utf-8").strip()


def test_packaged_skill_matches_repo_copy():
    repo = Path(__file__).parents[1]
    src = repo / "skills" / "texturesight" / "SKILL.md"
    pkg = repo / "texturesight" / "skill_data" / "SKILL.md"
    if not src.exists():
        pytest.skip("repo layout not present")
    assert src.read_text(encoding="utf-8") == pkg.read_text(encoding="utf-8")


# --- dogfooding round: islands are the actionable unit --------------------

def test_island_detail_names_the_starved_island(broken):
    """'Lowest at face 8' tells nobody what to grab in the UV editor.
    The report must name the island, its uv bbox and its density."""
    rep = analyze_uv(broken, texture_px=1024)
    rep.pop("_arrays")
    detail = rep["islands"]["detail"]
    assert len(detail) == 6
    dens = [i["mean_density_px_per_unit"] for i in detail]
    assert min(dens) == pytest.approx(327.68 / 3, abs=1.0)
    chk = next(c for c in rep["checks"] if c["id"] == "texel-density-uneven")
    assert "island #" in chk["where"]
    assert "x in" in chk["try"] or "scale island" in chk["try"]


def test_diff_proves_a_layout_fix(tmp_path):
    from texturesight.report import diff_reports, inspect
    a = inspect(EX / "cube_broken.obj", [], tmp_path / "a")
    b = inspect(EX / "cube_clean.obj", [], tmp_path / "b")
    a.pop("_out_dir"), b.pop("_out_dir")
    text = "\n".join(diff_reports(a, b))
    assert "GONE [uv-flipped-faces]" in text
    assert "spread 3.0x -> 1.0x" in text


def test_cli_names_the_sparsest_island(tmp_path):
    """The summary itself must say WHICH island is starved — sending the
    agent into report.json for the one number it always needs is
    friction (found on examples/02-crate)."""
    crate = Path(__file__).parents[1] / "examples" / "02-crate"
    r = subprocess.run(
        [sys.executable, "-m", "texturesight.cli", "inspect",
         "--mesh", str(crate / "crate_starved.obj"),
         "--out", str(tmp_path / "o")],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "islands: #4 is the sparsest" in r.stdout


def test_correspondence_and_checker_renders_exist(tmp_path):
    """The two 'explain it to a human' renders ship with every mesh
    inspect: 3D<->UV correspondence and the checker preview."""
    from texturesight.report import inspect
    rep = inspect(EX / "cube_clean.obj", [], tmp_path / "o")
    assert "correspondence.png" in rep["files"]["renders"]
    assert "checker_preview.png" in rep["files"]["renders"]
    assert (tmp_path / "o" / "correspondence.png").exists()
    assert (tmp_path / "o" / "checker_preview.png").exists()


def test_new_renders_are_deterministic(tmp_path):
    from texturesight.report import inspect
    inspect(EX / "cube_clean.obj", [], tmp_path / "a")
    inspect(EX / "cube_clean.obj", [], tmp_path / "b")
    for name in ("correspondence.png", "checker_preview.png"):
        assert (tmp_path / "a" / name).read_bytes() == \
               (tmp_path / "b" / name).read_bytes()


def test_checker_preview_reacts_to_uv_defects(tmp_path):
    """The checker is sampled THROUGH the UVs, so a broken unwrap must
    change its pixels — a human-eye render that hides the defects it
    exists to show would be worse than no render."""
    from texturesight.report import inspect
    from PIL import Image
    inspect(EX / "cube_clean.obj", [], tmp_path / "a")
    inspect(EX / "cube_broken.obj", [], tmp_path / "b")
    ia = np.asarray(Image.open(tmp_path / "a" / "checker_preview.png"),
                    dtype=int)
    ib = np.asarray(Image.open(tmp_path / "b" / "checker_preview.png"),
                    dtype=int)
    assert ia.shape == ib.shape
    frac = (np.abs(ia - ib).max(axis=2) > 8).mean()
    assert frac > 0.005, f"checker barely changed ({frac:.4%})"


def test_save_obj_round_trips(tmp_path):
    """parse -> save -> parse preserves geometry, UVs (including the
    winding sign — a writer that unflips faces would hide the defect)
    and material groups."""
    from texturesight import parse_obj, save_obj
    a = parse_obj(EX / "cube_broken.obj")
    save_obj(a, tmp_path / "rt.obj")
    b = parse_obj(tmp_path / "rt.obj")
    assert np.allclose(a.verts, b.verts, atol=1e-5)
    assert (a.tri_v == b.tri_v).all() and (a.tri_uv == b.tri_uv).all()
    assert np.allclose(a.face_area_uv(), b.face_area_uv(), atol=1e-9)
    assert set(a.groups) == set(b.groups)


def test_preview_builds_an_index_page(tmp_path):
    from texturesight.report import inspect
    from texturesight.preview import build_preview
    inspect(EX / "cube_broken.obj", [], tmp_path / "o")
    page = build_preview(tmp_path / "o")
    text = page.read_text(encoding="utf-8")
    assert "verdict" in text and "uv_layout.png" in text


def test_uninstall_also_drops_the_aisight_umbrella(tmp_path, monkeypatch):
    """`pip install aisight` depends on this package, so removing it and
    leaving the umbrella behind is a broken install. The other tools are
    NOT touched — pip does not cascade, and they are not ours to remove.
    User: 'deberia desinstalar los pips tambien los unistalls'."""
    from texturesight import skill_install as si
    calls = []
    monkeypatch.setattr(si.subprocess, "call",
                        lambda a, **k: (calls.append(a), 0)[1])
    monkeypatch.setattr(si, "_installed", lambda name: name == "aisight")
    monkeypatch.setattr(si, "default_skill_dir", lambda: tmp_path / "gone")
    monkeypatch.setattr(si, "memory_file",
                        lambda: tmp_path / "CLAUDE.md")
    assert si.uninstall() == 0
    removed = [c[-1] for c in calls]
    assert "texturesight" in removed
    assert "aisight" in removed
    assert not [r for r in removed
                if r not in ("texturesight", "aisight", "-y", "uninstall")]


def test_the_routing_note_is_written_and_taken_back(tmp_path):
    """A skill on disk does nothing unless the global instructions route
    requests to it, so the package writes that block itself — and takes it
    back out on uninstall, touching nothing else in a file that belongs to
    the user. A hand-written mention has no fence and is never ours.
    User: 'quiero que eso lo escriba y lo borre la herramienta'."""
    from texturesight.skill_install import BEGIN, END, drop_memory, write_memory
    md = tmp_path / "CLAUDE.md"
    mine = "# my own notes\nkeep this line.\n"
    md.write_text(mine, encoding="utf-8")

    assert write_memory(md) is True
    body = md.read_text(encoding="utf-8")
    assert mine.strip() in body and BEGIN in body and END in body
    assert write_memory(md) is False          # idempotent, never duplicated
    assert body.count(BEGIN) == 1

    assert drop_memory(md) is True
    assert md.read_text(encoding="utf-8").strip() == mine.strip()
    assert drop_memory(md) is False

    md.write_text("# texturesight\nmy own hand-written note.\n", encoding="utf-8")
    assert drop_memory(md) is False           # no fence: not ours to delete
    assert "hand-written" in md.read_text(encoding="utf-8")

    gone = tmp_path / "no-claude-code" / "CLAUDE.md"
    assert write_memory(gone) is False        # never create it from nothing
    assert not gone.parent.exists()
