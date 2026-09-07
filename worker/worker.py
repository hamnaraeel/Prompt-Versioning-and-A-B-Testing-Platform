"""Async metric-computation + guardrail/winner worker.

Runs as its own container/process, polling the database on an interval. This
keeps metric scoring (which can be slow, e.g. an LLM-as-judge call) and
statistical significance checks off the request-serving critical path.
"""
import logging
import time

from app import models
from app.config import settings
from app.database import SessionLocal
from app.metrics import builtin  # noqa: F401 populates the metric registry
from app.services import guardrails, metric_compute

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(levelname)s %(message)s")
log = logging.getLogger("worker")


def tick():
    db = SessionLocal()
    try:
        processed = metric_compute.compute_pending_metrics(db)
        if processed:
            log.info("scored metrics for %d request(s)", processed)

        active = (
            db.query(models.Experiment)
            .filter(models.Experiment.status.in_([
                models.ExperimentStatus.running,
                models.ExperimentStatus.winner_declared,
            ]))
            .all()
        )
        for experiment in active:
            if experiment.status == models.ExperimentStatus.running:
                stopped = guardrails.check_guardrails(db, experiment)
                if stopped:
                    log.warning("experiment %s auto-stopped: %s", experiment.id, experiment.stop_reason)
                    continue
            guardrails.check_winner_and_promote(db, experiment)

        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("worker tick failed")
    finally:
        db.close()


def main():
    log.info("worker starting, poll interval=%ss", settings.worker_poll_seconds)
    while True:
        tick()
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
