"""Named-part scene registry.

A model file declares its output by calling emit(solid, name="..."). Names let
the CLI render/validate/export a single part (`--part lid`) and let the report
speak about "lid" and "hinge_pin" instead of an anonymous blob.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import SceneError
from .geom import Solid

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Muted engineering palette (assigned round-robin to unnamed colors).
PALETTE = [
    "#5b7c99",  # steel blue
    "#c2884e",  # amber
    "#7a9471",  # sage
    "#a56a6a",  # clay
    "#6f6a94",  # slate violet
    "#8a8f65",  # olive
    "#5f8f8b",  # teal gray
    "#9c7b9a",  # mauve
]

NAMED_COLORS = {
    "steel": "#5b7c99", "amber": "#c2884e", "sage": "#7a9471",
    "clay": "#a56a6a", "slate": "#6f6a94", "olive": "#8a8f65",
    "teal": "#5f8f8b", "mauve": "#9c7b9a", "gray": "#8b8b88",
    "dark": "#4a4a48", "light": "#b8b8b4",
}


GHOST_COLOR = "#9aa0a6"


@dataclass
class Part:
    name: str
    solid: Solid
    color: str
    ghost: bool = False
    features: list = field(default_factory=list)
    material: dict = field(default_factory=dict)


# PBR finish presets for emit(material=...). Purely visual: they drive
# the live viewer and GLB export; the deterministic evidence renders and
# all measurements ignore them.
MATERIALS = {
    "steel":    {"metallic": 1.0, "roughness": 0.35},
    "aluminum": {"metallic": 1.0, "roughness": 0.25},
    "chrome":   {"metallic": 1.0, "roughness": 0.08},
    "brass":    {"metallic": 1.0, "roughness": 0.30},
    "metal":    {"metallic": 1.0, "roughness": 0.40},
    "plastic":  {"metallic": 0.0, "roughness": 0.55},
    "glossy":   {"metallic": 0.0, "roughness": 0.12},
    "matte":    {"metallic": 0.0, "roughness": 0.95},
    "rubber":   {"metallic": 0.0, "roughness": 0.90},
    "glass":    {"metallic": 0.0, "roughness": 0.05, "opacity": 0.35},
}
_MAT_KEYS = {"metallic", "roughness", "opacity"}


def _resolve_material(name: str, material) -> dict:
    if material is None:
        return {}
    if isinstance(material, str):
        if material not in MATERIALS:
            raise SceneError(
                f'part "{name}": unknown material preset {material!r}',
                suggestion="one of: " + ", ".join(sorted(MATERIALS))
                           + '; or a dict like {"metallic": 1.0, '
                             '"roughness": 0.3, "opacity": 1.0}')
        return dict(MATERIALS[material])
    if isinstance(material, dict):
        bad = set(material) - _MAT_KEYS
        if bad:
            raise SceneError(
                f'part "{name}": unknown material key(s) '
                f'{", ".join(sorted(bad))}',
                suggestion="allowed keys: metallic, roughness, opacity "
                           "(each 0..1)")
        out = {}
        for k, v in material.items():
            try:
                out[k] = min(1.0, max(0.0, float(v)))
            except (TypeError, ValueError):
                raise SceneError(
                    f'part "{name}": material {k} must be a number 0..1, '
                    f"got {v!r}")
        return out
    raise SceneError(
        f'part "{name}": material must be a preset name or a dict',
        suggestion="e.g. material=\"steel\" or material={\"metallic\": 1, "
                   "\"roughness\": 0.3}")


@dataclass
class Scene:
    parts: list[Part] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    expectations: list[dict] = field(default_factory=list)
    joints: list[dict] = field(default_factory=list)

    def emit(self, solid: Solid, name: str, color: str | None = None,
             ghost: bool = False, features: list | None = None,
             material: str | dict | None = None) -> Solid:
        if not isinstance(solid, Solid):
            got = type(solid).__name__
            hint = ("call .extrude(height) on the Sketch first"
                    if got == "Sketch" else
                    "emit each entry separately, e.g. "
                    'emit(parts["box"], name="box")' if got == "dict"
                    else "emit() takes a Solid as its first argument")
            raise SceneError(f"emit() got a {got}, not a Solid", suggestion=hint)
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise SceneError(
                f"emit() part name {name!r} is invalid",
                suggestion="use lowercase snake_case starting with a letter, "
                           'e.g. "base_plate", "leg_1", "snap_clip"')
        if any(p.name == name for p in self.parts):
            raise SceneError(
                f'a part named "{name}" was already emitted',
                suggestion=f'give each part a unique name, e.g. "{name}_2"')
        if solid.is_empty:
            raise SceneError(
                f'part "{name}" is empty geometry',
                suggestion="an earlier boolean removed everything; check the "
                           "construction of this part")
        resolved = (GHOST_COLOR if ghost and color is None
                    else _resolve_color(color, len(self.parts)))
        feats = _validate_features(name, features)
        self.parts.append(Part(name=name, solid=solid, color=resolved,
                               ghost=ghost, features=feats,
                               material=_resolve_material(name, material)))
        return solid

    def warn(self, code: str, message: str, where: str | None = None,
             suggestion: str | None = None) -> None:
        self.warnings.append({"code": code, "message": message,
                              "where": where, "suggestion": suggestion})

    def get(self, name: str) -> Part:
        for p in self.parts:
            if p.name == name:
                return p
        known = ", ".join(p.name for p in self.parts) or "(none)"
        raise SceneError(f'no part named "{name}" in this model',
                         where=f"emitted parts: {known}",
                         suggestion="check --part spelling against the list above")

    def combined(self) -> Solid:
        from .geom import union
        if not self.parts:
            raise SceneError(
                "the model emitted no parts",
                suggestion="end the model file with emit(some_solid, "
                           'name="body") for every part you want built')
        if len(self.parts) == 1:
            return self.parts[0].solid
        return union(*[p.solid for p in self.parts])


def _validate_features(part_name: str, features: list | None) -> list:
    """Semantic feature metadata: what the geometry MEANS, not just what
    it is. Each entry is a dict with at least a 'type' (hole, boss, rib,
    fillet, shaft, gear, hinge, window, thread, slot, ...) and whatever
    parameters make it useful (at=[x,y,z], d=, count=, axis=...). Stored
    verbatim in report.json parts[].features."""
    if features is None:
        return []
    if not isinstance(features, list) or not all(
            isinstance(f, dict) and f.get("type") for f in features):
        raise SceneError(
            f'emit(features=...) for "{part_name}" must be a list of '
            "dicts, each with a 'type' key",
            suggestion='e.g. features=[{"type": "hole", "d": 5, '
                       '"at": [10, 0, 0], "thru": True}]')
    return features


def _resolve_color(color: str | None, index: int) -> str:
    if color is None:
        return PALETTE[index % len(PALETTE)]
    c = color.strip().lower()
    if c in NAMED_COLORS:
        return NAMED_COLORS[c]
    if re.match(r"^#[0-9a-f]{6}$", c):
        return c
    raise SceneError(
        f"unknown color {color!r}",
        suggestion="use a hex value like #5b7c99 or one of: "
                   + ", ".join(sorted(NAMED_COLORS)))


# ---------------------------------------------------------------------------
# Active-scene plumbing: the runner installs a Scene here; emit() in model
# files talks to it.
# ---------------------------------------------------------------------------

_current: Scene | None = None

# Directory of the model file currently executing (stack: from_model() nests).
# Lets relative paths in from_model()/from_stl() resolve against the model
# file that wrote them, not the process working directory.
model_dir_stack: list = []


def current_model_dir():
    return model_dir_stack[-1] if model_dir_stack else None


def current() -> Scene | None:
    return _current


def activate(scene: Scene) -> None:
    global _current
    _current = scene


def deactivate() -> None:
    global _current
    _current = None


def emit(solid: Solid, name: str, color: str | None = None,
         ghost: bool = False, features: list | None = None,
         material: str | dict | None = None) -> Solid:
    """Register a finished part under a name. Call once per part, at the end
    of the model file. Returns the solid unchanged so it can be reused.

    ghost=True makes it a REFERENCE volume: it participates fully in the
    pair collision/clearance analysis (keep-out zones, swept insertion
    paths, board outlines) but is rendered as an X-ray outline and excluded
    from print checks, material totals and STL/3MF exports.

    features=[...] attaches SEMANTIC metadata — what the geometry means:
    [{"type": "hole", "d": 5, "at": [10, 0, 0], "thru": True},
     {"type": "boss", "d": 8, "at": [0, 0, 12]}]. Stored verbatim in
    report.json parts[].features so downstream consumers reason about
    named features instead of raw triangles.

    material=... sets the part's visual FINISH for the live viewer and
    GLB export (measurements and the deterministic evidence renders are
    unaffected). A preset name — "steel", "aluminum", "chrome", "brass",
    "metal", "plastic", "glossy", "matte", "rubber", "glass" — or a dict
    {"metallic": 0..1, "roughness": 0..1, "opacity": 0..1}."""
    sc = current()
    if sc is None:
        raise SceneError(
            "emit() called outside a solidsight build",
            suggestion="run the model through `solidsight build model.py`; "
                       "for ad-hoc scripts create a Scene and call scene.emit()")
    return sc.emit(solid, name=name, color=color, ghost=ghost,
                   features=features, material=material)
