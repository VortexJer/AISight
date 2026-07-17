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
    src = repo / "skill" / "SKILL.md"
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
