# Furniture, framing and joinery

Load for: tables, shelves, chairs, desks, frames, workbenches, T-slot
machine frames, anything built from long members and joints at
human/room scale.

Different from every other domain in one way: **the parts are stock**.
You are not designing a shape, you are choosing lengths of standard
material and deciding how they meet. Model it that way.

## Stock sizes (assume these, state them)

| material | real sizes |
|---|---|
| aluminium T-slot | 20x20, 20x40, 30x30, 40x40 (`parts.extrusion_profile(length, size=20)`) |
| pine/softwood (nominal -> actual) | 2x4 -> 38 x 89 mm; 1x4 -> 19 x 89; 2x2 -> 38 x 38 |
| plywood | 12, 15, 18, 21 mm |
| MDF | 12, 16, 18, 22 mm |
| steel tube | 20x20x2, 25x25x2, 30x30x2 |
| dowel | 6, 8, 10, 12 mm |

## Human dimensions (these are not negotiable)

| thing | mm |
|---|---|
| seat height | 420-460 |
| desk / table height | 720-760 |
| standing desk | 950-1200 |
| kitchen counter | 900 |
| dining knee clearance under top | >= 620 |
| shelf depth, books | 200-300 |
| shelf depth, general | 350-450 |
| shelf clear height, books | 300-350 |
| walkway between furniture | >= 750 |
| chair seat depth | 400-450 |

Load: a shelf carrying books is ~30 kg/m. An 18 mm plywood shelf spans
~800 mm before visible sag; add a back or a front rail past that. Say
this to the user instead of drawing a 1.4 m unsupported shelf.

## Build it as a real frame

```python
LEG, RAIL = 38.0, 89.0          # 2x4 actual
H, W, D = 740.0, 1200.0, 600.0  # desk

leg = box(LEG, LEG, H - 18)     # top is 18 mm ply
for i, (x, y) in enumerate([(-W/2 + LEG/2, -D/2 + LEG/2),
                            ( W/2 - LEG/2, -D/2 + LEG/2),
                            (-W/2 + LEG/2,  D/2 - LEG/2),
                            ( W/2 - LEG/2,  D/2 - LEG/2)]):
    place(leg, name=f"leg_{i+1}", at=(x, y, 0))

top = box(W, D, 18)
place(top, name="top", at=(0, 0, H - 18))
expect("leg_1", "top", status="touching")     # the joint is DECLARED
```
Each member is its own `emit`/`place` — that gives you a real cut list
in `solidsight assembly` (BOM), and pair analysis at every joint.

## Joinery, honestly

| joint | model it as | note |
|---|---|---|
| butt + screws | two members touching + hole cutters | weakest; fine with brackets |
| dowelled | 8 mm holes, 30 deep, in BOTH members | model the dowels as ghosts |
| mortise & tenon | tenon = box on member A, mortise = same box (+0.2) cut from B | the classic; `expect(clearance=(0.1, 0.3))` |
| half lap | subtract half the thickness from each | strong, easy, ugly if visible |
| pocket hole | angled `parts.hole(...).aim(...)` at 15 deg | say it needs a jig |
| T-slot | `extrusion_profile` + corner brackets as ghosts | no joinery, that is the point |

Mortise-and-tenon done right, with the fit declared:
```python
TENON = box(20, 60, 30)
rail = rail + TENON.translate(...)                        # on the rail
leg  = leg  - TENON.scale(1.01, 1.01, 1.0).translate(...)  # mortise +1%
expect("rail", "leg", status="touching")
```

## Stability and racking — measure, do not assume

- `stability` in report.json: COM vs footprint. A tall shelf with a deep
  top shelf goes `barely-stable` -> tell the user it needs wall fixing.
  That is a real answer, not a failure.
- Four legs and a top rack sideways with no diagonal. If there is no
  back panel, no diagonal brace and no rigid corner bracket, SAY SO —
  the geometry cannot tell you, but the absence is visible in the BOM.
- Long spans: quote the span and the material. 18 mm ply over 800 mm =
  fine. Over 1400 = sag.

## The five ways furniture models fail

1. **Fantasy stock.** A 33 mm leg. Use real sizes; the user has to buy it.
2. **One fused blob.** Modeled as a single union -> no cut list, no
   joints, nothing to check. One member = one part.
3. **Human dimensions wrong.** A 680 mm desk, a 380 mm seat. The table
   above is not decoration.
4. **Joints that only exist in the render.** Members that touch but with
   no dowel, screw or tenon modeled. Every joint is either modeled or
   named in the notes.
5. **No thought about assembly order or racking.** `solidsight assembly`
   gives a suggested sequence — read it and sanity-check it.

## Done means

- BOM = a real cut list (`solidsight assembly`): every member, its size,
  quantity. Group identical members (the BOM does this by geometry).
- Every joint is a MET `expect()`.
- Human dimensions quoted against the table above.
- Stability read from the report; wall-fixing stated if `barely-stable`.
- Mode: `--free` is fine for wood (you are not printing it) — but read
  the report anyway; a `collision` between a tenon and a mortise is a
  real error in any material.
