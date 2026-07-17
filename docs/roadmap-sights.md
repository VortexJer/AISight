# The *Sight family

The solidsight philosophy — the agent is blind; give it exact numbers
instead of pictures, and renders only as evidence for what the numbers
found — applied to four more domains where software was built for human
eyes.

This document used to be the honest scoping of tools that did not exist.
They exist now, each in its own sibling package in this repo, each with
its own CLI, Claude Code skill (self-installing), synthetic
known-ground-truth examples and regression tests in both directions
(every injected defect found, every clean reference clean).

| tool | replaces | the measurements |
|---|---|---|
| [`animationsight/`](../animationsight) | watching a clip | BVH + FK: velocity/accel/jerk, angular rates, contacts, foot sliding, balance vs support, floor penetration, pops, loop seams |
| [`texturesight/`](../texturesight) | squinting at a checker | texel density, UV-Jacobian stretch, islands/seams counted from topology, packing/overlap, tiling vs the texture's own statistics, normal-map validity, data-map range |
| [`shadersight/`](../shadersight) | rendering a sphere | energy conservation by MIS over the hemisphere, Helmholtz reciprocity, positivity, node-graph cycles/dead-nodes/cost |
| [`pcbsight/`](../pcbsight) | eyeballing copper | net connectivity by union-find, exact clearances with coordinates, IPC-2221 current at the narrowest track, diff-pair skew, microstrip Z0 |

Install any of them:

```bash
pip install "git+https://github.com/VortexJer/AISight#subdirectory=animationsight"   # or texturesight / shadersight / pcbsight
```

## What "built" means here

Each tool holds itself to the standard set by solidsight's dogfooding:

- **Known ground truth.** Every example is synthetic on purpose, with
  defects injected at exact magnitudes, so the tests assert the *right*
  answer, not merely *an* answer — and assert the clean reference stays
  clean, because false positives are how a tool loses the right to be
  believed.
- **Findings carry `where` and `try:`**, coordinates and frames
  included; assumptions (clearance class, dT, integration grid, texture
  size) are stated inside the report.
- **Deterministic**: same input, byte-identical report; fixed seeds
  where sampling is involved, with the resolution reported.
- **Self-hosting skills**: the first CLI run installs the Claude Code
  skill; `<tool> uninstall` removes skill and package together.
- **Scope stated, not implied**: each README lists what is NOT read or
  checked (pours in pcbsight, GLSL in shadersight, rigging in
  animationsight, unwrapping in texturesight).

## Bugs the tools caught in their own references

The pattern that keeps recurring — and the reason the family exists:
every one of these was invisible to inspection and obvious to
measurement.

- animationsight: the first synthetic walk never planted a foot
  (sinusoids moonwalk); the floor estimate let a penetration defect
  define the floor and hide itself.
- texturesight: a transposed matrix reported conformal UVs as 2.6:1
  stretched; one-axis blocking accused posterised maps of being JPEGs;
  repetition warned on every correctly tiling texture.
- shadersight: a uniform-grid integrator read a mirror's albedo as 0.02
  or 1.19 depending only on resolution; the naive Lambert*(1-F)+GGX
  coupling measured ITSELF at 1.478x the energy ceiling at grazing.
- pcbsight: the first "clean" board routed +5V through two pads
  (flagged at 0.0 mm); diff pairs were reported once per matching
  suffix rule.

## Still future

- animationsight: glTF animation clips, IK-chain validation, per-frame
  mesh contact (needs the solidsight kernel).
- texturesight: per-texel overlap (a real rasterizer), UDIM sets,
  mipmap-chain audits.
- shadersight: GLSL/HLSL subset parsing into the graph model,
  multi-scatter reference curves, anisotropic BRDFs.
- pcbsight: zones/pours (the big one — nets routed through pours),
  arcs, courtyard checks against the solidsight enclosure directly.
