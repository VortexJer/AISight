# Car bodies and styled shells — station lofting

For any commission whose shape is a designed OUTER SKIN rather than an
engineered prism: cars, boat hulls, aircraft fuselages, appliance
shells, helmets. Load this BEFORE writing any geometry for such an
object. The generic box-and-cylinder toolbox produces "a box with a
cabin glued on", and a modern car is nothing like that.

## Say what you can deliver BEFORE you start

A styled body is where this tool is weakest, and the user must hear it
from you at the start, not discover it after twenty builds. State it in
one or two plain sentences and let them decide:

- there is **no surface modelling** here — no NURBS, no sub-D, no
  class-A blends, no 3D fillet across arbitrary edges. Booleans and
  station lofts give correct proportions and a clean single shell; they
  do not give a finished exterior.
- the report measures **manufacturability, not likeness**: watertight,
  0 findings and every spec met can still look nothing like the
  referent. `--ref` compares, but nothing scores resemblance — that
  judgement is the user's eye.
- every non-body piece (lights, glass, grille, mirrors, trim) is its own
  little commission carved out of the body shell, and one bad piece
  ruins the whole. A faithful car is dozens of them, minutes per build.

So offer the honest deal: **a well-proportioned massing** is realistic;
a photo-faithful car is not. If they want the real exterior, say a
sub-D/NURBS modeller is the right tool and offer solidsight for the
parts around it. If they accept the massing, do exactly that and don't
promise likeness later.

## The one rule that matters most

**A modern car body is ONE piece.** Hood, fenders, greenhouse, haunches
and decklid are a single continuous surface — there is no "body box"
with a "cabin box" on top (that died in the 1940s). If your bill of
parts contains a part called `cabin` or `greenhouse` as a separate
solid welded onto a `body`, you have already failed the commission.
The whole outer skin is one `parts.loft_sections()` solid; everything
else (wheel arches, DLO, grille, vents) is CARVED OUT of it or added
as small separate parts (wheels, glass, mirrors).

## Speak the domain language

Use these words in your Feature Specification — they are how the
photos will read:

- **beltline**: where glass meets sheetmetal, running the car's length.
- **shoulder**: the surface just below the beltline turning into the
  body side. In section it is a CONCAVE corner — the reason `loft()`
  (convex hulls) cannot do bodywork and `loft_sections()` exists.
- **tumblehome**: the inward lean of the glass above the beltline.
  Steep on a sports car (~65-70 deg from horizontal at the base).
- **greenhouse / DLO**: the glassed upper zone / the window graphic.
- **character line**: a crease running along the side.
- **haunch**: the muscular swell over the REAR axle — widest point of
  a sports coupe, and what makes it read "planted".
- **Kamm tail**: the chopped, near-vertical rear face. A flat-ish tail
  section is correct, not lazy.

## The method

**Do not eyeball the photo.** A car is lost or won on its silhouette,
and "it looks about right" is exactly the squint solidsight exists to
kill. You MEASURE the reference into numbers, then build to those
numbers. Pipeline: clean side view -> `solidsight profile` turns it
into an exact mm envelope -> your stations SAMPLE that envelope ->
build with `--ref` and compare.

1. **Research + get a clean side view** (detail-mode rules apply): the
   four numbers are published for every car — overall length, width,
   height, wheelbase `[researched]` (Vantage 2024: 4465 x 1942 x 1273,
   WB 2704). Then fetch a **straight-on side profile** — search
   "<car> blueprint side" or "<car> side profile" and pick clean
   line-art / a filled silhouette on a plain background (NOT a 3/4
   glamour shot — perspective lies). Grab a **front** view too; width
   and tumblehome only exist there.
2. **MEASURE the side view** — the step that replaces guessing:

       solidsight profile side.png --length 4465 --stations 14 \
                                   --out side.measured.png

   It returns, in real mm: overall length and height, the wheel axles
   (with the measured wheelbase — check it against the published one to
   confirm scale), and the **upper envelope (roof/hood/decklid crown)
   and lower envelope (rocker/underside) sampled at every station**.
   **LOOK at side.measured.png** (Read tool): red dots must sit on the
   roofline, green on the underside, orange lines through the wheel
   centres. If they do not, the silhouette was dirty — raise/lower
   `--threshold` or pick a cleaner image; do NOT proceed on a bad read.
   Run it on the front view too to measure half-width and glass taper.
