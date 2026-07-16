"""Executes a model file deterministically and returns the populated Scene.

Errors inside the model are re-packaged with the offending source line and an
actionable suggestion, so an agent can fix its own code without guessing.
"""

from __future__ import annotations

import traceback
from pathlib import Path

from . import scene as scene_mod
from .errors import ModelRuntimeError, SolidsightError
from .scene import Scene

_SUGGESTIONS: list[tuple[type, str]] = [
    (NameError, "the name is not defined — check spelling; all solidsight "
                "primitives come from `from solidsight import *`"),
    (TypeError, "check the argument names against `solidsight catalog` or "
                "references/design-language.md; most sizes are keyword "
                "arguments like d=, h=, r="),
    (AttributeError, "that method does not exist on this object; Sketches "
                     "have extrude()/revolve(), Solids have translate()/"
                     "rotate()/fillet()"),
    (ZeroDivisionError, "a parameter expression divided by zero — guard "
                        "derived values like pitch = length / count"),
    (ImportError, "model files may import solidsight, the Python standard "
                  "library (math, itertools, ...) and sibling .py files "
                  "next to the model (e.g. a shared params.py)"),
]


def run_model(path: str | Path) -> Scene:
    """Execute a model file, returning the Scene with its emitted parts."""
    p = Path(path)
    if not p.exists():
        raise ModelRuntimeError(
            f"model file not found: {p}",
            suggestion="check the path; it must point at a .py model file")
    source = p.read_text(encoding="utf-8")

    sc = Scene()
    prev = scene_mod.current()  # re-entrant: from_model() runs models nested
    scene_mod.activate(sc)
    model_dir = p.resolve().parent
    scene_mod.model_dir_stack.append(model_dir)
    # allow `from params import *` — shared dimension files next to the model
    import sys
    path_added = str(model_dir) not in sys.path
    if path_added:
        sys.path.insert(0, str(model_dir))
    model_globals: dict = {"__name__": "__solidsight_model__",
                           "__file__": str(p)}
    exec("from solidsight import *", model_globals)
    try:
        code = compile(source, str(p), "exec")
        exec(code, model_globals)
    except SolidsightError as e:
        line = _model_line(p)
        if line is not None and e.where is None:
            e.where = f"{p.name}:{line[0]} -> {line[1]}"
        elif line is not None:
            e.where = f"{p.name}:{line[0]} -> {line[1]}  |  {e.where}"
        raise
    except SyntaxError as e:
        raise ModelRuntimeError(
            f"Python syntax error: {e.msg}",
            where=f"{p.name}:{e.lineno} -> {(e.text or '').strip()}",
            suggestion="fix the syntax; the model file is plain Python") from e
    except Exception as e:
        line = _model_line(p)
        where = f"{p.name}:{line[0]} -> {line[1]}" if line else p.name
        suggestion = next((s for t, s in _SUGGESTIONS if isinstance(e, t)),
                          "read the message above; the failing line is shown "
                          "under 'where'")
        raise ModelRuntimeError(
            f"{type(e).__name__}: {e}", where=where,
            suggestion=suggestion) from e
    finally:
        scene_mod.model_dir_stack.pop()
        if path_added:
            try:
                sys.path.remove(str(model_dir))
            except ValueError:
                pass
        if prev is not None:
            scene_mod.activate(prev)
        else:
            scene_mod.deactivate()

    if not sc.parts:
        raise ModelRuntimeError(
            "the model ran but emitted no parts",
            where=p.name,
            suggestion='finish the file with emit(solid, name="body") for '
                       "each part that should exist in the output")
    return sc


def _model_line(model_path: Path) -> tuple[int, str] | None:
    """Deepest traceback frame that lives inside the model file itself."""
    tb = traceback.extract_tb(__import__("sys").exc_info()[2])
    frames = [f for f in tb if Path(f.filename) == model_path]
    if not frames:
        return None
    f = frames[-1]
    return (f.lineno or 0, (f.line or "").strip())
