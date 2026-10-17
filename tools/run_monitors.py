"""Второй проход по видео без нейросети: сигналы, которых нет в детекциях.

  python tools/run_monitors.py /path/to/videos [--fps 2] [--only Х-28 Х-29]

На каждый ролик пишется out/monitors/<имя>.npz:
  t         — секунды кадров
  thumb     — уменьшенный серый кадр 58×106 (для сравнения зон сейфа и двери с эталоном)
  luma      — средняя яркость кадра (выключили свет)
  screen_*  — яркость, доля светлых пикселей и их голубизна (B−R) в области экрана ноутбука
  occluded  — человек перекрывает ноутбук в этом кадре
Область ноутбука берётся из out/detections/<имя>.json.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from analyze_signals import anchors  # noqa: E402
from app.pipeline.video import frames, probe  # noqa: E402

DET = ROOT / "out" / "detections"
OUT = ROOT / "out" / "monitors"


def overlaps(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def run(path: Path, fps: int) -> dict:
    det = json.loads((DET / f"{path.stem}.json").read_text(encoding="utf-8"))
    fr = det["frames"]
    anc = anchors(fr)
    laptop = anc.get("laptop", (None, 0))[0]
    info = probe(path)
    ts, thumbs, lumas, s_luma, s_bright, s_br, occ = [], [], [], [], [], [], []
    if laptop:
        x1, y1, x2, y2 = map(int, laptop)
        w, h = x2 - x1, y2 - y1
        # экран — верхняя часть рамки ноутбука (крышка), чуть сжатая по бокам
        sx1, sx2, sy1, sy2 = x1 + w // 7, x2 - w // 7, y1 + h // 10, y1 + int(h * 0.55)
    for t, img in frames(path, info, fps):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ts.append(t)
        thumbs.append(cv2.resize(gray, (58, 106), interpolation=cv2.INTER_AREA))
        lumas.append(float(gray.mean()))
        if laptop:
            roi = img[sy1:sy2, sx1:sx2]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            bright = hsv[..., 2] >= 150
            s_luma.append(float(hsv[..., 2].mean()))
            s_bright.append(float(bright.mean()))
            # включённый экран голубоватый: B−R на светлых пикселях заметно больше нуля,
            # шкаф или стена за ноутбуком — нейтральные (около нуля)
            br = roi[..., 0].astype(int) - roi[..., 2].astype(int)
            s_br.append(float(br[bright].mean()) if bright.any() else 0.0)
            near = min(fr, key=lambda q: abs(q["t"] - t))
            occ.append(any(overlaps(p["box"], laptop) for p in near["persons"]))
        else:
            s_luma.append(np.nan); s_bright.append(np.nan); s_br.append(np.nan); occ.append(False)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / f"{path.stem}.npz", t=np.array(ts, np.float32), thumb=np.stack(thumbs).astype(np.uint8),
                        luma=np.array(lumas, np.float32), screen_luma=np.array(s_luma, np.float32),
                        screen_bright=np.array(s_bright, np.float32), screen_br=np.array(s_br, np.float32), occluded=np.array(occ, bool),
                        laptop=np.array(laptop or [0, 0, 0, 0], np.float32),
                        safe=np.array(anc.get("tv", ([0, 0, 0, 0], 0))[0], np.float32))
    return {"file": path.name, "frames": len(ts), "laptop": bool(laptop), "safe_anchor": "tv" in anc}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos")
    ap.add_argument("--fps", type=int, default=2)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    vids = sorted(Path(a.videos).glob("*.mov"), key=lambda p: (len(p.stem), p.stem))
    for v in vids:
        if a.only and v.stem not in a.only:
            continue
        if not (DET / f"{v.stem}.json").exists():
            print(f"{v.stem}: нет детекций, пропускаю", flush=True)
            continue
        print(v.stem, run(v, a.fps), flush=True)
    print("готово:", OUT, flush=True)


if __name__ == "__main__":
    main()
