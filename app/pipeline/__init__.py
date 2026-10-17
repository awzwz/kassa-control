"""Конвейер анализа одного видео.

  кадры (ffmpeg, 5 к/с) → YOLOX: люди и предметы (640×352), раз в секунду крупнее (960×544)
  → ByteTrack: треки людей → сигналы (signals.py) → правила (rules.py)
  → описание по каталогу норм (describe.py) → кадры-доказательства (video.py)

analyze() пишет в Partial по мере работы: сторож дедлайна в worker.py может забрать
лучший частичный результат в любой момент. Если времени не хватает, анализ досрочно
переходит к правилам по уже просмотренным кадрам.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import cv2
import numpy as np

from . import describe, rules
from . import signals as S
from .video import VideoInfo, frame_base64, frames, probe  # noqa: F401

log = logging.getLogger("pipeline")

STAGES = [
    "Видео загружено",
    "Файл проверен",
    "Люди и предметы в кадре",
    "Сопоставление с правилами",
    "Кадры-доказательства",
]
FPS = 5           # частота анализа
HD_EVERY = FPS    # каждый пятый кадр (раз в секунду) — крупный проход ради мелких предметов


@dataclass
class Finding:
    """Одно найденное событие. Поля с префиксом ui_ в ответ API не попадают."""
    type: str
    timecode_sec: float
    description: str
    frames_b64: list[tuple[float, str]]
    ui_confidence: str = "средняя"
    ui_rule: dict[str, Any] = field(default_factory=dict)
    ui_signals: list[dict[str, Any]] = field(default_factory=list)
    ui_boxes: list[dict[str, Any]] = field(default_factory=list)
    ui_type_id: str = ""
    ui_t_end: float | None = None


@dataclass
class Partial:
    stage: int = 1
    frames_done: int = 0
    frames_total: int = 0
    findings: list[Finding] = field(default_factory=list)
    checked: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    timed_out: bool = False
    scene: dict[str, Any] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)   # треки людей для интерфейса
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def progress(self, started: float) -> dict[str, Any]:
        return {
            "stage": self.stage, "stages": len(STAGES),
            "label": STAGES[min(self.stage, len(STAGES)) - 1],
            "frames_done": self.frames_done, "frames_total": self.frames_total,
            "elapsed_sec": round(time.monotonic() - started, 1),
        }


_detector = None
_det_lock = threading.Lock()


def get_detector():
    """Один экземпляр детектора на процесс: веса грузятся один раз."""
    global _detector
    with _det_lock:
        if _detector is None:
            from .detector import YOLOX
            import os
            _detector = YOLOX("yolox_s_dyn", threads=int(os.environ.get("DET_THREADS", "4")))
            log.info("детектор YOLOX-s загружен, провайдер %s", _detector.provider)
    return _detector


def _tracker(fps: float):
    import inspect

    from trackers import ByteTrackTracker
    want = dict(frame_rate=fps, lost_track_buffer=int(3 * fps), track_activation_threshold=0.4,
                minimum_consecutive_frames=2, minimum_iou_threshold=0.2)
    sig = inspect.signature(ByteTrackTracker.__init__).parameters
    return ByteTrackTracker(**{k: v for k, v in want.items() if k in sig})


def perceive(path: str, info: VideoInfo, partial: Partial, deadline: float,
             on_progress: Callable[[], None] | None = None) -> list[dict[str, Any]]:
    """Проход по кадрам: детекции, треки, яркость. Возвращает структуру frames для signals/rules."""
    import supervision as sv

    det = get_detector()
    tracker = _tracker(FPS)
    out: list[dict[str, Any]] = []
    prev = None
    budget_stop = deadline - 25.0  # оставляем время правилам и кадрам-доказательствам
    for k, (t, img) in enumerate(frames(path, info, FPS)):
        if time.monotonic() > budget_stop:
            partial.timed_out = True
            partial.notes.append(f"Просмотр остановлен на {t:.0f} с из {info.duration:.0f}: не хватило времени.")
            break
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
        rec = {
            "t": round(t, 2), "luma": round(float(gray.mean()), 1), "motion": round(motion, 2),
            "persons": [{"id": int(i), "box": [round(float(v)) for v in b], "s": round(float(s), 2)}
                        for b, i, s in zip(tracks.xyxy, tracks.tracker_id, tracks.confidence)],
            "objects": [{"c": d.name, "box": [round(v) for v in d.box], "s": round(d.score, 2)} for d in objects],
        }
        if k % HD_EVERY == 0:
            hd = det(img, size=(960, 544), conf=0.15)
            rec["objects_hd"] = [{"c": d.name, "box": [round(v) for v in d.box], "s": round(d.score, 2)}
                                 for d in hd if d.cls != 0]
        out.append(rec)
        partial.frames_done = k + 1
        if on_progress and k % 25 == 0:
            on_progress()
    return out


def screen_probe_for(path: str, info: VideoInfo, laptop_box, frames_struct) -> rules.ScreenProbe:
    """Измеряет экран ноутбука на отрезке [t0, t1]: доля светлых пикселей и их голубизна (B−R).
    Декодирует только нужный отрезок видео."""
    x1, y1, x2, y2 = map(int, laptop_box)
    w, h = x2 - x1, y2 - y1
    sx1, sx2, sy1, sy2 = x1 + w // 7, x2 - w // 7, y1 + h // 10, y1 + int(h * 0.55)

    def overlaps(a, b):
        return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

    def probe(t0: float, t1: float):
        import subprocess
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, t0):.2f}", "-i", path, "-t", f"{max(0.5, t1 - t0):.2f}",
               "-vf", "fps=2", "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
        raw = subprocess.run(cmd, capture_output=True, timeout=60).stdout
        size = info.width * info.height * 3
        n = len(raw) // size
        if n == 0:
            return None
        vals = []
        for i in range(n):
            img = np.frombuffer(raw[i * size:(i + 1) * size], np.uint8).reshape(info.height, info.width, 3)
            tt = t0 + i / 2
            near = min(frames_struct, key=lambda q: abs(q["t"] - tt))
            if any(overlaps(p["box"], [x1, y1, x2, y2]) for p in near["persons"]):
                continue
            roi = img[sy1:sy2, sx1:sx2]
            if roi.size == 0:
                continue
            v = roi.max(2)
            bright = v >= 150
            br = (roi[..., 0].astype(int) - roi[..., 2].astype(int))[bright]
            vals.append((float(bright.mean()), float(br.mean()) if br.size else 0.0))
        if not vals:
            return None
        return float(np.median([a for a, _ in vals])), float(np.median([b for _, b in vals]))
    return probe


def _evidence(path: str, t: float, duration: float) -> list[tuple[float, str]]:
    """1–3 кадра: в момент события, за секунду до и через секунду после (в пределах ролика)."""
    ts = [t] + [x for x in (t - 1.0, t + 1.0) if 0.0 <= x <= duration - 0.05]
    out = []
    for x in ts:
        try:
            out.append((round(x, 2), frame_base64(path, x)))
        except Exception as e:  # noqa: BLE001
            log.warning("кадр %.2f не вырезан: %s", x, e)
    return out


def analyze(path: str, info: VideoInfo, partial: Partial, deadline: float,
            on_progress: Callable[[], None] | None = None) -> None:
    partial.stage = 2
    partial.frames_total = max(1, int(info.duration * FPS))
    if on_progress:
        on_progress()

    partial.stage = 3
    struct = perceive(path, info, partial, deadline, on_progress)

    partial.stage = 4
    if on_progress:
        on_progress()
    seen_duration = struct[-1]["t"] + 1.0 / FPS if struct else 0.0
    duration = min(info.duration, seen_duration) if partial.timed_out else info.duration
    sc = S.build_scene(struct, FPS, duration)
    probe = screen_probe_for(path, info, sc.anc["laptop"][0], struct) if "laptop" in sc.anc else None
    events, sc, checked = rules.evaluate(struct, FPS, duration, probe)
    with partial.lock:
        partial.checked = checked
        partial.scene = S.to_jsonable({
            "cashier_track": sc.cashier, "h_seated": round(sc.h_seated), "h_stand": round(sc.h_stand),
            "work": [round(v) for v in sc.work] if sc.cashier is not None else None,
            "desk": [round(v) for v in sc.desk] if sc.desk else None,
            "anchors": {k: [round(v) for v in b] for k, (b, _) in sc.anc.items()},
            "tracks": [{"id": t.id, "t0": t.t0, "t1": t.t1, "h": round(t.h), "role": "кассир" if t.id == sc.cashier else "посетитель"}
                       for t in sc.tracks.values()],
        })
        partial.timeline = [{"t": f["t"], "persons": [{"id": p["id"], "box": p["box"]} for p in f["persons"] if p["id"] >= 0]}
                            for f in struct if abs(f["t"] * 2 - round(f["t"] * 2)) < 1e-6]

    partial.stage = 5
    if on_progress:
        on_progress()
    for ev in events:
        r = describe.rule_for(ev.type_id)
        text = describe.describe(ev.type_id, ev.fields)
        bad = describe.check_banned(text)
        if bad:
            log.warning("в описании запрещённые слова %s", bad)
        f = Finding(type=r["type"], timecode_sec=round(ev.t, 1), description=text,
                    frames_b64=_evidence(path, ev.t, info.duration),
                    ui_confidence=ev.confidence, ui_rule=describe.ui_rule(ev.type_id),
                    ui_signals=ev.signals, ui_boxes=ev.boxes, ui_type_id=ev.type_id, ui_t_end=ev.t_end)
        with partial.lock:
            partial.findings.append(f)
        if time.monotonic() > deadline - 3.0:
            partial.timed_out = True
            partial.notes.append("Не все кадры-доказательства успели подготовиться.")
            break
    if not events:
        partial.notes.append("Признаков нарушений по правилам первой версии не найдено.")
