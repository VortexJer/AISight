# Car bodies and styled shells — station lofting

For any commission whose shape is a designed OUTER SKIN rather than an
engineered prism: cars, boat hulls, aircraft fuselages, appliance
shells, helmets. Load this BEFORE writing any geometry for such an
object. The generic box-and-cylinder toolbox produces "a box with a
cabin glued on", and a modern car is nothing like that.

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

1. **Research first** (detail-mode rules apply): the four numbers that
   anchor everything are published for every car — overall length,
   width, height, wheelbase `[researched]`. Fetch 3-6 photos (side,
   front, rear, 3/4) and keep them as `--ref` images `[photo]`.
   Example, Vantage 2024: 4465 x 1942 x 1273, WB 2704.
2. **Lay the datums**: X along the length, Z up, ground at z=0. Place
   the axles from wheelbase + overhangs (front overhang of a
   front-engine coupe ~0.8-0.9 m, rear slightly longer).
3. **Write ONE parametric station template** — a function that returns
   a closed section polygon (same point count every call; that is what
   `loft_sections` welds station to station). Half-template, mirrored:
   - floor (flat, at ground-clearance height ~110-130)
   - rocker turn-up
   - body side rising to the beltline with a **barrel bulge** (widest
     ~55% up the side)
   - **shoulder**: the concave inboard run to the greenhouse base
   - **top region**: an elliptical tumblehome arc ending
     TANGENT-HORIZONTAL at the centerline. On hood/decklid stations
     this same arc IS the hood crown — that identity is what makes the
     body one piece.
4. **Evaluate the template at 10-14 stations**: splitter lip, grille
   face, pre-arch, front axle (fender peak), hood mid, cowl, A-pillar,
   roof crown (over the seats), C-pillar, rear axle (the haunch:
   widest y of the whole car), decklid, tail face. Parameters that
   move: half-width, beltline z, greenhouse half-width, top z, crown
   fullness.
5. **`body = parts.loft_sections(sections, xs)`** — then carve:
   wheel arches (a centered cylinder along Y at each axle), grille and
   intake pockets, DLO inset if you want the glass line engraved.
6. **Separate parts**: wheels (`material="matte"`, dark), glass band
   if modeled (`material="glass"`), mirrors. Body gets
   `material="glossy"` and its real paint color.
7. **Build with `--ref photo_side.jpg` and LOOK at every render**
   against the photos. Judge like a designer: stance, DLO shape,
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
- tyres at z=0; arch gap over tyre 35-60 mm.
- rear haunch is the widest point; front fender slightly narrower.
- viewer check: `solidsight view` was already running from Step 0.5 —
  orbit it; a car reads instantly or not at all.
