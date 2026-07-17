"""Procedural BVH generator: humanoid parkour vault sequence (blind one-shot).

Approach run (4 left-foot strides) -> kong-style vault over a 0.9 m obstacle
(z = 620..660 cm, top at y = 90) -> right-foot landing with absorption dip ->
90-degree left turn -> two strides along +X -> settling stop with breathing.

240 frames @ 30 fps, centimeters, Y-up, character starts facing +Z (left = +X).
Rotation order is Yrotation Xrotation Zrotation for every joint (R = Ry.Rx.Rz),
so yaw is outermost on the root and the turn does not corrupt pitch/roll.

Legs are solved with analytic 2-bone IK against an authored ball-of-foot
contact schedule: stance = identical held keys -> feet exactly planted.
Late stance pivots the foot on the ball (heel raise) which extends toe-off
reach realistically; the toe joint counter-rotates to stay flat on ground.

Pure Python stdlib + numpy only.
"""

import bisect
import math
import os

import numpy as np

FPS = 30
NFRAMES = 240

L1 = 42.0            # thigh length (cm)
L2 = 42.0            # shin length (cm)
D_MIN, D_MAX = 21.7, 83.7   # hip->ankle distance clamp (knee flex ~150..8 deg)
HIP_OFF = {'L': np.array([9.0, -3.0, 0.0]), 'R': np.array([-9.0, -3.0, 0.0])}
BALL_OFF = np.array([0.0, -7.0, 13.0])   # ankle -> ball of foot, foot local


# ---------------------------------------------------------------- rotations

def rx(d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0, 0], [0, c, -s], [0, s, c]])


def ry(d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1.0, 0], [-s, 0, c]])


