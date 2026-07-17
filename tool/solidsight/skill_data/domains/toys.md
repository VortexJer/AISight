# Toys, games and tabletop

Load for: toys, puzzles, board-game inserts, dice towers, game pieces,
building blocks, marble runs, kids' props.

Two constraints no other domain has: **children's safety is a legal
standard, not an opinion**, and **the thing must survive being thrown at
a wall**.

## Safety — these are hard rules

| rule | value | source |
|---|---|---|
| small-parts cylinder (choking) | anything that fits in 31.7 mm dia x 57.1 mm deep is a choking hazard for under-3s | US 16 CFR 1501 |
| no sharp points or edges | radius >= 1 mm everywhere a child touches | EN 71-1 / ASTM F963 |
| no accessible magnets | swallowed magnet pairs perforate bowel — do not design them into kids' toys | EN 71-1 |
| cords/loops | > 220 mm loop = strangulation risk | EN 71-1 |
| material | PLA is fine for hands; **no PLA for mouthed toys** (layer lines harbour bacteria, cannot sterilise) | |
| paint/finish | must be non-toxic if it can be mouthed | EN 71-3 |

If the user says "for a 2-year-old", the small-parts rule applies to
EVERY separate piece and to any piece that could break off. Check it —
you have exact bboxes:
```python
# every emitted piece must NOT fit inside the small-parts cylinder
# report bbox: if all three dims < 31.7 and length < 57.1 -> hazard
```
Say it out loud when a design fails this. It is not a nag; it is the
whole reason the standard exists.

## Durability: toys get abused

| feature | value |
|---|---|
| wall thickness | 2.5-3 mm (double the usual — kids are a load case) |
| corner radius | >= 2 mm, and 3-4 mm where hands grip |
| snap fits for kids | thicker arms, lower strain (< 1.5 %), see `mechanisms.md` |
| moving joints | 0.4-0.5 mm clearance (dirt, paint, fingers) |
| print orientation | layer lines PERPENDICULAR to the expected load |
| infill for toys | 30-40 % (say so — it is not a geometry decision, but they need it) |

PETG over PLA for anything that gets dropped: PLA is stiff and brittle,
PETG bends first. Say which and why.

## Standard sizes worth knowing

| thing | mm |
|---|---|
| LEGO stud pitch | 8.0 (exact) |
| LEGO brick height | 9.6 (3 plates of 3.2) |
| LEGO stud dia | 4.8, height 1.8 |
| standard d6 die | 16 (12 and 19 also common) |
| poker card | 63.5 x 88.9 |
| standard sleeve (card) | 66 x 91 |
| mini card (Catan) | 44 x 68 |
| meeple | 16 tall |
| 28 mm miniature base | 25 dia round, or 25 x 25 square |
| marble | 16 dia (standard), 25 (shooter) |
| board-game box insert | measure the box: ASK, they vary |

LEGO-compatible is a real request and a real trap: the stud pitch is
8.0 mm exactly, but printed studs need clearance (stud 4.8 -> hole 5.0)
and the clutch power comes from tolerances an FDM printer cannot hold.
Model it, but tell the user the clutch will be wrong.

## Board-game inserts: measure the box, use ghosts

```python
# the components are GHOSTS: keep-outs you cut around, never printed
place(box(66, 91, 25), name="card_stack", at=(0, 0, 5), ghost=True)
place(cylinder(h=10, d=16), name="tokens", at=(50, 0, 5), ghost=True)
expect("card_stack", "insert", clearance=(0.5, 1.5))   # fingers need room
```
Rules that make inserts good rather than merely tight:
- **finger scoops**: every compartment needs a way to get the pieces OUT.
  A 20 mm radius scallop cut into the wall. Without it the insert is a
  trap. This is the single most common insert failure.
- 0.5-1.0 mm clearance around sleeved cards (they swell).
- The insert must lift out as one piece, or be clearly separate trays.
- Total height must clear the lid: measure and `expect()` it.

## Puzzles and mechanisms

- Interlocking puzzles: clearance 0.15-0.25 mm per mating face —
  tighter binds, looser rattles. Declare it with `expect()`.
- Print-in-place mechanisms (`parts.hinge`) need 0.4 mm gaps at this
  scale, not 0.2 — kids' toys get dirt in them.
- A marble run needs slope: > 4 deg to keep rolling, and the channel
  1.5x the marble diameter. Verify with `--slice` along the run.
- Dice: 16 mm cube, pips 2.5 mm dia x 0.8 deep, edges rounded 1.5 mm.
  A printed die is NOT fair (infill, layer mass, pip volume) — say so.

## The five ways toys fail

1. **Choking hazard nobody checked.** The bbox is right there.
2. **Sharp edges / thin walls** — modeled like a display piece, then
   handed to a 4-year-old. 2.5-3 mm walls, 2 mm radii.
3. **Insert with no finger scoops.** Components go in, never come out.
4. **Sleeved cards measured unsleeved.** 3 mm short across a stack.
5. **"LEGO compatible"** promised without mentioning that printed clutch
   is unreliable.

## Done means

- Age stated; if under 3, small-parts rule checked against every part's
  bbox and the result reported.
- All accessible radii >= 1 mm (>= 2 preferred), walls >= 2.5 mm.
- `--print-safe` clean; material (PETG/PLA) and infill recommended
  explicitly.
- Inserts: every compartment has a scoop; `expect()` on every component
  ghost; total height under the lid verified.
- Moving parts: clearances declared, `solidsight motion` if they rotate.
