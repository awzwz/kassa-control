"""Сигналы поверх детекций: где стол и кассир, когда кассир встаёт и уходит, кто входит,
что лежит на столе. Чистые функции над структурой кадров:

frames: [{"t", "luma", "motion", "persons": [{"id","box","s"}], "objects": [...], "objects_hd": [...]}]

Логика настроена на обучающих роликах (tools/analyze_signals.py) и перенесена сюда без изменений смысла.
Все пороги выражены в долях роста человека, а не в пикселях, чтобы переносились на другой ракурс.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

FURNITURE = {"laptop", "suitcase", "keyboard", "mouse", "tv", "dining table", "chair"}
DESK_ITEMS = {"cell phone", "remote", "book", "cup", "bottle", "handbag", "backpack", "bowl"}
# Что считается «ценностью без присмотра»: пачка денег, документы, сумка инкассации плашмя.
UNATTENDED_ITEMS = {"cell phone", "remote", "book", "cup", "bottle", "bowl"}
BAG_ITEMS = {"handbag", "backpack"}

Box = list[float]


def center(b: Box) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def dist(a, b) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def inside(pt, box: Box) -> bool:
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def median_box(boxes) -> Box:
    return [float(v) for v in np.median(np.array(boxes, float), 0)]


def anchors(frames, min_share=0.2, score=0.4) -> dict[str, tuple[Box, float]]:
    """Медианные рамки неподвижных предметов по кадрам высокого разрешения (раз в секунду)."""
    acc: dict[str, list] = {}
    hd = [f for f in frames if "objects_hd" in f]
    for f in hd:
        seen = set()
        for o in f["objects_hd"]:
            if o["c"] in FURNITURE and o["s"] >= score and o["c"] not in seen:
                acc.setdefault(o["c"], []).append(o["box"])
                seen.add(o["c"])
    n = len(hd) or 1
    return {c: (median_box(b), len(b) / n) for c, b in acc.items() if len(b) / n >= min_share}


@dataclass
class Track:
    id: int
    pts: list[tuple[float, Box]]
    t0: float
    t1: float
    n: int
    h: float            # медианная высота рамки
    box: Box            # медианная рамка

    def pos(self, t: float):
        """Центр рамки в ближайший к t момент (или None, если трек в это время отсутствует)."""
        best = min(self.pts, key=lambda p: abs(p[0] - t))
        return center(best[1]) if abs(best[0] - t) <= 0.6 else None


def tracks_from(frames) -> dict[int, Track]:
    tr: dict[int, list] = {}
    for f in frames:
        for p in f["persons"]:
            if p["id"] < 0:
                continue
            tr.setdefault(p["id"], []).append((f["t"], p["box"]))
    out = {}
    for tid, pts in tr.items():
        hs = [b[3] - b[1] for _, b in pts]
        out[tid] = Track(tid, pts, pts[0][0], pts[-1][0], len(pts), float(np.median(hs)), median_box([b for _, b in pts]))
    return out


def filter_reflections(tracks: dict[int, Track], fps: float) -> dict[int, Track]:
    """Отражения в стекле и люди в коридоре: маленькие или очень короткие треки."""
    if not tracks:
        return tracks
    hmax = max(t.h for t in tracks.values())
    return {k: t for k, t in tracks.items() if t.h >= 0.5 * hmax and t.n >= fps}


def pick_cashier(tracks: dict[int, Track]) -> int | None:
    """Кассир — самый длинный трек: он дольше всех в кадре."""
    return max(tracks, key=lambda k: tracks[k].n) if tracks else None


def seated_height(track: Track) -> float:
    hs = sorted(b[3] - b[1] for _, b in track.pts)
    return float(np.median(hs[: max(3, len(hs) // 3)]))  # нижняя треть высот = сидя


def standing_height(track: Track) -> float:
    hs = sorted(b[3] - b[1] for _, b in track.pts)
    return float(np.median(hs[-max(3, len(hs) // 4):]))  # верхняя четверть = стоя


def work_position(track: Track, h_seated: float):
    pts = [center(b) for _, b in track.pts if (b[3] - b[1]) <= 1.15 * h_seated]
    pts = pts or [center(b) for _, b in track.pts]
    return float(np.median([p[0] for p in pts])), float(np.median([p[1] for p in pts]))


def is_seated(box: Box, h_seated: float) -> bool:
    return (box[3] - box[1]) <= 1.15 * h_seated


def desk_zone(work, h_seated: float, anc: dict) -> Box:
    """Стол: по ширине ±1,5 роста сидя от кассира; по высоте — вокруг ноутбука (он стоит на столе),
    иначе область перед сидящим кассиром. Работает и когда кассир сидит спиной к камере."""
    x, y = work
    if "laptop" in anc:
        lx1, ly1, lx2, ly2 = anc["laptop"][0]
        lh = ly2 - ly1
        return [x - 1.5 * h_seated, min(ly1 - 0.3 * lh, y - 0.2 * h_seated), x + 1.5 * h_seated, max(ly2 + 0.6 * lh, y + 0.9 * h_seated)]
    return [x - 1.2 * h_seated, y - 0.2 * h_seated, x + 1.2 * h_seated, y + 0.9 * h_seated]


def stand_ups(track: Track, fps: float, h_seated: float) -> list[tuple[float, float | None]]:
    """Моменты, когда высота рамки растёт ≥ 1,25× от сидячей и держится не меньше секунды.
    Возвращает (t_встал, t_сел | None)."""
    pts = track.pts
    out, i = [], 0
    while i < len(pts):
        t, b = pts[i]
        if (b[3] - b[1]) >= 1.25 * h_seated and (i == 0 or (pts[i - 1][1][3] - pts[i - 1][1][1]) < 1.25 * h_seated):
            j = i
            while j < len(pts) and (pts[j][1][3] - pts[j][1][1]) >= 1.15 * h_seated:
                j += 1
            if j - i >= fps:
                out.append((round(t, 1), round(pts[j - 1][0], 1) if j < len(pts) else None))
            i = j
        i += 1
    return out


def stationary_segments(track: Track, h_stand: float, min_dwell=2.0, speed_frac=0.12) -> list[tuple[float, float]]:
    """Отрезки, где человек стоит или сидит на месте не меньше min_dwell секунд."""
    pts = track.pts
    raw, start = [], None
    for i, (t, b) in enumerate(pts):
        j = i
        while j > 0 and t - pts[j - 1][0] < 1.0:
            j -= 1
        speed = dist(center(b), center(pts[j][1])) if j < i else 0.0
        still = speed <= speed_frac * h_stand
        if still and start is None:
            start = (t, center(b))
        if (not still or i == len(pts) - 1) and start is not None:
            raw.append([start[0], t, start[1]])
            start = None
    merged: list = []
    for seg in raw:
        if merged and seg[0] - merged[-1][1] < 1.5 and dist(seg[2], merged[-1][2]) < 0.3 * h_stand:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)
    return [(a, b) for a, b, _ in merged if b - a >= min_dwell]


@dataclass
class Leave:
    t: float        # точка отсчёта (покинул последнее рабочее место)
    door: float     # момент у двери
    gone: bool      # пропал из кадра до конца ролика


def leave_event(track: Track, fps: float, duration: float, h_seated: float, work) -> Leave | None:
    """Уход кассира из помещения: встал и больше не сел; дверь — точка максимального удаления
    от стола в последние 10 с трека; точка отсчёта — конец последнего места, где стоял ≥ 2 с."""
    h_stand = standing_height(track)
    pts = track.pts
    last_t = pts[-1][0]
    ups = stand_ups(track, fps, h_seated)
    if not ups or ups[-1][1] is not None and last_t - ups[-1][1] > 1.0:
        return None
    t_up = ups[-1][0]
    window = [(t, b) for t, b in pts if t >= max(t_up, last_t - 10.0)]
    t_door, b_door = max(window, key=lambda tb: dist(center(tb[1]), work))
    gone = last_t < duration - 0.5
    if dist(center(b_door), work) < 0.4 * h_stand and not gone:
        return None
    spots = [s for s in stationary_segments(track, h_stand) if s[1] <= t_door and s[1] > t_up + 1.0]
    t_leave = spots[-1][1] if spots and t_door - t_up > 6.0 else t_up
    return Leave(round(t_leave, 1), round(t_door, 1), gone)


def static_objects(frames, before_t: float, min_share=0.5) -> set:
    """Предметы, видимые большую часть времени до before_t — часть обстановки, а не оставленная вещь."""
    hd = [f for f in frames if "objects_hd" in f and f["t"] < before_t]
    cnt: dict = {}
    for f in hd:
        for o in f["objects_hd"]:
            if o["c"] in DESK_ITEMS:
                key = (o["c"], round(center(o["box"])[0] / 25), round(center(o["box"])[1] / 25))
                cnt[key] = cnt.get(key, 0) + 1
    return {k for k, n in cnt.items() if hd and n / len(hd) >= min_share}


@dataclass
class Item:
    cls: str
    share: float            # доля кадров окна, где предмет виден
    box: Box                # медианная рамка
    score: float


def items_in(frames, t0: float, t1: float, desk: Box, classes=UNATTENDED_ITEMS, static=frozenset(),
             min_share=0.4, min_score=0.15) -> list[Item]:
    """Мелкие предметы, лежащие на столе в окне [t0, t1] и не относящиеся к обстановке."""
    sel = [f for f in frames if t0 <= f["t"] <= t1 and "objects_hd" in f]
    if not sel:
        return []
    acc: dict[str, list] = {}
    for f in sel:
        seen = set()
        for o in f["objects_hd"]:
            if o["c"] not in classes or o["s"] < min_score or not inside(center(o["box"]), desk) or o["c"] in seen:
                continue
            key = (o["c"], round(center(o["box"])[0] / 25), round(center(o["box"])[1] / 25))
            if key in static:
                continue
            acc.setdefault(o["c"], []).append((o["box"], o["s"]))
            seen.add(o["c"])
    out = [Item(c, len(v) / len(sel), median_box([b for b, _ in v]), float(np.median([s for _, s in v])))
           for c, v in acc.items() if len(v) / len(sel) >= min_share]
    return sorted(out, key=lambda i: -i.share)


@dataclass
class Scene:
    fps: float
    duration: float
    anc: dict
    tracks: dict[int, Track]
    cashier: int | None
    h_seated: float = 0.0
    h_stand: float = 0.0
    work: tuple = (0.0, 0.0)
    desk: Box = field(default_factory=list)
    visitors: list[Track] = field(default_factory=list)

    @property
    def ct(self) -> Track | None:
        return self.tracks.get(self.cashier) if self.cashier is not None else None

    def cashier_enters(self) -> bool:
        """Кассир появляется в кадре не с начала ролика и стоит (входит в помещение, а не сидит с начала)."""
        ct = self.ct
        if not ct or ct.t0 < 1.0:
            return False
        first = ct.pts[: max(1, int(self.fps))]
        return any(not is_seated(b, self.h_seated) for _, b in first)

    def seated_at(self, t: float) -> bool:
        ct = self.ct
        if not ct:
            return False
        best = min(ct.pts, key=lambda p: abs(p[0] - t))
        return abs(best[0] - t) <= 0.6 and is_seated(best[1], self.h_seated)


def build_scene(frames, fps: float, duration: float) -> Scene:
    anc = anchors(frames)
    tracks = filter_reflections(tracks_from(frames), fps)
    cashier = pick_cashier(tracks)
    sc = Scene(fps, duration, anc, tracks, cashier)
    if cashier is None:
        return sc
    ct = tracks[cashier]
    sc.h_seated = seated_height(ct)
    sc.h_stand = standing_height(ct)
    sc.work = work_position(ct, sc.h_seated)
    sc.desk = desk_zone(sc.work, sc.h_seated, anc)
    sc.visitors = sorted((t for k, t in tracks.items() if k != cashier), key=lambda t: t.t0)
    return sc


def to_jsonable(x: Any):
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, dict):
        return {k: to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v) for v in x]
    return x
