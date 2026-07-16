"""Orchestrates a build: run model -> validate -> render -> report.json.

The report is deterministic: no timestamps, no machine-specific paths inside
(file references are relative to the output directory).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import __version__
from .events import BUS
from .render import render_slice, render_view, turntable_views
from .runner import run_model
from .scene import Scene
from .validate import ValidationOptions, analyze_scene


def build_model(model_path: Path, out_dir: Path, mode: str = "free",
                views: list[str] | None = None, turntable: int = 0,
                slices: list[tuple[str, float]] | None = None,
                only_parts: list[str] | None = None,
                export_stl: bool = False, export_3mf: bool = False,
                export_obj: bool = False, export_glb: bool = False,
                export_dxf: bool = False, export_svg: bool = False,
                size: int = 900,
                min_wall: float = 1.2, max_overhang: float = 50.0,
                allow_multiple_shells: bool = False,
                exploded: bool = False,
                focus: tuple | None = None,
                scene: Scene | None = None,
                unchanged_parts: set[str] | None = None,
                skip_pairs: bool = False) -> dict:
    """scene: pass a pre-executed Scene to skip re-running the model (watch
    mode does this to fingerprint first). unchanged_parts: export files for
    these parts are reused if already on disk (incremental rebuilds)."""
    views = views or ["iso", "front", "right", "top"]
    slices = slices or []

    if scene is None:
        with BUS.stage("model", f"executing {model_path.name}"):
            scene = run_model(model_path)
    BUS.emit("model", "info",
             f"{len(scene.parts)} part(s): "
             + ", ".join(p.name for p in scene.parts))

    if only_parts:
        keep = [scene.get(name) for name in only_parts]  # errors on bad names
        kept_names = {p.name for p in keep}
        scene = Scene(parts=keep, warnings=scene.warnings,
                      expectations=[e for e in scene.expectations
                                    if {e["a"], e["b"]} <= kept_names])

    opts = ValidationOptions(mode=mode, min_wall=min_wall,
                             max_overhang=max_overhang,
                             allow_multiple_shells=allow_multiple_shells)
    with BUS.stage("validate", "metrics + checks + pair analysis"):
        metrics, checks, pairs = analyze_scene(scene, opts,
                                               skip_pairs=skip_pairs)

    combined = scene.combined()
    lo, hi = combined.bbox

    out_dir.mkdir(parents=True, exist_ok=True)
    renders_dir = out_dir / "renders"
    renders_dir.mkdir(exist_ok=True)

    title = model_path.stem
    render_files: list[str] = []
    n_renders = (len(views) + len(slices) + max(turntable, 0)
                 + (1 if exploded and len(scene.parts) > 1 else 0))
    with BUS.stage("render", total=n_renders) as st:
        # named views render in parallel (independent framebuffers ->
        # byte-identical to sequential); files are saved in view order
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(views))) as pool:
            futures = [pool.submit(render_view, scene, view, size=size,
                                   title=title, subtitle=mode, focus=focus)
                       for view in views]
            for i, (view, fut) in enumerate(zip(views, futures), start=1):
                img = fut.result()
                fname = (f"{i:02d}_{view}_focus.png" if focus
                         else f"{i:02d}_{view}.png")
                img.save(renders_dir / fname)
                render_files.append(f"renders/{fname}")
                st.tick(f"view {view}")

        for axis, value in slices:
            img = render_slice(scene, axis, value, size=size, title=title)
            fname = f"slice_{axis}_{_slug(value)}.png"
            img.save(renders_dir / fname)
            render_files.append(f"renders/{fname}")
            st.tick(f"slice {axis}={value:g}")

        if exploded and len(scene.parts) > 1:
            img = render_view(_exploded_scene(scene), "iso", size=size,
                              title=title, subtitle=f"{mode} · exploded")
            img.save(renders_dir / "exploded.png")
            render_files.append("renders/exploded.png")
            st.tick("exploded view")

        if turntable > 0:
            for i, tview in enumerate(turntable_views(turntable)):
                img = render_view(scene, tview, size=size, title=title,
                                  subtitle=f"{mode} · frame "
                                           f"{i + 1}/{turntable}")
                fname = f"turntable_{i:02d}.png"
                img.save(renders_dir / fname)
                render_files.append(f"renders/{fname}")
                st.tick(f"turntable frame {i + 1}")

    export_files: list[str] = []
    solid_parts = [p for p in scene.parts if not p.ghost]
    formats = [(export_stl, "stl"), (export_3mf, "3mf"),
               (export_obj, "obj"), (export_glb, "glb")]
    n_exports = sum(1 for e, _ in formats if e) * (
        len(solid_parts) + (1 if len(solid_parts) > 1 else 0))
    with BUS.stage("export", total=n_exports or None) as st:
        for enabled, ext in formats:
            if not enabled:
                continue
            mesh_dir = out_dir / ext
            mesh_dir.mkdir(exist_ok=True)
            for part in solid_parts:
                target = mesh_dir / f"{part.name}.{ext}"
                if (unchanged_parts and part.name in unchanged_parts
                        and target.exists()):
                    st.tick(f"{part.name}.{ext} (reused, unchanged)")
                else:
                    _export_mesh(part.solid.to_trimesh(), target,
                                 name=part.name, color=part.color)
                    st.tick(f"{part.name}.{ext}")
                export_files.append(f"{ext}/{part.name}.{ext}")
            if len(solid_parts) > 1:
                target = mesh_dir / f"combined.{ext}"
                if ext == "glb":
                    # GLB keeps the assembly structure: named parts + colors
                    _export_glb_scene(solid_parts, target)
                else:
                    from .geom import union as _union
                    _union(*[p.solid for p in solid_parts]).to_trimesh(
                        ).export(target)
                export_files.append(f"{ext}/combined.{ext}")
                st.tick(f"combined.{ext}")

        for axis, value in (slices if (export_dxf or export_svg) else []):
            for enabled, ext in ((export_dxf, "dxf"), (export_svg, "svg")):
                if not enabled:
                    continue
                path2d = _slice_path(combined, axis, value)
                if path2d is None:
                    BUS.warn("export", f"slice {axis}={value:g} does not "
                                       "intersect the model; no {ext}")
                    continue
                mesh_dir = out_dir / ext
                mesh_dir.mkdir(exist_ok=True)
                fname = f"slice_{axis}_{_slug(value)}.{ext}"
                path2d.export(str(mesh_dir / fname))
                export_files.append(f"{ext}/{fname}")
                st.tick(fname)

    from .bom import bom as _bom
    _bom_rows = _bom(scene)

    from .plugins import run_validators
    checks = checks + run_validators(scene)

    has_fail = any(c["level"] == "fail" for c in checks)
    has_warn = any(c["level"] == "warn" for c in checks)
    status = "failed" if has_fail else ("warnings" if has_warn else "ok")

    report = {
        "tool": f"solidsight {__version__}",
        "model": model_path.name,
        "mode": mode,
        "units": "mm",
        "status": status,
        "scene": {
            "part_count": len(scene.parts),
            "bbox": {"min": _r3(lo), "max": _r3(hi)},
            "size": _r3(combined.size),
            "total_volume_mm3": round(sum(p.solid.volume for p in scene.parts
                                          if not p.ghost), 3),
        },
        "parts": metrics,
        "pairs": pairs,
        "checks": checks,
        "bom": _bom_rows,
        "files": {
            "report": str(out_dir / "report.json"),
            "renders": [str(out_dir / r) for r in render_files],
            "exports": [str(out_dir / e) for e in export_files],
        },
    }

    on_disk = dict(report)
    on_disk["files"] = {"report": "report.json", "renders": render_files,
                        "exports": export_files}
    (out_dir / "report.json").write_text(
        json.dumps(on_disk, indent=2) + "\n", encoding="utf-8")
    return report


def _export_mesh(tm, target: Path, name: str, color: str) -> None:
    """Single-mesh export by extension; GLB carries the name + color."""
    if target.suffix == ".glb":
        import trimesh
        tm = tm.copy()
        tm.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=name, baseColorFactor=_rgba(color)))
        sc = trimesh.Scene({name: tm})
        sc.export(target)
    else:
        tm.export(target)


def _export_glb_scene(parts, target: Path) -> None:
    import trimesh
    sc = trimesh.Scene()
    for p in parts:
        tm = p.solid.to_trimesh()
        tm.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=p.name, baseColorFactor=_rgba(p.color)))
        sc.add_geometry(tm, node_name=p.name, geom_name=p.name)
    sc.export(target)


def _rgba(hexcolor: str) -> list[float]:
    h = hexcolor.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [1.0]


def _slice_path(combined, axis: str, value: float):
    """Planar outline of a cross-section as a trimesh Path2D (DXF/SVG)."""
    import numpy as np
    normal = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[axis]
    origin = np.array(normal, dtype=float) * value
    sec = combined.to_trimesh().section(plane_origin=origin,
                                        plane_normal=normal)
    if sec is None:
        return None
    planar, _ = sec.to_2D()
    return planar


def _exploded_scene(scene: Scene) -> Scene:
    """Parts pushed radially away from the assembly center (60% of their
    center offset, plus a Z stagger) so mating faces become visible."""
    from .scene import Part
    combined = scene.combined()
    c = combined.bbox_center
    diag = max(combined.size)
    out = []
    for i, p in enumerate(scene.parts):
        pc = p.solid.bbox_center
        d = [pc[k] - c[k] for k in range(3)]
        norm = max((d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5, 1e-9)
        f = 0.6 * diag / norm if norm < 1e-6 else 0.6
        moved = p.solid.translate(d[0] * f, d[1] * f,
                                  d[2] * f + i * diag * 0.06)
        out.append(Part(name=p.name, solid=moved, color=p.color))
    return Scene(parts=out, warnings=[])


def _r3(v) -> list[float]:
    return [round(float(x), 3) for x in v]


def _slug(value: float) -> str:
    s = f"{value:g}".replace("-", "m").replace(".", "p")
    return s
