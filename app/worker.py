"""Обработчик: берёт задачу из очереди, запускает конвейер, следит за дедлайном, пишет результат.

Запуск: python -m app.worker   (можно несколько копий — очередь делит задачи между ними)
"""
import logging
import os
import socket
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from . import config, pipeline, store
from .pipeline.video import NotAVideo, probe

log = logging.getLogger("worker")


def _response(job_id: str, partial: pipeline.Partial, duration: float) -> dict[str, Any]:
    """Собирает ответ строго по §10. Всё лишнее уходит в details."""
    violations = []
    for f in partial.findings:
        frames = [
            {"timestamp_sec": round(min(max(t, 0.0), duration), 2), "image_base64": b64}
            for t, b64 in f.frames_b64[:3]
        ]
        if not frames:
            continue
        violations.append({
            "type": f.type,
            "timecode_sec": round(min(max(f.timecode_sec, 0.0), duration), 2),
            "description": f.description,
            "evidence_frames": frames,
        })
    violations.sort(key=lambda v: v["timecode_sec"])
    return {
        "job_id": job_id,
        "status": "done",
        "verdict": "violation" if violations else "no_violation",
        "violations": violations,
    }


def _details(partial: pipeline.Partial, info, elapsed: float) -> dict[str, Any]:
    return {
        "pipeline_version": config.PIPELINE_VERSION,
        "duration_sec": round(info.duration, 2),
        "width": info.width, "height": info.height, "fps_src": round(info.fps, 2), "codec": info.codec,
        "elapsed_sec": round(elapsed, 1),
        "timed_out": partial.timed_out,
        "mode": partial.mode, "fps": partial.fps,
        "frames_total": partial.frames_total,
        "scene": partial.scene, "timeline": partial.timeline, "strip": partial.strip,
        "checked": partial.checked,
        "notes": partial.notes,
        "findings": [
            {"type": f.type, "type_id": f.ui_type_id, "timecode_sec": f.timecode_sec, "t_end": f.ui_t_end,
             "confidence": f.ui_confidence, "rule": f.ui_rule, "signals": f.ui_signals, "boxes": f.ui_boxes,
             "description": f.description, "frame_times": [t for t, _ in f.frames_b64]}
            for f in partial.findings
        ],
    }


def process(job: dict[str, Any]) -> None:
    job_id, path = job["id"], job["path"]
    started = time.monotonic()
    deadline = started + config.DEADLINE_SEC
    partial = pipeline.Partial()
    store.set_progress(job_id, partial.progress(started))

    try:
        info = probe(path)
    except NotAVideo as e:
        log.warning("%s: файл не читается: %s", job_id, e)
        store.fail_job(job_id, f"Файл не является видео или повреждён: {e}")
        _cleanup(path)
        return

    def on_progress() -> None:
        store.set_progress(job_id, partial.progress(started))

    error: list[BaseException] = []

    def run() -> None:
        try:
            pipeline.analyze(path, info, partial, deadline, on_progress, queue_depth=max(0, store.queue_size() - 1))
        except BaseException as e:  # noqa: BLE001 — любая ошибка конвейера не должна ронять обработчик
            error.append(e)

    t = threading.Thread(target=run, name=f"analyze-{job_id}", daemon=True)
    t.start()
    t.join(timeout=max(0.0, deadline - time.monotonic()) + 5)

    if t.is_alive():
        partial.timed_out = True
        partial.notes.append(f"Анализ не уложился в {config.DEADLINE_SEC} с, отдан частичный результат.")
        log.warning("%s: дедлайн, отдаём частичный результат", job_id)
    if error:
        partial.notes.append("Ошибка конвейера, отдан частичный результат: " + repr(error[0])[:200])
        log.error("%s: ошибка конвейера\n%s", job_id, "".join(traceback.format_exception(error[0])))

    elapsed = time.monotonic() - started
    with partial.lock:
        result = _response(job_id, partial, info.duration)
        details = _details(partial, info, elapsed)
    store.finish_job(job_id, result, details)
    _cleanup(path)
    log.info("%s: %s, %d событий, %.1f с", job_id, result["verdict"], len(result["violations"]), elapsed)


def _cleanup(path: str | None) -> None:
    """Видео удаляем сразу после обработки: таково требование банка о хранении данных."""
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            log.warning("не удалось удалить %s", path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store.init()
    worker = f"{socket.gethostname()}:{os.getpid()}"
    n = store.requeue_stale(config.DEADLINE_SEC + 60)
    if n:
        log.info("вернул в очередь %d зависших задач", n)
    log.info("обработчик %s готов, предел %d с", worker, config.DEADLINE_SEC)
    while True:
        job = store.claim_job(worker)
        if job is None:
            time.sleep(config.WORKER_POLL_SEC)
            continue
        try:
            process(job)
        except Exception:  # noqa: BLE001
            log.error("%s: сбой обработчика\n%s", job["id"], traceback.format_exc())
            store.fail_job(job["id"], "внутренняя ошибка обработчика")
            _cleanup(job.get("path"))


if __name__ == "__main__":
    main()
