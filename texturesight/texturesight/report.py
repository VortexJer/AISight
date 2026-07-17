"""Assemble the deterministic texture report + its evidence renders."""

from __future__ import annotations

import json
from pathlib import Path

from . import images as I
from . import uv as U
from .obj import parse_obj


def _check(id_, level, message, where=None, suggestion=None) -> dict:
    c = {"id": id_, "level": level, "message": message}
    if where:
        c["where"] = where
    if suggestion:
        c["try"] = suggestion
    return c


def _island_detail(mesh, isl: dict, dens: dict) -> list[dict]:
    """Per-island stats: THE actionable unit for layout fixes. 'Face 8
    is starved' tells nobody what to grab in the UV editor; 'island #4,
    the one at uv (0.35,0.35)-(0.45,0.45), needs 3x' does."""
    import numpy as np
    roots = isl["uv_root_per_face"]
    density = dens.get("per_face")
    uv = mesh.uvs[mesh.tri_uv]                       # (F, 3, 2)
    a3 = mesh.face_area_3d()

    order = sorted(set(int(r) for r in roots))
    out = []
    for i, r in enumerate(order):
        faces = np.nonzero(roots == r)[0]
        pts = uv[faces].reshape(-1, 2)
        d = None
        if density is not None:
            dv = density[faces]
            w = a3[faces]
            ok = np.isfinite(dv) & (dv > 0)
            if ok.any():
                d = float(np.average(dv[ok], weights=np.maximum(w[ok],
                                                                1e-12)))
        out.append({
            "island": i,
            "faces": [int(f) for f in faces],
            "face_count": int(len(faces)),
            "uv_bbox": [round(float(pts[:, 0].min()), 4),
                        round(float(pts[:, 1].min()), 4),
                        round(float(pts[:, 0].max()), 4),
                        round(float(pts[:, 1].max()), 4)],
            "mean_density_px_per_unit": round(d, 2) if d is not None
            else None,
            "surface_mm2": round(float(a3[faces].sum()), 2),
        })
    return out


