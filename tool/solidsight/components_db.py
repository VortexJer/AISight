"""Offline database of real-world engineering components.

Search real parts by name ("M4 socket head", "608 bearing", "NEMA17"),
read their datasheet dimensions, and drop them into a model:

    solidsight components search "m4 socket head"
    solidsight components show iso4762_m3

    # inside a model:
    screw = parts.component("iso4762_m4", length=16)
    motor = place(parts.component("nema17"), name="motor", ghost=True)

No network, no vendor APIs: the data lives here, versioned with the tool,
so a build is reproducible forever. Every entry maps to a parametric
catalog generator with the standard's exact functional dimensions.
"""

from __future__ import annotations

from .errors import BadArgumentError
from .parts.components import (BEARING_DIMS, CAP_HEAD, NEMA_DIMS,
                               WASHER_DIMS)

# ISO 4032 hex nuts / ISO 4017 hex bolts: m -> across_flats
HEX_AF = {2: 4, 2.5: 5, 3: 5.5, 4: 7, 5: 8, 6: 10, 8: 13, 10: 16, 12: 18}
NUT_H = {2: 1.6, 2.5: 2, 3: 2.4, 4: 3.2, 5: 4.7, 6: 5.2, 8: 6.8,
         10: 8.4, 12: 10.8}


def _build_database() -> dict[str, dict]:
    db: dict[str, dict] = {}

    def add(id_: str, name: str, kind: str, standard: str, fn: str,
            args: dict, keywords: list[str], free: dict | None = None,
            note: str = "") -> None:
        db[id_] = {"id": id_, "name": name, "kind": kind,
                   "standard": standard, "fn": fn, "args": args,
                   "free_params": free or {}, "keywords": keywords,
                   "note": note}

    for m, (hd, hh, af) in CAP_HEAD.items():
        add(f"iso4762_m{m:g}".replace(".", "_"),
            f"M{m:g} socket head cap screw", "fastener", "ISO 4762",
            "cap_screw", {"m": m},
            [f"m{m:g}", "socket", "shcs", "allen", "cap", "screw", "bolt"],
            free={"length": "thread length in mm (e.g. 8, 12, 16, 20)"},
            note=f"head d{hd} x {hh}, hex socket {af} AF")
    for m, af in HEX_AF.items():
        add(f"iso4017_m{m:g}".replace(".", "_"),
            f"M{m:g} hex head bolt", "fastener", "ISO 4017",
            "bolt", {"d": m, "head_af": af, "head_h": round(0.65 * m, 2)},
            [f"m{m:g}", "hex", "bolt", "screw", "din933"],
            free={"length": "thread length in mm"},
            note=f"wrench {af} AF")
        add(f"iso4032_m{m:g}".replace(".", "_"),
            f"M{m:g} hex nut", "fastener", "ISO 4032",
            "nut", {"d": m, "af": af, "h": NUT_H[m]},
            [f"m{m:g}", "hex", "nut", "din934"],
            note=f"wrench {af} AF, height {NUT_H[m]}")
    for m, (di, do, t) in WASHER_DIMS.items():
        add(f"iso7089_m{m:g}".replace(".", "_"),
            f"M{m:g} flat washer", "fastener", "ISO 7089",
            "washer", {"m": m},
            [f"m{m:g}", "washer", "flat", "din125"],
            note=f"{di} id x {do} od x {t}")
    for bname, (bore, od, w) in BEARING_DIMS.items():
        add(f"bearing_{bname}", f"{bname} deep groove ball bearing",
            "bearing", f"{bname}-2RS/ZZ", "bearing", {"name": bname},
            [bname, "bearing", "ball", f"{bore}x{od}x{w}"],
            note=f"bore {bore} x od {od} x w {w}")
    for size, dims in NEMA_DIMS.items():
        add(f"nema{size}", f"NEMA {size} stepper motor", "motor",
            f"NEMA {size}", "nema_motor", {"size": size},
            [f"nema{size}", "stepper", "motor"],
            free={"length": "body length in mm (e.g. 34, 40, 48)"},
            note=f"faceplate {dims[0]}, holes {dims[5]} pitch, "
                 f"shaft d{dims[3]}")
    add("sg90", "SG90 micro servo", "motor", "SG90 class",
        "micro_servo", {}, ["sg90", "servo", "micro", "9g"],
        note="22.8 x 12.2 body, ears at z 16..18.6")
    for teeth in (16, 20, 36, 60):
        add(f"gt2_pulley_{teeth}t", f"GT2 pulley {teeth}T", "motion",
            "GT2 (2 mm pitch)", "timing_pulley", {"teeth": teeth},
            ["gt2", "pulley", "timing", f"{teeth}t", "belt"],
            free={"bore": "bore diameter (default 5)",
                  "width": "belt width zone (default 7)"})
    for size in (20, 40):
        add(f"extrusion_20{size}",
            f"20{size} aluminum T-slot extrusion",
            "framing", "V-slot / T-slot", "extrusion_profile",
            {"size": size},
            [f"20{size}", "extrusion", "vslot", "tslot", "aluminum",
             "profile"],
            free={"length": "extrusion length in mm"})
    for size in (7, 9, 12):
        add(f"mgn{size}_rail", f"MGN{size} linear rail", "motion",
            f"MGN{size}", "linear_rail", {"size": size},
            [f"mgn{size}", "linear", "rail", "guide"],
            free={"length": "rail length in mm"})
        add(f"mgn{size}_carriage", f"MGN{size} carriage block", "motion",
            f"MGN{size}", "linear_carriage", {"size": size},
            [f"mgn{size}", "linear", "carriage", "block", "guide"])
    add("tr8x8_leadscrew", "Tr8x8 lead screw", "motion", "Tr8x8 (4-start)",
        "lead_screw", {"d": 8, "pitch": 8},
        ["tr8", "lead", "screw", "leadscrew", "acme", "z-axis"],
        free={"length": "screw length in mm"},
        note="REPRESENTATIVE single-start form; real Tr8x8 is 4-start")
    return db


