from sqlalchemy.orm import Session

from app import models
from app.metrics.registry import all_metrics


def compute_pending_metrics(db: Session, batch_size: int = 200) -> int:
    """Runs every registered metric collector against RequestLogs that haven't
    been scored yet. Returns the number of request logs processed."""
    pending = (
        db.query(models.RequestLog)
        .filter(models.RequestLog.metrics_computed.is_(False))
        .limit(batch_size)
        .all()
    )
    for log_row in pending:
        for spec in all_metrics().values():
            value = spec.fn(log_row)
            if value is None:
                continue
            db.add(
                models.MetricValue(
                    request_log_id=log_row.id,
                    experiment_id=log_row.experiment_id,
                    variant_id=log_row.variant_id,
                    metric_name=spec.name,
                    metric_value=value,
                )
            )
        log_row.metrics_computed = True
    db.flush()
    return len(pending)
