# Vigia — a desk robot, the AISight showcase.
#
# bill of parts (mm):
#   body      78 x 62 x 42 shell, wall 2.4: standoffs AT THE BOARD'S OWN
#             mount positions (read from vigia_board.kicad_pcb through
#             pcbsight), USB window aligned to the board's J1, side
#             shaft holes for the arms, vented floor
#   head      52 dome on a 22 neck, engraved eye ring
#   arm_l/r   34 x 14 paddles on 5 mm servo shafts
#   ghosts    the PCB (real outline + 8 mm component envelope) and two
#             micro servos: measured in pairs[], never printed
from solidsight import *
from params import *

# ---- body -----------------------------------------------------------------
profile = rect(CASE_X, CASE_Y).round_corners(8)
body = parts.container(profile, CASE_Z, wall=WALL, floor=FLOOR)

for bx, by in MOUNTS:
    cx, cy = board_to_case(bx, by)
    body = body + parts.standoff(h=STANDOFF_H, od=6.0, id_=2.4) \
        .translate(cx, cy, FLOOR - 0.5)

# USB window in the -X wall, centred on the board's J1 column
_ux, _uy = board_to_case(0.0, USB_Y)
usb = box(WALL + 2, 13, 7)
body = body - usb.translate(-CASE_X / 2 + WALL / 2, 0.0,
                            FLOOR + STANDOFF_H + BOARD_T + 3.5)

# arm shaft holes through the side walls at x=+18 (the arm column;
# v1 also drilled an unused pair at x=-18 - dust holes, deleted)
SHAFT_Z = 26.0
shaft_hole = cylinder(h=WALL + 2, d=SHAFT_D + 0.5).aim("+y")
body = body - shaft_hole.translate(18, CASE_Y / 2 + 1, SHAFT_Z)             - shaft_hole.rotate(z=180).translate(18, -CASE_Y / 2 - 1,
                                                 SHAFT_Z)

# vent the floor under the board (hex, like every case that breathes)
body = body - parts.hex_grid(40, 26, FLOOR + 2, cell=6, wall=1.8) \
    .translate(0, 0, -1)

# roof + neck seat. v2's seat ring floated over the container's OPEN
# top ("body is 2 disconnected pieces"). The roof closes the shell with
# the neck bore through it; the ring overlaps 0.5 into the roof.
roof = profile.extrude(2.4) - cylinder(h=4.4, d=NECK_D + 0.6)     .translate(0, 0, -1)
body = body + roof.translate(0, 0, CASE_Z - 2.2)
body = body + (cylinder(h=4.5, d=NECK_D + 8)
               - cylinder(h=6.5, d=NECK_D + 0.6).translate(0, 0, -1))     .translate(0, 0, CASE_Z - 0.3)

emit(body, name="body", color="steel",
     features=[{"type": "standoff_pattern", "source": "vigia_board",
                "at": [list(board_to_case(*m)) for m in MOUNTS]},
               {"type": "usb_window", "aligned_to": "J1"}])

# ---- head -----------------------------------------------------------------
dome = sphere(d=DOME_D) & box(DOME_D + 2, DOME_D + 2, DOME_D / 2 + 1) \
    .translate(0, 0, DOME_D / 4)
dome = dome.translate(0, 0, NECK_H - DOME_D / 4 + 2)
neck = cylinder(h=NECK_H + 4, d=NECK_D)   # overlaps the dome
head = neck + dome
# the eye: an engraved ring + pupil on the -X face
eye = (torus(r_ring=8, r_tube=1.25)
       + cylinder(h=3, d=6)).rotate(y=-90) \
    .translate(-DOME_D / 2 + 3.5, 0, NECK_H + DOME_D / 5)
head = head - eye
head = head.translate(0, 0, CASE_Z + 3.0)
emit(head, name="head", color="light",
     features=[{"type": "eye", "d": 16}])

# ---- arms -----------------------------------------------------------------
def arm() -> Solid:
    paddle = rect(ARM_L, ARM_W).round_corners(6).extrude(ARM_T)
    hub = cylinder(h=10, d=12)
    shaft = cylinder(h=8, d=SHAFT_D)
    a = paddle.translate(ARM_L / 2 - 8, 0, 0) + hub + \
        shaft.translate(0, 0, -7.5)
    return a.rotate(x=90)                     # shaft along -Y -> +Y

arm_l = arm().rotate(z=180).translate(18, CASE_Y / 2 + 6, SHAFT_Z)
arm_r = arm().translate(18, -CASE_Y / 2 - 6, SHAFT_Z)
emit(arm_l, name="arm_l", color="clay")
emit(arm_r, name="arm_r", color="clay")

# ---- the bought/other-tool parts, as ghosts -------------------------------
# v1 wrapped the whole board in a blanket 8 mm envelope and stood the
# servos where the servo HEADERS are (board x=44 -> case x=19): the
# report flagged every contact with exact overlap boxes. The envelope
# is now honest - a tall strip over the headers, a low block over the
# MCU - and the servos lie LENGTHWISE on the empty left side
# (32.2 mm long, measured: two of them do not fit across the
# case, which iteration 4 proved by collision).
pcb = box(BOARD_W, BOARD_H, BOARD_T)     + box(8, 36, 10).translate(BOARD_W / 2 - 6, 0, BOARD_T - 0.2)     + box(10, 10, 4).translate(0, 0, BOARD_T - 0.2)
place(pcb, name="pcb", at=(0, 0, FLOOR + STANDOFF_H - 0.5),
      ghost=True)   # standoffs sink 0.5 into the floor

servo = parts.micro_servo()
place(servo, name="servo_l", at=(-20, 12, 9.0), ghost=True)
place(servo, name="servo_r", at=(-20, -12, 9.0), ghost=True)

# ---- declared relations ---------------------------------------------------
expect("pcb", "body", status="touching")          # it SITS on the standoffs
expect("head", "body", status="clear", clearance=(0.2, 1.0))
expect("arm_l", "body", status="clear", clearance=(0.1, 2.0))
expect("arm_r", "body", status="clear", clearance=(0.1, 2.0))
expect("servo_l", "pcb", status="clear", clearance=(0.2, 30.0))
expect("servo_r", "pcb", status="clear", clearance=(0.2, 30.0))

# ---- robot description ----------------------------------------------------
joint("body", "head", type="revolute", name="head_pan",
      origin=(0, 0, CASE_Z + 4), axis=(0, 0, 1), limits=(-120, 120))
joint("body", "arm_l", type="revolute", name="arm_l_pitch",
      origin=(18, CASE_Y / 2 + 6, SHAFT_Z), axis=(0, 1, 0),
      limits=(-40, 100))
joint("body", "arm_r", type="revolute", name="arm_r_pitch",
      origin=(18, -CASE_Y / 2 - 6, SHAFT_Z), axis=(0, 1, 0),
      limits=(-40, 100))
# the electronics ride the body rigidly - and the URDF wants ONE tree
joint("body", "pcb", type="fixed")
joint("body", "servo_l", type="fixed")
joint("body", "servo_r", type="fixed")
