"""pcbsight CLI — board review as measurement."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .errors import PCBSightError

_ASCII_FOLD = {ord(a): b for a, b in
               [("—", "-"), ("–", "-"), ("°", " deg"), ("·", "-"),
                ("…", "..."), ("×", "x"), ("→", "->")]}


def _say(text: str, err: bool = False) -> None:
    print(text.translate(_ASCII_FOLD), file=sys.stderr if err else sys.stdout,
          flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pcbsight",
        description="PCB review for AI agents: a .kicad_pcb in, exact "
                    "connectivity/clearance/current findings out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inspect", help="audit a board")
    i.add_argument("board", help="a .kicad_pcb file")
    i.add_argument("--clearance", type=float, default=0.2, metavar="MM",
                   help="minimum copper-to-copper clearance (default 0.2, "
                        "a common fab minimum - use YOUR fab's number)")
    i.add_argument("--dt", type=float, default=10.0, metavar="C",
                   help="allowed temperature rise for the IPC-2221 "
                        "current table (default 10)")
    i.add_argument("--out", default="out")
    i.add_argument("--json", action="store_true")

    z = sub.add_parser("impedance",
                       help="single-ended microstrip Z0 estimate")
    z.add_argument("width", type=float, help="trace width, mm")
    z.add_argument("height", type=float,
                   help="dielectric height to the reference plane, mm")
    z.add_argument("--er", type=float, default=4.5,
                   help="relative permittivity (FR4 ~4.2-4.7; default 4.5)")

    df = sub.add_parser("diff",
                        help="what changed between two boards (runs "
                             "inspect on both)")
    df.add_argument("a", help="the 'before' .kicad_pcb")
    df.add_argument("b", help="the 'after' .kicad_pcb")
    df.add_argument("--clearance", type=float, default=0.2, metavar="MM")
    df.add_argument("--dt", type=float, default=10.0, metavar="C")

    sub.add_parser("install-skill", help="(re)install the Claude Code skill")
    sub.add_parser("uninstall", help="remove the skill AND the package")
    sub.add_parser("version")

    args = p.parse_args(argv)
    if args.cmd not in ("install-skill", "uninstall"):
        from .skill_install import maybe_autoinstall
        maybe_autoinstall()

    try:
        if args.cmd == "version":
            _say(f"pcbsight {__version__}")
            return 0
        if args.cmd == "install-skill":
            from .skill_install import install_skill
            install_skill()
            return 0
        if args.cmd == "uninstall":
            from .skill_install import uninstall
            return uninstall()
        if args.cmd == "impedance":
            return _impedance(args)
        if args.cmd == "diff":
            return _diff(args)
        return _inspect(args)
    except PCBSightError as e:
        _say(f"FAILED\n{e.render()}", err=True)
        return 1


def _diff(args) -> int:
    from .board import parse_board
    from .report import analyze, diff_reports
    reps = [analyze(parse_board(p), args.clearance, args.dt)
            for p in (args.a, args.b)]
    for line in diff_reports(*reps):
        _say(line)
    return 0


def _impedance(args) -> int:
    from .checks import microstrip_z0
    z0 = microstrip_z0(args.width, args.height, er=args.er)
    _say(f"microstrip Z0 ~ {z0:.1f} ohm  (w={args.width} mm, "
         f"h={args.height} mm, er={args.er}, t=35 um)")
    _say("  note: IPC-2141 estimate, good to ~10%; for controlled "
         "impedance use the fab's field-solved stackup numbers")
    return 0


def _inspect(args) -> int:
    from pathlib import Path

    from .report import inspect
    rep = inspect(args.board, Path(args.out),
                  min_clearance=args.clearance, dt_c=args.dt)
    out = rep.pop("_out_dir")
    if args.json:
        print(json.dumps(rep, indent=2))
        return 2 if rep["status"] == "failed" else 0

    b = rep["board"]
    _say(f"pcbsight inspect: {rep['status'].upper()}")
    _say(f"  board: {b['source']} - {b['nets']} net(s), {b['tracks']} "
         f"track(s), {b['vias']} via(s), {b['pads']} pad(s), copper "
         f"{b['copper_um']} um")
    _say(f"  rules: clearance >= {rep['rules']['min_clearance_mm']} mm, "
         f"dT {rep['rules']['delta_t_c']} C")

    open_nets = [n for n in rep["connectivity"] if not n["routed"]]
    _say(f"  connectivity: {len(rep['connectivity']) - len(open_nets)}/"
         f"{len(rep['connectivity'])} nets fully routed")
    _say(f"  clearance: {len(rep['clearance_findings'])} finding(s)")
    for c in rep["current_capacity"]:
        _say(f"  current: '{c['net']}' min width {c['min_width_mm']} mm -> "
             f"{c['i_max_a']} A at dT={c['dt_c']}C ({c['layer_model']})")
    for pr in rep["diff_pairs"]:
        _say(f"  pair: {pr['pair']} - lengths {pr['length_mm']} mm, skew "
             f"{pr['skew_mm']} mm (~{pr['skew_ps_fr4']} ps)")

    for chk in [c for c in rep["checks"] if c["level"] == "fail"] + \
               [c for c in rep["checks"] if c["level"] == "warn"]:
        _say(f"  [{chk['level'].upper()}] {chk['message']}")
        if chk.get("where"):
            _say(f"         where: {chk['where']}")
        if chk.get("try"):
            _say(f"         try:   {chk['try']}")

    _say(f"  report: {out}/report.json")
    _say(f"  render: {out}/board.png")
    _say("  NEXT: LOOK at board.png (findings circled in red), then read "
         "report.json.")
    return 2 if rep["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
