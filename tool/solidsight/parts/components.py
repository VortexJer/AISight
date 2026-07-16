"""Real-world engineering components: fasteners, bearings, motion parts,
framing. All parametric, all deterministic.

Geometry level is stated per part: EXACT means faithful to the standard's
functional dimensions; REPRESENTATIVE means correct envelope + mounting
interfaces (what an assembly needs) with simplified cosmetic detail.
Motors, bearings and rails are usually placed as ghost reference parts
(`place(..., ghost=True)`) — they get bought, not printed.
"""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import Solid, box, cylinder, prism, union
from .threads import iso_thread


# ISO 7089 flat washers: d -> (inner, outer, thickness)
WASHER_DIMS = {2: (2.2, 5, 0.3), 2.5: (2.7, 6, 0.5), 3: (3.2, 7, 0.5),
               4: (4.3, 9, 0.8), 5: (5.3, 10, 1.0), 6: (6.4, 12, 1.6),
               8: (8.4, 16, 1.6), 10: (10.5, 20, 2.0), 12: (13, 24, 2.5)}

# common deep-groove ball bearings: name -> (bore, outer, width)
BEARING_DIMS = {"608": (8, 22, 7), "623": (3, 10, 4), "624": (4, 13, 5),
                "625": (5, 16, 5), "626": (6, 19, 6), "688": (8, 16, 5),
                "6000": (10, 26, 8), "6001": (12, 28, 8),
                "6201": (12, 32, 10), "6802": (15, 24, 5)}

# NEMA stepper motors: size -> (faceplate, boss_d, boss_h, shaft_d,
#                               shaft_len, hole_pitch, hole_d)
NEMA_DIMS = {14: (35.2, 22, 2.0, 5, 24, 26.0, 3.0),
             17: (42.3, 22, 2.0, 5, 24, 31.0, 3.0),
             23: (57.2, 38.1, 1.6, 6.35, 21, 47.14, 5.0)}


# ISO 4762 socket head cap screws: m -> (head_d, head_h, socket_af)
CAP_HEAD = {2: (3.8, 2, 1.5), 2.5: (4.5, 2.5, 2.0), 3: (5.5, 3, 2.5),
            4: (7.0, 4, 3.0), 5: (8.5, 5, 4.0), 6: (10.0, 6, 5.0),
            8: (13.0, 8, 6.0), 10: (16.0, 10, 8.0), 12: (18.0, 12, 10.0)}


def cap_screw(m: float, length: float, segments: int = 32) -> Solid:
    """ISO 4762 socket-head cap screw (EXACT head/thread dimensions). The
    shank runs Z=0..length, the cylindrical head sits on top with its hex
    socket cut in.

        s = parts.cap_screw(4, 16)     # M4x16 SHCS
    """
    if m not in CAP_HEAD:
        raise BadArgumentError(
            f"no ISO 4762 data for M{fmt_num(m)}",
            suggestion="sizes: " + ", ".join(f"M{k:g}" for k in CAP_HEAD))
    head_d, head_h, af = CAP_HEAD[m]
    shank = iso_thread(m, length, segments=segments)
    head = cylinder(h=head_h, d=head_d).translate(0, 0, length)
    socket = prism(6, h=head_h * 0.6 + 1, across_flats=af).translate(
        0, 0, length + head_h * 0.4)
    return (union(shank, head) - socket).describe(
        f"cap_screw(M{m:g}x{fmt_num(length)})")


def washer(m: float, t: float | None = None) -> Solid:
    """ISO 7089 flat washer for an M<m> bolt (EXACT). Sits on Z=0.

        stack = parts.washer(5)          # 5.3 id, 10 od, 1.0 thick
    """
    if m not in WASHER_DIMS:
        raise BadArgumentError(
            f"no ISO 7089 washer for M{fmt_num(m)}",
            suggestion="sizes: " + ", ".join(f"M{k:g}" for k in WASHER_DIMS))
    d_in, d_out, thick = WASHER_DIMS[m]
    t = t if t is not None else thick
    return (cylinder(h=t, d=d_out) - cylinder(h=t + 2, d=d_in)
            .translate(0, 0, -1)).describe(f"washer(M{m:g})")


