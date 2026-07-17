"""Tests for pcbsight — the example boards carry defects of exactly
known magnitude, and the clean board must stay clean."""

import subprocess
import sys
from pathlib import Path

import pytest

from pcbsight import analyze, microstrip_z0, parse_board
from pcbsight.checks import _seg_seg_dist, diff_pairs
from pcbsight.errors import BadBoardError

EX = Path(__file__).parents[1] / "examples" / "01-board"
CLEAN, BROKEN = EX / "board_clean.kicad_pcb", EX / "board_broken.kicad_pcb"


@pytest.fixture(scope="module")
def clean():
    return parse_board(CLEAN)


@pytest.fixture(scope="module")
def broken():
    return parse_board(BROKEN)


# --- parsing ---------------------------------------------------------------

def test_parses_nets_tracks_pads(clean):
    assert clean.nets[1] == "+5V"
    assert len(clean.nets) == 5
    assert len(clean.pads) == 7
    assert any(t.layer == "B.Cu" for t in clean.tracks)


def test_rotated_footprint_pads_are_composed(clean):
    """J1 sits at (60,20) rotated 180: its pad 1 (local -1.5,0) must land
    at (61.5, 20), not (58.5, 20). Skipping the rotation puts every pad
    of every rotated footprint in the wrong place, silently."""
    j1_1 = next(p for p in clean.pads if p.ref == "J1" and p.name == "1")
    assert j1_1.at[0] == pytest.approx(61.5, abs=1e-6)
    assert j1_1.at[1] == pytest.approx(20.0, abs=1e-6)


def test_not_a_board_is_rejected(tmp_path):
    p = tmp_path / "x.kicad_pcb"
    p.write_text("(kicad_sch (junk))", encoding="utf-8")
    with pytest.raises(BadBoardError):
        parse_board(p)


def test_unbalanced_parens_error(tmp_path):
    p = tmp_path / "y.kicad_pcb"
    p.write_text("(kicad_pcb (net 1 \"GND\"", encoding="utf-8")
    with pytest.raises(BadBoardError) as ei:
        parse_board(p)
    assert "unbalanced" in str(ei.value)


# --- geometry --------------------------------------------------------------

def test_segment_distance():
    assert _seg_seg_dist((0, 0), (10, 0), (0, 5), (10, 5)) == pytest.approx(5)
    assert _seg_seg_dist((0, 0), (10, 0), (5, -5), (5, 5)) == 0.0  # crossing
    assert _seg_seg_dist((0, 0), (1, 0), (3, 4), (3, 5)) == pytest.approx(
        ((3 - 1) ** 2 + 16) ** 0.5)


# --- the clean board stays clean -------------------------------------------

def test_clean_board_is_ok(clean):
    rep = analyze(clean)
    assert rep["status"] == "ok", [c["message"] for c in rep["checks"]]
    assert all(n["routed"] for n in rep["connectivity"])
    assert rep["clearance_findings"] == []


def test_clean_pair_is_matched(clean):
    pairs = diff_pairs(clean)
    assert len(pairs) == 1                     # deduped, not once per suffix
    assert pairs[0]["skew_mm"] == pytest.approx(0.0, abs=1e-9)
    assert pairs[0]["width_matched"]


# --- every injected defect is found ----------------------------------------

def test_finds_the_open_net(broken):
    rep = analyze(broken)
    gnd = next(n for n in rep["connectivity"] if n["net"] == "GND")
    assert gnd["islands"] == 2
    assert "J1.2" in gnd["unconnected_pads"]
    assert any(c["id"] == "net-open" and c["level"] == "fail"
               for c in rep["checks"])
    assert rep["status"] == "failed"


def test_finds_the_clearance_violation_exactly(broken):
    """The generator places SIG 0.08 mm from +5V by construction."""
    rep = analyze(broken)
    worst = rep["clearance_findings"][0]
    assert worst["clearance_mm"] == pytest.approx(0.08, abs=0.005)
    assert {worst["a"], worst["b"]} == {"+5V", "SIG"}


