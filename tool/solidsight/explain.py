"""Design review mode: `solidsight explain <check-id>`.

Every validator finding explained for an autonomous agent: what the
geometry fact IS, how to gather exact evidence for it, and the concrete
fix menu — ordered by how often each fix is the right one.
"""

from __future__ import annotations

EXPLANATIONS: dict[str, dict] = {
    "thin-wall": {
        "meaning": "Somewhere on this part two opposite surfaces are "
                   "closer than the printable minimum. The report gives "
                   "the exact thinnest point.",
        "evidence": "query ray <through the point> to read every wall "
                    "along a line; build --focus X,Y,Z,R --slice through "
                    "the point to SEE the sliver.",
        "fixes": [
            "thicken the region: move the two cutting features apart",
            "if a cutter grazes a face tangentially, sink it deeper or "
            "pull it fully outside",
            "if the sliver is intentional (living hinge), lower "
            "--min-wall explicitly — that documents the decision",
        ],
    },
    "internal-cavity": {
        "meaning": "A sealed void exists INSIDE the part: printable only "
                   "as trapped air/support, invisible in every render.",
        "evidence": "query voxels (cavity bbox); query ray through the "
                    "cavity center counts the extra ENTER/EXIT pair; "
                    "--slice through it shows the hole in the section.",
        "fixes": [
            "give buried features a path out (through_margin on holes "
            "so entry cones break the surface)",
            "overlap the cutter fully instead of stopping inside",
            "if the cavity is intentional (float chamber), document it "
            "and skip print-safe for that part",
        ],
    },
    "multiple-shells": {
        "meaning": "The 'part' is several disconnected solids: they will "
                   "print as loose pieces.",
        "evidence": "report shells count + first shell bboxes; renders "
                    "show pieces apart (or overlapping but unfused).",
        "fixes": [
            "features that only TOUCH do not fuse — overlap unions by "
            ">= 0.1 mm",
            "emit genuinely separate pieces as separate named parts",
            "--allow-multiple-shells only when printing them as a set",
        ],
    },
    "not-watertight": {
        "meaning": "The mesh has boundary edges — no defined inside, no "
                   "volume, unprintable and unanalyzable.",
        "evidence": "almost always an imported mesh (from_mesh); "
                    "solidsight's own booleans always produce manifolds.",
        "fixes": [
            "repair the import at its source (re-export with merged "
            "vertices / make manifold)",
            "rebuild the shape parametrically instead of importing",
        ],
    },
    "overhang": {
        "meaning": "Down-facing surface steeper than the threshold: FDM "
                   "needs support there, or the surface sags.",
        "evidence": "report worst face + area; --focus on the worst point; "
                    "flat wall-to-wall roofs are BRIDGES and usually fine.",
        "fixes": [
            "chamfer 45 deg under bosses and rims (teardrop holes)",
            "reorient: print the part on a different face",
            "accept supports — say so, it is a valid decision",
        ],
    },
    "parts-overlap": {
        "meaning": "Two named parts occupy the same space. Physical "
                   "objects cannot: one of them is mislocated or "
                   "oversized. The report gives exact overlap bbox, "
                   "volume, and patch decomposition.",
        "evidence": "multiple patches -> oversized (shrink); single "
                    "patch -> the move distance is computed; --focus on "
                    "the overlap bbox to see it.",
        "fixes": [
            "apply the suggested move or shrink",
            "snap-fit interference is the one legit case: sweep only "
            "the RIGID body (parts.swept) and judge hook depth vs "
            "deflection",
        ],
    },
    "expectation-violated": {
        "meaning": "You declared the intended relationship with expect() "
                   "and the geometry breaks it. This fails in EVERY mode "
                   "— declared intent outranks mode.",
        "evidence": "the pair entry shows declared vs measured.",
        "fixes": [
            "fix the geometry until the declared band holds",
            "if the intent changed, change the expect() — never delete "
            "it to silence the failure",
        ],
    },
    "union-touching": {
        "meaning": "A union joined faces that exactly COINCIDE (zero "
                   "overlap): float error can leave zero-thickness seams "
                   "or phantom shells.",
        "evidence": "shells count of the result; the warning names both "
                    "operands.",
        "fixes": ["overlap the pieces by >= 0.1 mm — sink one into the "
                  "other; exact coplanar stacking is never needed"],
    },
    "noop-difference": {
        "meaning": "A subtraction removed NOTHING — the cutter missed "
                   "the part entirely. Almost always a placement or "
                   "aim() mistake.",
        "evidence": "the warning prints both bounding boxes: compare "
                    "them axis by axis.",
        "fixes": [
            "extrusions grow +Z: lower cutters before aim() — "
            ".extrude(d).translate(0,0,-d).aim('+x')",
            "check the translate: entry point goes AT the surface",
        ],
    },
    "self-intersecting-polygon": {
        "meaning": "The outline crosses itself (bowtie): even-odd fill "
                   "splits it into multiple loops, usually not what the "
                   "coordinates meant.",
        "evidence": "the sketch produced >1 contour from one ring.",
        "fixes": ["reorder the points to walk the outline in one "
                  "non-crossing loop"],
    },
    "floating": {
        "meaning": "In print-safe mode a part starts above the build "
                   "plate: nothing under it to print on.",
        "evidence": "part bbox min z > 0.",
        "fixes": ["finish parts with .on_ground(); position assemblies "
                  "for ANALYSIS, export parts for PRINTING"],
    },
    "below-plate": {
        "meaning": "Part geometry extends below Z=0 — the slicer will "
                   "cut it off at the plate.",
        "evidence": "part bbox min z < 0.",
        "fixes": ["translate up or .on_ground()"],
    },
    "unstable": {
        "meaning": "The center of mass is outside the footprint's convex "
                   "hull: the part falls over as printed/placed.",
        "evidence": "report stability: COM vs footprint margin.",
        "fixes": ["widen the base, add feet, or print on a wider face "
                  "and accept the orientation"],
    },
    "barely-stable": {
        "meaning": "COM is inside the footprint but within the warning "
                   "margin: a nudge tips it.",
        "evidence": "stability margin in the report.",
        "fixes": ["same as unstable, or accept for display pieces"],
    },
    "expectation-unknown-part": {
        "meaning": "expect() names a part that was never emitted.",
        "evidence": "the check lists the emitted names.",
        "fixes": ["match expect() names to emit()/place() names exactly"],
    },
    "expectation-self-pair": {
        "meaning": "expect() got the same part twice.",
        "evidence": "-",
        "fixes": ["declare the relationship between two DIFFERENT parts"],
    },
}


def explain(check_id: str) -> dict | None:
    return EXPLANATIONS.get(check_id)


def all_ids() -> list[str]:
    return sorted(EXPLANATIONS)
