"""Vigia's controller board: a deterministic .kicad_pcb generator.

A small 50 x 40 mm 2-layer board: an MCU (8 pads), two servo headers,
a USB power entry, decoupling, and — the part the rest of the showcase
hangs off — four M3 mounting pads whose POSITIONS are the contract with
the enclosure: solidsight reads them from pcbsight's report and puts
its standoffs exactly there.

Run: python make_board.py   ->  vigia_board.kicad_pcb
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent

W, H = 50.0, 40.0                    # board size, mm
MOUNT = [(4.0, 4.0), (46.0, 4.0), (4.0, 36.0), (46.0, 36.0)]

NETS = {1: "+5V", 2: "GND", 3: "SERVO1_PWM", 4: "SERVO2_PWM",
        5: "USB_P", 6: "USB_N", 7: "XTAL"}


def seg(x1, y1, x2, y2, w, layer, net):
    return (f"  (segment (start {x1} {y1}) (end {x2} {y2}) "
            f"(width {w}) (layer \"{layer}\") (net {net}))")


def via(x, y, net):
    return (f"  (via (at {x} {y}) (size 0.6) (drill 0.3) "
            f"(layers \"F.Cu\" \"B.Cu\") (net {net}))")


def fp(ref, x, y, rot, pads):
    out = [f"  (footprint \"vigia:{ref}\" (at {x} {y} {rot})",
           f"    (property \"Reference\" \"{ref}\" (at 0 -2))"]
    for name, px, py, sx, sy, shape, net, netname, ptype in pads:
        layers = '"*.Cu" "*.Mask"' if ptype == "thru_hole" \
            else '"F.Cu" "F.Mask"'
        netpart = f" (net {net} \"{netname}\")" if net else ""
        out.append(f"    (pad \"{name}\" {ptype} {shape} (at {px} {py}) "
                   f"(size {sx} {sy}) (layers {layers}){netpart})")
    out.append("  )")
    return "\n".join(out)


def build() -> str:
    L = ["(kicad_pcb (version 20240108) (generator vigia)"]
    for nid, name in NETS.items():
        L.append(f"  (net {nid} \"{name}\")")

    # mounting pads: the mechanical contract with the enclosure
    for i, (mx, my) in enumerate(MOUNT, 1):
        L.append(fp(f"H{i}", mx, my, 0, [
            ("1", 0, 0, 5.4, 5.4, "circle", 2, "GND", "thru_hole")]))

    # U1: the MCU, 8 pads, centre of the board
    mcu_pads = []
    for k in range(4):
        y = -4.5 + k * 3.0
        net, nn = [(1, "+5V"), (2, "GND"), (3, "SERVO1_PWM"),
                   (4, "SERVO2_PWM")][k]
        mcu_pads.append((str(k + 1), -3.6, y, 1.6, 1.2, "rect",
                         net, nn, "smd"))
    for k in range(4):
        y = 4.5 - k * 3.0
        net, nn = [(5, "USB_P"), (6, "USB_N"), (7, "XTAL"),
                   (2, "GND")][k]
        mcu_pads.append((str(k + 5), 3.6, y, 1.6, 1.2, "rect",
                         net, nn, "smd"))
    L.append(fp("U1", 25, 20, 0, mcu_pads))

    # J1: USB power entry on the left edge
    L.append(fp("J1", 6, 20, 0, [
        ("1", 0, -3.0, 1.7, 1.7, "circle", 1, "+5V", "thru_hole"),
        ("2", 0, 3.0, 1.7, 1.7, "circle", 2, "GND", "thru_hole"),
        ("3", 2.5, -1.0, 1.0, 1.0, "rect", 5, "USB_P", "smd"),
        ("4", 2.5, 1.0, 1.0, 1.0, "rect", 6, "USB_N", "smd")]))

    # J2/J3: servo headers on the right edge (5V, GND, PWM each)
    for jref, jy, pwm_net, pwm_name in (("J2", 12, 3, "SERVO1_PWM"),
                                        ("J3", 28, 4, "SERVO2_PWM")):
        L.append(fp(jref, 44, jy, 0, [
            ("1", 0, -2.54, 1.7, 1.7, "circle", 1, "+5V", "thru_hole"),
            ("2", 0, 0, 1.7, 1.7, "circle", 2, "GND", "thru_hole"),
            ("3", 0, 2.54, 1.7, 1.7, "circle", pwm_net, pwm_name,
             "thru_hole")]))

    # --- routing ---------------------------------------------------------
    # Three iterations against pcbsight to get here. The rules it taught:
    # thru-hole pads exist on BOTH layers, so a bottom spine may not pass
    # under another net's header pin; and x=44 (the header column) is a
    # no-fly zone for anything that is not that exact pad's net.

    # +5V: J1.1 (6,17) -> U1.1 (21.4,15.5) -> J2.1 -> around J2 -> J3.1
    L.append(seg(6, 17, 6, 12, 1.0, "F.Cu", 1))
    L.append(seg(6, 12, 21.4, 12, 1.0, "F.Cu", 1))
    L.append(seg(21.4, 12, 21.4, 15.5, 1.0, "F.Cu", 1))
    L.append(seg(21.4, 12, 40, 8, 1.0, "F.Cu", 1))
    L.append(seg(40, 8, 44, 9.46, 1.0, "F.Cu", 1))
    L.append(seg(44, 9.46, 48.2, 11, 1.0, "F.Cu", 1))
    L.append(seg(48.2, 11, 48.2, 24, 1.0, "F.Cu", 1))
    L.append(seg(48.2, 24, 44, 25.46, 1.0, "F.Cu", 1))

    # GND: a B.Cu spine at y=32.5 (clear of J3.3 at y30.54), fed by
    # J1.2; headers ground on B.Cu into the mount drops (same net);
    # the MCU's two GND pads drop through their own vias.
    L.append(seg(6, 23, 6, 32.5, 1.0, "F.Cu", 2))
    L.append(via(6, 32.5, 2))
    L.append(seg(6, 32.5, 46, 32.5, 1.0, "B.Cu", 2))
    L.append(seg(4, 32.5, 6, 32.5, 0.8, "B.Cu", 2))
    L.append(seg(4, 4, 4, 32.5, 0.8, "B.Cu", 2))        # H1 + H3 drop
    L.append(seg(4, 36, 4, 32.5, 0.8, "B.Cu", 2))
    L.append(seg(46, 4, 46, 32.5, 0.8, "B.Cu", 2))      # H2 + H4 drop
    L.append(seg(46, 36, 46, 32.5, 0.8, "B.Cu", 2))
    L.append(seg(44, 12, 46, 12, 0.8, "B.Cu", 2))       # J2.2 -> H2 drop
    L.append(seg(44, 28, 46, 28, 0.8, "B.Cu", 2))       # J3.2 -> H2 drop
    L.append(seg(21.4, 18.5, 18, 18.5, 0.5, "F.Cu", 2))  # U1.4
    L.append(via(18, 18.5, 2))
    L.append(seg(18, 18.5, 18, 32.5, 0.5, "B.Cu", 2))
    L.append(seg(28.6, 15.5, 30, 15.5, 0.5, "F.Cu", 2))  # U1.8
    L.append(via(30, 15.5, 2))
    L.append(seg(30, 15.5, 30, 32.5, 0.5, "B.Cu", 2))

    # servo PWM. SERVO1 takes the BOTTOM layer south of the MCU: its
    # old F.Cu loop (x16 up, y34 across, x42 down) fenced J3.3 off and
    # crossed both USB_P and SERVO2 (iteration 3's findings).
    L.append(seg(21.4, 21.5, 19.8, 21.5, 0.3, "F.Cu", 3))
    L.append(via(19.8, 21.5, 3))
    L.append(seg(19.8, 21.5, 19.8, 10, 0.3, "B.Cu", 3))
    L.append(seg(19.8, 10, 41, 10, 0.3, "B.Cu", 3))
    L.append(via(41, 10, 3))
    L.append(seg(41, 10, 42.5, 13, 0.3, "F.Cu", 3))
    L.append(seg(42.5, 13, 44, 14.54, 0.3, "F.Cu", 3))  # J2.3
    L.append(seg(21.4, 24.5, 24, 26.5, 0.3, "F.Cu", 4))
    L.append(seg(24, 26.5, 38, 26.5, 0.3, "F.Cu", 4))
    L.append(seg(38, 26.5, 44, 30.54, 0.3, "F.Cu", 4))  # J3.3

    # USB pair. v1 swapped the ends AND crossed the traces; v2 ran N
    # through a SERVO pad and P through the other; v4 threads P at
    # y=23.2 (between the pad rows) and dives to B.Cu to cross N.
    L.append(seg(28.6, 24.5, 27.4, 23.2, 0.25, "F.Cu", 5))
    L.append(seg(27.4, 23.2, 13, 23.2, 0.25, "F.Cu", 5))
    L.append(via(13, 23.2, 5))
    L.append(seg(13, 23.2, 10, 19, 0.25, "B.Cu", 5))
    L.append(via(10, 19, 5))
    L.append(seg(10, 19, 8.5, 19, 0.25, "F.Cu", 5))
    # N is 2.2 mm shorter than P; the serpentine at x16-18 length-
    # matches the pair (pcbsight measured the skew, the jog repays it)
    L.append(seg(28.6, 21.5, 27, 20.3, 0.25, "F.Cu", 6))
    L.append(seg(27, 20.3, 18, 20.3, 0.25, "F.Cu", 6))
    L.append(seg(18, 20.3, 18, 19.2, 0.25, "F.Cu", 6))
    L.append(seg(18, 19.2, 16, 19.2, 0.25, "F.Cu", 6))
    L.append(seg(16, 19.2, 16, 20.3, 0.25, "F.Cu", 6))
    L.append(seg(16, 20.3, 10.5, 20.3, 0.25, "F.Cu", 6))
    L.append(seg(10.5, 20.3, 8.5, 21, 0.25, "F.Cu", 6))

    # XTAL stub: U1.7 (28.6, 18.5) -> a short trace
    L.append(seg(28.6, 18.5, 33, 18.5, 0.25, "F.Cu", 7))

    L.append(")")
    return "\n".join(x for x in L if x) + "\n"


if __name__ == "__main__":
    (HERE / "vigia_board.kicad_pcb").write_text(build(), encoding="utf-8")
    print(f"vigia_board.kicad_pcb: {W}x{H} mm, mounts at {MOUNT}")