def analyze_uv(mesh, texture_px: int = 1024) -> dict:
    dens = U.texel_density(mesh, texture_px)
    dist = U.distortion(mesh)
    isl = U.islands(mesh)
    pack = U.packing(mesh, isl)
    detail = _island_detail(mesh, isl, dens)

    checks: list[dict] = []
    if dist["flipped_face_count"]:
        checks.append(_check(
            "uv-flipped-faces", "fail",
            f"{dist['flipped_face_count']} face(s) have inverted UV winding",
            where=f"first at face {dist['flipped_faces'][0]}",
            suggestion="mirror those UV islands back: a flipped face "
                       "samples normal maps mirrored, so lighting is wrong "
                       "in a way no texture edit can fix"))
    if pack["overlap_cells"]:
        checks.append(_check(
            "uv-overlap", "warn",
            f"UV islands overlap in {pack['overlap_cells']} cell(s) of a "
            f"{pack['overlap_grid']}x{pack['overlap_grid']} grid",
            where="stacked islands share texels",
            suggestion="if the overlap is deliberate (mirrored/tiled "
                       "parts sharing texture), ignore this; otherwise "
                       "re-pack the layout"))
    if pack["faces_outside_0_1"]:
        checks.append(_check(
            "uv-out-of-bounds", "warn",
            f"{pack['faces_outside_0_1']} face(s) fall outside the 0..1 "
            f"UV square",
            where=f"uv bbox {pack['uv_bbox']}",
            suggestion="intentional for tiling/UDIMs; a mistake for a "
                       "single atlased asset - say which"))
    if dist["stretched_face_count"]:
        a = dist["anisotropy"]
        checks.append(_check(
            "uv-stretch", "warn",
            f"{dist['stretched_face_count']} face(s) stretched more than "
            f"{U.STRETCH_WARN}:1 ({dist['stretched_area_fraction'] * 100:.1f}"
            f"% of the surface); worst {a['max']}:1",
            where=f"worst at face {a['worst_face']}",
            suggestion="add a seam through the stretched region and "
                       "re-unwrap it; stretch cannot be painted out"))
    sr = dens.get("spread_ratio")
    if sr is not None and sr > U.DENSITY_SPREAD_WARN:
        d = dens["px_per_unit"]
        with_d = [i for i in detail
                  if i["mean_density_px_per_unit"] is not None]
        starved = min(with_d,
                      key=lambda i: i["mean_density_px_per_unit"]) \
            if with_d else None
        where = f"lowest at face {dens['worst_face']}"
        fix = ("scale the sparse islands up in the UV layout; uneven "
               "density reads as some parts being blurry")
        if starved:
            need = d["area_weighted_mean"] / max(
                starved["mean_density_px_per_unit"], 1e-9)
            bb = starved["uv_bbox"]
            where = (f"island #{starved['island']} at uv ({bb[0]}, {bb[1]})"
                     f"-({bb[2]}, {bb[3]}): "
                     f"{starved['mean_density_px_per_unit']} px/unit vs "
                     f"{d['area_weighted_mean']} mesh mean")
            fix = (f"scale island #{starved['island']} up ~{need:.1f}x in "
                   f"the UV editor (islands are labelled in "
                   f"uv_layout.png); repack if it no longer fits")
        checks.append(_check(
            "texel-density-uneven", "warn",
            f"texel density varies {sr}x across the mesh "
            f"({d['p2']}..{d['p98']} px/unit)",
            where=where, suggestion=fix))
    if pack["utilization"] < 0.5:
        checks.append(_check(
            "uv-packing-loose", "warn",
            f"the UV layout uses {pack['utilization'] * 100:.0f}% of the "
            f"square",
            where=f"{isl['uv_islands']} island(s)",
            suggestion="tighter packing = more texels per asset at the "
                       "same memory; below ~50% you are paying for empty "
                       "pixels"))

    return {
        "mesh": {"source": mesh.source, "faces": mesh.n_faces,
                 "vertices": int(len(mesh.verts)),
                 "uv_coords": int(len(mesh.uvs)),
                 "materials": sorted(mesh.groups)},
        "assumed_texture_px": texture_px,
        "texel_density": {k: v for k, v in dens.items() if k != "per_face"},
        "distortion": {k: v for k, v in dist.items()
                       if k != "per_face_anisotropy"},
        "islands": {**{k: v for k, v in isl.items()
                       if k != "uv_root_per_face"},
                    "detail": detail},
        "packing": pack,
        "checks": checks,
        "_arrays": {"density": dens.get("per_face"),
                    "aniso": dist["per_face_anisotropy"],
                    "uv_root": isl["uv_root_per_face"]},
    }


