---
name: pcbsight
description: "Use whenever the user asks to review, check or validate a PCB layout (.kicad_pcb) — unrouted nets, clearance violations, trace current capacity, differential pair symmetry, impedance estimates. You cannot eyeball copper; this tool turns the board into exact findings with coordinates."
---

# /pcbsight

A layout is judged by eyeballing the copper. But an open net is a
union-find question, a clearance is a segment distance, current capacity
is IPC-2221 arithmetic, and pair skew is a subtraction. So compute them,
with coordinates.

## Usage

```
pcbsight inspect board.kicad_pcb                  # the audit
pcbsight inspect board.kicad_pcb --clearance 0.15 # YOUR fab's minimum
pcbsight inspect board.kicad_pcb --dt 20          # allowed temp rise, C
pcbsight inspect board.kicad_pcb --out DIR --json
pcbsight impedance 0.3 0.2 --er 4.5               # microstrip Z0 estimate
pcbsight diff before.kicad_pcb after.kicad_pcb    # what the fix changed (proof)
pcbsight version
```

Exit codes: 0 ok, 1 bad input, 2 a FAIL-level finding.

## What You Must Do When Invoked

### Step 0 - Install

```bash
pcbsight version || pip install "git+https://github.com/VortexJer/AISight#subdirectory=pcbsight"
```

### Step 1 - Set the rules to the REAL ones

`--clearance 0.2` is a common fab minimum, not a law. Ask which fab /
class applies, or state that 0.2 was assumed. Same for `--dt`: 10 C is
conservative; power electronics often accept 20-30.

### Step 2 - Read the checks

| id | level | means |
|---|---|---|
| `net-open` | FAIL | the net's copper forms 2+ islands: it is not routed. The unconnected pads are named. A board with an open net does not work. |
| `clearance` | FAIL/warn | copper of different nets closer than the rule. FAIL below 50 % of spec (short risk after etch), warn above. Coordinates given. |
| `diff-pair-width` | warn | a pair mixing widths: differential impedance is no longer constant. |
| `diff-pair-skew` | warn | length mismatch, in mm and ~ps (6.6 ps/mm on FR4). Matters above ~100 MHz. |

And the always-on measurements:
- **connectivity** per net: islands, tracks, pads, total copper length.
- **current capacity** per net (IPC-2221, at the net's NARROWEST track,
  external-layer curve unless the net is fully internal): quote the
  amps together with the dT they assume.
- **diff pairs** found by net name (`*_P/_N`, `+/-`): lengths, skew,
  widths.

### Step 3 - LOOK at board.png

Copper as drawn (front/back coloured, pads, vias), clearance findings
circled in red with the measured gap. An open net is usually VISIBLE
there as a trace that stops short — the render is the fastest way to
see which fix is right.

### Step 4 - Prove the fix

After editing the board in KiCad, `pcbsight diff before.kicad_pcb
after.kicad_pcb`: islands per net, clearance findings, current at the
narrowest width, pair skew, and findings NEW/GONE. A fix without a diff
is a claim; with one it is a fact.

### Step 5 - Interpret honestly

- **Current numbers are IPC-2221**, computed at the narrowest point of
  the net. They assume the trace heats alone in still air; planes,
  pours and vias change the real number. Quote the assumption.
- **The impedance command is an IPC-2141 estimate** (~10 %): fine for
  "is this trace roughly 50 ohm", not for controlled-impedance signoff
  — that needs the fab's field-solved stackup.
- **What is NOT checked, say so**: zones/pours (a net routed only
  through a pour will read as open — check the board in KiCad if pours
  carry nets), thermal relief, creepage for mains voltages, EMI. This
  tool complements the EDA package's own DRC; it does not replace it.

## Honesty Rules

- Every clearance claim carries its coordinates; every current claim
  carries its dT and copper weight. No naked numbers.
- The clearance rule and stackup used are stated in the report - if
  they were assumed, say assumed.
- A review is not done until you have LOOKED at board.png.
- Never sign off "the board is fine": say which checks ran, with which
  rules, and what they found.

## Scope

Reads: .kicad_pcb (KiCad 6/7/8) - nets, segments, vias, footprint pads
(with placement composed through footprint rotation).
Does NOT read: zones/pours, arcs, curved traces, keepouts, mask/paste.
Does NOT do: autorouting, schematic review, EMI simulation, thermal
simulation.

Siblings, same philosophy: `solidsight` (geometry - including the
board's enclosure: export the outline and check the fit there),
`animationsight` (motion), `texturesight` (UVs), `shadersight`
(materials).
