# 02 — The floaty jump (before / after)

A full standing long-jump — crouch, drive, travelling flight, landing
absorb 60 cm ahead, recovery — written twice by `make_jump.py`. The two
clips have IDENTICAL poses; only the flight's timing differs:

| | apex | forward travel | airtime | effective gravity |
|---|---|---|---|---|
| `jump_floaty.bvh` | +493 mm | 600 mm | 0.833 s (+35%) | **0.554x g** |
| `jump_fixed.bvh` | +493 mm | 600 mm | 0.667 s | **0.905x g** |

That is exactly why the defect is invisible to inspection: every still
frame of both clips is a fine jump pose. Floatiness lives in time.

```bash
animationsight inspect jump_floaty.bvh --kind oneshot --out out_floaty
animationsight inspect jump_fixed.bvh  --kind oneshot --out out_fixed
animationsight diff jump_floaty.bvh jump_fixed.bvh
```

## The arc sheet makes time visible

`inspect` writes `flight_0_arc.png` for any clip with a flight: ghosted
poses across the jump, the measured COM arc in red (one dot per frame),
and dashed in green the arc physics would draw — same takeoff velocity,
same apex, landing where 1 g says (`T = 2*sqrt(2h/g)`, so the reference
is `sqrt(g_ratio)` as wide).

<p align="center">
  <img src="out_floaty/flight_0_arc.png" width="49%">
  <img src="out_fixed/flight_0_arc.png" width="49%">
</p>
<p align="center"><em>left, the floaty take: the red measured arc overshoots the green 1 g reference by a third of the jump. right, the fix: the two arcs coincide.</em></p>

## The findings

```
# floaty:
flight: frames 23..47 (0.8333s, apex +493.2 mm) -> 0.554x gravity
[WARN] flight at frames [23, 47] falls at 0.55x gravity: it will read as floaty
       where: apex +493.2 mm over 0.8333s; at 1 g that apex takes 0.63s of airtime
       try:   physics fixes it two ways: shorten the airtime to match the apex,
              or raise the apex to match the airtime (T = 2*sqrt(2h/g))

# fixed:
flight: frames 23..42 (0.6667s, apex +493.5 mm) -> 0.905x gravity
(no floaty-flight finding)
```

## The diff is the proof

```
animationsight diff jump_floaty.bvh jump_fixed.bvh
  flight 0: 0.554x gravity (0.8333s) -> 0.905x gravity (0.6667s)
  'RightShin': peak speed ... (+...)
  ... and N more joint(s) with peak-speed changes ...
  GONE [floaty-flight] flight at frames [23, 47] falls at 0.55x gravity ...
```

(Flights lead the diff, and near-identical per-joint peak lines fold
into one — both changes came from using this very example and finding
the headline buried.)

Both clips also report their pose snaps honestly: this is a
blocking-pass jump with instantaneous pose changes, and `--kind
oneshot` silences only the loop check, never the snaps.
