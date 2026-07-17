"""Tests for shadersight.

The BRDF laws are the ground truth here — a physically-based material
MUST conserve energy and be reciprocal, and a hacked one must be caught.
The example graphs carry defects known by construction.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from shadersight import Material, analyze_graph, analyze_material, parse_graph
from shadersight.brdf import (Material as Mat, d_ggx, directional_albedo,
                             hemisphere_grid)
from shadersight.errors import BadGraphError, BadModelError

EX = Path(__file__).parents[1] / "examples" / "01-graphs"


# --- the BRDF maths --------------------------------------------------------

def test_ggx_distribution_is_normalised():
    """The NDF integrates D*cos over the hemisphere to 1. If it does
    not, every albedo computed from it is scaled wrong."""
    dirs, w = hemisphere_grid(256, 512)
    for alpha in (0.1, 0.3, 0.6, 1.0):
        cos_h = dirs[:, 2]
        integral = np.sum(d_ggx(cos_h, alpha) * cos_h * w)
        assert integral == pytest.approx(1.0, abs=0.01)


def test_mirror_reflects_almost_all_energy():
    """A smooth white metal is ~100% reflective. This is the case the
    old uniform grid got catastrophically wrong (0.02 or 1.19 depending
    only on resolution); importance sampling must land near 1.0 at
    every angle."""
    m = Material(base_color=(1, 1, 1), roughness=0.02, metallic=1.0)
    for a in (0, 30, 60, 85):
        wo = (np.sin(np.radians(a)), 0.0, np.cos(np.radians(a)))
        assert directional_albedo(m, wo).max() == pytest.approx(1.0,
                                                                abs=0.03)


def test_physical_materials_conserve_energy():
    for r in (0.1, 0.3, 0.5, 0.8):
        for metal in (0.0, 1.0):
            m = Material(base_color=(0.9, 0.9, 0.9), roughness=r,
                         metallic=metal)
            rep = analyze_material(m, quality="fast")
            assert rep["energy_conservation"]["conserves_energy"], \
                f"r={r} metal={metal} albedo " \
                f"{rep['energy_conservation']['max_albedo']}"


def test_energy_estimate_is_deterministic():
    m = Material(base_color=(0.8, 0.5, 0.2), roughness=0.35, metallic=1.0)
    a = directional_albedo(m, (0.2, 0.0, 0.98))
    b = directional_albedo(m, (0.2, 0.0, 0.98))
    assert np.array_equal(a, b)


def test_reciprocity_holds_for_the_standard_brdf():
    m = Material(base_color=(0.7, 0.3, 0.1), roughness=0.4, metallic=0.5)
    r = analyze_material(m, quality="fast")["reciprocity"]
    assert r["reciprocal"]
    assert r["max_relative_error"] < 1e-6


def test_non_physical_material_is_caught():
    """A material that reflects 3x its input violates energy
    conservation, and the tool must FAIL it — the whole point."""
    class Overbright(Mat):
        def eval(self, wi, wo):
            return super().eval(wi, wo) * 3.0

    m = Overbright(base_color=(0.9, 0.9, 0.9), roughness=0.5)
    rep = analyze_material(m, quality="fast")
    assert rep["status"] == "failed"
    assert rep["energy_conservation"]["max_albedo"] > 1.5
    assert any(c["id"] == "energy-not-conserved" for c in rep["checks"])


def test_non_reciprocal_material_is_caught():
    class Asym(Mat):
        def eval(self, wi, wo):
            wi = np.atleast_2d(wi)
            wo = np.atleast_2d(wo)
            base = super().eval(wi, wo)
            return base * (1.0 + wo[:, 2:3])        # depends on wo only

    m = Asym(base_color=(0.6, 0.6, 0.6), roughness=0.4)
    rep = analyze_material(m, quality="fast")
    assert any(c["id"] == "not-reciprocal" for c in rep["checks"])


def test_rough_material_reports_energy_loss_as_a_warning_not_a_failure():
    m = Material(base_color=(1, 1, 1), roughness=0.9, metallic=1.0)
    rep = analyze_material(m, quality="fast")
    assert rep["furnace"]["energy_lost"] > 0.15
    ids = {c["id"] for c in rep["checks"]}
    assert "high-energy-loss" in ids
    assert "energy-not-conserved" not in ids     # loss is NOT a violation


def test_material_rejects_impossible_parameters():
    with pytest.raises(BadModelError):
        Material(base_color=(1.5, 0.5, 0.5))      # >1 creates energy
    with pytest.raises(BadModelError):
        Material(roughness=2.0)


# --- node graph analysis ---------------------------------------------------

@pytest.fixture(scope="module")
def clean_graph():
    return parse_graph(EX / "clean_graph.json")


@pytest.fixture(scope="module")
def broken_graph():
    return parse_graph(EX / "broken_graph.json")


def test_clean_graph_has_no_findings(clean_graph):
    rep = analyze_graph(clean_graph)
    assert [c["id"] for c in rep["checks"]] == []
    assert rep["reachable_nodes"] == rep["nodes"]
    assert rep["cycle_nodes"] == []


def test_clean_graph_evaluation_order_is_topological(clean_graph):
    rep = analyze_graph(clean_graph)
    order = rep["evaluation_order"]
    pos = {nid: i for i, nid in enumerate(order)}
    nodes = {n["id"]: n for n in clean_graph["nodes"]}
    from shadersight.graph import _links
    for nid, n in nodes.items():
        for _s, src, _ss in _links(n):
            assert pos[src] < pos[nid]           # inputs come first


def test_cost_counts_texture_fetches(clean_graph):
    rep = analyze_graph(clean_graph)
    assert rep["cost"]["texture_fetches"] == 3   # albedo, rough, normal
    assert rep["cost"]["alu_equivalents"] > 300  # 3 fetches at ~100 each


def test_broken_graph_finds_cycle_dead_and_dangling(broken_graph):
    rep = analyze_graph(broken_graph)
    ids = {c["id"] for c in rep["checks"]}
    assert "graph-cycle" in ids
    assert "dead-nodes" in ids
    assert "dangling-input" in ids
    assert rep["status"] == "failed"
    # mul <-> add are the cycle
    assert set(rep["cycle_nodes"]) == {"mul", "add"}


def test_cost_ignores_dead_nodes(broken_graph):
    """A dead fbm branch (cost 200+) must not inflate the cost: you do
    not pay for what does not reach the output."""
    rep = analyze_graph(broken_graph)
    assert rep["cost"]["counts_only_live_nodes"]
    assert "fbm" not in rep["cost"]["by_type"]


def test_unknown_node_type_is_flagged_and_excluded():
    g = {"name": "x", "output": "o", "nodes": [
        {"id": "a", "type": "quantum_flux", "inputs": {}},
        {"id": "o", "type": "output", "inputs": {"c": "a.out"}}]}
    rep = analyze_graph(g)
    assert any(c["id"] == "unknown-node-type" for c in rep["checks"])
    assert "quantum_flux" in rep["cost"]["excluded_unknown_types"]


def test_high_cost_graph_warns():
    nodes = [{"id": "uv", "type": "uv", "inputs": {}}]
    prev = "uv"
    for i in range(8):                            # 8 texture fetches = 800
        nodes.append({"id": f"t{i}", "type": "texture",
                      "inputs": {"uv": f"{prev}.out"}})
        prev = f"t{i}"
    nodes.append({"id": "o", "type": "output", "inputs": {"c": f"{prev}.out"}})
    rep = analyze_graph({"name": "heavy", "output": "o", "nodes": nodes})
    assert any(c["id"] == "shader-cost-high" for c in rep["checks"])


def test_duplicate_ids_rejected(tmp_path):
    p = tmp_path / "dup.json"
    p.write_text(json.dumps({"output": "a", "nodes": [
        {"id": "a", "type": "output", "inputs": {}},
        {"id": "a", "type": "uv", "inputs": {}}]}), encoding="utf-8")
    with pytest.raises(BadGraphError) as ei:
        parse_graph(p)
    assert "duplicate" in str(ei.value)


def test_missing_output_is_a_failure():
    rep = analyze_graph({"name": "x", "nodes": [
        {"id": "a", "type": "uv", "inputs": {}}]})
    assert any(c["id"] == "no-output" for c in rep["checks"])


# --- CLI + skill -----------------------------------------------------------

def test_cli_material_exit_codes(tmp_path):
    ok = subprocess.run(
        [sys.executable, "-m", "shadersight.cli", "material",
         "--roughness", "0.4", "--quality", "fast", "--out", str(tmp_path / "a")],
        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert (tmp_path / "a" / "preview.png").exists()
    assert (tmp_path / "a" / "albedo_curve.png").exists()


def test_cli_graph_exit_codes(tmp_path):
    bad = subprocess.run(
        [sys.executable, "-m", "shadersight.cli", "graph",
         str(EX / "broken_graph.json"), "--out", str(tmp_path / "b")],
        capture_output=True, text=True)
    assert bad.returncode == 2
    assert "cycle" in bad.stdout

    ok = subprocess.run(
        [sys.executable, "-m", "shadersight.cli", "graph",
         str(EX / "clean_graph.json"), "--out", str(tmp_path / "c")],
        capture_output=True, text=True)
    assert ok.returncode == 0


def test_skill_installs(tmp_path):
    from shadersight.skill_install import MARKER, install_skill
    dst = install_skill(tmp_path / "shadersight", quiet=True)
    assert (dst / "SKILL.md").exists()
    assert (dst / MARKER).read_text(encoding="utf-8").strip()


def test_packaged_skill_matches_repo_copy():
    repo = Path(__file__).parents[1]
    src = repo / "skill" / "SKILL.md"
    pkg = repo / "shadersight" / "skill_data" / "SKILL.md"
    if not src.exists():
        pytest.skip("repo layout not present")
    assert src.read_text(encoding="utf-8") == pkg.read_text(encoding="utf-8")
