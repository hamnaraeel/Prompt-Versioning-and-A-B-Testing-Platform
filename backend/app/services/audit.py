from sqlalchemy.orm import Session

from app import models


def log(db: Session, action: str, entity_type: str, entity_id: str | None, actor: str, details: dict | None = None):
    entry = models.AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        details=details or {},
    )
    db.add(entry)
    db.flush()
    return entry


def notify(db: Session, experiment_id: str | None, message: str, level: str = "info"):
    note = models.Notification(experiment_id=experiment_id, message=message, level=level)
    db.add(note)
    db.flush()
    return note
