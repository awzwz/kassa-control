"""Разбор сохранённых детекций: где стол и кассир, когда кассир встаёт и уходит, кто входит,
что остаётся на столе. Сравнивает найденные моменты с разметкой data/labels_verified.csv.

  python tools/analyze_signals.py [--only Х-26 Х-25] [--json]

Это инструмент для настройки правил (шаг 4). Логика отсюда потом переезжает в app/pipeline.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DET = ROOT / "out" / "detections"
LABELS = ROOT / "data" / "labels_verified.csv"

DESK_ITEMS = {"cell phone", "remote", "book", "cup", "bottle", "handbag", "backpack", "bowl"}
# Что считается «ценностью без присмотра»: пачка денег, документы, сумка инкассации плашмя.
# Сумки и рюкзаки сюда не входят: детектор так часто видит счётную машинку, а личные вещи —
# отдельное правило при кассире на месте.
UNATTENDED_ITEMS = {"cell phone", "remote", "book", "cup", "bottle", "bowl"}
FURNITURE = {"laptop", "suitcase", "keyboard", "mouse", "tv", "dining table", "chair"}


def center(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def dist(a, b):
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def median_box(boxes):
    return [float(v) for v in np.median(np.array(boxes, float), 0)]


def anchors(frames, min_share=0.2, score=0.4):
    """Медианные рамки неподвижных предметов по кадрам высокого разрешения (раз в секунду)."""
    acc = {}
    hd = [f for f in frames if "objects_hd" in f]
    for f in hd:
        seen = set()
        for o in f["objects_hd"]:
            if o["c"] in FURNITURE and o["s"] >= score and o["c"] not in seen:
                acc.setdefault(o["c"], []).append(o["box"])
                seen.add(o["c"])
    n = len(hd) or 1
    return {c: (median_box(b), len(b) / n) for c, b in acc.items() if len(b) / n >= min_share}


def tracks_from(frames):
    tr = {}
    for f in frames:
        for p in f["persons"]:
            if p["id"] < 0:
                continue
            tr.setdefault(p["id"], []).append((f["t"], p["box"]))
    out = {}
    for tid, pts in tr.items():
        hs = [b[3] - b[1] for _, b in pts]
        out[tid] = {"t0": pts[0][0], "t1": pts[-1][0], "n": len(pts), "pts": pts,
                    "h": float(np.median(hs)), "box": median_box([b for _, b in pts])}
    return out


def filter_reflections(tracks, fps):
    """Отражения в стекле и люди в коридоре: маленькие или очень короткие треки."""
    if not tracks:
        return tracks
    hmax = max(t["h"] for t in tracks.values())
    return {k: t for k, t in tracks.items() if t["h"] >= 0.5 * hmax and t["n"] >= fps}


def pick_cashier(tracks):
    """Кассир — самый длинный трек (он дольше всех в кадре)."""
    return max(tracks, key=lambda k: tracks[k]["n"]) if tracks else None


def seated_height(track):
    hs = sorted(b[3] - b[1] for _, b in track["pts"])
    return float(np.median(hs[: max(3, len(hs) // 3)]))  # нижняя треть высот = сидя


def work_position(track, h_seated):
    pts = [center(b) for _, b in track["pts"] if (b[3] - b[1]) <= 1.15 * h_seated]
    pts = pts or [center(b) for _, b in track["pts"]]
    return float(np.median([p[0] for p in pts])), float(np.median([p[1] for p in pts]))


def stand_ups(track, fps, h_seated):
    """Моменты, когда высота рамки растёт ≥ 1,3× от сидячей и держится не меньше секунды."""
    pts = track["pts"]
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


def standing_height(track):
    hs = sorted(b[3] - b[1] for _, b in track["pts"])
    return float(np.median(hs[-max(3, len(hs) // 4):]))  # верхняя четверть высот = стоя


def stationary_segments(track, h_stand, min_dwell=2.0, speed_frac=0.12):
    """Отрезки, где кассир стоит или сидит на месте не меньше min_dwell секунд.
    Скорость — смещение центра за 1 с, порог в долях роста стоя. Соседние отрезки с коротким
    разрывом (< 1,5 с) и почти той же позицией склеиваются."""
    pts = track["pts"]
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
    merged = []
    for seg in raw:
        if merged and seg[0] - merged[-1][1] < 1.5 and dist(seg[2], merged[-1][2]) < 0.3 * h_stand:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)
    return [(a, b) for a, b, _ in merged if b - a >= min_dwell]


def leave_event(track, fps, duration, h_seated, work):
    """Уход кассира из помещения.

    Логика: кассир встал и больше не сел. Дверь — точка максимального удаления от стола в
    последние 10 с трека (после выхода кассир ещё несколько секунд виден сквозь стекло, поэтому
    конец трека дверью не считается). Точка отсчёта — конец последнего места, где кассир стоял
    ≥ 2 с перед дверью (стол, сейф); если такого нет, момент вставания.
    Возвращает dict(t, door, gone) или None. gone — трек оборвался раньше конца ролика,
    то есть кассир действительно пропал из кадра."""
    h_stand = standing_height(track)
    pts = track["pts"]
    last_t = pts[-1][0]
    ups = stand_ups(track, fps, h_seated)
    if not ups or ups[-1][1] is not None and last_t - ups[-1][1] > 1.0:
        return None  # не вставал или сел обратно
    t_up = ups[-1][0]
    window = [(t, b) for t, b in pts if t >= max(t_up, last_t - 10.0)]
    t_door, b_door = max(window, key=lambda tb: dist(center(tb[1]), work))
    gone = last_t < duration - 0.5
    if dist(center(b_door), work) < 0.4 * h_stand and not gone:
        return None  # далеко от стола не уходил и из кадра не пропадал
    spots = [s for s in stationary_segments(track, h_stand) if s[1] <= t_door and s[1] > t_up + 1.0]
    t_leave = spots[-1][1] if spots else t_up
    return {"t": round(t_leave, 1), "door": round(t_door, 1), "gone": gone}


def static_objects(frames, before_t, min_share=0.5):
    """Предметы, которые видны большую часть времени до момента before_t — часть обстановки."""
    hd = [f for f in frames if "objects_hd" in f and f["t"] < before_t]
    cnt = {}
    for f in hd:
        for o in f["objects_hd"]:
            if o["c"] in DESK_ITEMS:
                key = (o["c"], round(center(o["box"])[0] / 25), round(center(o["box"])[1] / 25))
                cnt[key] = cnt.get(key, 0) + 1
    return {k for k, n in cnt.items() if hd and n / len(hd) >= min_share}


def desk_zone(work, h_seated):
    """Стол — область перед сидящим кассиром: по ширине ±1,2 роста сидя, вниз до 0,9 роста."""
    x, y = work
    return [x - 1.2 * h_seated, y - 0.2 * h_seated, x + 1.2 * h_seated, y + 0.9 * h_seated]


def inside(pt, box):
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def items_after(frames, t0, t1, static, desk, classes=UNATTENDED_ITEMS, min_share=0.4):
    """Мелкие предметы, лежащие на столе в окне [t0, t1] и не относящиеся к обстановке."""
    sel = [f for f in frames if t0 <= f["t"] <= t1 and "objects_hd" in f]
    if not sel:
        return {}
    cnt = {}
    for f in sel:
        seen = set()
        for o in f["objects_hd"]:
            if o["c"] not in classes or o["s"] < 0.15 or not inside(center(o["box"]), desk):
                continue
            key = (o["c"], round(center(o["box"])[0] / 25), round(center(o["box"])[1] / 25))
            if key in static or o["c"] in seen:
                continue
            cnt[o["c"]] = cnt.get(o["c"], 0) + 1
            seen.add(o["c"])
    return {c: round(n / len(sel), 2) for c, n in cnt.items() if n / len(sel) >= min_share}


def load_labels():
    with LABELS.open(encoding="utf-8") as f:
        return {r["file"]: r for r in csv.DictReader(f)}


def analyze(path, labels, as_json=False):
    d = json.loads(path.read_text(encoding="utf-8"))
    meta, frames = d["meta"], d["frames"]
    fps, dur = meta["fps"], meta["duration"]
    anc = anchors(frames)
    tracks = filter_reflections(tracks_from(frames), fps)
    cashier = pick_cashier(tracks)
    lab = labels.get(path.stem, {})
    res = {"file": meta["file"], "duration": dur, "anchors": {k: (list(map(round, v[0])), round(v[1], 2)) for k, v in anc.items()},
           "tracks": len(tracks), "cashier": cashier,
           "label": {"sec": lab.get("label_sec"), "type": lab.get("type_id")} if lab else None}
    if cashier is not None:
        ct = tracks[cashier]
        hs = seated_height(ct)
        work = work_position(ct, hs)
        res.update(h_seated=round(hs), h_stand=round(standing_height(ct)), work=list(map(round, work)),
                   span=(ct["t0"], ct["t1"]), stand_ups=stand_ups(ct, fps, hs))
        lv = leave_event(ct, fps, dur, hs, work)
        res["leave"] = lv
        if lv and lv["gone"]:  # «без присмотра» — только когда кассир пропала из кадра
            static = static_objects(frames, lv["t"] - 1)
            res["left_on_desk"] = items_after(frames, lv["t"] + 1.0, min(lv["door"] + 4.0, dur), static, desk_zone(work, hs))
        res["visitors"] = [{"id": k, "t0": t["t0"], "t1": t["t1"], "n": t["n"], "xy": list(map(round, center(t["box"])))}
                           for k, t in tracks.items() if k != cashier]
    if as_json:
        print(json.dumps(res, ensure_ascii=False))
        return res
    tag = f"[{lab.get('type_id')} @{lab.get('label_sec')}]" if lab and lab.get("label_sec") else "[чистый]"
    print(f"\n{path.stem} {tag}  {dur} с, треков {len(tracks)}, якоря: " + ", ".join(f"{k} {int(v[1]*100)}%" for k, v in anc.items()))
    if cashier is None:
        print("  кассир не найден")
        return res
    print(f"  кассир: трек {cashier} {res['span'][0]}–{res['span'][1]} с, сидя {res['h_seated']} px, стоя {res['h_stand']} px, место {res['work']}")
    print(f"  встаёт: {res['stand_ups']}  →  уход: {res['leave']}" + (f"  на столе после ухода: {res.get('left_on_desk') or '—'}" if res["leave"] else ""))
    for v in res["visitors"]:
        print(f"  другой человек {v['id']}: {v['t0']}–{v['t1']} с ({v['n']} кадров), центр {v['xy']}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    labels = load_labels()
    files = sorted(DET.glob("*.json"), key=lambda p: (len(p.stem), p.stem))
    for f in files:
        if f.stem != "index" and (not a.only or f.stem in a.only):
            analyze(f, labels, a.json)


if __name__ == "__main__":
    sys.exit(main())
