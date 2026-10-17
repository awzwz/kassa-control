"""Проверка правил на всех роликах по сохранённым детекциям и пиксельным сигналам.

  python tools/eval_rules.py [--only Х-26 Х-25] [-v]

Сравнивает с data/labels_verified.csv: вердикт по ролику, тип, расхождение по времени.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.pipeline import rules  # noqa: E402

DET, MON = ROOT / "out" / "detections", ROOT / "out" / "monitors"


def probe_from_npz(z):
    t, br, bf, occ = z["t"], z["screen_br"], z["screen_bright"], z["occluded"]

    def probe(t0, t1):
        sel = (t >= t0) & (t <= t1) & (~occ)
        if sel.sum() == 0:
            sel = (t >= t0) & (t <= t1)
        if sel.sum() == 0 or np.all(np.isnan(bf[sel])):
            return None
        return float(np.nanmedian(bf[sel])), float(np.nanmedian(br[sel]))
    return probe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    labels = {r["file"]: r for r in csv.DictReader((ROOT / "data" / "labels_verified.csv").open(encoding="utf-8"))}
    tp = fp = fn = tn = 0
    type_ok = type_total = 0
    deltas = []
    rows = []
    for f in sorted(DET.glob("*.json"), key=lambda p: (len(p.stem), p.stem)):
        if f.stem == "index" or (a.only and f.stem not in a.only):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        m, frames = d["meta"], d["frames"]
        npz = MON / f"{f.stem}.npz"
        probe = probe_from_npz(np.load(npz)) if npz.exists() else None
        events, sc, checked = rules.evaluate(frames, m["fps"], m["duration"], probe)
        lab = labels.get(f.stem, {})
        truth = lab.get("verdict") == "violation"
        pred = bool(events)
        if truth and pred:
            tp += 1
        elif truth:
            fn += 1
        elif pred:
            fp += 1
        else:
            tn += 1
        best = ""
        if truth:
            type_total += 1
            if events:
                sec = float(lab["label_sec"])
                e = min(events, key=lambda e: abs(e.t - sec))
                deltas.append(e.t - sec)
                if e.type_id == lab["type_id"]:
                    type_ok += 1
                best = f"Δ={e.t - sec:+.1f}"
        mark = "✓" if truth == pred else ("ЛОЖНАЯ" if pred else "ПРОПУСК")
        evs = ", ".join(f"{e.type_id}@{e.t}({e.confidence[:3]})" for e in events) or "—"
        lab_s = f"{lab.get('type_id')}@{lab.get('label_sec')}" if truth else "чистый"
        rows.append(f"{mark:7} {f.stem:6} {lab_s:>10} | {evs} {best}")
        if a.v:
            for c in checked:
                rows.append(f"            {c['result']:14} {c['category']}: {c['note']}")
    print("\n".join(rows))
    n_viol, n_clean = tp + fn, fp + tn
    print(f"\nроликов с нарушением: {n_viol}, найдено {tp} (полнота {tp / max(1, n_viol):.0%}); чистых: {n_clean}, ложных тревог {fp}")
    print(f"тип совпал: {type_ok}/{type_total}; |Δt| медиана {np.median(np.abs(deltas)) if deltas else 0:.1f} с, "
          f"в пределах 2 с: {sum(abs(x) <= 2 for x in deltas)}/{len(deltas)}, в пределах 3 с: {sum(abs(x) <= 3 for x in deltas)}/{len(deltas)}")


if __name__ == "__main__":
    main()
