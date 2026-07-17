# animationsight

**Animation review built exclusively for AI agents.** A clip in; exact
motion measurements, located findings, and renders of the frames that
are wrong out.

An animator judges a clip by watching it. An agent cannot watch
anything — and the defects that matter are the ones that hide from
watching anyway: a foot that slides 2 mm per frame, a single-frame pop
in a 4-second take, a toe 40 mm through the floor for 5 frames. Those
are all exact arithmetic. So do the arithmetic.

```
clip.bvh  ->  animationsight inspect  ->  report.json + flagged frames  ->  fix  ->  diff
```

## What it measures

| | |
|---|---|
| **kinematics** | per-joint velocity, acceleration, jerk (mm/s, /s², /s³) and true geodesic angular speed |
| **contacts** | plant/lift events per foot, with frames and times |
| **foot sliding** | drift while planted: total slip, peak speed, worst frame — the classic defect |
| **balance** | COM (real segment masses) vs the support base, per frame, with airborne frames separated |
| **ballistics** | effective gravity per airborne span from a parabola fit — floaty/heavy flights, quantified |
| **penetration** | any joint through the floor, with depth and frames |
| **smoothness** | discontinuity events, clustered: "pose snap" (many joints, one frame) vs "joint pop" (one bad key) |
| **loops** | seam gap judged against the clip's own per-frame motion, convention-aware; `--kind oneshot` declares the intent |

Findings carry `where` (frame, joint, magnitude) and a `try:`. Renders
mark the offending joint and draw the COM, the floor and the support.
Everything is deterministic: same clip, byte-identical report.

## Quickstart

```bash
pip install "git+https://github.com/VortexJer/AISight#subdirectory=animationsight"

animationsight inspect walk.bvh --unit cm --up y
# -> out/report.json
# -> out/frames/frame_0022.png   (the flagged frames, offender circled)
# -> out/track_foot_speed.png    (time series, slides marked)

animationsight diff before.bvh after.bvh    # prove the fix
animationsight track walk.bvh LeftFoot      # one joint, every frame
```

Exit codes: 0 ok, 1 bad clip, 2 a FAIL-level finding.

## Proof it works: known ground truth

`examples/01-walk` is synthetic **on purpose**. Real mocap has unknown
defects; a clip whose defects are known by construction is the only kind
that can prove a measurement is right.

`make_clips.py` builds a walk by authoring the foot's world trajectory
(stance planted, swing arcing) and solving the leg by inverse
kinematics, then writes two files: a clean reference, and the same walk
with three injected defects of exact magnitude.

| injected | measured |
|---|---|
| right foot dipped **40 mm**, frames 22-26 | `[FAIL] 'RightFoot_end' goes 40.0 mm through the floor` — worst at frame 22, 5 frames |
| left arm displaced 26° on **frame 47 only** | `[WARN] 9 single-frame acceleration spike(s); worst on 'LeftForearm'` — frame 47, robust z 102.5 |
| root travels **15 % faster** than the stride | `[WARN] 'LeftFoot_end' slides while planted: 130.5 mm over 58 frame(s)` |

And the clean reference reports **OK**, exit 0 — no findings. Both
directions are asserted in `tests/`.

<p align="center">
  <img src="examples/01-walk/out_broken/frames/frame_0022.png" width="44%">
  <img src="examples/01-walk/out_broken/track_foot_speed.png" width="54%">
</p>
<p align="center"><em>real committed output: frame 22 with the penetrating foot circled below the floor line · the foot-speed track with the sliding frames marked</em></p>

## Before / after: one turn of the loop

[`examples/02-jump`](examples/02-jump) is the defect nobody can see and
everybody can feel: a jump whose flight falls at **0.554x gravity**.
Every still frame looks fine; the parabola fit does not care.

```
flight: frames 23..47 (0.8333s, apex +493.2 mm) -> 0.554x gravity
[WARN] ... at 1 g that apex takes 0.63s of airtime
       try:   T = 2*sqrt(2h/g): shorten the airtime or raise the apex
```

Apply the `try:` line, re-inspect, and prove it:

```
animationsight diff jump_floaty.bvh jump_fixed.bvh
  flight 0: 0.554x gravity (0.8333s) -> 0.905x gravity (0.6667s)
  GONE [floaty-flight] flight at frames [23, 47] falls at 0.55x gravity ...
```

<p align="center">
  <img src="examples/02-jump/out_floaty/flight_0_arc.png" width="49%">
  <img src="examples/02-jump/out_fixed/flight_0_arc.png" width="49%">
</p>
<p align="center"><em>the arc sheet inspect writes for every flight: ghosted poses, the measured COM arc (red, one dot per frame) vs the 1 g reference (green, dashed). Left: floaty — the red arc overshoots the reference by a third of the jump. Right: fixed — the arcs coincide.</em></p>

## Three bugs this found in itself

Worth stating plainly, because they are the same class of bug the tool
exists to catch:

1. **The first walk generator did not plant its feet.** It was built
   from sinusoids, which look like a walk and are not one — every frame
   slid. animationsight caught it immediately (min foot speed 81 mm/s,
   never zero), which is why the generator now uses IK and why
   `test_clean_clip_plants_its_feet` exists.
2. **The floor was inferred from the clip's lowest point** — so the
   injected penetration defined the floor and made itself invisible.
   Now it is the 10th percentile of the per-frame lowest point: a defect
   is rare by nature and stays below it.
   (`test_a_penetration_cannot_define_the_floor`)
3. **The author's own jump was floaty.** While dogfooding, the ballistics
   metric measured the freshly-authored demo jump at 0.68 g — written as
   an "arbitrary nice parabola" and shipped without a second look. It is
   now `examples/02-jump`, defect preserved, with the fix beside it.

## Scope, honestly

Reads BVH. Measures kinematics, contacts, balance, smoothness, loops.

Does **not** do: character rendering, blend shapes / facial rigs,
retargeting, physics simulation, or editing clips. It reviews; you fix
the clip in the tool that made it.

For 3D geometry — parts, assemblies, robot URDF, collision sweeps —
see [solidsight](../solidsight/README.md), the sibling tool this shares its
philosophy with.

## The Claude Code skill

`skill/SKILL.md` ships inside the pip package and installs itself into
`~/.claude/skills/animationsight` on the first run. `animationsight
uninstall` removes the skill and the package.

## License

MIT
