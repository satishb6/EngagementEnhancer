"""GIFs synthesised locally from stills — Ken Burns / crossfade via ffmpeg.
Zero model cost. The cheapest 'motion' in the product."""

import asyncio
import shutil
import tempfile
from pathlib import Path


class FfmpegMissing(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "ffmpeg is not installed or not on PATH. Install it "
            "(https://ffmpeg.org/download.html) to enable GIF synthesis."
        )


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise FfmpegMissing()
    return path


async def ken_burns_gif(image_bytes: bytes, *, duration_s: float = 3.0,
                        width: int = 720) -> bytes:
    """Slow push-in over a still. Returns GIF bytes."""
    ffmpeg = _ffmpeg()
    frames = int(duration_s * 20)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.png"
        out = Path(tmp) / "out.gif"
        src.write_bytes(image_bytes)
        zoom_filter = (
            f"scale=8000:-1,zoompan=z='min(zoom+0.0012,1.20)':d={frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{width},"
            f"fps=20,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        )
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-y", "-i", str(src), "-vf", zoom_filter,
            "-loop", "0", str(out),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode()[-500:]}")
        return out.read_bytes()


async def crossfade_gif(images: list[bytes], *, per_image_s: float = 1.6,
                        width: int = 720) -> bytes:
    """Crossfade between 2+ stills. Returns GIF bytes."""
    if len(images) < 2:
        return await ken_burns_gif(images[0], duration_s=per_image_s * 2, width=width)
    ffmpeg = _ffmpeg()
    fade = 0.5
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, data in enumerate(images):
            p = Path(tmp) / f"in{i}.png"
            p.write_bytes(data)
            paths.append(p)
        out = Path(tmp) / "out.gif"

        inputs: list[str] = []
        for p in paths:
            inputs += ["-loop", "1", "-t", str(per_image_s), "-i", str(p)]

        # chain xfades, then palette for gif quality
        n = len(paths)
        filters = []
        last = "[0:v]"
        for i in range(1, n):
            offset = i * (per_image_s - fade)
            label = f"[x{i}]" if i < n - 1 else "[xf]"
            filters.append(
                f"{last}[{i}:v]xfade=transition=fade:duration={fade}:offset={offset}{label}"
            )
            last = label
        filters.append(
            f"[xf]scale={width}:-1,fps=16,split[s0][s1];[s0]palettegen[p];"
            f"[s1][p]paletteuse[outv]"
        )
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filters),
            "-map", "[outv]", "-loop", "0", str(out),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode()[-500:]}")
        return out.read_bytes()


async def concat_videos(video_paths: list[Path], out_path: Path) -> None:
    """Concat clips for the long-form pipeline (storyboard → shots → film)."""
    ffmpeg = _ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        listfile = Path(tmp) / "list.txt"
        listfile.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in video_paths), encoding="utf-8"
        )
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
            "-c", "copy", str(out_path),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {stderr.decode()[-500:]}")
