"""solidsight — a 3D design tool built exclusively for AI agents.

Model files do `from solidsight import *` and get the full design language:
primitives, sketches, booleans, transforms, the parametric parts catalog and
emit() for registering named parts.
"""

__version__ = "0.11.4"

from .errors import (BadArgumentError, EmptyGeometryError, ModelRuntimeError,
                     SceneError, SolidsightError)
from .geom import (DEFAULT_SEGMENTS, Sketch, Solid, box, circle, cone,
                   cylinder, difference, hull, intersection, ngon, polygon,
                   prism, rect, rounded_box, sphere, stroke, text, torus,
                   union, wedge)
from .scene import Scene, emit
from .assembly import expect, from_mesh, from_model, from_stl, place
from .robot import joint
from .vision import image_heightfield, image_outline, profile_read
from . import parts

__all__ = [
    # 3D primitives
    "box", "cylinder", "cone", "sphere", "prism", "wedge", "torus",
    "rounded_box",
    # 2D sketches
    "rect", "circle", "ngon", "polygon", "text", "stroke",
    # combinators
    "union", "difference", "intersection", "hull",
    # classes / registry
    "Solid", "Sketch", "Scene", "emit", "parts",
    # assembly
    "place", "from_model", "from_stl", "from_mesh", "expect", "joint",
    # image -> geometry
    "image_outline", "image_heightfield", "profile_read",
    # errors
    "SolidsightError", "EmptyGeometryError", "BadArgumentError",
    "SceneError", "ModelRuntimeError",
    "DEFAULT_SEGMENTS",
]
