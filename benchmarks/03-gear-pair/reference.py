from solidsight import *

m, z = 2, 20
gear = parts.spur_gear(m, z, 8, bore=6, backlash=0.2)
emit(gear, name="gear_a")
# meshed: center distance = module * z; half-tooth angular offset
emit(gear.rotate(z=360 / z / 2).translate(m * z, 0, 0), name="gear_b")
