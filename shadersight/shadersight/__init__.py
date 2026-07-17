"""shadersight — shader review built exclusively for AI agents.

A shader is judged by rendering a sphere and looking. But what is
actually WRONG with a material is physics: energy conservation,
Helmholtz reciprocity, positivity - laws, not opinions, and all of them
integrals over the hemisphere. And a node graph's problems are graph
theory: cycles, dead nodes, per-pixel cost. So compute them.

    from shadersight import Material, analyze_material, analyze_graph
"""

__version__ = "0.1.0"

from .brdf import Material, energy_conservation, reciprocity
from .errors import (BadArgumentError, BadGraphError, BadModelError,
                     ShaderSightError)
from .graph import analyze_graph, parse_graph
from .report import analyze_material, inspect_graph, inspect_material

__all__ = [
    "Material", "analyze_material", "inspect_material",
    "energy_conservation", "reciprocity",
    "parse_graph", "analyze_graph", "inspect_graph",
    "ShaderSightError", "BadGraphError", "BadModelError", "BadArgumentError",
]