def bearing(name: str = "608") -> Solid:
    """Deep-groove ball bearing (REPRESENTATIVE: exact bore/OD/width and
    ring sections; the ball row is a solid web). Axis +Z, base on Z=0.
    Place as a ghost reference part in assemblies, or print the envelope.

        b = parts.bearing("608")     # the skateboard/printer classic
    """
    if name not in BEARING_DIMS:
        raise BadArgumentError(
            f"unknown bearing {name!r}",
            suggestion="available: " + ", ".join(sorted(BEARING_DIMS)))
    bore, od, w = BEARING_DIMS[name]
    ring_wall = (od - bore) / 2 * 0.30
    outer = (cylinder(h=w, d=od)
             - cylinder(h=w + 2, d=od - 2 * ring_wall).translate(0, 0, -1))
    inner = (cylinder(h=w, d=bore + 2 * ring_wall)
             - cylinder(h=w + 2, d=bore).translate(0, 0, -1))
    web_d1 = od - 2 * ring_wall + 0.2
    web_d2 = bore + 2 * ring_wall - 0.2
    web = (cylinder(h=w * 0.4, d=web_d1)
           - cylinder(h=w, d=web_d2).translate(0, 0, -0.3)
           ).translate(0, 0, w * 0.3)
    return union(outer, inner, web).describe(f"bearing({name})")


def shaft(d: float, length: float, flat: float | None = None,
          circlip_grooves: list[float] | None = None,
          segments: int = 64) -> Solid:
    """Round shaft along +Z from Z=0 (EXACT). flat=depth mills a D-flat over
    the top third (set screws). circlip_grooves: list of Z positions for
    DIN 471-style grooves (width 1.1, depth 0.55).

        s = parts.shaft(5, 60, flat=0.5)             # NEMA17-style D-shaft
    """
    if d <= 0 or length <= 0:
        raise BadArgumentError("shaft() needs positive d and length")
    s = cylinder(h=length, d=d, segments=segments)
    if flat is not None:
        cut = box(d, d, length / 3 + 1).translate(
            0, d - flat, length * 5 / 6)
        s = s - cut
    for z in (circlip_grooves or []):
        groove = (cylinder(h=1.1, d=d + 2)
                  - cylinder(h=3, d=d - 1.1).translate(0, 0, -1))
        s = s - groove.translate(0, 0, z)
    return s.describe(f"shaft(d{fmt_num(d)}x{fmt_num(length)})")


def timing_pulley(teeth: int = 20, belt: str = "GT2", width: float = 7.0,
                  bore: float = 5.0, flanges: bool = True) -> Solid:
    """Timing-belt pulley (REPRESENTATIVE: exact pitch diameter and tooth
    count; tooth form is a round-groove approximation of the GT2 profile).
    Axis +Z, base on Z=0. GT2 pitch 2 mm.

        p = parts.timing_pulley(20, bore=5)   # the 3D-printer classic
    """
    pitch = {"GT2": 2.0, "GT3": 3.0}.get(belt)
    if pitch is None:
        raise BadArgumentError(f"unknown belt {belt!r}",
                               suggestion="belt='GT2' or 'GT3'")
    if teeth < 10:
        raise BadArgumentError("timing_pulley() needs at least 10 teeth")
    pd = teeth * pitch / math.pi                # pitch diameter
    flange_h = 1.0 if flanges else 0.0
    z0 = flange_h                               # tooth zone starts here
    body = cylinder(h=width, d=pd - 0.5, segments=teeth * 4).translate(
        0, 0, z0)
    groove_d = pitch * 0.55
    cutters = []
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        cutters.append(
            cylinder(h=width + 2, d=groove_d, segments=12).translate(
                (pd / 2) * math.cos(a), (pd / 2) * math.sin(a), z0 - 1))
    body = body - union(*cutters)
    if flanges:
        body = union(body,
                     cylinder(h=flange_h + 0.1, d=pd + 3),
                     cylinder(h=flange_h + 0.1, d=pd + 3).translate(
                         0, 0, z0 + width - 0.1))
    total = width + 2 * flange_h
    body = body - cylinder(h=total + 2, d=bore).translate(0, 0, -1)
    return body.describe(f"timing_pulley({teeth}T {belt})")


def spring(d: float = 10.0, wire: float = 1.2, length: float = 25.0,
           coils: int = 8) -> Solid:
    """Helical compression spring (REPRESENTATIVE; printable in flexibles,
    otherwise a reference part). Axis +Z from Z=0.

        s = parts.spring(d=12, wire=1.6, length=30, coils=7)
    """
    if coils < 2 or length <= wire * coils:
        raise BadArgumentError(
            "spring() needs coils >= 2 and length > wire*coils",
            suggestion="a solid-stacked spring has length = wire*coils")
    from .paths import tube_path
    r = (d - wire) / 2
    pts = []
    steps_per_coil = 16
    total = coils * steps_per_coil
    for i in range(total + 1):
        a = 2 * math.pi * i / steps_per_coil
        z = wire / 2 + (length - wire) * i / total
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return tube_path(pts, d=wire).describe(
        f"spring(d{fmt_num(d)} L{fmt_num(length)})")


