# Domain playbooks

One file per domain, each a complete working method: the numbers you may
assume, the build order that works, the recipes, the specific ways that
domain fails, and what "done" means there.

**Load the ONE that matches the request** (two if it genuinely spans
both — a robot in a printed case is `mechanisms` + `enclosures`). They
are written to be read in full when they apply, and never otherwise.

| file | load it for |
|---|---|
| `enclosures.md` | project boxes, PCB housings, brackets, jigs, wall mounts, adapters |
| `mechanisms.md` | gearboxes, linkages, robot joints, drivetrains, anything that moves |
| `product-design.md` | handheld devices, appliances, grips, consumer shells, ergonomics |
| `furniture.md` | tables, shelves, chairs, frames, T-slot machine frames, joinery |
| `architecture.md` | buildings, rooms, floor plans, site massing, interiors |
| `vehicles.md` | cars, bikes, boats, hulls, aircraft, drones, rockets |
| `organic.md` | vases, sculpture, characters, creatures, props, twisted/flowing forms |
| `terrain.md` | landscapes, heightmaps, topographic models, procedural scatter |
| `jewelry-miniatures.md` | rings, pendants, tabletop miniatures, scale models |
| `game-ready.md` | assets for a game engine / real-time renderer (GLB, budgets, LODs) |
| `toys.md` | toys, puzzles, board-game inserts, game pieces (safety standards) |
| `scientific.md` | molecules, lab fixtures, data made physical, teaching aids |

Nothing here overrides the core loop in `SKILL.md` (bill of parts ->
catalog -> build -> LOOK -> measure -> adjust) or the honesty rules.
A playbook tells you WHAT to build and what to check; the loop is how
you find out whether you did.
