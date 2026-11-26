"""Pond scene composition.

The scene is evaluated on a character grid. Each layer writes a luminance
value (which selects the glyph) and an RGB color (which tints it) per cell.
Layers, from bottom to top:

    water caustics -> fish shadows -> koi -> surface ripples -> lily pads
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .glyphs import RAMP, build_atlas
from .koi import TAU, Koi

BACKGROUND = np.array([6, 11, 15], dtype=np.float32)
WATER_DEEP = np.array([8, 34, 52], dtype=np.float32)
WATER_LIGHT = np.array([26, 150, 176], dtype=np.float32)
PAD_DARK = np.array([22, 104, 40], dtype=np.float32)
PAD_LIGHT = np.array([92, 214, 70], dtype=np.float32)
PETAL = np.array([255, 112, 176], dtype=np.float32)
PETAL_TIP = np.array([255, 214, 234], dtype=np.float32)
POLLEN = np.array([255, 216, 40], dtype=np.float32)


@dataclass
class SceneConfig:
    width: int = 1920
    height: int = 1080
    cell_w: int = 8
    cell_h: int = 14
    duration: float = 60.0
    fps: int = 60
    koi: int = 8
    pads: int = 7
    ripples: int = 7
    seed: int = 7
    font: str | None = None
    speed: float = 1.0
    saturation: float = 1.25

    @property
    def frames(self) -> int:
        return int(round(self.duration * self.fps))


class LilyPad:
    def __init__(self, rng: np.random.Generator, width: int, height: int, duration: float, scale: float):
        self.duration = duration
        self.radius = rng.uniform(45.0, 115.0) * scale
        edge = rng.random() < 0.6
        if edge:
            # Favor the borders so the center of the screen stays open.
            side = rng.integers(4)
            u = rng.uniform(0.0, 1.0)
            m = rng.uniform(0.0, 0.12)
            self.x, self.y = [(u * width, m * height), (u * width, (1 - m) * height),
                              (m * width, u * height), ((1 - m) * width, u * height)][side]
        else:
            self.x, self.y = rng.uniform(0.1, 0.9) * width, rng.uniform(0.1, 0.9) * height
        self.notch = rng.uniform(0.0, TAU)
        self.spin = rng.uniform(-0.04, 0.04)
        self.drift = rng.uniform(3.0, 8.0) * scale
        self.drift_phase = rng.uniform(0.0, TAU, size=2)
        self.flower = rng.random() < 0.35
        self.flower_offset = rng.uniform(0.0, 0.35) * self.radius
        self.flower_angle = rng.uniform(0.0, TAU)

    def center(self, t: float) -> tuple[float, float]:
        w = TAU * t / self.duration
        return (self.x + self.drift * np.sin(w + self.drift_phase[0]),
                self.y + self.drift * np.sin(w + self.drift_phase[1]))

    def draw(self, t: float, cx: np.ndarray, cy: np.ndarray, lum: np.ndarray, col: np.ndarray, shadow_only=False):
        px, py = self.center(t)
        if shadow_only:
            px, py = px + 14, py + 20
        dx, dy = cx - px, cy - py
        r = np.hypot(dx, dy)
        inside = r <= self.radius
        if not inside.any():
            return
        notch = self.notch + self.spin * np.sin(TAU * t / self.duration)
        ang = np.arctan2(dy, dx)
        dang = np.abs(np.angle(np.exp(1j * (ang - notch))))
        mask = inside & ~((dang < 0.32) & (r > 0.08 * self.radius))
        if shadow_only:
            lum[mask] *= 0.35
            col[mask] *= 0.45
            return

        rn = r[mask] / self.radius
        veins = 0.5 + 0.5 * np.cos(ang[mask] * 13.0)
        shade = 0.55 + 0.12 * veins * rn - 0.25 * rn ** 6
        lum[mask] = np.clip(shade, 0.0, 1.0)
        mix = np.clip(0.35 + 0.5 * (1 - rn) + 0.2 * veins - 0.3 * (rn > 0.9), 0.0, 1.0)
        col[mask] = PAD_DARK + (PAD_LIGHT - PAD_DARK) * mix[:, None]

        if self.flower:
            fx = px + self.flower_offset * np.cos(self.flower_angle)
            fy = py + self.flower_offset * np.sin(self.flower_angle)
            fr = 0.45 * self.radius
            fdx, fdy = cx - fx, cy - fy
            fd = np.hypot(fdx, fdy)
            fa = np.arctan2(fdy, fdx) + 0.1 * np.sin(TAU * t / self.duration)
            petal = (fd <= fr * (0.55 + 0.45 * np.abs(np.cos(fa * 4.0)))) & (fd <= fr)
            core = fd <= 0.22 * fr
            pn = (fd / fr)[petal]
            lum[petal] = 0.62 + 0.3 * (1 - pn)
            col[petal] = PETAL + (PETAL_TIP - PETAL) * np.clip(pn, 0, 1)[:, None]
            lum[core] = 0.9
            col[core] = POLLEN


class Pond:
    def __init__(self, cfg: SceneConfig):
        self.cfg = cfg
        self.cols = cfg.width // cfg.cell_w
        self.rows = cfg.height // cfg.cell_h
        # Center the grid when the resolution is not an exact multiple of the cell size.
        self.pad_x = (cfg.width - self.cols * cfg.cell_w) // 2
        self.pad_y = (cfg.height - self.rows * cfg.cell_h) // 2

        gx = (np.arange(self.cols) + 0.5) * cfg.cell_w + self.pad_x
        gy = (np.arange(self.rows) + 0.5) * cfg.cell_h + self.pad_y
        self.cx, self.cy = np.meshgrid(gx, gy)

        self.atlas = build_atlas(cfg.cell_w, cfg.cell_h, cfg.font, RAMP, bold=cfg.cell_h >= 18)
        scale = cfg.height / 1080.0
        self.scale = scale

        rng = np.random.default_rng(cfg.seed)
        self.koi = sorted((Koi(rng, cfg.width, cfg.height, cfg.duration, scale, cfg.speed) for _ in range(cfg.koi)),
                          key=lambda k: -k.depth)
        self.pads = [LilyPad(rng, cfg.width, cfg.height, cfg.duration, scale) for _ in range(cfg.pads)]
        self.drops = [(rng.uniform(0.05, 0.95) * cfg.width, rng.uniform(0.05, 0.95) * cfg.height,
                       rng.uniform(0.0, cfg.duration)) for _ in range(cfg.ripples)]

        nx = (self.cx - cfg.width / 2) / (cfg.width / 2)
        ny = (self.cy - cfg.height / 2) / (cfg.height / 2)
        self.vignette = np.clip(1.0 - 0.25 * (nx ** 2 + ny ** 2) ** 1.5, 0.5, 1.0)

    # ------------------------------------------------------------------ layers
    def _water(self, t: float):
        T = self.cfg.duration
        s = self.scale
        x, y = self.cx / s, self.cy / s
        w = TAU * t / T
        xw = x + 28.0 * np.sin(y * 0.011 + w)
        yw = y + 28.0 * np.cos(x * 0.009 - w)
        f = (np.sin(xw * 0.021 + yw * 0.013 + 2 * w)
             + np.sin(xw * -0.017 + yw * 0.024 - 3 * w + 1.3)
             + np.sin(xw * 0.012 - yw * 0.019 + w + 2.1)
             + np.sin(np.hypot(xw - 900, yw - 500) * 0.018 - 2 * w))
        caustic = (1.0 - np.abs(f) / 4.0) ** 10
        lum = 0.02 + 0.24 * caustic
        mix = np.clip(caustic * 1.4, 0.0, 1.0)[..., None]
        col = WATER_DEEP + (WATER_LIGHT - WATER_DEEP) * mix
        return lum, col

    def _cells_in(self, box):
        x0, y0, x1, y1 = box
        c0 = max(0, int((x0 - self.pad_x) // self.cfg.cell_w))
        c1 = min(self.cols, int((x1 - self.pad_x) // self.cfg.cell_w) + 1)
        r0 = max(0, int((y0 - self.pad_y) // self.cfg.cell_h))
        r1 = min(self.rows, int((y1 - self.pad_y) // self.cfg.cell_h) + 1)
        if c0 >= c1 or r0 >= r1:
            return None
        return slice(r0, r1), slice(c0, c1)

    def _koi(self, t: float, lum: np.ndarray, col: np.ndarray):
        shadow_offset = np.array([16.0, 22.0]) * self.scale
        for fish in self.koi:
            x0, y0, x1, y1 = fish.bbox(t)
            box = self._cells_in((x0, y0, x1 + shadow_offset[0], y1 + shadow_offset[1]))
            if box is None:
                continue
            rs, cs = box
            centers = np.stack([self.cx[rs, cs].ravel(), self.cy[rs, cs].ravel()], axis=1)
            sub_lum = lum[rs, cs].reshape(-1)
            sub_col = col[rs, cs].reshape(-1, 3)

            # Shadow cast on the pond floor; deeper fish sit closer to the floor.
            depth_gap = 1.0 - 0.6 * fish.depth
            _, _, sb, st, sp = fish.geometry(t, centers, shadow_offset * depth_gap)
            sm = sb | st | sp
            sub_lum[sm] *= 0.45
            sub_col[sm] *= 0.5

            u, vn, body, tail, pect = fish.geometry(t, centers)
            fade = 1.0 - 0.3 * fish.depth

            if tail.any() or pect.any():
                fins = tail | pect
                base = np.asarray(fish.base, dtype=np.float32)
                fin_col = np.clip(base * 0.85 + 40.0, 0, 255)
                rays = 0.5 + 0.5 * np.sin(u[fins] * 70.0)
                alpha = 0.55 * fade
                sub_col[fins] = sub_col[fins] * (1 - alpha) + fin_col * alpha
                sub_lum[fins] = np.maximum(sub_lum[fins], (0.45 + 0.25 * rays) * fade)

            if body.any():
                bu, bv = u[body], vn[body]
                rounded = np.sqrt(np.clip(1.0 - bv ** 2, 0.0, 1.0))
                shade = 0.6 + 0.4 * rounded
                color = fish.body_color(bu, bv) * shade[:, None]
                spine_light = np.exp(-((bv + 0.1) / 0.28) ** 2)
                color += (60.0 if fish.metallic else 28.0) * spine_light[:, None]
                color = color * fade + WATER_DEEP * (1 - fade)
                sub_col[body] = np.clip(color, 0, 255)
                sub_lum[body] = np.clip((0.72 + 0.28 * rounded) * (0.85 + 0.15 * fade), 0, 1)

            lum[rs, cs] = sub_lum.reshape(lum[rs, cs].shape)
            col[rs, cs] = sub_col.reshape(col[rs, cs].shape)

    def _ripples(self, t: float, lum: np.ndarray, col: np.ndarray):
        life = 5.0
        speed = 85.0 * self.scale
        width = 9.0 * self.scale
        ring_col = np.array([150, 205, 212], dtype=np.float32)
        for x, y, t0 in self.drops:
            age = (t - t0) % self.cfg.duration
            if age > life:
                continue
            radius = speed * age
            d = np.hypot(self.cx - x, self.cy - y)
            ring = np.zeros_like(d)
            for k in range(3):
                rk = radius - k * 26.0 * self.scale
                if rk > 0:
                    ring = np.maximum(ring, np.exp(-((d - rk) / width) ** 2) * (0.75 ** k))
            ring *= (1.0 - age / life) ** 2
            m = ring > 0.02
            lum[m] = np.clip(lum[m] + 0.45 * ring[m], 0, 1)
            col[m] = col[m] + (ring_col - col[m]) * np.clip(ring[m], 0, 1)[:, None]

    # ------------------------------------------------------------------ output
    def frame(self, index: int) -> np.ndarray:
        """Render frame ``index`` as an (height, width, 3) uint8 array."""
        t = (index / self.cfg.fps) % self.cfg.duration
        lum, col = self._water(t)
        for pad in self.pads:
            pad.draw(t, self.cx, self.cy, lum, col, shadow_only=True)
        self._koi(t, lum, col)
        self._ripples(t, lum, col)
        for pad in self.pads:
            pad.draw(t, self.cx, self.cy, lum, col)

        col = col * self.vignette[..., None]
        gray = col.mean(axis=-1, keepdims=True)
        col = np.clip(gray + (col - gray) * self.cfg.saturation, 0.0, 255.0)
        idx = np.clip(np.rint(lum * (len(RAMP) - 1)), 0, len(RAMP) - 1).astype(np.int32)
        return self._compose(idx, col)

    def _compose(self, idx: np.ndarray, col: np.ndarray) -> np.ndarray:
        cfg = self.cfg
        glyphs = self.atlas[idx]  # (rows, cols, ch, cw)
        tint = col - BACKGROUND
        cells = BACKGROUND + glyphs[..., None] * tint[:, :, None, None, :]
        grid = cells.transpose(0, 2, 1, 3, 4).reshape(self.rows * cfg.cell_h, self.cols * cfg.cell_w, 3)
        out = np.empty((cfg.height, cfg.width, 3), dtype=np.uint8)
        out[:] = BACKGROUND.astype(np.uint8)
        out[self.pad_y:self.pad_y + grid.shape[0], self.pad_x:self.pad_x + grid.shape[1]] = np.clip(grid, 0, 255)
        return out
