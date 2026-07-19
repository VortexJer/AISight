"""Interactive engineering viewer: `solidsight view model.py`.

Builds the model, then serves a self-contained browser viewer (vendored
three.js, no CDN, no GPU needed server-side) with orbit/pan/zoom, part
isolation, transparency, wireframe, normals, section planes, exploded
assemblies, bounding boxes, centers of mass, collision boxes, finding
markers (thin walls, overhangs, cavities) and a two-point measurement
tool. By default it watches the model source and hot-reloads the page's
scene on every successful rebuild — the browser polls /version, whose
content is the scene fingerprint (deterministic, no timestamps).
"""

from __future__ import annotations

import json
import shutil
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ASSETS = Path(__file__).parent / "viewer_assets"


# ---------------------------------------------------------------------------
# payload
# ---------------------------------------------------------------------------

def scene_payload(scene, report: dict) -> dict:
    """Everything the browser needs, rounded for determinism."""
    parts = []
    for p in scene.parts:
        tm = p.solid.to_trimesh()
        m = report["parts"].get(p.name, {})
        wall = m.get("wall_thickness") or {}
        over = m.get("overhangs") or {}
        voids = (m.get("internal_voids") or {}).get("voids", [])
        parts.append({
            "name": p.name,
            "color": p.color,
            "ghost": bool(p.ghost),
            "material": p.material or {},
            "positions": [round(float(v), 3)
                          for xyz in tm.vertices for v in xyz],
            "indices": [int(i) for tri in tm.faces for i in tri],
            "bbox": m.get("bbox") or {
                "min": [round(float(v), 3) for v in tm.bounds[0]],
                "max": [round(float(v), 3) for v in tm.bounds[1]]},
            "com": m.get("center_of_mass"),
            "volume": m.get("volume_mm3"),
            "wall_min": wall.get("min_mm"),
            "wall_at": wall.get("at"),
            "overhang_at": over.get("worst_at"),
            "void_boxes": voids,
        })
    return {
        "model": report["model"],
        "mode": report["mode"],
        "status": report["status"],
        "scene": report["scene"],
        "parts": parts,
        "pairs": report.get("pairs", []),
        "checks": [c for c in report["checks"]
                   if c["level"] in ("fail", "warn")],
    }


def write_viewer(viewer_dir: Path, payload: dict, version: str) -> None:
    viewer_dir.mkdir(parents=True, exist_ok=True)
    for asset in ("index.html", "three.module.min.js"):
        src = ASSETS / asset
        dst = viewer_dir / asset
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copyfile(src, dst)
    (viewer_dir / "scene.json").write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    (viewer_dir / "version.txt").write_text(version, encoding="utf-8")


# ---------------------------------------------------------------------------
# server
# ---------------------------------------------------------------------------

class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):   # no per-request console noise
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve_viewer(viewer_dir: Path, port: int, say) -> ThreadingHTTPServer:
    handler = partial(_Quiet, directory=str(viewer_dir))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError:
        with socket.socket() as s:      # port busy: let the OS pick one
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    say(f"viewer:  http://127.0.0.1:{httpd.server_address[1]}/  "
        f"(serving {viewer_dir})")
    return httpd


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------

def run_view(model_path: Path, build_kwargs: dict, say,
             port: int = 8377, watch: bool = True,
             poll_s: float = 0.5, open_browser: bool = True) -> int:
    import time
    import webbrowser

    from .errors import SolidsightError
    from .report import build_model
    from .runner import run_model
    from .watch import run_watch, scene_fingerprint

    out_dir = build_kwargs["out_dir"]
    viewer_dir = out_dir / "viewer"

    def rebuild_payload(scene, report) -> None:
        fp, _ = scene_fingerprint(scene, {})
        write_viewer(viewer_dir, scene_payload(scene, report), fp)

    # the screen comes up FIRST: serve a waiting placeholder (spinner)
    # immediately, so the human has a window from second one — the model
    # file may not even exist yet
    write_viewer(viewer_dir,
                 {"status": "waiting", "model": model_path.name,
                  "parts": []}, "waiting-0")
    httpd = serve_viewer(viewer_dir, port, say)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{httpd.server_address[1]}/")

    if not model_path.exists():
        say(f"waiting for {model_path.name} to appear "
            "(the viewer shows a spinner until the first build) ...")
        try:
            while not model_path.exists():
                time.sleep(poll_s)
        except KeyboardInterrupt:
            say("viewer stopped.")
            return 0

    try:
        scene = run_model(model_path)
        report = build_model(model_path, scene=scene, **build_kwargs)
        rebuild_payload(scene, report)
        say(f"build: {report['status'].upper()} ({report['model']})")
    except SolidsightError as e:
        say("initial build FAILED - the viewer keeps its spinner and "
            "hot-reloads on the next successful save")
        say(e.render())

    if not watch:
        say("serving until ctrl-c (no watch) ...")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            say("viewer stopped.")
        return 0

    def on_build(report, error, scene=None) -> None:
        if report is not None and scene is not None:
            rebuild_payload(scene, report)

    return run_watch(model_path, build_kwargs, say=say, poll_s=poll_s,
                     on_build=on_build)
