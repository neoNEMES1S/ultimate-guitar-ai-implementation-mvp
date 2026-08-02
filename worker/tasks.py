import json

from app import repository

from .celery_app import celery_app
from .pipeline import analyze_source


@celery_app.task(name="worker.tasks.analyze_job")
def analyze_job(job_id: str) -> None:
    job = repository.get_job(job_id)
    if not job:
        return
    repository.set_processing(job_id)
    try:
        tuning = json.loads(job.get("tuning_json") or "[]")
        result = analyze_source(
            job["audio_path"],
            job["source_text"],
            job["source_kind"],
            job.get("bpm"),
            job.get("capo", 0),
            tuning,
        )
        repository.set_complete(job_id, result)
    except Exception as exc:
        repository.set_failed(job_id, str(exc))
        raise
