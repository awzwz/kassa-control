# КассаКонтроль

Сервис проверки кассовой дисциплины по видеозаписи с камеры над рабочим местом кассира.
DATATHON '26, кейс ForteBank.

## API (раздел 10 кейса)

```
POST /api/v1/analyze          multipart, поле file, заголовок X-API-Key → {"job_id":"…","status":"processing"}
GET  /api/v1/jobs/{job_id}    заголовок X-API-Key → processing | done | failed
```

Ответ `done`:

```json
{"job_id":"3f2a9c1e","status":"done","verdict":"violation",
 "violations":[{"type":"…","timecode_sec":57.0,"description":"…",
   "evidence_frames":[{"timestamp_sec":57.0,"image_base64":"/9j/4AAQ…"}]}]}
```

## Как устроено

```
Caddy (HTTPS) → api (FastAPI) → очередь задач в SQLite → worker ×2 (ffmpeg → детектор → правила)
                                   общий том /data: результаты; видео удаляется после обработки
```

- Обработчик отдаёт результат не позже 240 с: при нехватке времени — лучший частичный.
- Статус `failed` только если файл не читается как видео.
- Всё работает локально, без внешних AI-сервисов. Лица не распознаются.

## Запуск для разработки

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
export API_KEY=test DATA_DIR=./data
uvicorn app.main:app --port 8000          # терминал 1
python -m app.worker                      # терминал 2
python tools/jury_sim.py --key test --concurrency 3 video1.mov video2.mov
```

## Запуск на сервере

```bash
cp .env.example .env   # задать API_KEY и DOMAIN
docker compose up -d --build
```

## Состояние

Шаг 1: каркас сервиса с заглушкой (всегда `no_violation`). Дальше: детектор, правила, интерфейс, PDF.
