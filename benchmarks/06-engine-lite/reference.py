from solidsight import *

BORE, PITCH, DECK = 30.0, 45.0, 80.0
block = box(100, 60, DECK)

# crankcase, open to the bottom
block = block - box(84, 44, 37).translate(0, 0, -1)

# crank tunnel
block = block - cylinder(h=102, d=26).aim("+x").translate(51, 0, 18)

# bores, open into the crankcase
for cx in (-PITCH / 2, PITCH / 2):
    block = block - cylinder(h=60, d=BORE).translate(cx, 0, 25)

# water jacket: annulus around the bank, vented to the deck by 4 holes
bank = [(-PITCH / 2, 0), (PITCH / 2, 0)]
jacket = stroke(bank, BORE + 12) - stroke(bank, BORE + 6)
block = block - jacket.extrude(25).translate(0, 0, DECK - 24)
for cx in (-PITCH / 2, PITCH / 2):
    for sy in (1, -1):
        block = block - cylinder(h=30, d=5).translate(
            cx, sy * (BORE / 2 + 4.5), DECK - 25)

# head bolts: blind, safely above the jacket floor
head_bolt = parts.hole(6.8, 10, chamfer=0.5)
for hx in (-42, 42):
    for hy in (-22, 22):
        block = block - head_bolt.translate(hx, hy, DECK)

emit(block, name="block")
