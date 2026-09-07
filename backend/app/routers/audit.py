from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

router = APIRouter(tags=["audit"])


@router.get("/audit-log")
def list_audit_log(limit: int = 200, db: Session = Depends(get_db)):
    rows = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
            "actor": r.actor, "details": r.details, "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/notifications")
def list_notifications(unread_only: bool = False, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(models.Notification)
    if unread_only:
        q = q.filter(models.Notification.read.is_(False))
    rows = q.order_by(models.Notification.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "experiment_id": r.experiment_id, "level": r.level,
            "message": r.message, "created_at": r.created_at, "read": r.read,
        }
        for r in rows
    ]


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, db: Session = Depends(get_db)):
    note = db.get(models.Notification, notification_id)
    if note:
        note.read = True
        db.commit()
    return {"ok": True}