def rz(d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def euler_yxz(M):
    """Decompose M = Ry(y).Rx(x).Rz(z); returns degrees (y, x, z)."""
    sx = max(-1.0, min(1.0, -M[1, 2]))
    x = math.asin(sx)
    if abs(math.cos(x)) > 1e-6:
        y = math.atan2(M[0, 2], M[2, 2])
        z = math.atan2(M[1, 0], M[1, 1])
    else:
        y = math.atan2(-M[2, 0], M[0, 0])
        z = 0.0
    return math.degrees(y), math.degrees(x), math.degrees(z)


# ------------------------------------------------------------------ tracks

class Track:
    """Piecewise smoothstep (zero slope at keys). Identical neighbouring
    keys hold a value exactly -> planted feet do not slide."""

    def __init__(self, keys):
        ks = sorted(keys, key=lambda k: k[0])
        dd = []
        for t, v in ks:
            if dd and abs(t - dd[-1][0]) < 1e-9:
                dd[-1] = (t, v)          # last one wins on duplicate times
            else:
                dd.append((t, v))
        self.t = [k[0] for k in dd]
        self.v = [k[1] for k in dd]

    def __call__(self, t):
        ts, vs = self.t, self.v
        if t <= ts[0]:
            return vs[0]
        if t >= ts[-1]:
            return vs[-1]
        i = bisect.bisect_right(ts, t) - 1
        s = (t - ts[i]) / (ts[i + 1] - ts[i])
        u = s * s * (3.0 - 2.0 * s)
        return vs[i] + (vs[i + 1] - vs[i]) * u


class CRTrack:
    """Cubic Hermite with finite-difference tangents (Catmull-Rom style):
    continuous velocity for root translation / yaw."""

    def __init__(self, keys):
        ks = sorted(keys, key=lambda k: k[0])
        self.t = [k[0] for k in ks]
        self.v = [k[1] for k in ks]
        n = len(self.t)
        m = [0.0] * n
        for i in range(n):
            if i == 0:
                m[i] = (self.v[1] - self.v[0]) / (self.t[1] - self.t[0])
            elif i == n - 1:
                m[i] = (self.v[-1] - self.v[-2]) / (self.t[-1] - self.t[-2])
            else:
                m[i] = (self.v[i + 1] - self.v[i - 1]) / (self.t[i + 1] - self.t[i - 1])
        self.m = m

    def __call__(self, t):
        ts, vs, ms = self.t, self.v, self.m
        if t <= ts[0]:
            return vs[0]
        if t >= ts[-1]:
            return vs[-1]
        i = bisect.bisect_right(ts, t) - 1
        h = ts[i + 1] - ts[i]
        s = (t - ts[i]) / h
        h00 = 2 * s ** 3 - 3 * s ** 2 + 1
        h10 = s ** 3 - 2 * s ** 2 + s
        h01 = -2 * s ** 3 + 3 * s ** 2
        h11 = s ** 3 - s ** 2
        return h00 * vs[i] + h10 * h * ms[i] + h01 * vs[i + 1] + h11 * h * ms[i + 1]


# ----------------------------------------------------------- foot schedule
# contact = (t_down, t_up, ball_x, ball_z, foot_yaw_deg, toeoff_pitch_deg)

CONTACTS_L = [
    (0.20, 0.40,   9.0,  50.0,  0.0, 35.0),   # approach stride 1
    (1.00, 1.20,   9.0, 285.0,  0.0, 35.0),   # approach stride 2
    (1.80, 2.05,   9.0, 535.0,  0.0, 45.0),   # takeoff punch step
    (2.95, 3.42,  12.0, 805.0, 10.0, 20.0),   # landing second foot / absorb
    (3.85, 4.18,  49.0, 855.0, 75.0, 25.0),   # pivot step 2
    (4.80, 5.12, 170.0, 872.0, 90.0, 25.0),   # outbound stride 2
    (5.62, 9.00, 232.0, 872.0, 90.0,  0.0),   # closing step, held to end
]
CONTACTS_R = [
    (-0.50, 0.10,  -9.0, -20.0,  0.0, 35.0),  # already planted at frame 0
    (0.60, 0.80,   -9.0, 165.0,  0.0, 35.0),
    (1.40, 1.62,   -9.0, 410.0,  0.0, 40.0),  # last plant before takeoff
    (2.72, 3.05,  -10.0, 745.0,  0.0, 15.0),  # vault landing foot
    (3.45, 3.80,    8.0, 846.0, 40.0, 25.0),  # pivot step 1
    (4.30, 4.62,  105.0, 884.0, 90.0, 25.0),  # outbound stride 1
    (5.30, 9.00,  225.0, 888.0, 90.0,  0.0),  # settle step, held to end
]

# Tuck waypoints for the swing that crosses the obstacle (after contact idx 2).
# (time, ball_x, ball_y, ball_z) -- checked against faces z=620/660, top y=90.
VAULT_L = {2: [(2.20, 9.0, 87.0, 606.0),
               (2.36, 10.0, 97.0, 648.0),
               (2.65, 12.0, 52.0, 742.0)]}
VAULT_R = {2: [(1.90, -9.0, 55.0, 565.0),
               (2.14, -11.0, 96.0, 622.0),
               (2.30, -12.0, 99.0, 655.0),
               (2.50, -11.0, 60.0, 715.0)]}


def build_foot(contacts, vault, pre_pos=None, pre_pitch=None):
    px, py, pz, pp, pyaw = [], [], [], [], []
    if pre_pos is not None:
        t0, x0, y0, z0 = pre_pos
        px.append((t0, x0)); py.append((t0, y0)); pz.append((t0, z0))
    if pre_pitch is not None:
        pp.append(pre_pitch)
    for i, (td, tu, bx, bz, yw, poff) in enumerate(contacts):
        for tt in (td, tu):
            px.append((tt, bx)); py.append((tt, 0.0)); pz.append((tt, bz))
            pyaw.append((tt, yw))
        pp.append((td, 0.0))
        pp.append((td + 0.65 * (tu - td), 0.0))
        pp.append((tu, poff))
        if i + 1 < len(contacts):
            tdn = contacts[i + 1][0]
            T = tdn - tu
            wps = vault.get(i)
            if wps:
                for (tw, wx, wy, wz) in wps:
                    px.append((tw, wx)); py.append((tw, wy)); pz.append((tw, wz))
            else:
                tm = tu + 0.45 * T
                nx, nz = contacts[i + 1][2], contacts[i + 1][3]
                px.append((tm, bx + 0.55 * (nx - bx)))
                pz.append((tm, bz + 0.55 * (nz - bz)))
                py.append((tm, 22.0))
            pp.append((tu + 0.30 * T, 0.30 * poff))
            pp.append((tu + 0.60 * T, -8.0))       # dorsiflex through swing
            pp.append((tdn, 0.0))                  # flat midfoot strike
    return (Track(px), Track(py), Track(pz), Track(pp), Track(pyaw))


FOOT_L = build_foot(CONTACTS_L, VAULT_L,
                    pre_pos=(0.0, 9.0, 14.0, 20.0), pre_pitch=(0.0, -4.0))
FOOT_R = build_foot(CONTACTS_R, VAULT_R)


# ------------------------------------------------------------- root tracks

ROOT_X = CRTrack([(0, 0), (1.0, 0), (2.0, 0), (2.9, 0), (3.3, 4), (3.6, 14),
                  (3.9, 35), (4.15, 58), (4.4, 85), (4.8, 150), (5.1, 185),
                  (5.3, 203), (5.62, 220), (5.9, 226), (6.5, 228), (8.0, 228)])
ROOT_Z = CRTrack([(0, 0), (0.2, 35), (0.6, 150), (1.0, 270), (1.4, 395),
                  (1.8, 520), (2.05, 548), (2.35, 645), (2.72, 738),
                  (2.95, 775), (3.1, 790), (3.3, 812), (3.6, 838), (3.9, 858),
                  (4.15, 866), (4.4, 872), (4.8, 880), (5.3, 884),
                  (5.62, 883), (5.9, 881), (6.5, 880), (8.0, 880)])
ROOT_Y = Track([(0, 89), (0.30, 86.5), (0.45, 91), (0.70, 86.5), (0.85, 91),
                (1.10, 86.5), (1.25, 91), (1.50, 86.5), (1.65, 91),
                (1.90, 86), (2.05, 95), (2.35, 126), (2.60, 108), (2.72, 92),
                (3.10, 74), (3.45, 82), (3.60, 86), (3.95, 84.5), (4.10, 88),
                (4.40, 84.5), (4.55, 88), (4.90, 85), (5.05, 88), (5.30, 87),
                (5.62, 89), (6.00, 90.5), (6.60, 91.5), (7.20, 90.8),
                (7.80, 91.2), (8.00, 91.0)])
ROOT_YAW = CRTrack([(0, 0), (2.8, 0), (3.0, 5), (3.2, 14), (3.6, 40),
                    (4.0, 68), (4.3, 84), (4.6, 90), (5.0, 90), (8.0, 90)])
ROOT_PITCH = Track([(0, 5), (1.8, 7), (2.0, 3), (2.2, 15), (2.35, 24),
                    (2.55, 18), (2.72, 8), (3.10, 14), (3.6, 8), (4.2, 5),
                    (5.0, 4), (5.9, 2), (6.6, 1), (8.0, 1)])
ROOT_ROLL = Track([(0, 0), (2.9, 0), (3.3, -6), (3.9, -8), (4.4, -3),
                   (4.8, 0), (8.0, 0)])
SWAY = Track([(0.10, -2), (0.30, 2), (0.70, -2), (1.10, 2), (1.50, -2),
              (1.92, 3), (2.4, 0), (2.85, -2), (3.15, 2), (3.6, -2),
              (4.0, 2), (4.45, -2), (4.95, 2), (5.4, -1), (5.9, 0), (8.0, 0)])
STEP_YAW = Track([(0.2, -3), (0.6, 3), (1.0, -3), (1.4, 3), (1.8, -4),
                  (2.05, 0), (2.72, 3), (2.95, -3), (3.45, 3), (3.85, -3),
                  (4.3, 3), (4.8, -3), (5.3, 2), (5.65, 0), (8.0, 0)])

# ------------------------------------------------------------ torso / head

SPINE_PITCH = Track([(0, 4), (1.9, 5), (2.1, 8), (2.35, 13), (2.7, 9),
                     (3.1, 12), (3.6, 7), (4.5, 4), (5.9, 3), (6.6, 2), (8, 2)])
CHEST_PITCH = Track([(0, 4), (1.9, 5), (2.1, 7), (2.35, 11), (2.7, 8),
                     (3.1, 10), (3.6, 6), (4.5, 4), (5.9, 3), (6.6, 2), (8, 2)])
CHEST_YAW_X = Track([(2.9, 0), (3.3, 10), (4.1, 6), (4.6, 0), (8, 0)])
NECK_PITCH = Track([(0, -5), (1.6, -4), (2.0, -12), (2.35, -22), (2.72, -12),
                    (3.1, -12), (3.6, -7), (4.5, -4), (5.9, -2), (8, -2)])
HEAD_PITCH = Track([(0, -3), (2.35, -12), (2.72, -6), (3.1, -6), (4.5, -2),
                    (8, -1)])
LOOK_YAW = Track([(0, 0), (2.6, 0), (3.0, 22), (3.6, 28), (4.1, 10),
                  (4.6, 0), (8, 0)])

# -------------------------------------------------------------------- arms
# Arm X swing: forward = negative (both sides). Arm Z: drop from T-pose,
# negative for left, positive for right. Elbow flex: negative Y left,
# positive Y right.

LARM_X = Track([(0.2, 28), (0.6, -32), (1.0, 28), (1.4, -32), (1.8, 20),
                (1.95, 35), (2.1, -45), (2.25, -75), (2.45, -95), (2.62, -55),
                (2.8, -22), (3.1, -28), (3.45, -25), (3.85, 20), (4.3, -20),
                (4.8, 16), (5.3, -10), (5.7, 4), (6.3, 2), (8, 2)])
RARM_X = Track([(0.2, -32), (0.6, 28), (1.0, -32), (1.4, 28), (1.8, -25),
                (1.95, 32), (2.1, -48), (2.25, -78), (2.45, -92), (2.62, -52),
                (2.8, -25), (3.1, -28), (3.45, 22), (3.85, -22), (4.3, 18),
                (4.8, -16), (5.3, 8), (5.7, -4), (6.3, 1), (8, 1)])
LARM_Z = Track([(0, -66), (1.9, -62), (2.1, -50), (2.45, -48), (2.75, -55),
                (3.1, -45), (3.7, -60), (4.8, -65), (5.9, -70), (8, -71)])
RARM_Z = Track([(0, 66), (1.9, 62), (2.1, 50), (2.45, 48), (2.75, 55),
                (3.1, 45), (3.7, 60), (4.8, 65), (5.9, 70), (8, 71)])
LELB_Y = Track([(0, -78), (1.9, -70), (2.05, -30), (2.2, -12), (2.5, -10),
                (2.7, -35), (3.0, -55), (3.4, -70), (4.8, -75), (5.4, -60),
                (6.2, -28), (8, -22)])
RELB_Y = Track([(0, 78), (1.9, 70), (2.05, 30), (2.2, 12), (2.5, 10),
                (2.7, 35), (3.0, 55), (3.4, 70), (4.8, 75), (5.4, 60),
                (6.2, 28), (8, 22)])


# --------------------------------------------------------------------- IK

def leg_ik(hip_w, ankle_w, Rh):
    """2-bone leg IK in the hips frame. Pole = hips-local forward (+Z).
    Returns (thigh rotation matrix in hips frame, knee flex degrees)."""
    tl = Rh.T @ (ankle_w - hip_w)
    d = float(np.linalg.norm(tl))
    if d < 1e-6:
        tl = np.array([0.0, -1.0, 0.0]); d = 1e-6
    that = tl / d
    d = max(D_MIN, min(D_MAX, d))
    cphi = (L1 * L1 + L2 * L2 - d * d) / (2 * L1 * L2)
    knee = 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, cphi))))
    ca = (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)
    alpha = math.acos(max(-1.0, min(1.0, ca)))
    pole = np.array([0.0, 0.0, 1.0])
    n = np.cross(that, pole)
    nn = float(np.linalg.norm(n))
    n = n / nn if nn > 1e-6 else np.array([-1.0, 0.0, 0.0])
    w = np.cross(n, that)                       # unit, toward pole
    thigh = math.cos(alpha) * that + math.sin(alpha) * w
    Xt = -n
    Yt = -thigh
    Zt = np.cross(Xt, Yt)
    M = np.column_stack([Xt, Yt, Zt])           # rest pose -> identity
    return M, knee


