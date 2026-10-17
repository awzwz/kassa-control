"""Прогон детектора и трекера по всем роликам (на ноутбуке). Делается один раз, потом правила
проверяются по сохранённым файлам за секунды, без повторного запуска модели.

  python tools/run_detections.py /path/to/videos [--fps 5] [--only Х-4 Х-25]

На каждый ролик пишется out/detections/<имя>.json:
  meta   — файл, md5, длительность, размер кадра
  frames — по кадру: t, яркость, движение, люди с номерами треков, предметы (640×352),
           раз в секунду предметы в большем разрешении (960×544) для мелочи на столе
Дубликаты (одинаковый md5) пропускаются.
"""
import argparse
import hashlib
import inspect
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import supervision as sv
from trackers import ByteTrackTracker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline.detector import COCO, YOLOX  # noqa: E402
from app.pipeline.video import frames, probe  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "out" / "detections"  # можно переопределить --out


def make_tracker(fps: float) -> ByteTrackTracker:
    want = dict(frame_rate=fps, lost_track_buffer=int(3 * fps), track_activation_threshold=0.4,
                minimum_consecutive_frames=2, minimum_iou_threshold=0.2)
    sig = inspect.signature(ByteTrackTracker.__init__).parameters
    return ByteTrackTracker(**{k: v for k, v in want.items() if k in sig})


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(path: Path, det: YOLOX, fps: int) -> dict:
    t0 = time.perf_counter()
    info = probe(path)
    tracker = make_tracker(fps)
    rec, prev = [], None
    for k, (t, img) in enumerate(frames(path, info, fps)):
        dets = det(img, size=(640, 352), conf=0.15)
        persons = [d for d in dets if d.cls == 0 and d.score >= 0.3]
        objects = [d for d in dets if d.cls != 0]
        if persons:
            pd = sv.Detections(xyxy=np.array([d.box for d in persons], np.float32),
                               confidence=np.array([d.score for d in persons], np.float32),
                               class_id=np.zeros(len(persons), int))
        else:
            pd = sv.Detections.empty()
        tracks = tracker.update(pd)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (116, 212)).astype(np.float32)
        motion = float(np.abs(small - prev).mean()) if prev is not None else 0.0
        prev = small
        frame = {
            "t": round(t, 2),
            "luma": round(float(gray.mean()), 1),
            "motion": round(motion, 2),
            "persons": [{"id": int(i), "box": [round(float(v)) for v in b], "s": round(float(s), 2)}
                        for b, i, s in zip(tracks.xyxy, tracks.tracker_id, tracks.confidence)],
            "objects": [{"c": d.name, "box": [round(v) for v in d.box], "s": round(d.score, 2)} for d in objects],
        }
        if k % fps == 0:  # раз в секунду — крупнее, ради мелких предметов на столе
            hd = det(img, size=(960, 544), conf=0.15)
            frame["objects_hd"] = [{"c": d.name, "box": [round(v) for v in d.box], "s": round(d.score, 2)}
                                   for d in hd if d.cls != 0]
        rec.append(frame)
    meta = {"file": path.name, "md5": md5(path), "duration": round(info.duration, 2), "width": info.width,
            "height": info.height, "fps_src": round(info.fps, 2), "fps": fps, "frames": len(rec),
            "elapsed_sec": round(time.perf_counter() - t0, 1)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{path.stem}.json").write_text(json.dumps({"meta": meta, "frames": rec}, ensure_ascii=False))
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos")
    ap.add_argument("--fps", type=int, default=5)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out")
    a = ap.parse_args()
    global OUT
    if a.out:
        OUT = Path(a.out)
    vids = sorted(Path(a.videos).glob("*.mov"), key=lambda p: (len(p.stem), p.stem))
    if a.only:
        vids = [v for v in vids if v.stem in a.only]
    det = YOLOX("yolox_s_dyn", threads=4)
    print(f"детектор: {det.provider}, роликов: {len(vids)}", flush=True)
    seen: dict[str, str] = {}
    index = []
    for v in vids:
        h = md5(v)
        if h in seen:
            print(f"{v.stem}: дубликат {seen[h]}, пропускаю", flush=True)
            index.append({"file": v.name, "same_as": seen[h]})
            continue
        seen[h] = v.stem
        m = run(v, det, a.fps)
        index.append(m)
        print(f"{v.stem}: {m['duration']} с, {m['frames']} кадров, {m['elapsed_sec']} с", flush=True)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    print("готово:", OUT, flush=True)


if __name__ == "__main__":
    main()
