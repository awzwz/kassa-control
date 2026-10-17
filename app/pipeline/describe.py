"""Тексты для ответа: описание события по шаблону из каталога норм. Ссылки на нормы берутся
только из rules.json и никогда не придумываются."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "rules.json"


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def rule_for(type_id: str) -> dict[str, Any]:
    for t in catalog()["types"]:
        if t["id"] == type_id:
            return t
    return next(t for t in catalog()["types"] if t["id"] == "T99")


class _Safe(dict):
    def __missing__(self, key):
        return ""


def fill(template: str, fields: dict[str, Any]) -> str:
    return template.format_map(_Safe(fields)).replace("  ", " ").strip()


def source_text(rule: dict[str, Any]) -> tuple[str, str]:
    """(короткая ссылка для описания, полная строка «Основание»)."""
    doc = catalog()["documents"][rule["source"]["doc"]]
    short = f"{doc['short']}, {rule['source']['point']}"
    return short, f"Основание: {doc['short']} (утв. постановлением Правления НБРК), {rule['source']['point']} ({doc['url']})"


def describe(type_id: str, fields: dict[str, Any]) -> str:
    """Описание для поля description ответа API: что видно, почему это может быть нарушением, основание."""
    r = rule_for(type_id)
    seen = fill(r["observation"], fields)
    why = r["interpretation"]
    _, basis = source_text(r)
    return f"{seen} {why} {basis}"


def ui_rule(type_id: str) -> dict[str, Any]:
    """Карточка нормы для интерфейса и PDF."""
    r = rule_for(type_id)
    doc = catalog()["documents"][r["source"]["doc"]]
    return {
        "id": r["id"], "type": r["type"], "moment": r["moment"],
        "doc": doc["short"], "doc_full": doc["full"], "point": r["source"]["point"],
        "quote": r["source"]["quote"], "url": doc["url"],
        "interpretation": r["interpretation"], "cannot_see": r["cannot_see"], "check": r["check"],
        "extra_sources": r.get("extra_sources", []), "extra_text": r.get("extra_text", ""),
    }


def check_banned(text: str) -> list[str]:
    low = text.lower()
    return [w for w in catalog()["banned_words"] if w.lower() in low]
