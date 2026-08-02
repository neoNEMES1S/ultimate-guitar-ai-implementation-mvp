import pytest

pytest.importorskip("celery")

from worker.celery_app import celery_app


def test_analysis_task_is_registered() -> None:
    celery_app.loader.import_default_modules()
    assert "worker.tasks.analyze_job" in celery_app.tasks
