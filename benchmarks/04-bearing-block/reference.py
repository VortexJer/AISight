from solidsight import *

W, H, T = 40, 34, 12                       # block envelope
block = box(W, T, H) + box(W + 28, T + 6, 6)   # body + wider/deeper foot
bore = cylinder(h=T + 2, d=22.2).aim("+y").translate(0, T / 2 + 1, 20)
block = block - bore
for sx in (1, -1):
    block = block - parts.hole(5.5, 8, counterbore=(9.5, 4)).translate(
        sx * (W / 2 + 7), 0, 6)
emit(block, name="block")

bearing = parts.bearing("608").aim("+y").translate(0, T / 2 + 3.5, 20)
place(bearing, name="bearing", ghost=True)
