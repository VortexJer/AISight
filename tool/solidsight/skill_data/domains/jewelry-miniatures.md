# Jewelry and miniatures

Load for: rings, pendants, earrings, charms, tabletop miniatures, scale
models, dioramas, any detail near the printer's resolution floor.

One thing defines this domain: **you are working at the machine's
limit**, so the numbers that are advisory elsewhere are hard walls here.
And the renders lie by default — at these sizes you must `--focus` on
everything.

## Process decides everything — ask FIRST

| process | min wall | min detail | typical use |
|---|---|---|---|
| FDM 0.4 nozzle | 0.8 mm | 0.4 mm | prototypes only; miniatures look bad |
| resin (MSLA/SLA) | 0.4 mm | 0.05 mm | miniatures, jewelry masters |
| casting (lost wax, from resin) | 0.6 mm | 0.2 mm | real metal jewelry |
| silver/gold, direct SLM | 0.5 mm | 0.1 mm | expensive, exact |

This is the ONE question to ask before modeling: *resin, FDM, or cast in
metal?* Then set the floor explicitly and say it:
```bash
solidsight build model.py --print-safe --min-wall 0.5   # resin master
```
Never leave `--min-wall` at the 1.2 default here — it will fail
everything and teach you nothing.

## Ring sizes (exact, use them)

Inner diameter in mm — this is not a place to improvise:

| US | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|
| ID mm | 15.7 | 16.5 | 17.3 | 18.1 | 18.9 | 19.8 | 20.6 | 21.4 |

EU size = inner circumference in mm (size 54 = 54 mm around = 17.2 ID).

| feature | value |
|---|---|
| band thickness (radial) | 1.4-2.0 mm (1.2 absolute min) |
| band width (axial) | 2-8 mm (comfort fit: round the inside edge) |
| ring sizing allowance for resin | print +0.15 mm on the ID |
| prong thickness | 0.7-0.9 mm |
| bezel wall | 0.6-0.8 mm |
| chain bail hole | >= 2.5 mm |
| pendant thickness | >= 1.2 mm |
| stone seat depth | 60 % of stone height |

```python
ID, BAND_T, BAND_W = 17.3, 1.6, 5.0        # US 7
band = (cylinder(h=BAND_W, d=ID + 2 * BAND_T) - cylinder(h=BAND_W + 2,
        d=ID).translate(0, 0, -1)).round_rim(0.4)   # comfort fit
```

## Miniature scales (exact ratios)

| scale | ratio | 6 ft human |
|---|---|---|
| 28 mm heroic | ~1:56 | 32 mm to eyes |
| 32 mm | ~1:48 | 35 mm |
| 1:35 (military) | 1:35 | 52 mm |
| 1:24 | 1:24 | 76 mm |
| N gauge | 1:148 | 12 mm |
| HO | 1:87 | 21 mm |
| O gauge | 1:48 | 38 mm |

Model at 1:1 in mm, then `.scale(1/35, 1/35, 1/35)`. Check `--print-safe`
AFTER scaling — a 20 mm rifle barrel at 1:35 is 0.57 mm and that is the
number that matters.

At miniature scale, detail must be EXAGGERATED to survive: a 2 mm real
seam at 1:35 is 0.06 mm and disappears. Deepen engravings to at least
0.3 mm and say you exaggerated them.

## Text and engraving at small scale

`text()` and `parts.wrapped_text(string, d, size, depth, outward)` for
inscriptions on rings. Rules that hold at this size:
- engraving depth >= 0.3 mm (resin), >= 0.5 mm (FDM), or it vanishes
- letter size >= 1.2 mm for resin, >= 2.5 mm for FDM
- `wrapped_text` covers at most 2/3 of the circumference — past that the
  wrap distorts
- **known limitation**: the ribs BETWEEN engraved letter strokes get
  flagged by the wall metric. That is a documented false positive
  (`report-guide.md`) — verify with `--focus` on the point and say so
  rather than thickening a letter into mush.

## Focus is mandatory, not optional

A 17 mm ring in a 900 px iso render is a blob. Every claim you make about
detail must come from a focused view or a query:
```bash
solidsight build model.py --focus 0,0,4,6 --views iso,front --size 1200
solidsight query model.py section z=4          # ASCII grid, exact
solidsight query model.py ray -20 0 4 1 0 0    # band wall, exact mm
```

## The five ways these fail

1. **`--min-wall` left at 1.2** — everything fails, or worse, you thicken
   a beautiful piece into a lump for no reason. Set it from the process.
2. **Scaled, then never re-validated.** The 0.57 mm barrel.
3. **Never focused.** Every render is a blob and every claim is a guess.
4. **Prongs/bezels at 0.4 mm** because they looked fine at 900 px.
5. **Engraving 0.15 mm deep** — invisible after printing, invisible after
   casting.

## Done means

- Process named, `--min-wall` set from it explicitly and quoted.
- `--focus` renders of every fine feature, LOOKED at.
- Ring ID from the table, +0.15 for resin, stated as a size.
- Miniatures: scaled, THEN `--print-safe`; detail exaggeration stated.
- Wall findings on engraved ribs verified with `--focus` before acting.
