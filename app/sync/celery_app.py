from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "accessgraph",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.sync.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