def nema_motor(size: int = 17, length: float = 40.0,
               shaft_flat: bool = True) -> Solid:
    """NEMA stepper motor (REPRESENTATIVE: exact faceplate, mounting holes,
    boss and shaft; body detail simplified). Mounting face ON Z=0, body
    below (-Z), boss and shaft above. Mount holes are REAL through-holes.
    Usually placed as a ghost reference: place(parts.nema_motor(17),
    ghost=True).

        m = parts.nema_motor(17, length=40)
    """
    if size not in NEMA_DIMS:
        raise BadArgumentError(f"unknown NEMA size {size}",
                               suggestion="sizes: 14, 17, 23")
    face, boss_d, boss_h, shaft_d, shaft_len, pitch, hole_d = NEMA_DIMS[size]
    body = box(face, face, length, center=True).translate(0, 0, -length / 2)
    corner = box(6, 6, length + 2, center=True).rotate(z=45)
    half = face / 2
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        body = body - corner.translate(sx * half, sy * half,
                                       -length / 2)
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        hole_c = cylinder(h=8, d=hole_d).translate(
            sx * pitch / 2, sy * pitch / 2, -6)
        body = body - hole_c
    boss = cylinder(h=boss_h, d=boss_d)
    sh = shaft(shaft_d, boss_h + shaft_len,
               flat=0.5 if shaft_flat else None)
    return union(body, boss, sh).describe(f"nema_motor({size})")


def micro_servo() -> Solid:
    """SG90-class micro servo (REPRESENTATIVE envelope: body, mounting ears
    with holes, output boss + spline shaft). Body base on Z=0, ears at
    Z=16..18.6, shaft up. Place as a ghost for bracket design.
    """
    body = box(22.8, 12.2, 22.7, center=True).translate(0, 0, 22.7 / 2)
    ear = box(4.7, 12.2, 2.6, center=True)
    ears = union(ear.translate(22.8 / 2 + 4.7 / 2, 0, 17.3),
                 ear.translate(-22.8 / 2 - 4.7 / 2, 0, 17.3))
    for sx in (1, -1):
        ears = ears - cylinder(h=5, d=2.2).translate(
            sx * (22.8 / 2 + 2.35), 0, 14.5)
    boss = cylinder(h=4, d=11.8).translate(-22.8 / 2 + 5.9, 0, 22.7)
    spline = cylinder(h=3.2, d=4.6).translate(-22.8 / 2 + 5.9, 0, 26.7)
    return union(body, ears, boss, spline).describe("micro_servo()")


def extrusion_profile(length: float, size: int = 20) -> Solid:
    """Aluminum T-slot extrusion (REPRESENTATIVE: exact envelope, slot
    openings and center bore; interior web simplified). 2020/2040-style,
    running along +Z from Z=0. size=20 -> 20x20; size=40 stacks two 20s
    in Y.

        rail = parts.extrusion_profile(240, size=20)
    """
    if size not in (20, 40):
        raise BadArgumentError("extrusion_profile() size must be 20 or 40",
                               suggestion="2020 (size=20) or 2040 (size=40)")
    w, h = 20.0, float(size)
    prof = box(w, h, length)
    slot_mouth, slot_inner, slot_depth = 6.2, 11.0, 6.5
    cells_y = [0.0] if size == 20 else [-10.0, 10.0]

    def slots_for(cy: float) -> list[Solid]:
        cut = []
        for sx in (1, -1):      # +-X faces
            mouth = box(slot_depth * 2, slot_mouth, length + 2).translate(
                sx * w / 2, cy, -1)
            inner = box(slot_depth, slot_inner, length + 2).translate(
                sx * (w / 2 - slot_depth / 2 - 1.5), cy, -1)
            cut += [mouth, inner]
        return cut

    cuts = []
    for cy in cells_y:
        cuts += slots_for(cy)
    for sy in (1, -1):          # +-Y faces (one slot each on the 20 axis)
        mouth = box(slot_mouth, slot_depth * 2, length + 2).translate(
            0, sy * h / 2, -1)
        inner = box(slot_inner, slot_depth, length + 2).translate(
            0, sy * (h / 2 - slot_depth / 2 - 1.5), -1)
        cuts += [mouth, inner]
    body = prof - union(*cuts)
    # the real profile's diagonal webs tie corners to the center boss —
    # without them the T-slot cavities sever the section into fragments
    webs = []
    for cy in cells_y:
        for ang in (45, -45):
            webs.append(box(w * 1.35, 1.8, length, center=True)
                        .rotate(z=ang)
                        .translate(0, cy, length / 2))
        webs.append(cylinder(h=length, d=7.5).translate(0, cy, 0))
    body = union(body, *webs) & prof
    for cy in cells_y:          # re-drill the center bores through the boss
        body = body - cylinder(h=length + 2, d=4.2).translate(0, cy, -1)
    return body.describe(f"extrusion_{size:02d}20({fmt_num(length)})")


