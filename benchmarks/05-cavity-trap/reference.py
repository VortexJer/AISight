from solidsight import *

body = sphere(d=30)
chamber = sphere(d=22)
emit(body - chamber, name="float")
