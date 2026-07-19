# 09 — coupe body: one-piece station lofting

The commission class that used to fail: "model a 2024 sports coupe".
The generic toolbox produces a box with a cabin glued on; a modern car
body is ONE continuous skin. This example is the worked recipe from
[`references/car-bodies.md`](../../references/car-bodies.md):

- **one parametric station template** (34 points: floor, rocker,
  barrel-bulged body side, concave shoulder, tumblehome arc ending
  tangent-horizontal at the centerline) evaluated at 12 stations from
  splitter lip to Kamm tail — hood and roof are the same "top region"
  of the template, which is what makes the body one piece;
- **`parts.loft_sections()`** welds the stations into a single
  watertight solid (sections are concave at the shoulder — hull-based
  `loft()` cannot do this);
- wheel arches carved with centered cylinders; wheels as separate
  matte parts, tyres touching the ground (wheel center z = D/2);
- proportions anchored on the researched numbers of a real 2024 coupe:
  4465 x 1942 x 1273 mm, wheelbase 2704 `[researched]`.

The three pitfalls this example hit and fixed (now documented in the
reference): a tent-peak roof (non-tangent top arc), floating wheels,
and the front arch punching through the hood surface.

```bash
solidsight build model.py --views iso,right,front --stl
solidsight view model.py     # orbit it: a car reads instantly or not at all
```
