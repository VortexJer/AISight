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
import os
import shutil
import socket
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ASSETS = Path(__file__).parent / "viewer_assets"


# ---------------------------------------------------------------------------
# payload
# ---------------------------------------------------------------------------

def scene_payload(scene, report: dict) -> tuple[dict, bytes]:
    """Everything the browser needs: metadata (JSON) + meshes (binary).

    Geometry used to travel as JSON number lists — a 100k-triangle scene
    was a 22 MB text file, re-encoded in Python loops on every rebuild
    and re-parsed by the page on every hot reload. It now rides in one
    mesh.bin (float32 positions, uint32 indices) that numpy writes in a
    millisecond and the browser maps straight into typed arrays; the
    JSON keeps only offsets. Still deterministic: same scene, same bytes.
    """
    import numpy as np
    parts, blobs, off = [], [], 0
    for p in scene.parts:
        tm = p.solid.to_trimesh()
        m = report["parts"].get(p.name, {})
        wall = m.get("wall_thickness") or {}
        over = m.get("overhangs") or {}
        voids = (m.get("internal_voids") or {}).get("voids", [])
        pos = np.round(np.asarray(tm.vertices, dtype=np.float64),
                       3).astype("<f4")
        idx = np.asarray(tm.faces, dtype="<u4")
        pos_b, idx_b = pos.tobytes(), idx.tobytes()
        parts.append({
            "name": p.name,
            "color": p.color,
            "ghost": bool(p.ghost),
            "material": p.material or {},
            "pos_off": off, "pos_n": int(pos.size),
            "idx_off": off + len(pos_b), "idx_n": int(idx.size),
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
        blobs.append(pos_b)
        blobs.append(idx_b)
        off += len(pos_b) + len(idx_b)
    return {
        "model": report["model"],
        "mode": report["mode"],
        "status": report["status"],
        "scene": report["scene"],
        "parts": parts,
        "pairs": report.get("pairs", []),
        "checks": [c for c in report["checks"]
                   if c["level"] in ("fail", "warn")],
    }, b"".join(blobs)


def write_viewer(viewer_dir: Path, payload: dict, version: str,
                 mesh_bin: bytes = b"") -> None:
    viewer_dir.mkdir(parents=True, exist_ok=True)
    for asset in ("index.html", "three.module.min.js"):
        src = ASSETS / asset
        dst = viewer_dir / asset
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copyfile(src, dst)
    # meshes first: the page reads version.txt to decide when to reload,
    # so it must be the LAST thing written or a poll can catch a scene
    # whose geometry is still half on disk
    (viewer_dir / "mesh.bin").write_bytes(mesh_bin)
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

    # --- liveness: every request is a heartbeat from an open window ---
    def _touch(self) -> None:
        srv = self.server
        srv.last_seen = time.monotonic()
        srv.had_client = True
        srv.bye_at = None            # a live request cancels a pending bye

    def do_GET(self):
        self._touch()
        super().do_GET()

    def do_HEAD(self):
        self._touch()
        super().do_HEAD()

    def do_POST(self):
        # the page beacons here when its window closes (pagehide)
        if self.path.rstrip("/") == "/bye":
            try:
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
            except (ValueError, OSError):
                pass
            self.server.bye_at = time.monotonic()
            self.send_response(204)
            self.end_headers()
            return
        self.send_error(404)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    last_seen = 0.0        # monotonic time of the last request
    had_client = False     # a browser has connected at least once
    bye_at = None          # when the page said its window was closing
    # HTTPServer sets allow_reuse_address, and on Windows SO_REUSEADDR
    # lets a second process bind a port another server is ACTIVELY
    # listening on: the bind succeeds, two viewers answer one URL and the
    # browser keeps talking to the stale one (it looks like the model
    # never updates). Never reuse there; on POSIX bind already fails when
    # the port is taken, and reuse only helps across TIME_WAIT restarts.
    allow_reuse_address = os.name != "nt"


def _port_is_free(port: int) -> bool:
    """True if a server can really own this port right now."""
    with socket.socket() as s:
        if os.name == "nt":     # exclusive = the honest answer on Windows
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


PORT_SCAN = 20      # how many ports above the requested one to try


def serve_viewer(viewer_dir: Path, port: int, say) -> ThreadingHTTPServer:
    handler = partial(_Quiet, directory=str(viewer_dir))
    wanted, httpd = port, None
    candidates = range(port, port + PORT_SCAN) if port else ()
    for cand in candidates:     # port 0 = "any free port", asked for it
        if not _port_is_free(cand):
            continue
        try:
            httpd = _Server(("127.0.0.1", cand), handler)
            break
        except OSError:         # lost the race between probe and bind
            continue
    if httpd is None:           # nothing free nearby: let the OS choose
        httpd = _Server(("127.0.0.1", 0), handler)
        if not port:
            wanted = httpd.server_address[1]     # nothing to warn about
    got = httpd.server_address[1]
    if got != wanted:
        say(f"note:    port {wanted} is in use (another viewer?) - "
            f"serving on {got} instead")
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    say(f"viewer:  http://127.0.0.1:{got}/  (serving {viewer_dir})")
    return httpd


BYE_GRACE_S = 4.0      # a reload also fires pagehide: wait it out
IDLE_EXIT_S = 150.0    # backup for a window killed without a beacon


def watch_for_window_close(httpd, say, on_exit) -> threading.Thread:
    """Close the server when the last viewer window goes away.

    Otherwise every closed window leaves a process holding its port, and
    the next `view` lands on 8378, 8379 ... while the human keeps
    looking at whichever stale window answered first. The page beacons
    /bye on pagehide; a reload beacons too, so a bye only counts if no
    request arrives during the grace. A window killed outright (crash,
    task manager) leaves no beacon — the idle timeout catches that.
    """
    def loop() -> None:
        while True:
            time.sleep(1.0)
            if not httpd.had_client:
                continue          # nobody ever opened it: keep serving
            now = time.monotonic()
            quiet = now - httpd.last_seen
            said_bye = httpd.bye_at is not None
            if (said_bye and quiet > BYE_GRACE_S) or quiet > IDLE_EXIT_S:
                port = httpd.server_address[1]
                say(f"viewer window closed - freeing port {port} and "
                    "stopping (use --keep-alive to stay up)")
                on_exit()
                return
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# opening it: an app window, not a tab
# ---------------------------------------------------------------------------

# Chromium's --app=URL gives a frameless window with no tab strip, no
# omnibox and its own taskbar entry: the viewer stops looking like a web
# page and behaves like the desktop application it is.
_CHROMIUM = {
    "nt": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application"
        r"\brave.exe",
    ],
    "posix": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
}
_CHROMIUM_CMDS = ["google-chrome", "google-chrome-stable", "chromium",
                  "chromium-browser", "brave-browser", "microsoft-edge"]


def find_app_browser() -> str | None:
    """Path to a Chromium-family browser that can do --app=, or None."""
    import shutil as _sh
    env = os.environ.get("SOLIDSIGHT_BROWSER")
    if env:
        return env if Path(env).exists() else _sh.which(env)
    for cand in _CHROMIUM.get(os.name, []) + _CHROMIUM["posix"]:
        if Path(cand).exists():
            return cand
    for cmd in _CHROMIUM_CMDS:
        found = _sh.which(cmd)
        if found:
            return found
    return None


def open_viewer_window(url: str, say, app_mode: bool = True) -> None:
    """Open the viewer as an app window; fall back to a normal tab."""
    import subprocess
    import webbrowser
    exe = find_app_browser() if app_mode else None
    if exe:
        try:
            subprocess.Popen(
                [exe, f"--app={url}", "--window-size=1280,860",
                 "--new-window"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            say(f"window:  app mode ({Path(exe).stem})")
            return
        except OSError as e:      # browser present but unlaunchable
            say(f"note:    could not start {Path(exe).stem} ({e}); "
                "opening a normal tab")
    elif app_mode:
        say("note:    no Chromium-family browser found for app mode "
            "(set SOLIDSIGHT_BROWSER=<path>); opening a normal tab")
    webbrowser.open(url)


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------

def run_view(model_path: Path, build_kwargs: dict, say,
             port: int = 8377, watch: bool = True, poll_s: float = 0.5,
             open_browser: bool = True, app_mode: bool = True,
             light: bool = True, keep_alive: bool = False) -> int:

    from .errors import SolidsightError
    from .report import build_model
    from .runner import run_model
    from .watch import run_watch, scene_fingerprint

    out_dir = build_kwargs["out_dir"]
    viewer_dir = out_dir / "viewer"
    if light:
        # A live preview needs geometry and nothing else. The full
        # pipeline — 600-ray wall probes, decompose, void detection,
        # PNG renders, and pair analysis over every part combination —
        # is what made a 138k-triangle bottle take 81 s per reload (and
        # minutes with expect() specs), so the human watched a spinner
        # and concluded the viewer was dead. Measure with
        # `solidsight build`; look with `solidsight view`.
        build_kwargs = dict(build_kwargs)
        build_kwargs.update(light=True, skip_pairs=True, views=[],
                            slices=[], turntable=0, exploded=False,
                            export_stl=False, export_3mf=False,
                            export_obj=False, export_glb=False,
                            export_dxf=False, export_svg=False)
        say("mode:    light builds (geometry only, no metrics/renders) — "
            "run `solidsight build` for checks, or `view --full`")
    state = {"pid": os.getpid(), "model": str(model_path),
             "state": "starting", "builds": 0, "last_build": None,
             "last_error": None, "url": None}

    def note_state(**kw) -> None:
        """Heartbeat an agent can read: `view` never returns, so a
        caller watching only stdout concludes it crashed. This file (and
        GET /status.json) says otherwise, in one read."""
        state.update(kw)
        try:
            (viewer_dir / "status.json").write_text(
                json.dumps(state, indent=1), encoding="utf-8")
        except OSError:
            pass

    def rebuild_payload(scene, report) -> None:
        fp, _ = scene_fingerprint(scene, {})
        payload, mesh_bin = scene_payload(scene, report)
        write_viewer(viewer_dir, payload, fp, mesh_bin)
        note_state(state="serving", builds=state["builds"] + 1,
                   last_build=report["status"], last_error=None)

    # the screen comes up FIRST: serve a waiting placeholder (spinner)
    # immediately, so the human has a window from second one — the model
    # file may not even exist yet
    write_viewer(viewer_dir,
                 {"status": "waiting", "model": model_path.name,
                  "parts": []}, "waiting-0")
    httpd = serve_viewer(viewer_dir, port, say)
    note_state(state="waiting", port=httpd.server_address[1],
               url=f"http://127.0.0.1:{httpd.server_address[1]}/")
    say("alive:   this command stays in the foreground until ctrl-c — "
        "that is not a hang. Liveness: GET /status.json (or read "
        f"{viewer_dir / 'status.json'})")
    if not keep_alive:
        import _thread

        def _stop() -> None:
            note_state(state="closed")
            httpd.shutdown()
            _thread.interrupt_main()   # unwinds the watch loop cleanly
        watch_for_window_close(httpd, say, _stop)
    if open_browser:
        open_viewer_window(f"http://127.0.0.1:{httpd.server_address[1]}/",
                           say, app_mode=app_mode)

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
        # "building" is a state of its own: a first build can take a
        # while, and a reader that only sees "waiting" concludes the
        # viewer never started one
        note_state(state="building")
        scene = run_model(model_path)
        report = build_model(model_path, scene=scene, **build_kwargs)
        rebuild_payload(scene, report)
        say(f"build: {report['status'].upper()} ({report['model']})")
    except KeyboardInterrupt:        # window closed mid-build, or ctrl-c
        return 0
    except SolidsightError as e:
        note_state(state="build-failed", last_error=str(e).split("\n")[0])
        say("initial build FAILED - the viewer keeps its spinner and "
            "hot-reloads on the next successful save (the server is up: "
            "check status.json)")
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
        elif error is not None:
            note_state(state="build-failed",
                       last_error=str(error).split("\n")[0])

    try:
        return run_watch(model_path, build_kwargs, say=say, poll_s=poll_s,
                         on_build=on_build,
                         on_start=lambda reason: note_state(state="building"))
    except KeyboardInterrupt:
        return 0
