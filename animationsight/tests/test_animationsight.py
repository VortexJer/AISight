"""Tests for animationsight.

The example clips are synthetic ON PURPOSE: their defects are known by
construction, so these tests assert that the measurements find exactly
the injected magnitudes — and, just as importantly, that the clean
reference stays clean (a tool that cries wolf is not usable).
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from animationsight import analyze, forward_kinematics, parse_bvh
from animationsight.errors import BadClipError
from animationsight.metrics import infer_floor, loop_continuity

EX = Path(__file__).parents[1] / "examples" / "01-walk"
CLEAN, BROKEN = EX / "walk_clean.bvh", EX / "walk_broken.bvh"


@pytest.fixture(scope="module")
def clean():
    return parse_bvh(CLEAN, unit="cm")


@pytest.fixture(scope="module")
def broken():
    return parse_bvh(BROKEN, unit="cm")


# --- parsing ---------------------------------------------------------------

def test_parses_hierarchy_and_motion(clean):
    assert clean.n_frames == 120
    assert clean.fps == pytest.approx(30.0, abs=0.01)
    assert clean.duration_s == pytest.approx(4.0, abs=0.01)
    assert clean.root.name == "Hips"
    assert "LeftFoot" in clean.names and "RightFoot_end" in clean.names
    # end sites carry no channels but are real points
    assert [j for j in clean.joints if j.is_end]


def test_channel_count_matches_motion_width(clean):
    assert clean.frames.shape[1] == sum(len(j.channels) for j in clean.joints)


def test_unit_scaling_is_applied(clean):
    pos_cm, _ = forward_kinematics(clean)
    clip_mm = parse_bvh(CLEAN, unit="mm")
    pos_mm, _ = forward_kinematics(clip_mm)
    assert np.allclose(pos_cm, pos_mm * 10.0)


def test_bad_file_says_what_it_wanted(tmp_path):
    p = tmp_path / "nope.bvh"
    p.write_text("not a bvh at all", encoding="utf-8")
    with pytest.raises(BadClipError) as ei:
        parse_bvh(p)
    assert "HIERARCHY" in str(ei.value)


def test_single_frame_clip_is_rejected(tmp_path):
    src = CLEAN.read_text(encoding="utf-8")
    head = src.split("MOTION")[0]
    p = tmp_path / "one.bvh"
    p.write_text(head + "MOTION\nFrames: 1\nFrame Time: 0.0333\n"
                 + "0 " * 54 + "\n", encoding="utf-8")
    with pytest.raises(BadClipError) as ei:
        parse_bvh(p)
    assert "at least 2" in str(ei.value)


def test_parse_is_deterministic():
    a, _ = forward_kinematics(parse_bvh(CLEAN, unit="cm"))
    b, _ = forward_kinematics(parse_bvh(CLEAN, unit="cm"))
    assert np.array_equal(a, b)


# --- forward kinematics ----------------------------------------------------

def test_fk_respects_bone_lengths(clean):
    """A rotation cannot change a bone's length: the shin is 40 cm in
    every frame or the FK is composing transforms wrong."""
    pos, _ = forward_kinematics(clean)
    knee, ankle = clean.names.index("LeftShin"), clean.names.index("LeftFoot")
    length = np.linalg.norm(pos[:, ankle] - pos[:, knee], axis=1)
    assert np.allclose(length, 400.0, atol=1e-6)


def test_fk_root_matches_the_channels(clean):
    pos, _ = forward_kinematics(clean)
    # the root's world position is its position channels, in mm
    assert np.allclose(pos[:, 0, 1], clean.frames[:, 1] * 10.0)
    assert np.allclose(pos[:, 0, 2], clean.frames[:, 2] * 10.0)


# --- the ground truth: the clean clip is clean -----------------------------

def test_clean_clip_has_no_findings(clean):
    rep = analyze(clean, up="y")
    rep.pop("_arrays")
    assert rep["status"] == "ok", \
        f"clean reference reported: {[c['id'] for c in rep['checks']]}"


def test_clean_clip_plants_its_feet(clean):
    """The whole reason the example is built by IK: a foot in stance is
    world-stationary. The first version of the generator used sinusoids
    and every frame slid — this test is why that was caught."""
    pos, _ = forward_kinematics(clean)
    j = clean.names.index("LeftFoot_end")
    speed = np.linalg.norm(np.gradient(pos, clean.frame_time,
                                       axis=0)[:, j], axis=1)
    assert speed.min() < 1.0                     # truly stationary somewhere
    assert (speed < 50.0).sum() > 20             # for a real share of frames


def test_clean_clip_loops_by_the_full_convention(clean):
    pos, _ = forward_kinematics(clean)
    from animationsight.metrics import derivatives
    d = derivatives(pos, clean.frame_time)
    loop = loop_continuity(pos, d, clean.names, "y")
    assert loop["loops_cleanly"]
    assert loop["convention"].startswith("full")


# --- the ground truth: every injected defect is found ----------------------

def test_finds_the_injected_penetration(broken):
    """make_clips.py dips the right foot by DIP=4.0 cm on frames 22-26."""
    rep = analyze(broken, up="y")
    rep.pop("_arrays")
    pen = rep["penetration"]
    assert pen, "the 40 mm foot dip was not found"
    worst = pen[0]
    assert worst["joint"] == "RightFoot_end"
    assert worst["max_depth_mm"] == pytest.approx(40.0, abs=1.0)
    assert set(worst["frames"]) >= {22, 23, 24, 25, 26}
    assert rep["status"] == "failed"


def test_finds_the_injected_pop(broken):
    """make_clips.py displaces the left arm by 26 deg on frame 47 only."""
    rep = analyze(broken, up="y")
    rep.pop("_arrays")
    pops = rep["smoothness"]["pops"]
    assert pops, "the one-frame arm pop was not found"
    worst = pops[0]
    assert any(46 <= f <= 48 for f in worst["frames"])
    assert worst["worst_joint"].startswith("Left")


def test_pose_snaps_cluster_into_events():
    """A blocking pass snaps MANY joints in the same frame; reporting
    each joint separately buried 5 real snaps under 154 entries (found
    dogfooding a jump clip). Same-frame spikes must cluster."""
    import numpy as np

    from animationsight.metrics import derivatives, smoothness
    rng = np.random.default_rng(3)
    F, J = 90, 12
    pos = np.cumsum(rng.normal(0, 0.4, (F, J, 3)), axis=0) + 900.0
    pos[45:] += 80.0                     # one instantaneous FULL-pose snap
    names = [f"j{k}" for k in range(J)]
    s = smoothness(derivatives(pos, 1 / 30), names, 1 / 30)
    assert s["pop_count"] <= 3           # one event (+ tolerance), not ~12
    assert s["pops"][0]["kind"] == "pose snap"
    assert s["pops"][0]["joints_hit"] >= J // 2
    assert s["raw_spike_count"] >= J // 2


def test_ballistics_measures_effective_gravity():
    """A COM authored to fall at exactly half gravity must read 0.5x —
    the 'floaty jump' every animator ships and nobody can see."""
    import numpy as np

    from animationsight.metrics import G_MM_S2, ballistics
    dt = 1 / 30
    F = 40
    com = np.zeros((F, 3))
    com[:, 1] = 900.0
    g_eff = 0.5 * G_MM_S2
    t = (np.arange(10, 30) - 10) * dt
    com[10:30, 1] = 900.0 + 1200.0 * t - 0.5 * g_eff * t * t
    b = ballistics(com, list(range(10, 30)), dt, "y")
    assert len(b["flights"]) == 1
    assert b["flights"][0]["gravity_ratio"] == pytest.approx(0.5, abs=0.02)


def test_oneshot_kind_silences_the_loop_check():
    """Cut a walk mid-cycle: the seam is genuinely discontinuous, so
    'auto' reports it — and 'oneshot' silences it, because a jump or a
    cut take is not supposed to loop and the warning is pure noise."""
    clip = parse_bvh(CLEAN, unit="cm")
    clip.frames = clip.frames[:90]           # 2.25 cycles: seam mismatch

    rep = analyze(clip, up="y", kind="auto")
    rep.pop("_arrays")
    assert any(c["id"] == "loop-discontinuity" for c in rep["checks"])

    rep2 = analyze(clip, up="y", kind="oneshot")
    rep2.pop("_arrays")
    assert not any(c["id"] == "loop-discontinuity" for c in rep2["checks"])


def test_finds_the_injected_sliding(broken):
    """The root travels 15 % faster than the stride, so planted feet
    drift. Nothing about this is visible in a still frame."""
    rep = analyze(broken, up="y")
    rep.pop("_arrays")
    slides = rep["contacts"]["sliding"]
    assert slides, "foot sliding was not found"
    assert any(s["joint"].startswith(("Left", "Right")) for s in slides)
    assert max(s["total_slip_mm"] for s in slides) > 50.0


def test_a_penetration_cannot_define_the_floor(broken):
    """The floor estimate must not be dragged down by the defect: taking
    the clip minimum made the injected 40 mm dip invisible."""
    pos, _ = forward_kinematics(broken)
    floor, info = infer_floor(pos, "y")
    assert floor == pytest.approx(0.0, abs=2.0)
    assert info["clip_min_mm"] == pytest.approx(-40.0, abs=1.0)
    assert info["frames_below_floor"] >= 5


# --- report shape ----------------------------------------------------------

def test_report_is_deterministic_and_json_safe(clean, tmp_path):
    import json
    a = analyze(clean, up="y")
    a.pop("_arrays")
    b = analyze(parse_bvh(CLEAN, unit="cm"), up="y")
    b.pop("_arrays")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_com_uses_anthropometric_weights_when_names_are_known(clean):
    rep = analyze(clean, up="y")
    rep.pop("_arrays")
    assert rep["com"]["anthropometric_weights"] is True
    # a standing/walking human COM sits near the pelvis, not the head
    assert 850.0 < rep["com"]["height_mm"]["mean"] < 1050.0


def test_unknown_joint_names_fall_back_and_say_so(tmp_path):
    """A skeleton whose joints are named j0..j16 carries no anatomy, so
    segment masses cannot be assigned and the report must SAY the COM is
    approximate rather than quietly inventing one."""
    src = CLEAN.read_text(encoding="utf-8")
    real_names = ["LeftUpperArm", "LeftForearm", "LeftHand",
                  "RightUpperArm", "RightForearm", "RightHand",
                  "LeftThigh", "LeftShin", "LeftFoot",
                  "RightThigh", "RightShin", "RightFoot",
                  "Hips", "Spine", "Chest", "Neck", "Head"]
    for i, real in enumerate(real_names):        # longest first: no partial hits
        src = src.replace(real, f"j{i}")
    p = tmp_path / "anon.bvh"
    p.write_text(src, encoding="utf-8")

    clip = parse_bvh(p, unit="cm")
    assert not any(t in n.lower() for n in clip.names
                   for t in ("foot", "arm", "hand", "shin", "hip", "head"))
    rep = analyze(clip, up="y")
    rep.pop("_arrays")
    assert rep["com"]["anthropometric_weights"] is False
    assert any(c["id"] == "com-weights-unknown" for c in rep["checks"])


# --- CLI -------------------------------------------------------------------

def test_cli_inspect_exit_codes(tmp_path):
    def run(clip, out):
        return subprocess.run(
            [sys.executable, "-m", "animationsight.cli", "inspect",
             str(clip), "--out", str(out), "--frames", "2"],
            capture_output=True, text=True)

    ok = run(CLEAN, tmp_path / "a")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert (tmp_path / "a" / "report.json").exists()

    bad = run(BROKEN, tmp_path / "b")
    assert bad.returncode == 2          # a FAIL-level finding
    assert "through the floor" in bad.stdout


def test_cli_diff_reports_the_difference(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "animationsight.cli", "diff",
         str(CLEAN), str(BROKEN)], capture_output=True, text=True)
    assert r.returncode == 0
    assert "NEW" in r.stdout
    assert "ground-penetration" in r.stdout


def test_skill_installs(tmp_path):
    from animationsight.skill_install import MARKER, install_skill
    dst = install_skill(tmp_path / "animationsight", quiet=True)
    assert (dst / "SKILL.md").exists()
    assert (dst / MARKER).read_text(encoding="utf-8").strip()


def test_packaged_skill_matches_repo_copy():
    repo = Path(__file__).parents[1]
    src = repo / "skill" / "SKILL.md"
    pkg = repo / "animationsight" / "skill_data" / "SKILL.md"
    if not src.exists():
        pytest.skip("repo layout not present")
    assert src.read_text(encoding="utf-8") == pkg.read_text(encoding="utf-8")
