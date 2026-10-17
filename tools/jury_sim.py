"""Симулятор жюри: отправляет несколько видео одновременно, ждёт ответы, проверяет формат и время.

  python tools/jury_sim.py --url http://localhost:8000 --key КЛЮЧ video1.mov video2.mov --concurrency 5

На удалённый сервер отправляйте только свои записи: обучающие ролики загружать куда-либо нельзя.
"""
import argparse
import base64
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

import requests

ALLOWED_TOP = {"job_id", "status", "verdict", "violations"}
ALLOWED_V = {"type", "timecode_sec", "description", "evidence_frames"}
ALLOWED_F = {"timestamp_sec", "image_base64"}


def check(body: dict, duration_hint: float | None) -> list[str]:
    errs = []
    if set(body) - ALLOWED_TOP:
        errs.append(f"лишние поля: {set(body) - ALLOWED_TOP}")
    if body.get("verdict") not in ("violation", "no_violation"):
        errs.append(f"verdict={body.get('verdict')!r}")
    vs = body.get("violations")
    if not isinstance(vs, list):
        errs.append("violations не список")
        return errs
    if (body.get("verdict") == "violation") != (len(vs) > 0):
        errs.append("verdict не согласован с violations")
    for i, v in enumerate(vs):
        if set(v) != ALLOWED_V:
            errs.append(f"violations[{i}] поля: {set(v)}")
        if not isinstance(v.get("timecode_sec"), (int, float)):
            errs.append(f"violations[{i}].timecode_sec не число")
        elif duration_hint and v["timecode_sec"] > duration_hint + 0.5:
            errs.append(f"violations[{i}].timecode_sec {v['timecode_sec']} больше длительности")
        fr = v.get("evidence_frames") or []
        if not 1 <= len(fr) <= 3:
            errs.append(f"violations[{i}]: {len(fr)} кадров, нужно 1–3")
        for j, f in enumerate(fr):
            if set(f) != ALLOWED_F:
                errs.append(f"violations[{i}].frames[{j}] поля: {set(f)}")
            b = f.get("image_base64", "")
            if not b.startswith("/9j/"):
                errs.append(f"violations[{i}].frames[{j}] не JPEG base64")
            else:
                try:
                    base64.b64decode(b, validate=True)
                except Exception:  # noqa: BLE001
                    errs.append(f"violations[{i}].frames[{j}] base64 не декодируется")
        if fr and abs(fr[0].get("timestamp_sec", -1) - v.get("timecode_sec", -2)) > 0.01:
            errs.append(f"violations[{i}]: первый кадр не в таймкоде")
    return errs


def run_one(url: str, key: str, path: Path, poll: float, timeout: float) -> dict:
    t0 = time.monotonic()
    with path.open("rb") as fh:
        r = requests.post(f"{url}/api/v1/analyze", headers={"X-API-Key": key},
                          files={"file": (path.name, fh, "video/quicktime")}, timeout=300)
    if r.status_code != 200:
        return {"file": path.name, "error": f"POST {r.status_code}: {r.text[:200]}", "sec": time.monotonic() - t0}
    job_id = r.json()["job_id"]
    t_upload = time.monotonic() - t0
    while time.monotonic() - t0 < timeout:
        s = requests.get(f"{url}/api/v1/jobs/{job_id}", headers={"X-API-Key": key}, timeout=60)
        body = s.json()
        if body.get("status") == "done":
            return {"file": path.name, "job_id": job_id, "sec": time.monotonic() - t0, "upload_sec": t_upload,
                    "verdict": body["verdict"], "n": len(body["violations"]),
                    "timecodes": [v["timecode_sec"] for v in body["violations"]],
                    "errors": check(body, None), "bytes": len(s.content)}
        if body.get("status") == "failed":
            return {"file": path.name, "job_id": job_id, "sec": time.monotonic() - t0, "error": body.get("error")}
        time.sleep(poll)
    return {"file": path.name, "job_id": job_id, "sec": time.monotonic() - t0, "error": "не дождались за лимит"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--key", required=True)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--poll", type=float, default=3.0)
    ap.add_argument("--timeout", type=float, default=300.0)
    a = ap.parse_args()
    paths = [Path(p) for p in a.videos]
    t0 = time.monotonic()
    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        results = list(ex.map(lambda p: run_one(a.url, a.key, p, a.poll, a.timeout), paths))
    total = time.monotonic() - t0
    bad = 0
    for r in results:
        if "error" in r:
            bad += 1
            print(f"✗ {r['file']}: {r['error']} ({r['sec']:.0f} с)")
        else:
            flag = "✗" if r["errors"] else "✓"
            bad += bool(r["errors"])
            print(f"{flag} {r['file']}: {r['verdict']} ({r['n']} соб. {r['timecodes']}) за {r['sec']:.0f} с, "
                  f"загрузка {r['upload_sec']:.1f} с, ответ {r['bytes']/1024:.0f} КБ" + (f" — {r['errors']}" if r["errors"] else ""))
    worst = max((r["sec"] for r in results), default=0)
    print(f"\nвсего {len(results)} видео, параллельно {a.concurrency}, общее время {total:.0f} с, "
          f"худшее {worst:.0f} с (предел 300), ошибок формата или сбоев: {bad}")
    print("ИТОГ:", "ОК" if bad == 0 and worst <= 240 else "ЕСТЬ ПРОБЛЕМЫ")
    return 0 if bad == 0 and worst <= 240 else 1


if __name__ == "__main__":
    sys.exit(main())