# ---------------------------------------------------------------- skeleton

def node(name, off, children=(), end=None):
    return (name, off, children, end)


SKEL = node("Hips", (0, 0, 0), (
    node("Spine", (0, 10, 0), (
        node("Chest", (0, 15, 0), (
            node("Neck", (0, 22, 0), (
                node("Head", (0, 10, 0), (), (0, 18, 0)),)),
            node("LeftShoulder", (3, 18, 0), (
                node("LeftArm", (13, 0, 0), (
                    node("LeftForeArm", (29, 0, 0), (
                        node("LeftHand", (26, 0, 0), (), (17, 0, 0)),)),)),)),
            node("RightShoulder", (-3, 18, 0), (
                node("RightArm", (-13, 0, 0), (
                    node("RightForeArm", (-29, 0, 0), (
                        node("RightHand", (-26, 0, 0), (), (-17, 0, 0)),)),)),)),
        )),)),
    node("LeftUpLeg", (9, -3, 0), (
        node("LeftLeg", (0, -42, 0), (
            node("LeftFoot", (0, -42, 0), (
                node("LeftToeBase", (0, -7, 13), (), (0, 0, 7)),)),)),)),
    node("RightUpLeg", (-9, -3, 0), (
        node("RightLeg", (0, -42, 0), (
            node("RightFoot", (0, -42, 0), (
                node("RightToeBase", (0, -7, 13), (), (0, 0, 7)),)),)),)),
))