def lead_screw(d: float = 8.0, length: float = 100.0,
               pitch: float = 8.0) -> Solid:
    """Lead screw (REPRESENTATIVE: single-start thread of the given pitch;
    a real Tr8x8 is 4-start — use this for envelopes and end-support
    placement, buy the screw). Axis +Z from Z=0.
    """
    return iso_thread(d, length, pitch=min(pitch, d / 2)).describe(
        f"lead_screw(d{fmt_num(d)}x{fmt_num(pitch)})")


def linear_rail(length: float, size: int = 9) -> Solid:
    """MGN-style linear rail (REPRESENTATIVE: exact width/height and hole
    spacing). Runs along +X from X=0, base on Z=0, holes every 20 mm.
    Pair with parts.linear_carriage(size) as a separate part.
    """
    dims = {7: (7, 4.8, 2.4), 9: (9, 6.0, 3.0), 12: (12, 8.0, 3.5)}
    if size not in dims:
        raise BadArgumentError("linear_rail() size must be 7, 9 or 12")
    w, h, hole = dims[size]
    rail = box(length, w, h).translate(length / 2, 0, 0)
    n = max(1, int((length - 10) // 20) + 1)
    for i in range(n):
        rail = rail - cylinder(h=h + 2, d=hole).translate(10 + i * 20, 0, -1)
    return rail.describe(f"linear_rail(MGN{size})")


def linear_carriage(size: int = 9) -> Solid:
    """MGN-style carriage block (REPRESENTATIVE envelope + mounting holes).
    Sits OVER the rail: bottom channel at Z=0..rail height, mounting face
    on top. Position it on a rail placed with linear_rail().
    """
    dims = {7: (23, 17, 8, 12, 8, 2.4), 9: (28.9, 20, 10, 15, 10, 3.0),
            12: (34.7, 27, 13, 20, 15, 3.5)}
    if size not in dims:
        raise BadArgumentError("linear_carriage() size must be 7, 9 or 12")
    L, W, H, hx, hy, m = dims[size]
    rail_w, rail_h = {7: (7, 4.8), 9: (9, 6.0), 12: (12, 8.0)}[size]
    blockx = box(L, W, H, center=True).translate(0, 0, H / 2)
    channel = box(L + 2, rail_w + 0.4, rail_h + 0.2, center=True).translate(
        0, 0, (rail_h + 0.2) / 2 - 0.1)
    blockx = blockx - channel
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        blockx = blockx - cylinder(h=4, d=m).translate(
            sx * hx / 2, sy * hy / 2, H - 3)
    return blockx.describe(f"linear_carriage(MGN{size})")


def cable_chain_link(w: float = 15.0, h: float = 10.0,
                     pitch: float = 20.0, wall: float = 1.6) -> Solid:
    """One printable cable-chain (drag chain) link: two side plates with a
    pin on one end and a socket on the other; links snap together and
    articulate. Chain runs along +X, link base on Z=0.

        link = parts.cable_chain_link()
        chain = parts.linear_pattern(link, 6, dx=20)   # 6 loose links
    """
    if wall * 2 >= h or wall * 2 >= w:
        raise BadArgumentError("cable_chain_link() wall too thick for w/h")
    pin_d = h * 0.35
    # a cylinder along +Y (0..len): rotate the +Z cylinder about X by -90
    def y_cyl(length: float, d: float) -> Solid:
        return cylinder(h=length, d=d).rotate(x=-90)

    plate = box(pitch, wall, h)                         # centered X, y 0..?
    # plates flank the channel; pins point INWARD at the pin end, sockets
    # are through-holes at the other end (next link snaps pin-into-socket)
    socket = y_cyl(wall + 2, pin_d + 0.35).translate(
        -pitch / 2 + pin_d, -wall / 2 - 1, h / 2)
    side = plate - socket
    left = side.translate(0, -(w / 2 - wall / 2), 0)
    right = side.translate(0, w / 2 - wall / 2, 0)
    pin_l = y_cyl(wall * 0.9, pin_d).translate(
        pitch / 2 - pin_d, -(w / 2 - wall), h / 2)      # inward from left
    pin_r = y_cyl(wall * 0.9, pin_d).rotate(z=180).translate(
        pitch / 2 - pin_d, w / 2 - wall, h / 2)         # inward from right
    bottom = box(pitch * 0.6, w - 0.2, wall)
    return union(left, right, pin_l, pin_r, bottom).describe(
        "cable_chain_link()")
