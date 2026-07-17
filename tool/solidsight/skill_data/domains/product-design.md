# Product design and consumer electronics shells

Load for: handheld devices, remotes, speakers, appliances, tool bodies,
grips, anything a HAND holds or a room sees. The judge is a person, but
the failures are still geometric.

## The two-surface discipline

A product shell is an outer surface people touch and an inner cavity
that holds hardware — and they are NOT independent. Model the outside
first as one continuous form, then hollow it, then split it. Never
model two half-shells separately and hope they meet.

```python
# 1. one continuous outer body (see the loft rules below)
body = parts.loft([rect(62, 24).round_corners(11),
                   rect(70, 28).round_corners(13),
                   rect(66, 26).round_corners(12)],
                  heights=[0, 40, 78])

# 2. hollow: the inner cavity is the SAME form, scaled/offset inward
cavity = parts.loft([rect(56, 18).round_corners(8),
                     rect(64, 22).round_corners(10),
                     rect(60, 20).round_corners(9)],
                    heights=[2.0, 40, 76])
shell = body - cavity

# 3. split into halves LAST, with a real seam
upper = shell & box(200, 200, 40).translate(0, 0, 40 + 20)
lower = shell - box(200, 200, 40).translate(0, 0, 40 + 20)
```
`parts.loft(profiles, heights)` requires CONVEX profiles (it hulls
consecutive slabs — a concave section silently fills in). Check the
render every single time; a loft that "looks fine" from iso can be
filled at the waist.

## Numbers

| thing | value |
|---|---|
| shell wall | 2.0-2.5 mm (injection: 1.2-2.0, uniform) |
| draft angle (if it will ever be molded) | 1-2 deg per side, minimum |
| grip diameter, power grip | 30-45 mm |
| grip diameter, precision grip | 8-16 mm |
| thumb reach from grip axis | 45-70 mm |
| button diameter, finger | 8-12 mm, travel 0.8-1.5 |
| button spacing, centre-to-centre | >= 14 mm |
| seam gap between halves | 0.15-0.25 mm |
| screw bosses per shell | >= 4, in the corners, 2.5 x screw d |
| edge radius people touch | >= 1.5 mm (sharp edges read as cheap) |

## Fillets and radii — the whole aesthetic

Consumer products read as expensive because of edge continuity. Rules:
- **One radius family.** Pick a base radius R (say 3 mm) and use
  R, 2R, R/2 — not seven arbitrary values.
- **Bigger radius on bigger features.** A 3 mm radius on a 70 mm face
  looks unfinished; on an 8 mm rib it looks right.
- **Fillet LAST**, after every boolean. `.fillet(r)` auto-simplifies;
  filleting early then cutting slices the fillet in half.
- Rims of prismatic parts: `.chamfer_rim(c)` / `.round_rim(r)` break the
  top/bottom edge exactly — this is the tool for "the edge where the
  lid meets the hand".
- If a fillet takes minutes, your radius is fighting a boolean. Reduce
  it or reorder.

## Ergonomics is measurable

You cannot feel the grip, so measure it:
```python
# is the waist actually 34 mm where the palm sits?
```
`solidsight query model.py section z=40` — read the ASCII grid width.
`solidsight query model.py ray -60 0 40 1 0 0` — exact wall crossings
across the grip. `solidsight build --focus 0,0,40,25` — zoom the views
onto the palm zone. State the numbers to the user ("grip waist 34 mm,
in the power-grip band"), never "it feels ergonomic".

`stability` in report.json (COM vs footprint) is the answer to "does the
speaker tip over": `unstable` or `barely-stable` are findings, and the
fix is usually mass low and a wider foot, not a bigger base.

## The five ways product shells fail

1. **Loft filled the concave waist** — you got a potato. Split into
   convex pieces and union, or use a different strategy.
2. **Wall thickness varies wildly** — 3.5 mm here, 0.9 mm there, because
   outer and inner forms were drawn independently. The `thin-wall`
   finding with its exact point is your friend; `--slice` at several
   heights and LOOK.
3. **The seam is a lie** — halves modeled separately never meet. Split
   ONE body.
4. **Buttons/ports placed by eye** on a curved face and half-buried.
   `.aim()` the cutter along the LOCAL surface normal, use
   `through_margin=` so it always breaks out, verify with a ray.
5. **It is pretty and un-printable/un-moldable** — no draft, undercuts
   everywhere, 0.9 mm walls. Decide the process FIRST and say it.

## Done means

- Report clean in the mode you declared; wall thickness essentially
  uniform (state min and where).
- Turntable render (`--turntable 8`) looked at, not just iso — form
  reads differently from every angle, and that is the whole point here.
- Grip/reach numbers quoted from queries, not adjectives.
- Halves `expect()`-ed at the seam clearance you chose.