def joint_order(nd, out):
    out.append(nd[0])
    for c in nd[2]:
        joint_order(c, out)
    return out


JOINTS = joint_order(SKEL, [])


def write_hierarchy(nd, depth, lines, is_root):
    ind = "\t" * depth
    lines.append("%s%s %s" % (ind, "ROOT" if is_root else "JOINT", nd[0]))
    lines.append(ind + "{")
    ind2 = "\t" * (depth + 1)
    lines.append("%sOFFSET %.4f %.4f %.4f" % (ind2, nd[1][0], nd[1][1], nd[1][2]))
    if is_root:
        lines.append(ind2 + "CHANNELS 6 Xposition Yposition Zposition "
                            "Yrotation Xrotation Zrotation")
    else:
        lines.append(ind2 + "CHANNELS 3 Yrotation Xrotation Zrotation")
    for c in nd[2]:
        write_hierarchy(c, depth + 1, lines, False)
    if nd[3] is not None:
        lines.append(ind2 + "End Site")
        lines.append(ind2 + "{")
        lines.append("%sOFFSET %.4f %.4f %.4f"
                     % ("\t" * (depth + 2), nd[3][0], nd[3][1], nd[3][2]))
        lines.append(ind2 + "}")
    lines.append(ind + "}")


# ------------------------------------------------------------- frame build