3. **Lay the datums**: X along the length, Z up, ground at z=0. Take
   the axle x's straight from the read; the crown at each station is
   `top_z`, the underside `bottom_z` — measured, not guessed.
4. **Write ONE parametric station template** — a function that returns
   a closed section polygon (same point count every call; that is what
   `loft_sections` welds station to station). Half-template, mirrored:
   - floor (flat, at the measured ground clearance = min `bottom_z`)
   - rocker turn-up
   - body side rising to the beltline with a **barrel bulge** (widest
     ~55% up the side; max half-width comes from the front read)
   - **shoulder**: the concave inboard run to the greenhouse base
   - **top region**: an elliptical tumblehome arc ending
     TANGENT-HORIZONTAL at the centerline, its **peak z set to the
     measured `top_z` at that station**. On hood/decklid stations this
     same arc IS the hood crown — that identity makes the body one piece.
5. **Evaluate the template at the profile's stations**: splitter lip,
   grille face, pre-arch, front axle (fender peak), hood mid, cowl,
   A-pillar, roof crown (over the seats), C-pillar, rear axle (the
   haunch: widest y of the whole car), decklid, tail face. Each
   station's top z is its measured `top_z`; half-width and greenhouse
   half-width interpolate from the front-view measurement. You are
   FITTING the template to measured points, not inventing them.
6. **`body = parts.loft_sections(sections, xs)`** — then carve:
   wheel arches (a centered cylinder along Y at each axle), grille and
   intake pockets, DLO inset if you want the glass line engraved.
7. **Separate parts**: wheels (`material="matte"`, dark), glass band
   if modeled (`material="glass"`), mirrors. Body gets
   `material="glossy"` and its real paint color.
8. **Build with `--ref side.png` and LOOK at every render** against the
   photo and the measured overlay. The roofline of your render must
   trace the red dots. Judge like a designer: stance, DLO shape,
   haunch, tumblehome — not like a machinist.

## Measured pitfalls (each cost the pilot an iteration)

- **Tent roof**: a top arc whose last segment lands at the centerline
  with slope makes a ridge like a tent. End the arc tangent-horizontal
  (points at cos/sin of 18..90 deg, exponent ~1.3-1.8 on the sine).
- **Floating wheels**: tyres touch the ground — wheel center z =
  wheel_diameter/2, EXACTLY. The body floor stays at clearance height;
  the wheels hang below it. `query point <x> <track_y> 5` under a tyre
  should be INSIDE the wheel.
- **Arch punch-through**: the arch cylinder's top (center z + r) must
  stay below the LOCAL shoulder height, or the cut opens a hole in the
  hood surface. Front fender lines are high on modern cars partly for
  this reason. Verify: `query ray <axle_x> 0 <belt_z+20> 0 1 0` should
  cross body material, not void.
- **Wheels poking out**: at the wheel center height the body side sits
  near its bulge maximum; track/2 + tyre width must stay inside it.
  Measure the section, do not eyeball.
- **Greenhouse too domed**: if the roof reads like a beetle, the
  greenhouse base is too narrow — glass base half-width on a coupe is
  ~55-65% of the body half-width, and the roof panel itself stays
  nearly flat between the side arcs (raise the sine exponent).

## Sanity checklist before showing the human

- One `body` part; NO part named cabin/greenhouse/hood as a solid.
- length/width/height within 1% of the researched numbers
  (`report.json scene.size`).
- the render's roofline traces the red dots of `side.measured.png`; the
  crown z per station is within ~30 mm of the measured `top_z`.
- tyres at z=0; arch gap over tyre 35-60 mm.
- rear haunch is the widest point; front fender slightly narrower.
- viewer check: `solidsight view` was already running from Step 0.5 —
  orbit it; a car reads instantly or not at all.
