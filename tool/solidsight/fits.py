"""ISO 286 limits & fits: exact clearance/interference bands.

    solidsight fit 8 H7 g6        # the classic sliding fit
    solidsight fit 22 H7 p6       # bearing press fit

Values are the ISO 286-1 fundamental deviations and IT tolerance grades
for the common grades agents actually use (6/7/8; H h g f e k n p),
nominal sizes 1..120 mm. Output is the guaranteed clearance band plus a
verdict — and a 3D-printing note, because FDM parts hold ~±0.15 mm at
best and laugh at micrometers.
"""

from __future__ import annotations

from .errors import BadArgumentError

# nominal ranges (over, up-to] in mm
_RANGES = [(1, 3), (3, 6), (6, 10), (10, 18), (18, 30), (30, 50),
           (50, 80), (80, 120)]

# IT grades in micrometers per range
_IT = {6: [6, 8, 9, 11, 13, 16, 19, 22],
       7: [10, 12, 15, 18, 21, 25, 30, 35],
       8: [14, 18, 22, 27, 33, 39, 46, 54]}

# fundamental deviation (micrometers) per range.
# shafts: upper deviation es for e/f/g/h; lower deviation ei for k/n/p.
_DEV_SHAFT = {
    "e": [-14, -20, -25, -32, -40, -50, -60, -72],
    "f": [-6, -10, -13, -16, -20, -25, -30, -36],
    "g": [-2, -4, -5, -6, -7, -9, -10, -12],
    "h": [0, 0, 0, 0, 0, 0, 0, 0],
    "k": [1, 1, 1, 1, 2, 2, 2, 3],
    "n": [4, 8, 10, 12, 15, 17, 20, 23],
    "p": [6, 12, 15, 18, 22, 26, 32, 37],
}
_SHAFT_FROM_EI = {"k", "n", "p"}


def _range_index(nominal: float) -> int:
    for i, (over, upto) in enumerate(_RANGES):
        if over < nominal <= upto:
            return i
    raise BadArgumentError(
        f"nominal size {nominal} mm is outside the table (1..120 mm)",
        suggestion="solidsight fit works for 1 < D <= 120")


def _parse_grade(grade: str, hole: bool) -> tuple[str, int]:
    g = grade.strip()
    letter, digits = g[0], g[1:]
    if not digits.isdigit() or int(digits) not in _IT:
        raise BadArgumentError(
            f"unsupported grade {grade!r}",
            suggestion="IT grades 6, 7 or 8 (e.g. H7, g6, p6)")
    if hole:
        if letter != "H":
            raise BadArgumentError(
                f"hole grade {grade!r} not supported — the table covers "
                "H-basis fits (H6/H7/H8), which is how fits are normally "
                "specified",
                suggestion="use an H hole and choose the shaft letter")
    else:
        if letter.lower() not in _DEV_SHAFT:
            raise BadArgumentError(
                f"shaft letter {letter!r} not in the table",
                suggestion="supported shafts: e, f, g, h (clearance), "
                           "k, n (transition), p (interference)")
    return letter, int(digits)


def fit(nominal: float, hole_grade: str, shaft_grade: str) -> dict:
    """Exact ISO 286 fit analysis for an H-basis hole/shaft pair."""
    i = _range_index(nominal)
    _hl, hit = _parse_grade(hole_grade, hole=True)
    sl, sit = _parse_grade(shaft_grade, hole=False)
    sl = sl.lower()

    hole_lo = 0.0                       # H: EI = 0
    hole_hi = _IT[hit][i] / 1000.0
    dev = _DEV_SHAFT[sl][i] / 1000.0
    it_s = _IT[sit][i] / 1000.0
    if sl in _SHAFT_FROM_EI:
        shaft_lo, shaft_hi = dev, dev + it_s
    else:
        shaft_hi, shaft_lo = dev, dev - it_s

    c_min = hole_lo - shaft_hi          # tightest
    c_max = hole_hi - shaft_lo          # loosest
    if c_min >= 0:
        kind = "clearance"
    elif c_max <= 0:
        kind = "interference"
    else:
        kind = "transition"
    return {
        "nominal_mm": nominal,
        "hole": f"{nominal:g} {hole_grade}: "
                f"+{hole_lo:.3f}/+{hole_hi:.3f}",
        "shaft": f"{nominal:g} {shaft_grade}: "
                 f"{shaft_lo:+.3f}/{shaft_hi:+.3f}",
        "clearance_min_mm": round(c_min, 4),
        "clearance_max_mm": round(c_max, 4),
        "type": kind,
        "printing_note": (
            "FDM printers hold about +-0.15 mm: micrometer fits are a "
            "machining concept. For printed parts use design clearance "
            "0.15-0.3 mm (sliding) or 0.05-0.1 mm interference (press), "
            "and use this table when mating printed parts with MACHINED "
            "ones (bearings, shafts, pins)."),
    }
