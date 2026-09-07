"""Guardrails + winner declaration / auto-promotion lifecycle.

Called from the worker loop for every running (or winner_declared) experiment.
Keeping this logic out of the request-serving path means a slow guardrail
check never adds latency to a completion call.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import audit, results_engine


def check_guardrails(db: Session, experiment: models.Experiment) -> bool:
    """Returns True if the experiment was auto-stopped."""
    results = results_engine.build_results(db, experiment)

    for variant in results["variants"]:
        if variant["n_requests"] >= 20 and variant["error_rate"] > settings.guardrail_error_rate_threshold:
            _stop_experiment(
                db, experiment,
                reason=(
                    f"Auto-stopped: variant '{variant['name']}' error rate "
                    f"{variant['error_rate']:.1%} exceeded threshold "
                    f"{settings.guardrail_error_rate_threshold:.0%}."
                ),
            )
            return True

    for cmp in results["comparisons"]:
        if cmp["significant"] and not cmp["favors_variant"] and cmp["n_variant"] >= 30:
            _stop_experiment(
                db, experiment,
                reason=(
                    f"Auto-stopped: variant '{cmp['variant_name']}' is significantly worse than "
                    f"control on '{experiment.primary_metric}' (p={cmp['p_value_ttest']:.4f})."
                ),
            )
            return True

    return False


def _stop_experiment(db: Session, experiment: models.Experiment, reason: str):
    experiment.status = models.ExperimentStatus.auto_stopped
    experiment.stop_reason = reason
    experiment.completed_at = datetime.utcnow()
    audit.log(db, "auto_stop", "experiment", experiment.id, "guardrail", {"reason": reason})
    audit.notify(db, experiment.id, reason, level="warning")
    db.flush()


def check_winner_and_promote(db: Session, experiment: models.Experiment):
    results = results_engine.build_results(db, experiment)

    if experiment.status == models.ExperimentStatus.running:
        if results["overall_status"] == "winner" and results["total_samples"] >= experiment.target_sample_size:
            experiment.status = models.ExperimentStatus.winner_declared
            experiment.winner_variant_id = results["winner_variant_id"]
            experiment.winner_declared_at = datetime.utcnow()
            experiment.promotion_hold_until = datetime.utcnow() + timedelta(hours=settings.auto_promote_hold_hours)
            winner_name = next(v["name"] for v in results["variants"] if v["variant_id"] == results["winner_variant_id"])
            msg = (
                f"Experiment '{experiment.name}' reached significance at "
                f"{experiment.confidence_level:.0%} confidence. Winner: '{winner_name}'. "
                f"Auto-promotion in {settings.auto_promote_hold_hours:.0f}h unless cancelled."
            )
            audit.log(db, "winner_declared", "experiment", experiment.id, "stats_engine", {"winner_variant_id": results["winner_variant_id"]})
            audit.notify(db, experiment.id, msg, level="success")
            db.flush()
        return

    if experiment.status == models.ExperimentStatus.winner_declared:
        if experiment.promotion_cancelled:
            return
        if not experiment.auto_promote:
            return
        if experiment.promotion_hold_until and datetime.utcnow() >= experiment.promotion_hold_until:
            _promote(db, experiment)


def _promote(db: Session, experiment: models.Experiment):
    variant = next(v for v in experiment.variants if v.id == experiment.winner_variant_id)
    prompt = db.get(models.Prompt, experiment.prompt_id)
    prompt.active_version_id = variant.version_id

    activation = models.PromptActivation(
        prompt_id=prompt.id,
        version_id=variant.version_id,
        activated_by="auto_promotion",
        reason=f"Auto-promoted winner of experiment '{experiment.name}' after hold period.",
    )
    db.add(activation)

    experiment.status = models.ExperimentStatus.completed
    experiment.completed_at = datetime.utcnow()

    audit.log(db, "auto_promote", "experiment", experiment.id, "auto_promotion", {"version_id": variant.version_id})
    audit.notify(db, experiment.id, f"Winner promoted to production for prompt '{prompt.name}'.", level="success")
    db.flush()
