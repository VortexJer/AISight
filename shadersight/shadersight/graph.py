"""Shader node graphs as graphs.

A node graph is judged by looking at the spaghetti. But the questions
that matter are graph theory: is there a cycle (it will not compile), is
anything unreachable from the output (you are paying for nothing), what
does it cost per pixel, and is any node's input left unconnected?

Input is a JSON graph — the lowest common denominator every DCC tool can
export:

    {"nodes": [{"id": "n1", "type": "multiply",
                "inputs": {"a": "n0.out", "b": 2.0}}],
     "output": "n1"}

An input value is either a literal or "<node_id>.<socket>".
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import BadGraphError

# Rough per-invocation cost in "ALU ops". These are ORDERS OF MAGNITUDE,
# not a vendor's instruction count: the point is that a texture fetch is
# ~100x an add and noise is ~50x, not that pow() is exactly 8.
NODE_COST = {
    "add": 1, "subtract": 1, "multiply": 1, "divide": 2, "clamp": 2,
    "min": 1, "max": 1, "abs": 1, "floor": 1, "fract": 1, "step": 1,
    "mix": 2, "lerp": 2, "dot": 2, "cross": 3, "normalize": 4,
    "length": 4, "distance": 4, "reflect": 4, "refract": 8,
    "pow": 8, "exp": 8, "log": 8, "sqrt": 4, "rsqrt": 2,
    "sin": 8, "cos": 8, "tan": 12, "atan": 16, "atan2": 16,
    "texture": 100, "texture_lod": 100, "texture_grad": 140,
    "cubemap": 120, "noise": 50, "voronoi": 120, "fbm": 200,
    "fresnel": 10, "ggx": 30, "brdf": 40,
    "constant": 0, "input": 0, "uv": 0, "normal": 0, "position": 0,
    "time": 0, "output": 0,
}
COST_BUDGET_WARN = 400          # per-pixel ALU: past this, question it


def parse_graph(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise BadGraphError(f"graph not found: {p}",
                            suggestion="check the path")
    try:
        g = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BadGraphError(f"{p.name} is not valid JSON: {e}") from e
    if not isinstance(g, dict) or "nodes" not in g:
        raise BadGraphError(
            f"{p.name} has no 'nodes' list",
            suggestion='expected {"nodes": [{"id":..., "type":..., '
                       '"inputs": {...}}], "output": "<id>"}')
    ids = [n.get("id") for n in g["nodes"]]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise BadGraphError(f"{p.name}: duplicate node id(s) {dupes}",
                            suggestion="node ids must be unique")
    if any(i is None for i in ids):
        raise BadGraphError(f"{p.name}: every node needs an 'id'")
    g.setdefault("name", p.stem)
    return g


def _links(node: dict) -> list[tuple[str, str, str]]:
    """(socket, source_id, source_socket) for each connected input."""
    out = []
    for socket, v in (node.get("inputs") or {}).items():
        if isinstance(v, str) and "." in v:
            src, _, ssock = v.partition(".")
            out.append((socket, src, ssock))
        elif isinstance(v, str):
            out.append((socket, v, "out"))
    return out


def analyze_graph(g: dict) -> dict:
    nodes = {n["id"]: n for n in g["nodes"]}
    output = g.get("output")
    checks: list[dict] = []

    def chk(id_, level, msg, where=None, try_=None):
        c = {"id": id_, "level": level, "message": msg}
        if where:
            c["where"] = where
        if try_:
            c["try"] = try_
        checks.append(c)

    # --- dangling references
    dangling = []
    for nid, n in nodes.items():
        for socket, src, _ss in _links(n):
            if src not in nodes:
                dangling.append((nid, socket, src))
    for nid, socket, src in dangling:
        chk("dangling-input", "fail",
            f"node '{nid}' input '{socket}' reads from '{src}', which does "
            f"not exist",
            where=f"node type {nodes[nid].get('type')}",
            try_="fix the id, or wire the socket to a real node/literal")

    # --- cycles (Kahn: whatever never reaches in-degree 0 is in a cycle)
    indeg = {nid: 0 for nid in nodes}
    adj: dict[str, list[str]] = {nid: [] for nid in nodes}
    for nid, n in nodes.items():
        for _s, src, _ss in _links(n):
            if src in nodes:
                adj[src].append(nid)
                indeg[nid] += 1
    queue = [nid for nid, d in indeg.items() if d == 0]
    order: list[str] = []
    d2 = dict(indeg)
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in adj[cur]:
            d2[nxt] -= 1
            if d2[nxt] == 0:
                queue.append(nxt)
    in_cycle = sorted(set(nodes) - set(order))
    if in_cycle:
        chk("graph-cycle", "fail",
            f"{len(in_cycle)} node(s) form a feedback cycle: the graph "
            f"cannot be evaluated",
            where=f"nodes: {', '.join(in_cycle)}",
            try_="a shader graph must be a DAG; break the loop (a value "
                 "cannot depend on itself within one pixel)")

    # --- reachability from the output
    reachable: set[str] = set()
    if output is None:
        chk("no-output", "fail", "the graph declares no 'output' node",
            try_='add "output": "<node id>" so the graph has a result')
    elif output not in nodes:
        chk("no-output", "fail",
            f"'output' points at '{output}', which does not exist",
            try_="point it at a real node id")
    else:
        stack = [output]
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            for _s, src, _ss in _links(nodes[cur]):
                if src in nodes:
                    stack.append(src)
        dead = sorted(set(nodes) - reachable)
        if dead:
            chk("dead-nodes", "warn",
                f"{len(dead)} node(s) do not reach the output: they are "
                f"computed for nothing",
                where=f"nodes: {', '.join(dead[:12])}"
                      + ("..." if len(dead) > 12 else ""),
                try_="delete them, or wire them in if they were meant to "
                     "be used")

    # --- unknown types (cost cannot be honest about what it never saw)
    unknown = sorted({n.get("type") for n in nodes.values()
                      if n.get("type") not in NODE_COST})
    if unknown:
        chk("unknown-node-type", "warn",
            f"{len(unknown)} node type(s) are not in the cost model: "
            f"{', '.join(str(u) for u in unknown[:8])}",
            try_="the cost estimate EXCLUDES them, so treat it as a lower "
                 "bound; add them to NODE_COST if you know their cost")

    # --- cost, counted only over what actually contributes
    live = reachable if reachable else set(nodes)
    per_type: dict[str, int] = {}
    total = 0
    for nid in live:
        t = nodes[nid].get("type")
        c = NODE_COST.get(t, 0)
        total += c
        per_type[str(t)] = per_type.get(str(t), 0) + c
    tex = sum(1 for nid in live
              if str(nodes[nid].get("type")).startswith(("texture", "cubemap")))
    if total > COST_BUDGET_WARN:
        chk("shader-cost-high", "warn",
            f"the live graph costs ~{total} ALU-equivalents per pixel "
            f"({tex} texture fetch(es))",
            where="dominant: " + ", ".join(
                f"{k} {v}" for k, v in sorted(per_type.items(),
                                              key=lambda kv: -kv[1])[:3]),
            try_="bake what is constant, move maths to the vertex stage or "
                 "a lookup texture, and check the fetch count first - a "
                 "fetch costs ~100x an add")

    fails = [c for c in checks if c["level"] == "fail"]
    return {
        "status": ("failed" if fails else
                   ("warnings" if checks else "ok")),
        "name": g.get("name", "graph"),
        "nodes": len(nodes),
        "output": output,
        "evaluation_order": order,
        "cycle_nodes": in_cycle,
        "reachable_nodes": len(reachable),
        "dead_nodes": sorted(set(nodes) - reachable) if reachable else [],
        "cost": {
            "alu_equivalents": total,
            "texture_fetches": tex,
            "by_type": dict(sorted(per_type.items(), key=lambda kv: -kv[1])),
            "counts_only_live_nodes": True,
            "excluded_unknown_types": unknown,
            "note": ("orders of magnitude, not a vendor instruction "
                     "count: a texture fetch is ~100x an add, noise ~50x. "
                     "Use it to compare graphs, never as a frame budget"),
        },
        "checks": checks,
    }
