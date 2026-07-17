"""Assembly intelligence: bill of materials, axis play, assembly sequence.

    solidsight assembly model.py       # BOM + play + suggested sequence

The BOM groups parts with identical geometry (exact mesh hash), keeps the
catalog provenance (parts.* generators name their solids), and estimates
material. Axis play sums the bbox gaps between consecutive parts along
each axis — the free travel of a fit chain. The assembly sequence is a
SUGGESTION derived from the contact graph: parts are added bottom-up,
each step listing what it registers against.
"""

from __future__ import annotations

import hashlib
import re

# a catalog/primitive descriptor worth printing as the BOM item, e.g.
# "bearing_608(bore=8)" or "spur_gear(teeth=20, m=2)". Composed solids
# carry their whole construction tree in .desc — useful in errors,
# useless (and unreadable) as a line item.
_CLEAN_DESC = re.compile(r"^[a-z_][a-z0-9_]*\([^()]*\)$", re.I)


def _item_label(solid) -> str:
    """The BOM identity of a solid: its catalog provenance when it has
    one, else 'custom part' (the part NAME is what identifies it then —
    a construction tree is not a line item)."""
    desc = (solid.desc or "").strip()
    if _CLEAN_DESC.match(desc) and not desc.startswith(("union(",
                                                        "difference(",
                                                        "intersection(",
                                                        "hull(")):
        return desc
    return "custom part"


def bom(scene) -> list[dict]:
    import numpy as np
    groups: dict[str, dict] = {}
    for p in scene.parts:
        tm = p.solid.to_trimesh()
        # geometric fingerprint, invariant to placement and vertex order:
        # counts + volume + area + sorted extents + COM offset from the
        # bbox center. Distinct parts colliding on ALL of these at once
        # is vanishingly unlikely; exact-mesh hashing is NOT usable here
        # because translation perturbs float rounding.
        com_off = np.linalg.norm(
            tm.center_mass - (tm.bounds[0] + tm.bounds[1]) / 2)
        ext = "|".join(f"{v:.2f}" for v in sorted(tm.extents))
        key = hashlib.sha1(
            f"{len(tm.vertices)}|{len(tm.faces)}|{tm.volume:.2f}|"
            f"{tm.area:.2f}|{ext}|{com_off:.3f}".encode()).hexdigest()[:12]
        g = groups.setdefault(key, {
            "item": _item_label(p.solid), "count": 0, "names": [],
            "ghost": p.ghost,
            "size_mm": [round(float(v), 2) for v in tm.extents],
            "volume_mm3": round(p.solid.volume, 3),
            "grams_pla_each": round(p.solid.volume * 0.00124, 1),
            "desc": p.solid.desc,   # full construction tree, for tracing
        })
        g["count"] += 1
        g["names"].append(p.name)
    rows = sorted(groups.values(),
                  key=lambda g: (-g["count"], g["names"][0]))
    return rows


def axis_play(scene) -> dict:
    """Per axis: the free bbox travel between consecutive non-ghost parts.
    A fit chain (drawer in a box, card in a slot) reads its total play
    here without any raycasting."""
    out = {}
    solid = [p for p in scene.parts if not p.ghost]
    for k, axis in enumerate("xyz"):
        spans = sorted((p.solid.bbox[0][k], p.solid.bbox[1][k], p.name)
                       for p in solid)
        gaps = []
        reach, prev_name = None, ""
        for lo, hi, name in spans:
            if reach is not None and lo > reach + 1e-9:
                gaps.append({"gap_mm": round(lo - reach, 3),
                             "after": prev_name, "before": name})
            if reach is None or hi > reach:
                reach, prev_name = hi, name
        out[axis] = {"total_play_mm": round(sum(g["gap_mm"] for g in gaps),
                                            3),
                     "gaps": gaps}
    return out


def assembly_sequence(scene, pairs: list[dict]) -> list[dict]:
    """Bottom-up placement order. Each step names the already-placed parts
    the new one touches (or its clearance to the closest one). A heuristic
    starting point, not a physics proof — check the exploded render."""
    solid = [p for p in scene.parts if not p.ghost]
    order = sorted(solid, key=lambda p: (p.solid.bbox[0][2],
                                         -p.solid.volume, p.name))
    rel: dict[frozenset, dict] = {
        frozenset((pr["a"], pr["b"])): pr for pr in pairs}
    placed: list[str] = []
    steps = []
    for p in order:
        contacts, nearest = [], None
        for q in placed:
            pr = rel.get(frozenset((p.name, q)))
            if pr is None:
                continue
            if pr["status"] in ("touching", "collision"):
                contacts.append(q)
            elif pr["min_clearance_mm"] is not None:
                if nearest is None or pr["min_clearance_mm"] < nearest[1]:
                    nearest = (q, pr["min_clearance_mm"])
        if not placed:
            note = "base part (lowest, largest)"
        elif contacts:
            note = "registers against " + ", ".join(sorted(contacts))
        elif nearest:
            note = (f"nearest already-placed part: '{nearest[0]}' at "
                    f"{nearest[1]} mm")
        else:
            note = "no measured relation to placed parts"
        steps.append({"step": len(steps) + 1, "part": p.name, "note": note})
        placed.append(p.name)
    return steps
