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
    src = repo / "skills" / "pcbsight" / "SKILL.md"
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


# --- the board is a substrate with named parts, not loose wires --------

def test_parses_footprints_outline_and_values(clean):
    # references, values and a body for every component
    refs = {fp.ref for fp in clean.footprints}
    assert {"U1", "J1", "J2"} <= refs
    u1 = next(fp for fp in clean.footprints if fp.ref == "U1")
    assert u1.value == "AP2112"
    assert len(u1.body) == 4                      # 4 silk fp_lines
    assert not u1.body_inferred                  # it came from F.SilkS
    # Edge.Cuts gives a real substrate rectangle
    x1, y1, x2, y2 = clean.outline_rect()
    assert (x2 - x1) == pytest.approx(54.0, abs=0.1)
    assert (y2 - y1) == pytest.approx(43.0, abs=0.1)


def test_body_is_inferred_when_no_silk(tmp_path):
    """A footprint with pads but no silk graphics must still get a body
    (the pad bbox), flagged as inferred so nothing is ever invisible."""
    from pcbsight.board import parse_board
    p = tmp_path / "b.kicad_pcb"
    p.write_text(
        '(kicad_pcb (net 1 "N")\n'
        '  (footprint "x:R1" (at 10 10 0)\n'
        '    (property "Reference" "R1" (at 0 -2))\n'
        '    (pad "1" smd rect (at -1 0) (size 1 1) (layers "F.Cu")'
        ' (net 1 "N"))\n'
        '    (pad "2" smd rect (at 1 0) (size 1 1) (layers "F.Cu")'
        ' (net 1 "N"))))\n', encoding="utf-8")
    b = parse_board(p)
    r1 = b.footprints[0]
    assert r1.body and r1.body_inferred


# --- the complex rover example: blind fails, autorouted clean is 0 -----

def test_rover_example_ground_truth():
    from pcbsight.report import analyze
    rover = Path(__file__).parents[1] / "examples" / "02-rover"
    blind = analyze(parse_board(rover / "rover_blind.kicad_pcb"))
    clean = analyze(parse_board(rover / "rover_clean.kicad_pcb"))
    # blind: routed without sight -> many open nets and shorts
    assert blind["status"] == "failed"
    open_blind = [n for n in blind["connectivity"] if not n["routed"]]
    assert len(open_blind) >= 8
    assert len(blind["clearance_findings"]) >= 10
    # clean: a real 2-layer autoroute -> everything closed, no shorts
    assert clean["status"] == "ok"
    assert all(n["routed"] for n in clean["connectivity"])
    assert clean["clearance_findings"] == []
    # it is a real board: 13 components with refs
    assert len({fp.ref for fp in
                parse_board(rover / "rover_clean.kicad_pcb").footprints}) >= 12


# --- edit loop + human preview --------------------------------------------

def test_sexpr_round_trips_and_board_survives(tmp_path):
    """load -> dumps -> parse must preserve the tree exactly (a no-op
    edit is a no-op), and the re-written file must still parse as a
    board with the same copper."""
    from pcbsight.sexpr import dumps, parse
    src = CLEAN.read_text(encoding="utf-8")
    tree = parse(src, "clean")
    assert parse(dumps(tree), "rt") == tree
    p = tmp_path / "rt.kicad_pcb"
    p.write_text(dumps(tree), encoding="utf-8")
    a, b = parse_board(CLEAN), parse_board(p)
    assert len(a.tracks) == len(b.tracks)
    assert len(a.vias) == len(b.vias)
    assert {t.net for t in a.tracks} == {t.net for t in b.tracks}


def test_preview_builds_an_index_page(tmp_path):
    from pcbsight.preview import build_preview
    out = tmp_path / "o"
    r = subprocess.run(
        [sys.executable, "-m", "pcbsight.cli", "inspect", str(CLEAN),
         "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    page = build_preview(out)
    text = page.read_text(encoding="utf-8")
    assert "verdict" in text and "board.png" in text


def test_uninstall_also_drops_the_aisight_umbrella(tmp_path, monkeypatch):
    """`pip install aisight` depends on this package, so removing it and
    leaving the umbrella behind is a broken install. The other tools are
    NOT touched — pip does not cascade, and they are not ours to remove.
    User: 'deberia desinstalar los pips tambien los unistalls'."""
    from pcbsight import skill_install as si
    calls = []
    monkeypatch.setattr(si.subprocess, "call",
                        lambda a, **k: (calls.append(a), 0)[1])
    monkeypatch.setattr(si, "_installed", lambda name: name == "aisight")
    monkeypatch.setattr(si, "default_skill_dir", lambda: tmp_path / "gone")
    monkeypatch.setattr(si, "memory_file",
                        lambda: tmp_path / "CLAUDE.md")
    assert si.uninstall() == 0
    removed = [c[-1] for c in calls]
    assert "pcbsight" in removed
    assert "aisight" in removed
    assert not [r for r in removed
                if r not in ("pcbsight", "aisight", "-y", "uninstall")]


def test_the_routing_note_is_written_and_taken_back(tmp_path):
    """A skill on disk does nothing unless the global instructions route
    requests to it, so the package writes that block itself — and takes it
    back out on uninstall, touching nothing else in a file that belongs to
    the user. A hand-written mention has no fence and is never ours.
    User: 'quiero que eso lo escriba y lo borre la herramienta'."""
    from pcbsight.skill_install import BEGIN, END, drop_memory, write_memory
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

    md.write_text("# pcbsight\nmy own hand-written note.\n", encoding="utf-8")
    assert drop_memory(md) is False           # no fence: not ours to delete
    assert "hand-written" in md.read_text(encoding="utf-8")

    gone = tmp_path / "no-claude-code" / "CLAUDE.md"
    assert write_memory(gone) is False        # never create it from nothing
    assert not gone.parent.exists()
