# shadersight

**Shader review built exclusively for AI agents.** A material or a node
graph in; physics verdicts, graph analysis and exact numbers out.

A shader is judged by rendering a sphere and squinting. But what is
actually *wrong* with a material is physics — laws, not opinions:

- **energy conservation** — a passive surface must not reflect more
  light than it receives (the white furnace test, swept over view
  angles because grazing is where materials cheat);
- **Helmholtz reciprocity** — `f(wi, wo) == f(wo, wi)`, always;
- **positivity** — a BRDF is never negative.

All three are integrals and identities over the hemisphere. So compute
them. And a node graph's problems are graph theory: cycles, dead nodes,
per-pixel cost.

```bash
pip install "git+https://github.com/VortexJer/AISight#subdirectory=shadersight"

shadersight material --base-color 0.7,0.4,0.15 --roughness 0.35 --metallic 1
# -> energy: max albedo 0.72 at 85 deg -> CONSERVES (grid 64x128, 12 views)
# -> reciprocity: max rel error 0.0 -> OK
# -> out/albedo_curve.png (the verdict, plotted against the 1.0 ceiling)
# -> out/preview.png      (the human-facing sphere)

shadersight graph shader_graph.json
# -> [FAIL] 2 node(s) form a feedback cycle: nodes: mul, add
# -> [WARN] 2 node(s) do not reach the output
# -> cost: ~340 ALU-equiv/pixel, 3 texture fetch(es)
```

Everything is deterministic (fixed-seed sampling; the resolution is in
the report, because a physics claim without its resolution is not a
claim).

## Proof it works

The tests hold the tool to the laws, in both directions:

- GGX's normal distribution integrates to 1 over the hemisphere
  (checked numerically, not trusted).
- A smooth white metal mirror measures albedo **1.00 at every angle** —
  the case a naive uniform-grid integrator gets catastrophically wrong
  (it read 0.02 or 1.19 depending only on resolution; the tool uses
  multiple importance sampling precisely because its own first
  integrator failed this test).
- A hacked material that reflects 3x its input is **FAILED** at 2.70.
- A material with a view-dependent asymmetric term is caught by the
  reciprocity check.
- The clean example graph reports zero findings; the broken one (cycle,
  dead branch, dangling reference — all by construction) reports
  exactly those three.

## A bug this tool found in its own reference material

The first version coupled diffuse and specular the way most engines do:
`Lambert * (1 - F) + GGX`. shadersight measured **its own material at
1.478x the energy ceiling at 85°** — the naive coupling genuinely
violates conservation at grazing angles, where the specular reflects
nearly everything while the diffuse lobe keeps contributing. The
reference now uses Ashikhmin-Shirley coupled diffuse (reciprocal,
rolls off toward grazing) and sweeps under 1.0 across the whole
roughness x metallic x angle space, asserted in
`test_physical_materials_conserve_energy`.

That defect ships in real engines. Now there is a number for it.

## Honest limitations

- The material model is standard metallic-roughness PBR — the model
  ~90 % of real shaders are. It does not parse GLSL/HLSL.
- Energy *loss* at high roughness is reported as a warning and labelled
  what it is: the known single-scattering GGX deficit, not a defect.
- The cost model is orders of magnitude (a fetch ~100x an add), counted
  over live nodes only. It compares graphs; it does not predict frame
  time on hardware it has never seen.

Siblings, same philosophy: [solidsight](../README.md) (geometry),
[animationsight](../animationsight/README.md) (motion),
[texturesight](../texturesight/README.md) (UVs/textures).

## License

MIT
