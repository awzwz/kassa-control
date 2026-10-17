"""Правила: из сигналов (signals.py) в события-нарушения.

Четыре момента проверки:
  уход кассира  → что осталось: наличные, сумка, документы (T01–T03), экран (T06)
  вход человека → дверь (T07), посторонний (T08), деньги прошлого клиента (T09)
  обслуживание  → инкассатор ушёл до проверки (T10)
  рабочее место → личные вещи (T15), напиток при наличных (T16)

Сейф (T04, T05), пересчёт и документы (T11–T14) в первой версии не проверяются: для них нет
надёжного признака без отдельного детектора. Это честно указано в «Ограничениях» и в checked[].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from . import signals as S

ScreenProbe = Callable[[float, float], tuple[float, float] | None]  # (t0, t1) -> (доля светлых, B−R)

ITEM_LABEL = {"cell phone": "наличные", "remote": "предмет на столе", "book": "документы", "cup": "предмет",
              "bottle": "бутылка", "bowl": "предмет", "handbag": "сумка", "backpack": "рюкзак"}


def fmt_t(t: float) -> str:
    t = max(0.0, float(t))
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


@dataclass
class Event:
    type_id: str
    t: float
    confidence: str                         # низкая | средняя | высокая
    fields: dict[str, Any] = field(default_factory=dict)   # подстановки в шаблоны описания
    signals: list[dict[str, Any]] = field(default_factory=list)  # [{"t": "00:49", "text": "..."}]
    boxes: list[dict[str, Any]] = field(default_factory=list)    # [{"t": 57.0, "box": [...], "label": "...", "kind": "obj|person"}]
    t_end: float | None = None


def _sig(t: float, text: str) -> dict:
    return {"t": fmt_t(t), "text": text}


def _box(t: float, box, label: str, kind: str = "obj") -> dict:
    return {"t": round(float(t), 1), "box": [round(float(v)) for v in box], "label": label, "kind": kind}


def _cashier_box_at(sc: S.Scene, t: float):
    ct = sc.ct
    best = min(ct.pts, key=lambda p: abs(p[0] - t))
    return best[1]


# ---------------------------------------------------------------- уход кассира

def rule_unattended(frames, sc: S.Scene, leave: S.Leave, duration: float) -> Event | None:
    """T01/T02/T03: кассир ушла, на столе остался предмет."""
    if not leave.gone:
        return None
    static = S.static_objects(frames, leave.t - 1)
    t1 = min(leave.door + 4.0, duration)
    items = S.items_in(frames, leave.t + 1.0, t1, sc.desk, S.UNATTENDED_ITEMS, static)
    if not items:
        return None
    top = items[0]
    area = (top.box[2] - top.box[0]) * (top.box[3] - top.box[1]) / max(1.0, sc.h_seated ** 2)
    if top.cls == "book" and top.share >= 0.6:
        type_id, label = "T03", "документы"
    elif area >= 0.08:
        type_id, label = "T02", "сумка"
    else:
        type_id, label = "T01", "наличные"
    # когда предмет появился на столе до ухода
    before = S.items_in(frames, max(0.0, leave.t - 12.0), leave.t, sc.desk, {top.cls}, static, min_share=0.1)
    first_seen = None
    for f in frames:
        if leave.t - 12.0 <= f["t"] <= leave.t and "objects_hd" in f and any(
                o["c"] == top.cls and S.inside(S.center(o["box"]), sc.desk) for o in f["objects_hd"]):
            first_seen = f["t"]
            break
    conf = "высокая" if top.share >= 0.8 and top.score >= 0.25 else "средняя"
    ev = Event(type_id, leave.t, conf, t_end=leave.door)
    ev.fields = {
        "leave_text": f"встаёт и идёт к двери в {fmt_t(leave.t)}, выходит в {fmt_t(leave.door)}",
        "duration_text": f" и остаётся там до конца записи" if t1 >= duration - 0.5 else "",
        "t_text": fmt_t(leave.t),
    }
    if first_seen is not None:
        ev.signals.append(_sig(first_seen, f"На столе появляется предмет ({label})"))
    ev.signals += [_sig(leave.t, "Кассир встаёт и отходит от рабочего места"),
                   _sig(leave.door, "Кассир у двери, выходит из помещения"),
                   _sig(min(leave.door + 1.0, duration), f"{label[0].upper() + label[1:]} остаются на столе без присмотра — правило сработало")]
    ev.boxes = [_box(leave.door + 1.0, top.box, label, "obj"), _box(leave.t, _cashier_box_at(sc, leave.t), "кассир", "person")]
    ev.fields["item_box"] = top.box
    ev.fields["item_share"] = round(top.share, 2)
    return ev


def rule_screen(frames, sc: S.Scene, leave: S.Leave, duration: float, probe: ScreenProbe | None) -> Event | None:
    """T06: после ухода экран ноутбука остаётся включённым. Признак — светлые голубоватые пиксели."""
    if not leave.gone or probe is None or "laptop" not in sc.anc:
        return None
    res = probe(leave.door, min(leave.door + 4.0, duration))
    if res is None:
        return None
    bright, br = res
    if not (bright >= 0.25 and br >= 20):
        return None
    conf = "высокая" if bright >= 0.4 and br >= 40 else "средняя"
    ev = Event("T06", leave.t, conf, t_end=leave.door)
    ev.fields = {"leave_text": f"встаёт и идёт к двери в {fmt_t(leave.t)}, выходит в {fmt_t(leave.door)}",
                 "duration_text": " до конца записи", "t_text": fmt_t(leave.t),
                 "screen_bright": round(bright, 2), "screen_br": round(br, 1)}
    ev.signals = [_sig(leave.t, "Кассир встаёт и отходит от рабочего места"),
                  _sig(leave.door, "Кассир выходит из помещения"),
                  _sig(min(leave.door + 1.0, duration), f"Экран ноутбука светится (светлых пикселей {bright:.0%}) — правило сработало")]
    ev.boxes = [_box(leave.door + 1.0, sc.anc["laptop"][0], "экран включён", "obj"),
                _box(leave.t, _cashier_box_at(sc, leave.t), "кассир", "person")]
    return ev


# ---------------------------------------------------------------- вход человека

def rule_door(frames, sc: S.Scene) -> Event | None:
    """T07: кассир вошла и не задержалась у двери, чтобы закрыть её (< 2,5 с у самой дальней от стола точки)."""
    if not sc.cashier_enters():
        return None
    ct = sc.ct
    first = [(t, b) for t, b in ct.pts if t <= ct.t0 + 15.0]
    t_far, b_far = max(first, key=lambda tb: S.dist(S.center(tb[1]), sc.work))
    door_pt = S.center(b_far)
    if S.dist(door_pt, sc.work) < 0.4 * sc.h_stand:
        return None
    near = [t for t, b in first if S.dist(S.center(b), door_pt) <= 0.3 * sc.h_stand]
    dwell = (near[-1] - near[0] + 1.0 / sc.fps) if near else 0.0
    sat = [t for t, b in ct.pts if t > t_far and S.is_seated(b, sc.h_seated)]
    if dwell >= 2.5 or not sat or sat[0] - t_far > 20.0:
        return None
    t = near[-1] if near else t_far
    ev = Event("T07", t, "средняя" if dwell < 1.5 else "низкая")
    ev.fields = {"leave_text": f"отходит от двери в {fmt_t(t)}", "duration_text": "", "t_text": fmt_t(t),
                 "dwell_sec": round(dwell, 1)}
    ev.signals = [_sig(ct.t0, "Кассир входит в помещение"),
                  _sig(t, f"Отходит от двери к столу, у двери провела {dwell:.1f} с — закрыть не успела бы"),
                  _sig(sat[0], "Садится за рабочее место, дверь не закрыта — правило сработало")]
    ev.boxes = [_box(t, b_far, "кассир у двери", "person")]
    return ev


def _clients(sc: S.Scene) -> list[S.Track]:
    """Сидящие клиенты: невысокая рамка (сидит напротив кассира), рядом со столом, не меньше 5 с.
    Люди в коридоре за стеклом тоже «невысокие», но далеко от стола."""
    return [v for v in sc.visitors if v.h <= 0.7 * sc.h_stand and v.t1 - v.t0 >= 5.0
            and S.dist(S.center(v.box), sc.work) <= 0.9 * sc.h_stand]


def rule_outsider(frames, sc: S.Scene) -> Event | None:
    """T08: (А) кто-то подошёл вплотную к кассиру; (Б) при сидящем клиенте в помещении второй стоящий человек."""
    best: Event | None = None
    for v in sc.visitors:
        if v.h < 0.6 * sc.h_stand:
            continue
        close = [t for t, b in v.pts if S.dist(S.center(b), sc.work) <= 0.5 * sc.h_stand]
        if len(close) >= sc.fps:  # ≥ 1 с рядом с кассиром (ближе половины роста)
            t = close[0]
            ev = Event("T08", t, "высокая" if len(close) >= 3 * sc.fps else "средняя")
            ev.fields = {"t_text": fmt_t(t), "context_text": ", вплотную к кассиру"}
            ev.signals = [_sig(v.t0, "В помещение входит человек"),
                          _sig(t, "Он находится вплотную к кассиру, на рабочей стороне стола — правило сработало")]
            ev.boxes = [_box(t, min(v.pts, key=lambda p: abs(p[0] - t))[1], "посторонний", "person")]
            return ev
    clients = _clients(sc)
    for v in sc.visitors:
        if v.h < 0.85 * sc.h_stand:
            continue
        for c in clients:
            if c is v:
                continue
            ov0, ov1 = max(v.t0, c.t0), min(v.t1, c.t1)
            pts = [(t, b) for t, b in v.pts if ov0 <= t <= ov1]
            if ov1 - ov0 >= 2.0 and pts and min(S.dist(S.center(b), sc.work) for _, b in pts) <= 0.95 * sc.h_stand:
                # момент, когда второй человек остановился у стола; иначе — ближайшая к кассиру точка
                segs = [sg for sg in S.stationary_segments(v, sc.h_stand, min_dwell=1.5) if sg[0] >= v.t0 + 0.5]
                if segs:
                    def seg_dist(sg):
                        mid = [S.center(b_) for t_, b_ in v.pts if sg[0] <= t_ <= sg[1]]
                        return S.dist((np.median([q[0] for q in mid]), np.median([q[1] for q in mid])), sc.work)
                    t = min(segs, key=seg_dist)[0]
                    b = min(pts, key=lambda tb: abs(tb[0] - t))[1]
                else:
                    t, b = min(pts, key=lambda tb: S.dist(S.center(tb[1]), sc.work))
                ev = Event("T08", t, "средняя")
                ev.fields = {"t_text": fmt_t(t), "context_text": " во время обслуживания клиента"}
                ev.signals = [_sig(c.t0, "Клиент у стола, идёт обслуживание"),
                              _sig(v.t0, "Входит второй человек"),
                              _sig(t, "Он подходит к столу со стороны кассира — правило сработало")]
                ev.boxes = [_box(t, b, "посторонний", "person"), _box(t, min(c.pts, key=lambda p: abs(p[0] - t))[1], "клиент", "person")]
                if best is None or t < best.t:
                    best = ev
    return best


def rule_next_client(frames, sc: S.Scene) -> Event | None:
    """T09: предыдущий клиент ушёл, деньги остались на столе, входит следующий."""
    vis = [v for v in sc.visitors if v.t1 - v.t0 >= 3.0]
    for i, v2 in enumerate(vis):
        prev = [v for v in vis if v is not v2 and v.t1 < v2.t0 + 1.0 and v2.t0 - v.t1 <= 15.0]
        if not prev:
            continue
        v1 = max(prev, key=lambda v: v.t1)
        items = S.items_in(frames, v2.t0 - 1.0, v2.t0 + 4.0, sc.desk, S.UNATTENDED_ITEMS, min_share=0.6, min_score=0.2)
        if not items:
            continue
        top = items[0]
        segs = S.stationary_segments(v2, sc.h_stand, min_dwell=1.0)
        t_sit = next((a for a, b in segs if a >= v2.t0 and a <= v2.t0 + 6.0), None)
        t = t_sit if t_sit is not None else v2.t0 + 2.0
        ev = Event("T09", t, "средняя" if top.share >= 0.8 else "низкая")
        ev.fields = {"prev_leave_text": fmt_t(v1.t1), "t_text": fmt_t(t)}
        ev.signals = [_sig(v1.t1, "Предыдущий клиент выходит, на столе остаётся предмет (наличные)"),
                      _sig(v2.t0, "В дверях появляется следующий посетитель"),
                      _sig(t, "Посетитель у стола, наличные всё ещё на столе — правило сработало")]
        ev.boxes = [_box(t, top.box, "наличные", "obj"), _box(t, min(v2.pts, key=lambda p: abs(p[0] - t))[1], "посетитель", "person")]
        return ev
    return None


# ---------------------------------------------------------------- обслуживание

def rule_collector(frames, sc: S.Scene) -> Event | None:
    """T10: стоящий посетитель (инкассатор) пробыл у стола меньше 12 с и ушёл, пока кассир работает."""
    clients = _clients(sc)
    for v in sc.visitors:
        if v.h < 0.85 * sc.h_stand or not (3.0 <= v.t1 - v.t0 < 12.0):
            continue
        if any(max(v.t0, c.t0) < min(v.t1, c.t1) for c in clients):
            continue
        if not sc.ct or sc.ct.t1 < v.t1 + 2.0:
            continue
        segs = S.stationary_segments(v, sc.h_stand, min_dwell=1.0)
        t = min(segs[0][0] + 3.0, (segs[0][0] + segs[0][1]) / 2) if segs else v.t0 + 2.0  # положил сумку
        ev = Event("T10", t, "низкая")
        ev.fields = {"t_text": fmt_t(t)}
        ev.signals = [_sig(v.t0, "Входит человек с сумкой (инкассатор), подходит к столу"),
                      _sig(t, "Уходит от стола, пробыв меньше 12 с"),
                      _sig(v.t1, "Выходит; кассир продолжает работу с сумкой одна — правило сработало")]
        ev.boxes = [_box(t, min(v.pts, key=lambda p: abs(p[0] - t))[1], "инкассатор", "person")]
        return ev
    return None


# ---------------------------------------------------------------- рабочее место

def _seated_times(sc: S.Scene) -> set:
    return {round(t, 1) for t, b in sc.ct.pts if S.is_seated(b, sc.h_seated)}


def rule_personal_items(frames, sc: S.Scene) -> Event | None:
    """T15: кассир вошла с сумкой, положила её на стол и работает при ней (≥ 3 с сидя)."""
    if not sc.cashier_enters():
        return None
    seated = _seated_times(sc)
    hits, first_bag = [], None
    for f in frames:
        if "objects_hd" not in f or f["t"] < sc.ct.t0:
            continue
        for o in f["objects_hd"]:
            if o["c"] in S.BAG_ITEMS and o["s"] >= 0.2 and S.inside(S.center(o["box"]), sc.desk):
                first_bag = first_bag if first_bag is not None else f["t"]
                if round(f["t"], 1) in seated:
                    hits.append((f["t"], o["box"], o["c"]))
                break
    if len(hits) < 3:
        return None
    _, box, cls = hits[0]
    sat = sorted(x for x in seated if x >= (first_bag or 0.0))
    t = sat[0] if sat else hits[0][0]
    ev = Event("T15", t, "высокая" if len(hits) >= 5 else "средняя")
    ev.fields = {"items_text": "сумку" if cls == "handbag" else "рюкзак", "t_text": fmt_t(t)}
    ev.signals = [_sig(sc.ct.t0, "Кассир входит в помещение с личными вещами"),
                  _sig(t, "Садится за рабочее место, сумка лежит на столе — правило сработало")]
    ev.boxes = [_box(t, box, "личные вещи", "obj"), _box(t, _cashier_box_at(sc, t), "кассир", "person")]
    return ev


def rule_drink(frames, sc: S.Scene) -> Event | None:
    """T16: стакан на столе у сидящего кассира не меньше 3 с."""
    seated = _seated_times(sc)
    hits = []
    for f in frames:
        if "objects_hd" not in f or round(f["t"], 1) not in seated:
            continue
        for o in f["objects_hd"]:
            if o["c"] == "cup" and o["s"] >= 0.4 and S.inside(S.center(o["box"]), sc.desk):
                hits.append((f["t"], o["box"]))
                break
    if len(hits) < 3:
        return None
    t, box = hits[0]
    early = [f["t"] for f in frames if "objects_hd" in f and t - 3.0 <= f["t"] < t
             and any(o["c"] == "cup" and o["s"] >= 0.3 and S.inside(S.center(o["box"]), sc.desk) for o in f["objects_hd"])]
    if early:
        t = early[0]
    ev = Event("T16", t, "средняя" if len(hits) < 6 else "высокая")
    ev.fields = {"t_text": fmt_t(t)}
    ev.signals = [_sig(t, "На столе у кассира стакан с напитком рядом с наличными"),
                  _sig(hits[-1][0], "Стакан остаётся на рабочем месте — правило сработало")]
    ev.boxes = [_box(t, box, "напиток", "obj"), _box(t, _cashier_box_at(sc, t), "кассир", "person")]
    return ev


# ---------------------------------------------------------------- всё вместе

CATEGORY_RULES = {
    "Наличные или ценности оставлены без присмотра": ["T01", "T02", "T03", "T09"],
    "Сейф или хранилище оставлены открытыми": ["T04", "T05"],
    "Экран компьютера не заблокирован при уходе": ["T06"],
    "Посторонний в зоне кассира": ["T07", "T08"],
    "Кассир покинул рабочее место во время обслуживания": ["T10", "T11"],
    "Личные вещи, еда или напитки на рабочем месте": ["T15", "T16"],
    "Выдача или приём наличных без видимого пересчёта": ["T12", "T13", "T14"],
}
NOT_IMPLEMENTED = {"T04", "T05", "T11", "T12", "T13", "T14"}


def evaluate(frames, fps: float, duration: float, screen_probe: ScreenProbe | None = None):
    """Возвращает (события, сцена, что проверено по категориям)."""
    sc = S.build_scene(frames, fps, duration)
    events: list[Event] = []
    checked: list[dict[str, Any]] = []
    if sc.cashier is None:
        for cat in CATEGORY_RULES:
            checked.append({"category": cat, "result": "not_applicable", "note": "кассир в кадре не найден"})
        return events, sc, checked

    leave = S.leave_event(sc.ct, fps, duration, sc.h_seated, sc.work)
    notes: dict[str, str] = {}
    if leave:
        for r in (rule_unattended(frames, sc, leave, duration), rule_screen(frames, sc, leave, duration, screen_probe)):
            if r:
                events.append(r)
        notes["leave"] = f"кассир уходит в {fmt_t(leave.t)}" + ("" if leave.gone else " (остаётся в кадре)")
    else:
        notes["leave"] = "кассир рабочее место не покидала"
    for r in (rule_door(frames, sc), rule_outsider(frames, sc), rule_next_client(frames, sc),
              rule_collector(frames, sc), rule_personal_items(frames, sc), rule_drink(frames, sc)):
        if r:
            events.append(r)
    events.sort(key=lambda e: e.t)

    found = {e.type_id for e in events}
    for cat, ids in CATEGORY_RULES.items():
        hit = [e for e in events if e.type_id in ids]
        if hit:
            checked.append({"category": cat, "result": "found", "note": f"событие в {fmt_t(hit[0].t)}"})
        elif all(i in NOT_IMPLEMENTED for i in ids):
            checked.append({"category": cat, "result": "not_checked", "note": "в этой версии не проверяется: нужен отдельный детектор"})
        elif ids == ["T07", "T08"] and not sc.visitors and not sc.cashier_enters():
            checked.append({"category": cat, "result": "not_applicable", "note": "посторонних и входов в кадре не было"})
        elif ids == ["T10", "T11"] and not sc.visitors:
            checked.append({"category": cat, "result": "not_applicable", "note": "обслуживания клиентов на записи не было"})
        else:
            note = notes.get("leave", "") if "T01" in ids or "T06" in ids else "признаков нет"
            checked.append({"category": cat, "result": "not_detected", "note": note})
    return events, sc, checked
