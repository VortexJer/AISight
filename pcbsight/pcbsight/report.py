"""Assemble the deterministic board report."""

from __future__ import annotations

import json
from pathlib import Path

from . import checks as C
from .board import parse_board


def _check(id_, level, message, where=None, suggestion=None) -> dict:
    c = {"id": id_, "level": level, "message": message}
    if where:
        c["where"] = where
    if suggestion:
        c["try"] = suggestion
    return c


def analyze(board, min_clearance: float = C.CLEARANCE_DEFAULT,
            dt_c: float = C.DT_DEFAULT) -> dict:
    conn = C.connectivity(board)
    clr = C.clearance(board, min_clearance)
    cur = C.current_capacity(board, dt_c)
    pairs = C.diff_pairs(board)

    checks: list[dict] = []
    for n in conn:
        if not n["routed"]:
            lonely = (", unconnected pad(s): "
                      + ", ".join(n["unconnected_pads"])
                      if n["unconnected_pads"] else "")
            checks.append(_check(
                "net-open", "fail",
                f"net '{n['net']}' is {n['islands']} separate island(s) - "
                f"it is not routed{lonely}",
                where=f"{n['pads']} pad(s), {n['tracks']} track(s)",
                suggestion="route the missing connection(s); an open net "
                           "is a board that does not work, not a style "
                           "issue"))
    for f in clr[:40]:
        checks.append(_check(
            "clearance", "fail" if f["clearance_mm"] < f["required_mm"] * 0.5
            else "warn",
            f"{f['kind']}: '{f['a']}' to '{f['b']}' at "
            f"{f['clearance_mm']} mm (required {f['required_mm']})",
            where=f"{f['layer']} near ({f['near'][0]}, {f['near'][1]})",
            suggestion="move the copper apart or drop the fab's clearance "
                       "class; below ~50% of spec this risks shorts after "
                       "etch, hence FAIL"))
    for p in pairs:
        if not p["width_matched"]:
            checks.append(_check(
                "diff-pair-width", "warn",
                f"pair {p['pair']} mixes widths {p['widths_mm']} mm",
                suggestion="a differential pair needs one width for a "
                           "constant differential impedance"))
        if p["skew_mm"] > 0.5:
            checks.append(_check(
                "diff-pair-skew", "warn",
                f"pair {p['pair']} is skewed {p['skew_mm']} mm "
                f"(~{p['skew_ps_fr4']} ps on FR4)",
                suggestion="length-match the pair (serpentine the short "
                           "side); relevant above ~100 MHz signals"))

    fails = [c for c in checks if c["level"] == "fail"]
    return {
        "status": ("failed" if fails else
                   ("warnings" if checks else "ok")),
        "board": {
            "source": board.source,
            "nets": len([n for n in board.nets if n != 0]),
            "tracks": len(board.tracks),
            "vias": len(board.vias),
            "pads": len(board.pads),
            "copper_um": round(board.copper_thickness_mm * 1000, 1),
        },
        "rules": {"min_clearance_mm": min_clearance, "delta_t_c": dt_c},
        "connectivity": conn,
        "clearance_findings": clr,
        "current_capacity": cur,
        "diff_pairs": pairs,
        "checks": checks,
    }


def diff_reports(a: dict, b: dict) -> list[str]:
    """What a layout fix actually changed — the proof step."""
    lines = [f"diff: {a['board']['source']} [{a.get('status')}] -> "
             f"{b['board']['source']} [{b.get('status')}]"]
    ba, bb = a["board"], b["board"]
    for k in ("nets", "tracks", "vias", "pads"):
        if ba[k] != bb[k]:
            lines.append(f"  {k}: {ba[k]} -> {bb[k]}")

    conn_a = {n["net"]: n for n in a["connectivity"]}
    conn_b = {n["net"]: n for n in b["connectivity"]}
    for net in sorted(set(conn_a) | set(conn_b)):
        ia = conn_a.get(net, {}).get("islands")
        ib = conn_b.get(net, {}).get("islands")
        if ia != ib:
            lines.append(f"  net '{net}': {ia} island(s) -> {ib}")

    na, nb = len(a["clearance_findings"]), len(b["clearance_findings"])
    if na != nb:
        lines.append(f"  clearance findings: {na} -> {nb}")

    cur_a = {c["net"]: c for c in a["current_capacity"]}
    cur_b = {c["net"]: c for c in b["current_capacity"]}
    for net in sorted(set(cur_a) & set(cur_b)):
        va, vb = cur_a[net]["i_max_a"], cur_b[net]["i_max_a"]
        if abs(va - vb) > 0.01:
            lines.append(f"  current '{net}': {va} A -> {vb} A "
                         f"(min width {cur_a[net]['min_width_mm']} -> "
                         f"{cur_b[net]['min_width_mm']} mm)")

    pa = {p["pair"]: p for p in a["diff_pairs"]}
    pb = {p["pair"]: p for p in b["diff_pairs"]}
    for pr in sorted(set(pa) & set(pb)):
        if pa[pr]["skew_mm"] != pb[pr]["skew_mm"]:
            lines.append(f"  pair {pr}: skew {pa[pr]['skew_mm']} -> "
                         f"{pb[pr]['skew_mm']} mm")

    ca = {(c["id"], c["message"]) for c in a.get("checks", [])}
    cb = {(c["id"], c["message"]) for c in b.get("checks", [])}
    for cid, msg in sorted(cb - ca, key=str):
        lines.append(f"  NEW  [{cid}] {msg}")
    for cid, msg in sorted(ca - cb, key=str):
        lines.append(f"  GONE [{cid}] {msg}")
    if len(lines) == 1:
        lines.append("  no differences worth reporting")
    return lines


def inspect(path: str | Path, out_dir: Path,
            min_clearance: float = C.CLEARANCE_DEFAULT,
            dt_c: float = C.DT_DEFAULT) -> dict:
    from .render import render_board
    board = parse_board(path)
    rep = analyze(board, min_clearance, dt_c)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    render_board(board, out / "board.png",
                 marks=rep["clearance_findings"][:20])
    rep["files"] = {"report": "report.json", "renders": ["board.png"]}
    (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n",
                                     encoding="utf-8")
    rep["_out_dir"] = str(out)
    return rep