DATABASE = _build_database()


def search(query: str, limit: int = 8) -> list[dict]:
    """Rank database entries against a free-text query."""
    terms = [t for t in query.lower().replace("-", " ").split() if t]
    if not terms:
        return []
    scored = []
    for e in DATABASE.values():
        hay_exact = set(e["keywords"]) | {e["id"].lower(), e["kind"]}
        hay_text = " ".join([e["name"].lower(), e["standard"].lower(),
                             e["id"].lower(), " ".join(e["keywords"])])
        score = 0.0
        for t in terms:
            if t in hay_exact:
                score += 3
            elif t in hay_text:
                score += 1
        if score > 0:
            scored.append((score, e["id"], e))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [e for _s, _i, e in scored[:limit]]


def component(id_: str, **overrides):
    """Instantiate a database component as a Solid (usable in models as
    parts.component(id, ...)). Free parameters (length, bore ...) are
    passed as keyword overrides."""
    from . import parts as parts_mod
    e = DATABASE.get(id_)
    if e is None:
        hits = search(id_.replace("_", " "), limit=3)
        hint = (", ".join(h["id"] for h in hits)
                if hits else "solidsight components search <words>")
        raise BadArgumentError(f"no component {id_!r} in the database",
                               suggestion=f"did you mean: {hint}")
    missing = [k for k in e["free_params"]
               if k not in overrides and k == "length"]
    if missing:
        raise BadArgumentError(
            f"component {id_!r} needs {missing[0]}=<mm>",
            suggestion=f'parts.component("{id_}", {missing[0]}=20)')
    fn = getattr(parts_mod, e["fn"])
    return fn(**{**e["args"], **overrides})


def make_expression(e: dict) -> str:
    """The exact parts.* call an agent should paste into a model."""
    args = ", ".join(f"{k}={v!r}" for k, v in e["args"].items())
    free = ", ".join(f"{k}=..." for k in e["free_params"])
    joined = ", ".join(x for x in (args, free) if x)
    return f"parts.{e['fn']}({joined})"
