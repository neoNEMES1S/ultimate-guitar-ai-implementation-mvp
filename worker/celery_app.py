from celery import Celery

from app.config import settings

celery_app = Celery(
    "tab_verification",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["worker.tasks"],
)
celery_app.conf.task_always_eager = settings.celery_task_always_eager
celery_app.conf.task_serializer = "json"
celery_app.conf.accept_content = ["json"]
