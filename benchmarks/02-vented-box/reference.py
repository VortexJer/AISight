from solidsight import *

shell_box = parts.container(rect(60, 40), 25, wall=2)
vents = parts.hex_grid(46, 26, 4, cell=8, wall=2.4).translate(0, 0, -1)
shell_box = shell_box - vents
emit(shell_box, name="box")

lid = rect(60, 40).round_corners(2).extrude(2.4)
emit(lid.translate(75, 0, 0), name="lid")
