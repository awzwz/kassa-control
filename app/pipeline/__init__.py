"""Конвейер анализа. Снаружи виден один вызов analyze(), внутри — этапы.

Шаг 1 (сейчас): заглушка, которая проверяет видео и всегда отвечает «нарушений нет».
Дальше сюда встанут детектор, треки, зоны и правила. Контракт не меняется:
analyze() пишет в Partial по мере работы, чтобы сторож дедлайна мог забрать
лучший частичный результат в любой момент.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .video import VideoInfo, probe  # noqa: F401  (probe нужен снаружи)

STAGES = [
    "Видео загружено",
    "Файл проверен",
    "Люди и предметы в кадре",
    "Сопоставление с правилами",
    "Кадры-доказательства",
]


@dataclass
class Finding:
    """Одно найденное событие. Поля с префиксом ui_ в ответ API не попадают."""
    type: str
    timecode_sec: float
    description: str
    frames_b64: list[tuple[float, str]]          # (секунда, base64 JPEG), 1–3 штуки
    ui_confidence: str = "средняя"               # низкая | средняя | высокая
    ui_rule: dict[str, Any] = field(default_factory=dict)
    ui_signals: list[dict[str, Any]] = field(default_factory=list)
    ui_boxes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Partial:
    """Текущее состояние анализа. Заполняется по ходу работы, читается сторожем."""
    stage: int = 1
    frames_done: int = 0
    frames_total: int = 0
    findings: list[Finding] = field(default_factory=list)
    checked: list[dict[str, Any]] = field(default_factory=list)   # что проверено по категориям
    notes: list[str] = field(default_factory=list)
    timed_out: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def progress(self, started: float) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "stages": len(STAGES),
            "label": STAGES[min(self.stage, len(STAGES)) - 1],
            "frames_done": self.frames_done,
            "frames_total": self.frames_total,
            "elapsed_sec": round(time.monotonic() - started, 1),
        }


def analyze(path: str, info: VideoInfo, partial: Partial, deadline: float,
            on_progress: Callable[[], None] | None = None) -> None:
    """Заглушка шага 1. Этапы проходятся честно, чтобы сторож и интерфейс работали уже сейчас."""
    partial.stage = 2
    partial.frames_total = max(1, int(info.duration * 3))
    if on_progress:
        on_progress()

    partial.stage = 3
    # Имитируем просмотр кадров, но без детектора: по 3 «кадра» в секунду, не дольше 2 с на всё.
    step = min(0.02, 2.0 / partial.frames_total)
    for i in range(partial.frames_total):
        if time.monotonic() > deadline:
            partial.timed_out = True
            return
        partial.frames_done = i + 1
        if on_progress and i % 25 == 0:
            on_progress()
        time.sleep(step)

    partial.stage = 4
    partial.checked = [
        {"category": c, "result": "not_checked", "note": "детектор ещё не подключён"}
        for c in (
            "Наличные или ценности оставлены без присмотра",
            "Сейф или хранилище оставлены открытыми",
            "Экран компьютера не заблокирован при уходе",
            "Посторонний в зоне кассира",
            "Кассир покинул рабочее место во время обслуживания",
            "Личные вещи, еда или напитки на рабочем месте",
            "Выдача или приём наличных без видимого пересчёта",
        )
    ]
    partial.notes.append("Версия-заглушка: правила не применялись.")
    partial.stage = 5
    if on_progress:
        on_progress()
