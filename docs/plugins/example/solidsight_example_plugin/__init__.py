"""Example solidsight plugin.

Install it next to solidsight (`pip install .`) and every build will run
the validator; `solidsight plugins` lists it. Crashing here never crashes
a build -- errors surface as warnings.
"""


def _max_size_validator(scene):
    """Warn when the scene exceeds a 220 mm printer envelope."""
    checks = []
    for part in scene.parts:
        if part.ghost:
            continue
        size = part.solid.size
        if max(size) > 220:
            checks.append({
                "level": "warn",
                "id": "plugin-example-envelope",
                "part": part.name,
                "message": f"part '{part.name}' exceeds a 220 mm printer "
                           f"envelope ({max(size):.0f} mm)",
                "suggestion": "split the part or target a larger machine",
            })
    return checks


def _manifest_exporter(scene, out_dir):
    """Write a plain-text manifest of the scene."""
    lines = [f"{p.name}: {p.solid.volume:.1f} mm3" for p in scene.parts]
    path = out_dir / "manifest.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ["manifest.txt"]


def register(api):
    api.add_validator("envelope", _max_size_validator)
    api.add_exporter("manifest", _manifest_exporter)
