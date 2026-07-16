# Example 05 — assembly (fixed): box + snap lid from example 02 + a card
# standing inside. Zero collisions; report.json pairs[] shows the real
# clearances (card to lid lip, clip to window, lid lip to box wall).
# Build: solidsight build model.py --exploded --slice x=20.45
from solidsight import *

OZ, LID_T = 24, 2.5          # body height / lid plate (from example 02)

body = from_model("../02-snap-box/model.py", "box")
cover = (from_model("../02-snap-box/model.py", "lid")
         .translate(-62, 0, 0)          # undo the print layout offset
         .rotate(x=180)                 # flip lip-down
         .translate(0, 0, OZ + LID_T))  # rest the plate on the box rim

card = box(40, 1.6, 16).translate(0, 5, 2.5)   # top at z=18.5, under the lip

place(body, name="box", color="steel")
place(cover, name="lid", color="amber")
place(card, name="card", color="sage")

# declared intent: the report FAILS if any of these stop holding
expect("lid", "box", status="touching")     # lid plate rests on the rim
expect("card", "box", status="touching")    # card stands on the floor
expect("card", "lid", clearance=0.15)       # must never bind on the clips