def test_finds_the_current_pinch(broken):
    rep = analyze(broken)
    v5 = next(c for c in rep["current_capacity"] if c["net"] == "+5V")
    assert v5["min_width_mm"] == pytest.approx(0.2)
    assert v5["i_max_a"] < 0.8                 # a 0.2 mm neck carries little


def test_finds_the_pair_skew_and_width_mix(broken):
    pairs = diff_pairs(broken)
    assert len(pairs) == 1
    assert pairs[0]["skew_mm"] == pytest.approx(3.0, abs=0.01)
    assert not pairs[0]["width_matched"]
    rep = analyze(broken)
    ids = {c["id"] for c in rep["checks"]}
    assert "diff-pair-skew" in ids and "diff-pair-width" in ids


# --- IPC numbers against published values ----------------------------------

def test_ipc_current_sanity():
    """A 1 mm external trace in 1 oz copper at dT=10 C is ~2.4 A on the
    IPC-2221 curve; 0.25 mm is under 1 A. If these drift, the formula
    or the unit conversion broke."""
    b = parse_board(CLEAN)
    rep = analyze(b)
    v5 = next(c for c in rep["current_capacity"] if c["net"] == "+5V")
    assert v5["i_max_a"] == pytest.approx(2.39, abs=0.05)
    usb = next(c for c in rep["current_capacity"] if c["net"] == "USB_P")
    assert usb["i_max_a"] < 1.0


def test_microstrip_z0_sanity():
    """0.3 mm over 0.2 mm of FR4 is a ~51 ohm microstrip (IPC-2141
    ballpark). And wider must mean lower impedance."""
    z = microstrip_z0(0.3, 0.2, er=4.5)
    assert 40 < z < 60
    assert microstrip_z0(0.6, 0.2) < microstrip_z0(0.3, 0.2)


# --- determinism / CLI -----------------------------------------------------

def test_report_is_deterministic(clean):
    import json
    a = analyze(clean)
    b = analyze(parse_board(CLEAN))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_cli_exit_codes(tmp_path):
    ok = subprocess.run(
        [sys.executable, "-m", "pcbsight.cli", "inspect", str(CLEAN),
         "--out", str(tmp_path / "a")], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert (tmp_path / "a" / "board.png").exists()

    bad = subprocess.run(
        [sys.executable, "-m", "pcbsight.cli", "inspect", str(BROKEN),
         "--out", str(tmp_path / "b")], capture_output=True, text=True)
    assert bad.returncode == 2
    assert "not routed" in bad.stdout


def test_cli_impedance():
    r = subprocess.run(
        [sys.executable, "-m", "pcbsight.cli", "impedance", "0.3", "0.2"],
        capture_output=True, text=True)
    assert r.returncode == 0
    assert "ohm" in r.stdout
    assert "estimate" in r.stdout              # honesty survives the CLI


def test_skill_installs(tmp_path):
    from pcbsight.skill_install import MARKER, install_skill
    dst = install_skill(tmp_path / "pcbsight", quiet=True)
    assert (dst / "SKILL.md").exists()
    assert (dst / MARKER).read_text(encoding="utf-8").strip()


def test_packaged_skill_matches_repo_copy():
    repo = Path(__file__).parents[1]
    src = repo / "skill" / "SKILL.md"
    pkg = repo / "pcbsight" / "skill_data" / "SKILL.md"
    if not src.exists():
        pytest.skip("repo layout not present")
    assert src.read_text(encoding="utf-8") == pkg.read_text(encoding="utf-8")


# --- dogfooding round: the proof step --------------------------------------

def test_diff_tells_the_story_of_the_fix(clean, broken):
    from pcbsight.report import diff_reports
    text = "\n".join(diff_reports(analyze(broken), analyze(clean)))
    assert "net 'GND': 2 island(s) -> 1" in text
    assert "GONE [net-open]" in text
    assert "clearance findings: 2 -> 0" in text
    assert "0.745 A -> 2.392 A" in text
