# solidsight benchmarks

Graded, deterministic design commissions for evaluating agents (or the
tool itself). Each directory holds the `prompt.md` an agent receives,
a `reference.py` proving the expectations are satisfiable, and
machine-checkable `expectations.json`.

| # | benchmark | level | exercises |
|---|---|---|---|
| 01 | washer | beginner | exact standard dims, print-safe |
| 02 | vented-box | easy | containers, cutters, plate layout, pair clearance |
| 03 | gear-pair | medium | catalog gears, meshing, measured backlash |
| 04 | bearing-block | hard | real component fit, ghost references, walls |
| 05 | cavity-trap | hard | INTENTIONAL sealed cavity, proving internals |
| 06 | engine-lite | expert | multi-feature interactions without paper walls |

Self-test all references:

    solidsight bench run --dir benchmarks

Grade an agent solution against one benchmark:

    solidsight bench run 03-gear-pair --dir benchmarks --solution my.py
