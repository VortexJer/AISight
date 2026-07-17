# Vehicles, aircraft and ships

Load for: cars, trucks, bikes, boats, hulls, planes, drones, rockets,
spacecraft — anything organised along a spine with sections across it.

The shared method: **a spine, stations along it, a section at each
station, lofted**. That is literally how real hulls and fuselages are
drawn, and it maps exactly onto `parts.loft`.

## The station method

```python
# stations along X (the spine), each a CONVEX section in its own plane
STATIONS = [0, 400, 1200, 2400, 3600, 4200]          # mm from the nose
SECTIONS = [circle(60), circle(220), rect(300, 240).round_corners(60),
            rect(300, 240).round_corners(60), circle(200), circle(80)]

fuselage = parts.loft(SECTIONS, heights=STATIONS).aim("+x")
```
`parts.loft` stacks along +Z and hulls consecutive slabs, so:
- build along Z, then `.aim("+x")` to lay it on its spine;
- **every section must be CONVEX** — a hull section with a concave
  tumblehome fills in silently. Split the form: hull the convex body,
  subtract the concavity afterwards;
- more stations = more faithful. Real drawings use 10-20; 4 gives you a
  crude toy and it will look like one.

## Real proportions (assume, and say you assumed)

| vehicle | length | width | height | notes |
|---|---|---|---|---|
| compact car | 4200 | 1750 | 1450 | wheelbase 2600, track 1500 |
| sedan | 4700 | 1820 | 1450 | wheelbase 2800 |
| SUV | 4800 | 1900 | 1700 | ground clearance 200 |
| van | 5400 | 2000 | 2500 | |
| bicycle | 1750 | 600 | 1100 | wheelbase 1030, wheel d 622 (700c) |
| motorcycle | 2100 | 750 | 1100 | wheelbase 1400 |
| light aircraft (C172-class) | 8300 | 11000 span | 2700 | |
| quadcopter (5") | 250 diag | | 60 | props 127 mm |
| sailing dinghy | 4000 | 1500 | | draft 150 (board up) |
| shipping container (40 ft) | 12192 | 2438 | 2591 | exact, ISO 668 |

Wheels/props are separate parts, always — they rotate, so they are their
own `emit`, and their contact is `expect("wheel_fl", "body",
status="clear", clearance=(2, 20))`.

## Aircraft: the aerofoil is data, not a guess

A wing section is a NACA profile, not a lens shape you drew. NACA 4-digit
thickness distribution (chord c, thickness fraction t):

```python
def naca(t, c, n=40):
    pts_up, pts_lo = [], []
    for i in range(n + 1):
        x = c * (0.5 - 0.5 * math.cos(math.pi * i / n))   # cosine spacing
        xc = x / c
        yt = 5 * t * c * (0.2969 * math.sqrt(xc) - 0.1260 * xc
                          - 0.3516 * xc**2 + 0.2843 * xc**3
                          - 0.1015 * xc**4)
        pts_up.append((x, yt))
        pts_lo.append((x, -yt))
    return polygon(pts_up + pts_lo[::-1])

wing_root = naca(0.12, 1600)        # NACA 0012, 1.6 m chord
wing_tip  = naca(0.12, 900)
wing = parts.loft([wing_root, wing_tip], heights=[0, 5500]).aim("+y")
```
Cosine spacing (not linear) is what makes the leading edge round instead
of chopped. Dihedral: rotate the lofted wing a few degrees (3-6 typical).
Say which NACA you used and why.

## Hulls: waterline is the number that matters

A hull that floats is a volume claim. The report gives you exact volume,
so displacement is arithmetic:
```python
# displaced volume up to the waterline -> mass it can carry
below = hull_solid & box(20000, 5000, 400).translate(0, 0, -200)
```
`below.volume` mm3 / 1e6 = litres = kg of fresh water displaced (1000 kg
per m3; 1025 for seawater). Quote it. `stability` in report.json (COM vs
footprint) is a rough proxy for tenderness — a high COM in a narrow hull
is `barely-stable` and it means what it says.

## Detail and semantics

- Panel lines, vents, hatches: cut them AFTER the main form, with
  `.aim()` along the local surface, `through_margin=` so they always
  break out (a buried panel line = a sealed cavity = a fail).
- Record what things ARE:
  ```python
  emit(body, name="fuselage", features=[
      {"type": "canopy", "at": [1800, 0, 320]},
      {"type": "engine_mount", "at": [4100, 0, 0], "thrust_n": 4500},
  ])
  ```
- Symmetry: model the port side, `.mirror("y")`, union. Never hand-place
  the mirror.

## The five ways these fail

1. **Too few stations.** 4 sections = a bar of soap. Use 8-20.
2. **Concave section silently filled** by the loft. Check EVERY station
   in `--slice x=<station>`.
3. **Invented proportions.** A 5.2 m "compact car". The table exists.
4. **Aerofoil drawn by eye.** It is a published polynomial. Use it.
5. **The wheels touch the body / float** and nobody measured. `pairs[]`
   with declared clearances.

## Done means

- `--turntable 8` + `--views iso,front,right,top` looked at: vehicles are
  judged in silhouette from the side and the front.
- `--slice x=` at 3+ stations to prove the sections are what you drew.
- Proportions quoted against the table (or against the user's spec).
- Mode `--free` for visual/game use; for a printed model run
  `--print-safe` and expect to thicken wings/masts — say so.
- Displacement/span/wheelbase stated as numbers from the report.
