# 04-bearing-block (hard)

A printable pillow block for a 608 bearing (22 mm OD x 7 mm wide): a
standing block with a horizontal 22.1..22.3 mm bore, two M5 base
mounting holes, everything >= 2 mm walls. Emit the block as `block` and
place the REAL bearing as a ghost reference named `bearing` seated in
the bore (use parts.bearing("608") and place(..., ghost=True)). The
ghost pair must measure nearly seated (clearance <= 0.2 mm), and the
block alone must pass --print-safe with --min-wall 2.