def frame_values(t):
    yaw = ROOT_YAW(t) + STEP_YAW(t)
    pitch = ROOT_PITCH(t)
    roll = ROOT_ROLL(t)
    Rh = ry(yaw) @ rx(pitch) @ rz(roll)
    pos = np.array([ROOT_X(t), ROOT_Y(t), ROOT_Z(t)])
    pos = pos + ry(yaw) @ np.array([SWAY(t), 0.0, 0.0])

    step = STEP_YAW(t)
    look = LOOK_YAW(t)

    vals = {}
    vals["Hips"] = [pos[0], pos[1], pos[2], yaw, pitch, roll]
    vals["Spine"] = [-0.6 * step, SPINE_PITCH(t), 0.0]
    vals["Chest"] = [-1.2 * step + CHEST_YAW_X(t), CHEST_PITCH(t), 0.0]
    vals["Neck"] = [0.5 * look, NECK_PITCH(t), 0.0]
    vals["Head"] = [0.5 * look, HEAD_PITCH(t), 0.0]
    vals["LeftShoulder"] = [0.0, 0.0, 0.0]
    vals["RightShoulder"] = [0.0, 0.0, 0.0]
    vals["LeftArm"] = [0.0, LARM_X(t), LARM_Z(t)]
    vals["RightArm"] = [0.0, RARM_X(t), RARM_Z(t)]
    vals["LeftForeArm"] = [LELB_Y(t), 0.0, 0.0]
    vals["RightForeArm"] = [RELB_Y(t), 0.0, 0.0]
    vals["LeftHand"] = [0.0, 0.0, 0.0]
    vals["RightHand"] = [0.0, 0.0, 0.0]

    for side, foot, names in (
            ('L', FOOT_L, ("LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase")),
            ('R', FOOT_R, ("RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"))):
        fx, fy, fz, fp, fyw = foot
        ball = np.array([fx(t), fy(t), fz(t)])
        fpitch = fp(t)
        fyaw = fyw(t)
        Rf = ry(fyaw) @ rx(fpitch)
        ankle = ball - Rf @ BALL_OFF
        hip_w = pos + Rh @ HIP_OFF[side]
        M, knee = leg_ik(hip_w, ankle, Rh)
        ty, tx, tz = euler_yxz(M)
        vals[names[0]] = [ty, tx, tz]
        vals[names[1]] = [0.0, knee, 0.0]
        R_shin_w = Rh @ M @ rx(knee)
        Ra = R_shin_w.T @ Rf
        ay, ax, az = euler_yxz(Ra)
        vals[names[2]] = [ay, ax, az]
        vals[names[3]] = [0.0, -0.9 * max(fpitch, 0.0), 0.0]

    row = []
    for j in JOINTS:
        row.extend(vals[j])
    return row


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "parkour_blind.bvh")

    lines = ["HIERARCHY"]
    write_hierarchy(SKEL, 0, lines, True)
    lines.append("MOTION")
    lines.append("Frames: %d" % NFRAMES)
    lines.append("Frame Time: %.7f" % (1.0 / FPS))

    n_channels = 6 + 3 * (len(JOINTS) - 1)
    for f in range(NFRAMES):
        t = f / float(FPS)
        row = frame_values(t)
        assert len(row) == n_channels, (len(row), n_channels)
        assert all(math.isfinite(v) for v in row), "non-finite value frame %d" % f
        lines.append(" ".join("%.4f" % v for v in row))

    with open(out_path, "w", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    print("Wrote %s" % out_path)
    print("Joints (%d): %s" % (len(JOINTS), ", ".join(JOINTS)))
    print("Frames: %d @ %d fps -> %.2f s, %d channels/frame"
          % (NFRAMES, FPS, NFRAMES / float(FPS), n_channels))


if __name__ == "__main__":
    main()