def analyze_texture(path: str | Path, kind: str = "auto") -> dict:
    p = Path(path)
    name = p.name
    guess = kind
    if kind == "auto":
        low = name.lower()
        for token, k in (("normal", "normal"), ("_nrm", "normal"),
                         ("_n.", "normal"), ("rough", "roughness"),
                         ("_r.", "roughness"), ("metal", "metallic"),
                         ("_ao", "ao"), ("occlusion", "ao"),
                         ("height", "height"), ("_disp", "height"),
                         ("albedo", "albedo"), ("basecolor", "albedo"),
                         ("diffuse", "albedo"), ("_col", "albedo")):
            if token in low:
                guess = k
                break
        else:
            guess = "albedo"

    img = I.load_image(p)
    out = {"basics": I.basics(img, name), "kind": guess,
           "kind_source": "filename" if kind == "auto" else "declared"}
    out["tiling"] = I.tiling_seams(img)
    out["repetition"] = I.repetition(img)
    out["compression"] = I.compression_artifacts(img)

    checks: list[dict] = []
    if not out["basics"]["power_of_two"]:
        checks.append(_check(
            "texture-not-power-of-two", "warn",
            f"{name} is {out['basics']['size_px'][0]}x"
            f"{out['basics']['size_px'][1]}: not a power of two",
            suggestion="GPUs mipmap and compress power-of-two textures "
                       "properly; resize unless the pipeline says "
                       "otherwise"))
    if not out["tiling"]["tiles"]:
        t = out["tiling"]
        axes = [a for a in ("horizontal", "vertical") if not t[a]["tiles"]]
        checks.append(_check(
            "tiling-seam", "warn",
            f"{name} does not tile ({', '.join(axes)}): the wrap jump is "
            f"{max(t[a]['ratio'] for a in axes)}x the texture's own "
            f"neighbouring-pixel difference",
            suggestion="offset the image by half and heal the cross, or "
                       "ignore this if it was never meant to tile"))
    # Repetition is REPORTED, never warned about on its own: a texture
    # that tiles is periodic by definition, so warning here would fire on
    # every correctly authored tiling material. The number is in
    # out["repetition"] for the agent to read against the intent - only a
    # tight repeat inside a map meant to look random is a defect, and
    # only the requester knows which it is.
    r = out["repetition"]
    if r.get("periodic") and r.get("peak_correlation", 0) > 0.9:
        off = r["peak_offset_px"]
        small = max(abs(off[0]), abs(off[1])) < min(out["basics"]
                                                    ["size_px"]) / 4
        if small:
            checks.append(_check(
                "visible-repetition", "warn",
                f"{name} repeats every {off} px with correlation "
                f"{r['peak_correlation']} - a short period inside one tile",
                suggestion="intended for a deliberate pattern (weave, "
                           "brick); for a material meant to read as random "
                           "the eye will lock onto it at this scale"))
    for b, d in out["compression"].items():
        if isinstance(d, dict) and d.get("blocking"):
            checks.append(_check(
                "compression-blocking", "warn",
                f"{name} shows {b.replace('block_', '')}x"
                f"{b.replace('block_', '')} block artifacts "
                f"(edge/interior gradient {d['ratio']}x)",
                suggestion="it was saved through a lossy codec: re-export "
                           "from the source at higher quality, especially "
                           "for normal/roughness maps where artifacts "
                           "become shading errors"))

    if guess == "normal":
        try:
            nm = I.normal_map(img)
            out["normal_map"] = nm
            if not nm["unit_length"]["ok"]:
                checks.append(_check(
                    "normal-not-unit-length", "fail",
                    f"{name}: {nm['unit_length']['off_spec_fraction'] * 100:.1f}"
                    f"% of texels are not unit-length vectors (mean "
                    f"{nm['unit_length']['mean']})",
                    suggestion="the map was resized or compressed as if it "
                               "were a picture; re-bake or re-export it, "
                               "and never store normals in sRGB"))
            if not nm["z_channel"]["ok"]:
                checks.append(_check(
                    "normal-bad-z", "fail",
                    f"{name}: the blue channel is wrong (mean Z "
                    f"{nm['z_channel']['mean']}, "
                    f"{nm['z_channel']['negative_fraction'] * 100:.2f}% "
                    f"negative)",
                    suggestion="tangent-space Z must point out of the "
                               "surface: this may be an object-space map, "
                               "or a height map mislabelled as a normal"))
        except Exception as e:                  # not a normal map after all
            checks.append(_check(
                "normal-map-unreadable", "warn", str(e),
                suggestion="pass --kind to declare what this map really is"))
    elif guess in ("roughness", "metallic", "ao", "height"):
        st = I.channel_stats(img, guess)
        out["channel"] = st
        if st["is_constant"]:
            checks.append(_check(
                "map-is-constant", "warn",
                f"{name} is a single value ({st['mean']}): it carries no "
                f"information",
                suggestion="replace it with a material constant and save "
                           "the texture memory"))
        elif st["range_used"] < 0.25:
            checks.append(_check(
                "map-range-wasted", "warn",
                f"{name} only uses {st['range_used']:.2f} of its 0..1 "
                f"range (p1 {st['percentiles']['p1']}, p99 "
                f"{st['percentiles']['p99']})",
                suggestion="stretch the values to the full range and "
                           "compensate in the material - the texture is "
                           "spending 8 bits to say very little"))
        if st["distinct_levels_of_256"] < 12 and not st["is_constant"]:
            checks.append(_check(
                "map-quantised", "warn",
                f"{name} has only {st['distinct_levels_of_256']} distinct "
                f"levels: it was quantised somewhere",
                suggestion="re-export from the source; banding in a data "
                           "map becomes visible steps in the shading"))
        if st.get("is_grayscale") is False:
            checks.append(_check(
                "data-map-not-grayscale", "warn",
                f"{name} is a {guess} map but its channels differ by "
                f"{st['channel_spread']}",
                suggestion="data maps should be single-channel; the RGB "
                           "channels are being averaged, which is probably "
                           "not what the shader does"))

    out["checks"] = checks
    return out


