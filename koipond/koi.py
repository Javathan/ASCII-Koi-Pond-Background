"""Koi geometry, motion and coloring.

Each fish swims along a smooth closed curve. The curve is traversed a whole
number of times per loop and the tail beat completes a whole number of cycles,
so the final frame of the video flows directly back into the first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

TAU = 2.0 * np.pi

# Spine sampling: u = 0 is the snout, u = 1 the base of the tail, u > 1 the caudal fin.
SPINE_U = np.linspace(0.0, 1.32, 56)

VARIETIES = ("kohaku", "sanke", "showa", "tancho", "ogon", "chagoi", "yamabuki", "asagi")

WHITE = (252, 250, 244)
RED = (240, 38, 18)
BLACK = (22, 22, 30)
GOLD = (255, 186, 30)
ORANGE = (255, 112, 14)
YELLOW = (255, 222, 52)
SLATE = (86, 142, 214)


@dataclass
class Patch:
    color: tuple[int, int, int]
    blobs: list[tuple[float, float, float, float]] = field(default_factory=list)  # (u, v, ru, rv)


def _random_blobs(rng: np.random.Generator, count: int, size: float, u_range=(0.08, 0.85)) -> list:
    blobs = []
    for _ in range(count):
        blobs.append((
            rng.uniform(*u_range),
            rng.uniform(-0.55, 0.55),
            rng.uniform(0.6, 1.1) * size,
            rng.uniform(0.7, 1.4),
        ))
    return blobs


def make_pattern(variety: str, rng: np.random.Generator) -> tuple[tuple[int, int, int], list[Patch]]:
    """Return the base color and the list of colored patches for a variety."""
    if variety == "kohaku":
        return WHITE, [Patch(RED, _random_blobs(rng, rng.integers(3, 5), 0.11))]
    if variety == "sanke":
        return WHITE, [
            Patch(RED, _random_blobs(rng, rng.integers(3, 5), 0.10)),
            Patch(BLACK, _random_blobs(rng, rng.integers(3, 6), 0.045, (0.2, 0.9))),
        ]
    if variety == "showa":
        return BLACK, [
            Patch(RED, _random_blobs(rng, rng.integers(3, 5), 0.10)),
            Patch(WHITE, _random_blobs(rng, rng.integers(2, 4), 0.07)),
        ]
    if variety == "tancho":
        return WHITE, [Patch(RED, [(0.11, 0.0, 0.065, 0.55)])]
    if variety == "ogon":
        return GOLD, []
    if variety == "chagoi":
        return ORANGE, [Patch(WHITE, _random_blobs(rng, rng.integers(0, 3), 0.06))]
    if variety == "yamabuki":
        return YELLOW, []
    if variety == "asagi":
        return SLATE, [Patch(ORANGE, [(0.5, 0.95, 0.45, 0.35), (0.5, -0.95, 0.45, 0.35), (0.06, 0.0, 0.06, 0.8)])]
    raise ValueError(f"unknown variety: {variety}")


def body_half_width(u: np.ndarray) -> np.ndarray:
    """Half-width of the body, as a fraction of fish length."""
    head = np.sqrt(np.clip(u / 0.2, 0.0, 1.0))
    taper = 1.0 - 0.86 * np.clip((u - 0.2) / 0.8, 0.0, 1.0) ** 1.35
    return 0.135 * head * taper


def tail_half_width(u: np.ndarray) -> np.ndarray:
    return 0.018 + 0.55 * np.clip(u - 1.0, 0.0, None)


class Koi:
    def __init__(self, rng: np.random.Generator, width: int, height: int, duration: float, scale: float,
                 speed: float = 1.0):
        self.duration = duration
        self.length = rng.uniform(240.0, 360.0) * scale
        self.depth = rng.uniform(0.0, 1.0)
        self.variety = str(rng.choice(VARIETIES))
        self.base, self.patches = make_pattern(self.variety, rng)
        self.metallic = self.variety in ("ogon", "yamabuki")

        # Closed swimming path.
        self.cx = rng.uniform(0.2, 0.8) * width
        self.cy = rng.uniform(0.25, 0.75) * height
        self.ax = rng.uniform(0.22, 0.42) * width
        self.ay = rng.uniform(0.22, 0.42) * height
        self.rot = rng.uniform(0.0, TAU)
        self.h2 = (rng.uniform(0.0, 0.12) * self.ax, rng.uniform(0.0, TAU), rng.uniform(0.0, 0.12) * self.ay, rng.uniform(0.0, TAU))
        self.h3 = (rng.uniform(0.0, 0.04) * self.ax, rng.uniform(0.0, TAU), rng.uniform(0.0, 0.04) * self.ay, rng.uniform(0.0, TAU))
        self.direction = rng.choice([-1.0, 1.0])
        self.phase = rng.uniform(0.0, TAU)

        # Arc-length table for the path.
        theta = np.linspace(0.0, TAU, 4097)
        pts = self._path(theta)
        seg = np.hypot(*np.diff(pts, axis=1))
        self._theta = theta
        self._arc = np.concatenate([[0.0], np.cumsum(seg)])
        self.path_length = float(self._arc[-1])

        # Choose laps and tail beats so that motion is periodic over the loop.
        target_speed = rng.uniform(32.0, 52.0) * scale * speed
        self.laps = max(1, int(round(target_speed * duration / self.path_length)))
        self.beats = max(1, int(round(rng.uniform(0.55, 0.8) * speed * duration)))
        self.fin_beats = max(1, int(round(rng.uniform(0.25, 0.4) * speed * duration)))
        self.wiggle = rng.uniform(0.045, 0.075)

    # ------------------------------------------------------------------ motion
    def _path(self, theta: np.ndarray) -> np.ndarray:
        a2, p2, b2, q2 = self.h2
        a3, p3, b3, q3 = self.h3
        x = self.ax * np.cos(theta) + a2 * np.cos(2 * theta + p2) + a3 * np.cos(3 * theta + p3)
        y = self.ay * np.sin(theta) + b2 * np.sin(2 * theta + q2) + b3 * np.sin(3 * theta + q3)
        c, s = np.cos(self.rot), np.sin(self.rot)
        return np.stack([self.cx + c * x - s * y, self.cy + s * x + c * y])

    def _pos_at_arc(self, s: np.ndarray) -> np.ndarray:
        s = np.mod(s, self.path_length)
        return self._path(np.interp(s, self._arc, self._theta))

    def spine(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Return spine points (n, 2) and unit tangents (n, 2) pointing toward the head."""
        progress = self.phase / TAU + self.direction * self.laps * t / self.duration
        s_head = np.mod(progress, 1.0) * self.path_length
        s = s_head - self.direction * SPINE_U * self.length
        pts = self._pos_at_arc(s).T

        tangent = np.gradient(pts, axis=0) * -1.0
        tangent /= np.linalg.norm(tangent, axis=1, keepdims=True) + 1e-9
        normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)

        beat = TAU * self.beats * t / self.duration
        u = SPINE_U
        sway = self.length * (self.wiggle * u ** 1.6 + 0.01) * np.sin(beat - 5.5 * u)
        pts = pts + normal * sway[:, None]

        tangent = np.gradient(pts, axis=0) * -1.0
        tangent /= np.linalg.norm(tangent, axis=1, keepdims=True) + 1e-9
        return pts, tangent

    # ---------------------------------------------------------------- geometry
    def geometry(self, t: float, centers: np.ndarray, offset=(0.0, 0.0)):
        """Classify cell centers against the fish silhouette.

        ``centers`` is an (m, 2) array of pixel coordinates. Returns per-cell
        ``u``, normalized lateral position ``vn`` and boolean masks for body,
        caudal fin and pectoral fins.
        """
        pts, tangent = self.spine(t)
        pts = pts + np.asarray(offset)

        diff = centers[:, None, :] - pts[None, :, :]
        d2 = np.einsum("mnk,mnk->mn", diff, diff)
        j = np.argmin(d2, axis=1)
        dist = np.sqrt(d2[np.arange(len(j)), j])
        rel = diff[np.arange(len(j)), j]
        tj = tangent[j]
        side = np.sign(tj[:, 0] * rel[:, 1] - tj[:, 1] * rel[:, 0])
        u = SPINE_U[j]
        L = self.length

        hw = body_half_width(u) * L
        body = (u <= 1.0) & (dist <= hw) & (hw > 0)

        tw = tail_half_width(u) * L
        fork = (u > 1.18) & (dist < (u - 1.18) * 0.9 * L)
        tail = (u > 1.0) & (dist <= tw) & ~fork

        flap = 0.75 + 0.25 * np.sin(TAU * self.fin_beats * t / self.duration)
        fin_extent = 0.16 * L * flap * np.sin(np.pi * np.clip((u - 0.2) / 0.17, 0.0, 1.0))
        pectoral = (u > 0.2) & (u < 0.37) & (dist > hw) & (dist <= hw + fin_extent)

        vn = np.where(hw > 0, side * dist / np.maximum(hw, 1e-6), 0.0)
        return u, np.clip(vn, -1.0, 1.0), body, tail, pectoral

    def bbox(self, t: float, pad: float = 0.25):
        pts, _ = self.spine(t)
        p = pad * self.length
        return pts[:, 0].min() - p, pts[:, 1].min() - p, pts[:, 0].max() + p, pts[:, 1].max() + p

    # ---------------------------------------------------------------- coloring
    def body_color(self, u: np.ndarray, vn: np.ndarray) -> np.ndarray:
        color = np.broadcast_to(np.asarray(self.base, dtype=np.float32), u.shape + (3,)).copy()
        ragged = 0.08 * np.sin(u * 47.0 + vn * 6.0) + 0.05 * np.sin(u * 91.0 - vn * 11.0)
        for patch in self.patches:
            field_ = np.zeros_like(u)
            for bu, bv, ru, rv in patch.blobs:
                field_ = np.maximum(field_, np.exp(-(((u - bu) / ru) ** 2 + ((vn - bv) / rv) ** 2)))
            mask = (field_ + ragged) > 0.5
            color[mask] = patch.color
        return color
