# Mechanisms, drivetrains and robot joints

Load for: gearboxes, reducers, linkages, cam/follower, winches, robot
arms and joints, CNC/printer motion, anything where parts MOVE against
each other.

A mechanism is not a shape, it is a set of RELATIONS. Model the
relations as declared specs (`expect()`), and the build fails the moment
a fit drifts — you stop re-judging numbers by eye every iteration.

## Gear math you must not re-derive

`parts.spur_gear(module, teeth, thickness, bore=0, pressure_angle=20,
backlash=0)` is a real involute. What you compute yourself:

- **pitch diameter** `d = module * teeth` — the circle that actually
  rolls. Gear geometry is defined here, not at the tips.
- **centre distance** `(d1 + d2) / 2 = module * (t1 + t2) / 2`. This is
  THE number: get it wrong and the teeth interfere or the mesh rattles.
- **ratio** `t_out / t_in`. Compound ratio = product of the stages.
- **module compatibility**: two gears mesh only at the SAME module and
  pressure angle. Different modules = a picture of a gearbox, not one.
- **minimum teeth** at 20 deg: 17 (below that the involute undercuts and
  the tooth root gets weak). Use 14+ only with profile shift you are
  not modeling — so: 17.
- **backlash for printed gears**: `backlash=0.15..0.25` (mm off the
  tooth thickness). Zero backlash printed = a gearbox that binds.

```python
M, T_IN, T_OUT = 2.0, 12, 24
CENTRE = M * (T_IN + T_OUT) / 2                      # = 36.0, exactly
pinion = parts.spur_gear(M, T_IN, 8, bore=5, backlash=0.2)
wheel  = parts.spur_gear(M, T_OUT, 8, bore=5, backlash=0.2)
place(pinion, name="pinion", at=(0, 0, 0))
place(wheel,  name="wheel",  at=(CENTRE, 0, 0))
expect("pinion", "wheel", status="clear", clearance=(0.1, 0.4))
```
The pair report then PROVES the mesh: a clearance around 0.19 mm is
backlash you designed; `collision` means the centre distance is wrong;
`clearance 2 mm` means they are not meshing at all.

## Fits, clearances and the printer

| fit | printed-to-printed | printed-to-machined (bearing, shaft, pin) |
|---|---|---|
| free rotation | 0.3-0.4 mm diametral | H7/g6 -> use `solidsight fit 8 H7 g6` |
| sliding | 0.2-0.3 | H7/h6 |
| location, no play | 0.1-0.15 | H7/k6 |
| press | 0.05-0.1 interference | H7/p6 |

`solidsight fit <d> H7 g6` gives real ISO 286 numbers. Its own note is
the important part: **an FDM printer holds about +/-0.15 mm**, so
micrometre fits are a machining concept. Use the ISO table when your
printed part mates with a BOUGHT part (608 bearing, 8 mm rod), and use
the printed column for printed-to-printed.

Bought parts enter as ghosts, always:
```python
place(parts.component("bearing_608"), name="brg", at=(0, 0, 10),
      ghost=True)
expect("brg", "housing", clearance=(0.0, 0.05))   # press fit, declared
```

## Robot joints: declare them, do not fake them

```python
joint("shoulder", type="revolute", parent="base", child="upper_arm",
      origin=(0, 0, 120), axis=(0, 0, 1), limits=(-90, 90))
```
Then:
- `solidsight robot model.py --sdf` -> URDF/SDF with EXACT masses and
  inertia tensors computed from the geometry (not guessed slabs).
- `solidsight motion model.py --steps 24` sweeps every joint through its
  limits and reports the exact collision map per sampled position. This
  is the answer to "does the arm hit itself": a table, not an opinion.

Fix a collision found at, say, step 17 of 24 by reading which parts
collided and by how much — then either change the geometry or tighten
`limits`, and say which you did and why.

## Insertion and travel: sweep it

A mechanism that cannot be assembled is a failed mechanism.
`parts.swept(solid, dx, dy, dz)` gives the volume a part passes through.

```python
place(parts.swept(carriage_body, dz=-25), name="insert_path", ghost=True)
```
**Snap fits are the exception**: hooks interfere BY DESIGN during
insertion — that is how they latch. So sweep the RIGID body only, never
the hook, and stop the sweep just above the seated position. Judge the
hook separately: interference depth vs arm deflection.

Cantilever snap math (`parts.snap_clip` / `parts.snap_slot` are paired
already — use them):
- deflection `y = hook overlap`; strain `e = 1.5 * t * y / L^2`
- keep `e < 0.02` (2 %) for PLA, `< 0.04` for PETG/nylon
- so for `t=1.6`, `hook=1.2`: `L >= sqrt(1.5*1.6*1.2/0.02)` = 12 mm.
  `snap_clip(length=12, t=1.6, hook=1.2)` is not an arbitrary default.

## The five ways mechanisms fail

1. **Centre distance off** — teeth collide or float. The pair report says
   which, exactly.
2. **No backlash** — binds when printed. 0.2 mm.
3. **Bore fits nothing** — you modeled the shaft at 8.0 and the hole at
   8.0. The hole needs +0.3 for rotation, and a printed hole comes out
   ~0.2 undersize on top of that.
4. **The mechanism is a still life** — nothing declares what may touch.
   Every moving pair gets `expect(...)`; `solidsight motion` sweeps it.
5. **Un-assemblable** — press-fit bearing behind a wall, a gear that must
   pass through a shaft that is already there. Sweep the insertion path.

## Done means

- Every mesh/fit is a MET `expect()`, with the number quoted to the user.
- `solidsight motion --steps 24`: zero collisions inside the limits, or
  the limits were tightened and you said so.
- `--print-safe` clean per part; gears exported flat (`.on_ground()`).
- For robots: `solidsight robot --sdf` runs, and you state the masses —
  they are computed from geometry and density, not invented.
