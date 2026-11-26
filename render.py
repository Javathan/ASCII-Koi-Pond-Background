"""Render the ASCII koi pond to a seamlessly looping video or a still image.

Examples:
    python render.py                                 # 1440p, 60 fps, 60 second loop
    python render.py --width 3840 --height 2160      # 4K
    python render.py --still preview.png --at 12.5   # single frame
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

from koipond import Pond, SceneConfig


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render a looping ASCII koi pond wallpaper.")
    p.add_argument("-o", "--output", type=Path, default=None, help="output video path (default: output/koi_pond_<H>p.mp4)")
    p.add_argument("--width", type=int, default=2560)
    p.add_argument("--height", type=int, default=1440)
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--duration", type=float, default=60.0, help="loop length in seconds")
    p.add_argument("--speed", type=float, default=1.0, help="swimming speed multiplier")
    p.add_argument("--saturation", type=float, default=1.25, help="color saturation multiplier")
    p.add_argument("--cell", type=str, default=None, help="character cell size WxH in pixels (default scales with height, 8x14 at 1080p)")
    p.add_argument("--koi", type=int, default=8, help="number of fish")
    p.add_argument("--pads", type=int, default=7, help="number of lily pads")
    p.add_argument("--ripples", type=int, default=7, help="surface ripples per loop")
    p.add_argument("--seed", type=int, default=7, help="random seed for the pond layout")
    p.add_argument("--font", type=str, default=None, help="path to a monospace .ttf font")
    p.add_argument("--crf", type=int, default=14, help="x264 quality (lower is better)")
    p.add_argument("--still", type=Path, default=None, help="render a single PNG instead of a video")
    p.add_argument("--at", type=float, default=0.0, help="time in seconds for --still")
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> SceneConfig:
    if args.cell:
        cw, ch = (int(v) for v in args.cell.lower().split("x"))
    else:
        s = args.height / 1080.0
        cw, ch = max(4, round(8 * s)), max(7, round(14 * s))
    return SceneConfig(width=args.width, height=args.height, cell_w=cw, cell_h=ch,
                       duration=args.duration, fps=args.fps, koi=args.koi, pads=args.pads,
                       ripples=args.ripples, seed=args.seed, font=args.font,
                       speed=args.speed, saturation=args.saturation)


def render_video(pond: Pond, output: Path, crf: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        sys.exit("error: ffmpeg was not found on PATH. Install it from https://ffmpeg.org/download.html")

    cfg = pond.cfg
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{cfg.width}x{cfg.height}", "-r", str(cfg.fps), "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-tune", "animation",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    start = time.perf_counter()
    total = cfg.frames
    try:
        for i in range(total):
            proc.stdin.write(pond.frame(i).tobytes())
            if i % cfg.fps == 0 or i == total - 1:
                elapsed = time.perf_counter() - start
                eta = elapsed / (i + 1) * (total - i - 1)
                print(f"\rframe {i + 1}/{total}  elapsed {elapsed:5.0f}s  eta {eta:5.0f}s", end="", flush=True)
    finally:
        proc.stdin.close()
        proc.wait()
    print()
    if proc.returncode != 0:
        sys.exit(f"error: ffmpeg exited with status {proc.returncode}")
    print(f"wrote {output}")


def main(argv=None) -> None:
    args = parse_args(argv)
    pond = Pond(build_config(args))
    if args.still:
        index = int(round(args.at * pond.cfg.fps))
        args.still.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(pond.frame(index)).save(args.still)
        print(f"wrote {args.still}")
        return
    output = args.output or Path("output") / f"koi_pond_{args.height}p.mp4"
    render_video(pond, output, args.crf)


if __name__ == "__main__":
    main()
