"""HTTP-сервис: приём видео, статус задачи, служебные страницы.

Публичный API — ровно §10 кейса:
  POST /api/v1/analyze        поле file, заголовок X-API-Key  → {"job_id","status":"processing"}
  GET  /api/v1/jobs/{job_id}  → processing | done (verdict, violations) | failed (error)
Запуск: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import json
import logging
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, store
from .pipeline.video import NotAVideo, probe
from .schemas import AnalyzeAccepted, JobDone, JobFailed, JobProcessing

log = logging.getLogger("api")

if not config.API_KEY:
    raise SystemExit("Задайте API_KEY в окружении (см. .env.example)")

app = FastAPI(title="КассаКонтроль", version=config.PIPELINE_VERSION, docs_url="/api/docs", redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    logging.basicConfig(level=logging.INFO)
    store.init()


# Интерфейс: статические страницы, данные берут из API с тем же ключом.
app.mount("/ui", StaticFiles(directory=str(Path(__file__).parent / "static"), html=True), name="ui")


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse("/ui/index.html")


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    """Ключ сравниваем за постоянное время, чтобы его нельзя было подобрать по задержке."""
    if not x_api_key or not secrets.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(status_code=401, detail="Неверный или отсутствующий X-API-Key")


@app.post("/api/v1/analyze", response_model=AnalyzeAccepted, dependencies=[Depends(require_key)])
async def analyze(file: UploadFile) -> AnalyzeAccepted:
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    safe_name = Path(file.filename or "video.mov").name[:120]
    tmp = config.UPLOAD_DIR / f"incoming-{secrets.token_hex(6)}.bin"
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(4 * 1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"Файл больше {config.MAX_UPLOAD_MB} МБ")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Пустой файл")
        try:
            probe(tmp)
        except NotAVideo as e:
            raise HTTPException(status_code=415, detail=f"Это не видеофайл: {e}") from e
    except HTTPException:
        tmp.unlink(missing_ok=True)
        raise

    job_id = store.create_job(safe_name, str(tmp), size)
    final = config.UPLOAD_DIR / f"{job_id}{Path(safe_name).suffix.lower() or '.mov'}"
    tmp.rename(final)
    store_path(job_id, final)
    log.info("принято %s (%s, %.1f МБ) → %s", safe_name, job_id, size / 2**20, final.name)
    return AnalyzeAccepted(job_id=job_id)


def store_path(job_id: str, final: Path) -> None:
    with store._conn() as c:  # noqa: SLF001 — одно место, где меняем путь после переименования
        c.execute("UPDATE jobs SET path=? WHERE id=?", (str(final), job_id))


@app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(require_key)])
def job_status(job_id: str) -> JSONResponse:
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if job["status"] in ("queued", "processing"):
        body = JobProcessing(job_id=job_id).model_dump()
    elif job["status"] == "failed":
        body = JobFailed(job_id=job_id, error=job["error"] or "неизвестная ошибка").model_dump()
    else:
        body = JobDone.model_validate_json(job["result_json"]).model_dump()
    return JSONResponse(body)


# ---- Служебное (не входит в §10, но нужно интерфейсу и проверке) ----

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": config.PIPELINE_VERSION, "queue": store.queue_size(), "time": time.time()}


@app.get("/api/v1/jobs/{job_id}/progress", dependencies=[Depends(require_key)])
def job_progress(job_id: str) -> dict:
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return {
        "job_id": job_id,
        "status": "processing" if job["status"] in ("queued", "processing") else job["status"],
        "filename": job["filename"],
        "size_bytes": job["size_bytes"],
        "created_at": job["created_at"],
        "progress": json.loads(job["progress_json"]) if job["progress_json"] else None,
        "details": json.loads(job["details_json"]) if job["details_json"] else None,
    }


@app.get("/api/v1/jobs", dependencies=[Depends(require_key)])
def jobs_list() -> dict:
    return {"jobs": store.list_recent()}


@app.middleware("http")
async def access_log(request: Request, call_next):
    t0 = time.monotonic()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        log.info("%s %s → %d за %.0f мс", request.method, request.url.path, response.status_code,
                 (time.monotonic() - t0) * 1000)
    return response
