"""animationsight — animation review built exclusively for AI agents.

An agent cannot watch an animation. It can read numbers. So: a clip in,
and out come exact velocities, accelerations, jerk, angular rates,
contact events, foot sliding, balance against the support base, ground
penetration, smoothness and loop continuity — plus renders of the exact
frames the findings point at.

    from animationsight import parse_bvh, analyze
    clip = parse_bvh("walk.bvh", unit="cm")
    report = analyze(clip, up="y")
"""

__version__ = "0.6.0"

from .bvh import Clip, Joint, forward_kinematics, parse_bvh
from .errors import AnimationSightError, BadArgumentError, BadClipError
from .report import analyze, diff_reports, inspect_clip

__all__ = [
    "parse_bvh", "forward_kinematics", "Clip", "Joint",
    "analyze", "inspect_clip", "diff_reports",
    "AnimationSightError", "BadClipError", "BadArgumentError",
]