def diff_reports(a: dict, b: dict) -> list[str]:
    """What a layout/texture fix actually changed — the proof step of
    the loop. Compares two written reports (out dirs)."""
    lines = [f"diff: [{a.get('status')}] -> [{b.get('status')}]"]

    ua, ub = a.get("uv"), b.get("uv")
    if ua and ub:
        da = ua["texel_density"].get("px_per_unit", {})
        db = ub["texel_density"].get("px_per_unit", {})
        if da and db:
            lines.append(
                f"  density: mean {da['area_weighted_mean']} -> "
                f"{db['area_weighted_mean']} px/unit; spread "
                f"{ua['texel_density'].get('spread_ratio')}x -> "
                f"{ub['texel_density'].get('spread_ratio')}x")
        aa = ua["distortion"]["anisotropy"].get("max")
        ab = ub["distortion"]["anisotropy"].get("max")
        if aa != ab:
            lines.append(f"  anisotropy max: {aa} -> {ab}")
        fa = ua["distortion"]["flipped_face_count"]
        fb = ub["distortion"]["flipped_face_count"]
        if fa != fb:
            lines.append(f"  flipped faces: {fa} -> {fb}")
        pa, pb = ua["packing"]["utilization"], ub["packing"]["utilization"]
        if abs(pa - pb) > 0.005:
            lines.append(f"  packing: {pa * 100:.0f}% -> {pb * 100:.0f}%")
        ia, ib = ua["islands"]["uv_islands"], ub["islands"]["uv_islands"]
        if ia != ib:
            lines.append(f"  islands: {ia} -> {ib}")

    ca = {(c["id"], c["message"]) for c in a.get("checks", [])}
    cb = {(c["id"], c["message"]) for c in b.get("checks", [])}
    for cid, msg in sorted(cb - ca, key=str):
        lines.append(f"  NEW  [{cid}] {msg}")
    for cid, msg in sorted(ca - cb, key=str):
        lines.append(f"  GONE [{cid}] {msg}")
    if len(lines) == 1:
        lines.append("  no differences worth reporting")
    return lines


def inspect(mesh_path: str | Path | None, texture_paths: list[str],
            out_dir: Path, texture_px: int = 1024,
            kind: str = "auto") -> dict:
    from .render import render_uv_layout, render_density_map

    rep: dict = {"status": "ok", "checks": [], "files": {}}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    if mesh_path:
        mesh = parse_obj(mesh_path)
        uvr = analyze_uv(mesh, texture_px=texture_px)
        arrays = uvr.pop("_arrays")
        rep["uv"] = uvr
        rep["checks"] += uvr["checks"]
        render_uv_layout(mesh, arrays["uv_root"], out / "uv_layout.png",
                         flipped=uvr["distortion"]["flipped_faces"],
                         stretched=uvr["distortion"]["stretched_faces"])
        files.append("uv_layout.png")
        render_density_map(mesh, arrays["density"], out / "uv_density.png")
        files.append("uv_density.png")

    rep["textures"] = []
    for t in texture_paths:
        tr = analyze_texture(t, kind=kind)
        rep["checks"] += tr.pop("checks")
        rep["textures"].append(tr)

    fails = [c for c in rep["checks"] if c["level"] == "fail"]
    rep["status"] = "failed" if fails else ("warnings" if rep["checks"]
                                            else "ok")
    rep["files"] = {"report": "report.json", "renders": files}
    (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n",
                                     encoding="utf-8")
    rep["_out_dir"] = str(out)
    return rep
