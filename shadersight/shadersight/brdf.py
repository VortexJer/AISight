"""BRDFs as mathematics, evaluated on a hemisphere.

A shader is judged by rendering a sphere and looking at it. But the
things that are actually WRONG with a material are laws, not opinions:

  * energy conservation - a surface must not reflect more light than it
    receives (white furnace test);
  * Helmholtz reciprocity - f(wi, wo) == f(wo, wi), always;
  * positivity - a BRDF is never negative.

All three are integrals and identities over the hemisphere, so they are
arithmetic. This module evaluates them deterministically.

Convention: local shading frame, normal = +Z, directions are unit
vectors with wz > 0, and f() returns the BRDF value (per channel).
"""

from __future__ import annotations

import numpy as np

from .errors import BadModelError


def hemisphere_grid(n_theta: int = 64, n_phi: int = 128
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Directions + solid-angle weights covering the hemisphere.

    Cosine-free: the weights are dw = sin(theta) dtheta dphi, so the
    caller multiplies by cos(theta) where the physics asks for it and
    nowhere else. Midpoint rule in both angles; deterministic, and the
    resolution is reported so nobody mistakes a coarse grid for a proof.
    """
    th = (np.arange(n_theta) + 0.5) * (np.pi / 2) / n_theta
    ph = (np.arange(n_phi) + 0.5) * (2 * np.pi) / n_phi
    dth = (np.pi / 2) / n_theta
    dph = (2 * np.pi) / n_phi

    T, P = np.meshgrid(th, ph, indexing="ij")
    dirs = np.stack([np.sin(T) * np.cos(P), np.sin(T) * np.sin(P),
                     np.cos(T)], axis=-1).reshape(-1, 3)
    w = (np.sin(T) * dth * dph).reshape(-1)
    return dirs, w


def _as_dir(v) -> np.ndarray:
    a = np.asarray(v, dtype=float)
    n = np.linalg.norm(a)
    if n < 1e-12:
        raise BadModelError("direction vector is zero-length")
    return a / n


# ---------------------------------------------------------------------------
# the standard microfacet pieces, written out so they can be checked
# ---------------------------------------------------------------------------

def d_ggx(cos_h: np.ndarray, alpha: float) -> np.ndarray:
    """Trowbridge-Reitz (GGX) normal distribution. Normalised so that
    the integral of D * cos over the hemisphere is 1 — which
    `test_ggx_distribution_is_normalised` checks rather than trusting."""
    a2 = alpha * alpha
    d = cos_h * cos_h * (a2 - 1.0) + 1.0
    return a2 / (np.pi * d * d + 1e-16)


def g_smith_ggx(cos_i: np.ndarray, cos_o: np.ndarray,
                alpha: float) -> np.ndarray:
    """Smith height-correlated masking-shadowing (Heitz 2014), the
    denominator folded in as in the usual 'visibility' form."""
    a2 = alpha * alpha
    li = cos_o * np.sqrt(cos_i * cos_i * (1 - a2) + a2)
    lo = cos_i * np.sqrt(cos_o * cos_o * (1 - a2) + a2)
    return 0.5 / (li + lo + 1e-16)


def f_schlick(f0: np.ndarray, cos_d: np.ndarray) -> np.ndarray:
    return f0 + (1.0 - f0) * np.power(np.clip(1.0 - cos_d, 0.0, 1.0), 5.0)


class Material:
    """A standard metallic-roughness PBR material.

    This is the model 90 % of real shaders are, written explicitly so
    its properties can be measured instead of assumed.
    """

    def __init__(self, base_color=(0.8, 0.8, 0.8), roughness: float = 0.5,
                 metallic: float = 0.0, specular: float = 0.5,
                 name: str = "material"):
        bc = np.asarray(base_color, dtype=float)
        if bc.shape != (3,):
            raise BadModelError(
                f"base_color must be 3 numbers, got {base_color!r}")
        if np.any(bc < 0) or np.any(bc > 1):
            raise BadModelError(
                f"base_color {tuple(bc)} is outside 0..1",
                suggestion="a base colour above 1.0 creates energy from "
                           "nothing; real dielectrics sit around 0.04-0.9")
        for nm, v in (("roughness", roughness), ("metallic", metallic),
                      ("specular", specular)):
            if not 0.0 <= v <= 1.0:
                raise BadModelError(f"{nm} must be in 0..1, got {v}")
        self.base_color = bc
        self.roughness = float(roughness)
        self.metallic = float(metallic)
        self.specular = float(specular)
        self.name = name

    @property
    def alpha(self) -> float:
        # the near-universal remap: perceptual roughness -> GGX alpha
        return max(self.roughness ** 2, 1e-4)

    @property
    def f0(self) -> np.ndarray:
        dielectric = 0.08 * self.specular
        return (dielectric * (1.0 - self.metallic)
                + self.base_color * self.metallic)

    @property
    def diffuse_albedo(self) -> np.ndarray:
        return self.base_color * (1.0 - self.metallic)

    def eval(self, wi: np.ndarray, wo: np.ndarray) -> np.ndarray:
        """BRDF value for incoming wi and outgoing wo (both (N,3) or
        (3,)). Returns (N,3): Lambert diffuse + GGX specular."""
        wi = np.atleast_2d(wi)
        wo = np.atleast_2d(wo)
        wi, wo = np.broadcast_arrays(wi, wo)
        cos_i = wi[:, 2]
        cos_o = wo[:, 2]
        out = np.zeros((len(wi), 3))
        ok = (cos_i > 1e-6) & (cos_o > 1e-6)
        if not ok.any():
            return out

        h = wi[ok] + wo[ok]
        hn = np.linalg.norm(h, axis=1, keepdims=True)
        h = h / np.maximum(hn, 1e-12)
        cos_h = np.clip(h[:, 2], 0.0, 1.0)
        cos_d = np.clip(np.sum(wi[ok] * h, axis=1), 0.0, 1.0)

        D = d_ggx(cos_h, self.alpha)
        G = g_smith_ggx(cos_i[ok], cos_o[ok], self.alpha)
        F = f_schlick(self.f0[None, :], cos_d[:, None])
        spec = F * (D * G)[:, None]

        # Coupled diffuse (Ashikhmin-Shirley 2000): the naive
        # Lambert*(1-F) coupling VIOLATES energy conservation at grazing
        # angles — the specular there reflects nearly everything while
        # diffuse keeps adding its full lobe (this very implementation
        # measured itself at 1.478x at 85 deg before the change; many
        # real engine materials share the defect). The A-S term rolls
        # the diffuse off toward grazing symmetrically in wi and wo, so
        # it is reciprocal and stays under the ceiling with a Fresnel
        # specular on top.
        rho = self.diffuse_albedo[None, :]
        f0m = self.f0[None, :]
        roll_i = 1.0 - np.power(1.0 - cos_i[ok] / 2.0, 5.0)
        roll_o = 1.0 - np.power(1.0 - cos_o[ok] / 2.0, 5.0)
        diff = (28.0 / (23.0 * np.pi)) * rho * (1.0 - f0m) \
            * (roll_i * roll_o)[:, None]
        out[ok] = diff + spec
        return out


# ---------------------------------------------------------------------------
# the laws
# ---------------------------------------------------------------------------

def directional_albedo(mat: Material, wo, n_theta: int = 64,
                       n_phi: int = 128, seed: int = 12345) -> np.ndarray:
    """Integral of f(wi, wo) * cos(theta_i) dwi over the hemisphere.

    The fraction of incoming energy the surface sends back for one view
    direction — the white furnace test; physics says <= 1.

    Computed by MULTIPLE IMPORTANCE SAMPLING, not a uniform grid. A
    uniform grid cannot see the narrow specular peak of a smooth
    surface: at roughness 0.02 it read this integral as 0.02 (miss) or
    1.19 (Riemann overshoot) depending only on resolution. GGX + cosine
    sampling under the balance heuristic gives a low-variance estimate
    at every roughness, and a FIXED seed keeps it deterministic. The
    sample count scales with the requested grid size.
    """
    wo = _as_dir(wo)
    ns = max(4096, n_theta * n_phi)
    rng = np.random.default_rng(seed)
    a = mat.alpha

    # --- strategy 1: sample the GGX half-vector, reflect wo about it
    u1, u2 = rng.random(ns), rng.random(ns)
    ct = np.sqrt((1.0 - u1) / (1.0 + (a * a - 1.0) * u1))     # cos(theta_h)
    st = np.sqrt(np.clip(1.0 - ct * ct, 0.0, 1.0))
    ph = 2 * np.pi * u2
    h = np.stack([st * np.cos(ph), st * np.sin(ph), ct], axis=1)
    wi_g = 2.0 * np.sum(wo * h, axis=1, keepdims=True) * h - wo

    # --- strategy 2: cosine-weighted hemisphere
    u3, u4 = rng.random(ns), rng.random(ns)
    r = np.sqrt(u3)
    phi = 2 * np.pi * u4
    wi_c = np.stack([r * np.cos(phi), r * np.sin(phi),
                     np.sqrt(np.clip(1.0 - u3, 0.0, 1.0))], axis=1)

    def pdf_ggx(wi):
        hh = wi + wo
        hn = np.linalg.norm(hh, axis=1, keepdims=True)
        hh = hh / np.maximum(hn, 1e-12)
        ch = np.clip(hh[:, 2], 0.0, 1.0)
        d = d_ggx(ch, a)
        odh = np.abs(np.sum(wo * hh, axis=1))
        return d * ch / np.maximum(4.0 * odh, 1e-9)

    def pdf_cos(wi):
        return np.clip(wi[:, 2], 0.0, None) / np.pi

    est = np.zeros(3)
    wo_t = np.tile(wo, (ns, 1))
    for wi in (wi_g, wi_c):
        valid = wi[:, 2] > 1e-6
        if not valid.any():
            continue
        wv = wi[valid]
        f = mat.eval(wv, wo_t[valid])                # (M,3)
        pg = pdf_ggx(wv)
        pc = pdf_cos(wv)
        w_mis = np.maximum(pg + pc, 1e-12)           # balance heuristic
        est += np.einsum("mc,m->c", f, wv[:, 2] / w_mis)
    return est / ns


def energy_conservation(mat: Material, n_theta: int = 64, n_phi: int = 128,
                        n_views: int = 12) -> dict:
    """Directional albedo at a sweep of view angles.

    A single grazing angle is the usual place a material blows past 1,
    so sweep instead of testing one direction and calling it physical.
    """
    angles = np.linspace(0.0, np.radians(85.0), n_views)
    rows = []
    worst = -1.0
    worst_at = 0.0
    for a in angles:
        wo = (np.sin(a), 0.0, np.cos(a))
        alb = directional_albedo(mat, wo, n_theta, n_phi)
        m = float(alb.max())
        rows.append({"theta_deg": round(float(np.degrees(a)), 2),
                     "albedo_rgb": [round(float(v), 5) for v in alb],
                     "max_channel": round(m, 5)})
        if m > worst:
            worst, worst_at = m, float(np.degrees(a))
    return {
        "per_view": rows,
        "max_albedo": round(worst, 5),
        "max_at_theta_deg": round(worst_at, 2),
        "conserves_energy": bool(worst <= 1.0 + 1e-3),
        "grid": {"n_theta": n_theta, "n_phi": n_phi, "n_views": n_views},
        "note": ("directional albedo = integral of f*cos over the "
                 "hemisphere; >1 means the surface emits energy it never "
                 "received. Values slightly under 1 at grazing angles are "
                 "expected: single-scattering GGX loses energy there"),
    }


def reciprocity(mat: Material, n_samples: int = 4096,
                seed: int = 7) -> dict:
    """Helmholtz reciprocity: f(wi, wo) must equal f(wo, wi).

    Not a preference — a physical law, and a BRDF that breaks it is
    wrong in any renderer. Sampled on a FIXED seed so the test is
    reproducible.
    """
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n_samples, 3))
    b = rng.normal(size=(n_samples, 3))
    a[:, 2] = np.abs(a[:, 2])
    b[:, 2] = np.abs(b[:, 2])
    a /= np.linalg.norm(a, axis=1, keepdims=True)
    b /= np.linalg.norm(b, axis=1, keepdims=True)

    fab = mat.eval(a, b)
    fba = mat.eval(b, a)
    denom = np.maximum(np.abs(fab) + np.abs(fba), 1e-9)
    rel = np.abs(fab - fba) / denom
    i = int(np.argmax(rel.max(axis=1)))
    return {
        "max_relative_error": round(float(rel.max()), 8),
        "mean_relative_error": round(float(rel.mean()), 8),
        "worst_pair": {"wi": [round(float(v), 4) for v in a[i]],
                       "wo": [round(float(v), 4) for v in b[i]]},
        "samples": n_samples, "seed": seed,
        "reciprocal": bool(rel.max() < 1e-6),
        "note": "f(wi,wo) == f(wo,wi) is a physical law, not a style",
    }


def positivity(mat: Material, n_theta: int = 32, n_phi: int = 64) -> dict:
    """A BRDF is never negative. Negative lobes come from a sign slip or
    an over-eager artistic 'energy compensation' term, and they punch
    black holes into the lighting."""
    dirs, _w = hemisphere_grid(n_theta, n_phi)
    worst = 0.0
    n_bad = 0
    for k in range(0, len(dirs), max(1, len(dirs) // 16)):
        f = mat.eval(dirs, np.tile(dirs[k], (len(dirs), 1)))
        n_bad += int((f < -1e-9).sum())
        worst = min(worst, float(f.min()))
    return {"min_value": round(worst, 9), "negative_samples": n_bad,
            "non_negative": bool(n_bad == 0)}


def furnace_residual(mat: Material, n_theta: int = 64,
                     n_phi: int = 128) -> dict:
    """How much energy single-scattering GGX loses at each roughness.

    This is NOT a bug in the material — it is a known limitation of the
    single-scattering model (multiple bounces between microfacets are
    not simulated), and it is why rough metals look too dark without a
    multi-scatter term. Reporting it stops an agent from 'fixing' a
    material that is behaving exactly as the model dictates.
    """
    wo = (0.0, 0.0, 1.0)
    alb = directional_albedo(mat, wo, n_theta, n_phi)
    lost = float(1.0 - alb.max())
    return {
        "normal_incidence_albedo": [round(float(v), 5) for v in alb],
        "energy_lost": round(lost, 5),
        "note": ("energy below 1 at high roughness is the known "
                 "single-scattering GGX deficit, not a defect: add a "
                 "multi-scatter term if it matters"),
    }
