"""Parametric parts catalog — battle-tested components an agent should
compose with instead of re-deriving geometry from scratch.

`solidsight catalog` lists everything here with signatures and docs.
"""

from ..components_db import component
from .components import (bearing, cable_chain_link, cap_screw,
                         extrusion_profile, lead_screw, linear_carriage,
                         linear_rail, micro_servo, nema_motor, shaft,
                         spring, timing_pulley, washer)
from .enclosures import (box_with_lid, container, hex_grid, honeycomb_panel,
                         standoff)
from .features import bolt_circle, hole
from .gears import spur_gear
from .lofts import loft, wrapped_text
from .mechanisms import hinge, snap_clip, snap_slot
from .paths import swept, tube_path
from .patterns import circular_pattern, grid_pattern, linear_pattern
from .threads import ISO_COARSE_PITCH, bolt, iso_thread, nut

CATALOG = {
    "hole": hole,
    "bolt_circle": bolt_circle,
    "spur_gear": spur_gear,
    "iso_thread": iso_thread,
    "bolt": bolt,
    "nut": nut,
    "hinge": hinge,
    "snap_clip": snap_clip,
    "snap_slot": snap_slot,
    "box_with_lid": box_with_lid,
    "container": container,
    "standoff": standoff,
    "hex_grid": hex_grid,
    "tube_path": tube_path,
    "swept": swept,
    "loft": loft,
    "wrapped_text": wrapped_text,
    "honeycomb_panel": honeycomb_panel,
    "linear_pattern": linear_pattern,
    "grid_pattern": grid_pattern,
    "circular_pattern": circular_pattern,
    "component": component,
    "cap_screw": cap_screw,
    "washer": washer,
    "bearing": bearing,
    "shaft": shaft,
    "timing_pulley": timing_pulley,
    "spring": spring,
    "nema_motor": nema_motor,
    "micro_servo": micro_servo,
    "extrusion_profile": extrusion_profile,
    "lead_screw": lead_screw,
    "linear_rail": linear_rail,
    "linear_carriage": linear_carriage,
    "cable_chain_link": cable_chain_link,
}

__all__ = [*CATALOG.keys(), "CATALOG", "ISO_COARSE_PITCH"]
