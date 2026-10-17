"""Работа с видеофайлом через ffprobe/ffmpeg: сведения о файле, кадры, JPEG для доказательств."""
import base64
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np


class NotAVideo(Exception):
    pass


@dataclass
class VideoInfo:
    duration: float
    width: int      # размеры уже с учётом поворота
    height: int
    fps: float
    codec: str
    rotation: int


def probe(path: str | Path) -> VideoInfo:
    """Читает параметры видео. Бросает NotAVideo, если это не видеофайл."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate:stream_side_data=rotation:format=duration",
        "-of", "json", str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as e:
        raise NotAVideo("ffprobe не ответил за 30 с") from e
    if out.returncode != 0:
        raise NotAVideo(out.stderr.strip()[:200] or "ffprobe не смог прочитать файл")
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise NotAVideo("в файле нет видеодорожки")
    s = streams[0]
    try:
        num, den = s["avg_frame_rate"].split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (KeyError, ValueError, ZeroDivisionError):
        fps = 0.0
    rotation = 0
    for sd in s.get("side_data_list", []):
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    duration = float((data.get("format") or {}).get("duration") or 0.0)
    if duration <= 0:
        raise NotAVideo("нулевая длительность")
    w, h = int(s["width"]), int(s["height"])
    if abs(rotation) % 180 == 90:
        w, h = h, w
    return VideoInfo(duration=duration, width=w, height=h, fps=fps, codec=s.get("codec_name", "?"), rotation=rotation)


def frames(path: str | Path, info: VideoInfo, fps: float, max_side: int | None = None) -> Iterator[tuple[float, np.ndarray]]:
    """Отдаёт кадры (время в секундах, картинка BGR) с частотой fps. ffmpeg сам учитывает поворот."""
    w, h = info.width, info.height
    vf = f"fps={fps}"
    if max_side and max(w, h) > max_side:
        k = max_side / max(w, h)
        w, h = int(w * k) // 2 * 2, int(h * k) // 2 * 2
        vf += f",scale={w}:{h}"
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", "-i", str(path),
           "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size, n = w * h * 3, 0
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield n / fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            n += 1
    finally:
        p.stdout.close()
        p.wait()


def frame_jpeg(path: str | Path, t: float, quality: int = 85) -> bytes:
    """Один кадр в момент t как JPEG в полном разрешении (точная перемотка)."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(path),
           "-frames:v", "1", "-q:v", str(max(2, min(31, round(31 - quality * 0.29)))),
           "-f", "image2", "-vcodec", "mjpeg", "pipe:1"]
    out = subprocess.run(cmd, capture_output=True, timeout=60)
    if out.returncode != 0 or not out.stdout:
        raise RuntimeError(f"не удалось вырезать кадр в {t:.2f} с")
    return out.stdout


def frame_base64(path: str | Path, t: float) -> str:
    return base64.b64encode(frame_jpeg(path, t)).decode("ascii")
