"""Vigia's shared datums — including the ones it does NOT own.

The board's mounting positions and connector locations belong to the
BOARD, so they are read from vigia_board.kicad_pcb through pcbsight's
parser instead of being copied by hand. Change the board, rebuild the
case, and the standoffs follow. Two tools, one contract.
"""

from pathlib import Path

from pcbsight import parse_board

_BOARD = parse_board(Path(__file__).parents[1] / "board"
                     / "vigia_board.kicad_pcb")

# board footprint (mm) and its mount pads, in board coordinates
BOARD_W = 50.0
BOARD_H = 40.0
BOARD_T = 1.6
MOUNTS = sorted((p.at for p in _BOARD.pads if p.ref.startswith("H")))
USB_Y = next(p.at[1] for p in _BOARD.pads
             if p.ref == "J1" and p.name == "1")   # J1 column, board y

# case: the board sits centred, components up, on 5 mm standoffs
WALL = 2.4
FLOOR = 2.0
CASE_X, CASE_Y, CASE_Z = 78.0, 62.0, 42.0
STANDOFF_H = 5.0

def board_to_case(bx: float, by: float) -> tuple[float, float]:
    """Board coords (origin at its corner) -> case coords (origin at
    the case centre)."""
    return bx - BOARD_W / 2.0, by - BOARD_H / 2.0

# head + arms
NECK_D, NECK_H = 22.0, 8.0
DOME_D = 52.0
ARM_L, ARM_W, ARM_T = 34.0, 14.0, 5.0
SHAFT_D = 5.0                        # servo output shaft
