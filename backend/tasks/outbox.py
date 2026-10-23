import os
from celery import Celery
from sqlalchemy.orm import Session
from db.database import _get_session_local
from api.models.models import OutboxEntry

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("customs", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]


@celery_app.task(name="tasks.dispatch_outbox_events")
def dispatch_outbox_events():
    """
    Poll the outbox table for PENDING entries and publish them to Redis.
    Marks each entry DISPATCHED on success, FAILED on error.
    """
    db: Session = _get_session_local()()
    try:
        pending = (
            db.query(OutboxEntry)
            .filter(OutboxEntry.status == "PENDING")
            .limit(50)
            .all()
        )
        for entry in pending:
            try:
                # Publish payload to the 'agent_actions' Redis stream
                celery_app.send_task(
                    "tasks.process_action",
                    args=[entry.payload],
                    queue="agent_actions",
                )
                entry.status = "DISPATCHED"
            except Exception:
                entry.status = "FAILED"
        db.commit()
    finally:
        db.close()


# Beat schedule: run every 5 seconds during the demo
celery_app.conf.beat_schedule = {
    "dispatch-outbox": {
        "task": "tasks.dispatch_outbox_events",
        "schedule": 5.0,
    },
}
