"""texturesight — UV and texture review built exclusively for AI agents.

An agent cannot squint at a checker map. So measure instead: texel
density, per-face stretch from the UV Jacobian, islands and seams
counted from the topology, packing and overlap, tiling judged against
the texture's own statistics, normal-map validity, and data-map range.

    from texturesight import parse_obj, analyze_uv, analyze_texture
"""

__version__ = "0.2.0"

from .errors import (BadArgumentError, BadMeshError, BadTextureError,
                     TextureSightError)
from .obj import Mesh, parse_obj
from .report import analyze_texture, analyze_uv, inspect

__all__ = [
    "parse_obj", "Mesh", "analyze_uv", "analyze_texture", "inspect",
    "TextureSightError", "BadMeshError", "BadTextureError",
    "BadArgumentError",
]
