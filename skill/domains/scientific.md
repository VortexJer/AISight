# Scientific and data visualization

Load for: molecular models, lab fixtures, anatomical models, physical
data plots, math surfaces, teaching aids, museum/exhibit pieces.

The rule that governs everything here: **the geometry is a claim about
reality**. A bond angle, a scale bar, a data height — get it wrong and
the object is not "less pretty", it is wrong. So: cite the source, tag
every number, and never invent one silently.

## Cite or ask. Never invent.

Tag every value in the model header, the same way detail mode does:
```python
# Caffeine C8H10N4O2 — geometry from PubChem CID 2519 [researched]
# scale: 1 A = 10 mm  [chosen: fits a 200 mm print bed]
# C-N bond 1.34 A [researched]; C=O 1.23 A [researched]
```
If the user gives no data and none is at hand, ASK. A fabricated protein
is worse than no protein. (Detail mode's research step applies here:
`detail-mode.md`.)

## Molecular models

Standard practice, use it:

| convention | value |
|---|---|
| scale | 1 A (angstrom) = 10 mm is common; state yours |
| ball-and-stick atom radius | 0.3 x van der Waals |
| space-filling (CPK) radius | full van der Waals |
| bond (stick) diameter | 2-3 mm at 1 A = 10 mm |
| C-C single bond | 1.54 A |
| C=C double | 1.34 A |
| C-H | 1.09 A |
| tetrahedral angle | 109.47 deg |
| trigonal planar | 120 deg |
| benzene C-C | 1.39 A (all equal — do not alternate) |

vdW radii (A): H 1.20, C 1.70, N 1.55, O 1.52, S 1.80, P 1.80.
CPK colors: H white, C dark, N blue, O red, S yellow.

```python
A = 10.0                                   # mm per angstrom
def atom(el, x, y, z):
    r = {"C": 1.70, "N": 1.55, "O": 1.52, "H": 1.20}[el] * 0.3 * A
    return sphere(d=2 * r).translate(x * A, y * A, z * A)

bond = parts.tube_path([(0, 0, 0), (1.54 * A, 0, 0)], d=2.5)
```
Printed molecules: bonds are the weak point. Below 2.5 mm they snap.
`--print-safe --min-wall 2.0` and be ready to thicken bonds — say that
you did and that it is a legibility/strength decision, not chemistry.

## Physical data plots

The data must survive the trip to geometry:
- **A 3D bar chart is a grid of boxes.** Height = value x scale. Write
  the scale down, put it in a `features` entry, and add a physical scale
  reference (a labeled cube of known height).
- **A surface plot** is `refine()` + `warp()` where the warp is the
  function — see `terrain.md` for the refine-first rule. Same for
  `image_heightfield` when the data arrives as an image.
- **Never exaggerate silently.** If z is exaggerated 5x so the variation
  reads, that goes in the text on the object AND in what you tell the
  user.
- Real units, always: `emit(bars, name="chart", features=[
  {"type": "scale", "mm_per_unit": 4.0, "unit": "kWh"}])`.

## Lab fixtures and anatomical models

Standard sizes worth knowing:

| thing | mm |
|---|---|
| microscope slide | 76 x 26 x 1 |
| Eppendorf 1.5 mL tube | 10 dia, 39 tall (conical) |
| 15 mL Falcon | 17 dia, 120 |
| 50 mL Falcon | 30 dia, 115 |
| 96-well plate | 127.76 x 85.48 (SBS standard, exact) |
| 96-well spacing | 9.0 mm |
| Petri dish | 90 dia, 15 tall |
| optical breadboard | M6 holes on 25 mm grid |
| standard cuvette | 12.5 x 12.5 x 45 |

Racks and holders: model the vessel as a GHOST, cut the pocket around
it, declare the fit.
```python
tube = cylinder(h=39, d=10.2)          # +0.2 clearance
place(tube, name="sample", at=(0, 0, 6), ghost=True)
expect("sample", "rack", clearance=(0.1, 0.4))
```
Autoclavable? Then it is PP/PC, not PLA (PLA deforms at 60 C). Say so.

Anatomical models: source the geometry (a scan, a published dataset) or
say plainly that it is representative. "A representative femur" is
honest; "a femur" implies data you do not have.

## Measure, because the whole point is the numbers

`solidsight query` is not optional in this domain — it is the instrument:
- `query point X Y Z` — is this coordinate inside the structure?
- `query ray ...` — exact wall/segment thicknesses along a line
- `query distance a b` — exact min distance between two atoms/parts
- `query section z=` — an exact cross-section, ASCII, no rendering
- report `volume` / `area` — exact, cite them

The bond angle you claim should come from the coordinates you used, and
the distance between two atoms should be verified with `query distance`,
not assumed from the code.

## The five ways these fail

1. **Invented data.** A plausible-looking wrong molecule. Cite or ask.
2. **No scale stated.** A model of unknown size is not a measurement.
3. **Silent exaggeration** on a data axis. State the factor, on the
   object if possible.
4. **Un-printable truth** — 0.8 mm bonds that break. Thicken and SAY
   you thickened; do not pretend it is to scale if it is not.
5. **Bonds/atoms not verified** — `query distance` exists; use it.

## Done means

- Every number tagged `[researched]` / `[standard]` / `[assumed]`, with
  the source named for researched ones.
- Scale and any exaggeration stated, and recorded in `features`.
- Key distances/angles verified with `query`, not assumed.
- Printed: `--print-safe`, material named if it matters (autoclave, food
  contact), thin members thickened deliberately and disclosed.
