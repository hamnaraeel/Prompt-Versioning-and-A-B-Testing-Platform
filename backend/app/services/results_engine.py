from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.metrics.registry import higher_is_better
from app.services import stats_engine


def metric_values_by_variant(db: Session, experiment_id: str, metric_name: str) -> dict[str, list[float]]:
    rows = (
        db.query(models.MetricValue.variant_id, models.MetricValue.metric_value)
        .filter(
            models.MetricValue.experiment_id == experiment_id,
            models.MetricValue.metric_name == metric_name,
        )
        .all()
    )
    out: dict[str, list[float]] = {}
    for variant_id, value in rows:
        out.setdefault(variant_id, []).append(value)
    return out


def sample_counts(db: Session, experiment_id: str) -> dict[str, int]:
    rows = (
        db.query(models.RequestLog.variant_id, func.count(models.RequestLog.id))
        .filter(models.RequestLog.experiment_id == experiment_id, models.RequestLog.variant_id.isnot(None))
        .group_by(models.RequestLog.variant_id)
        .all()
    )
    return {variant_id: count for variant_id, count in rows}


def error_rates(db: Session, experiment_id: str) -> dict[str, float]:
    rows = (
        db.query(models.RequestLog.variant_id, models.RequestLog.error)
        .filter(models.RequestLog.experiment_id == experiment_id, models.RequestLog.variant_id.isnot(None))
        .all()
    )
    totals: dict[str, int] = {}
    errors: dict[str, int] = {}
    for variant_id, error in rows:
        totals[variant_id] = totals.get(variant_id, 0) + 1
        if error:
            errors[variant_id] = errors.get(variant_id, 0) + 1
    return {vid: errors.get(vid, 0) / total for vid, total in totals.items()}


def build_results(db: Session, experiment: models.Experiment) -> dict:
    metric_name = experiment.primary_metric
    by_variant = metric_values_by_variant(db, experiment.id, metric_name)
    counts = sample_counts(db, experiment.id)
    err_rates = error_rates(db, experiment.id)
    hib = higher_is_better(metric_name)

    control = next((v for v in experiment.variants if v.is_control), experiment.variants[0])
    control_values = by_variant.get(control.id, [])

    variant_summaries = []
    comparisons = []
    for variant in experiment.variants:
        values = by_variant.get(variant.id, [])
        n, mean, std = stats_engine.describe(values)
        variant_summaries.append(
            {
                "variant_id": variant.id,
                "name": variant.name,
                "is_control": variant.is_control,
                "n_metric_samples": n,
                "n_requests": counts.get(variant.id, 0),
                "mean": mean,
                "std": std,
                "error_rate": err_rates.get(variant.id, 0.0),
            }
        )
        if not variant.is_control:
            cmp = stats_engine.compare_variant_to_control(
                control_values=control_values,
                variant_id=variant.id,
                variant_name=variant.name,
                control_id=control.id,
                variant_values=values,
                alpha=1 - experiment.confidence_level,
                higher_is_better=hib,
            )
            comparisons.append(cmp)

    total_n = sum(counts.values())
    progress = min(1.0, total_n / experiment.target_sample_size) if experiment.target_sample_size else 1.0

    # Among variants that beat control significantly, the winner is the one
    # furthest ahead of control (not just the first one found in variant
    # order) — otherwise a middling-but-significant variant could shadow a
    # much stronger one tested alongside it.
    significant_winners = [cmp for cmp in comparisons if cmp.significant and cmp.favors_variant]
    winner = max(significant_winners, key=lambda cmp: abs(cmp.diff), default=None)

    if winner:
        overall_status = "winner"
    elif any(c.significant and not c.favors_variant for c in comparisons):
        overall_status = "no_winner"
    else:
        overall_status = "inconclusive"

    return {
        "experiment_id": experiment.id,
        "status": experiment.status,
        "primary_metric": metric_name,
        "higher_is_better": hib,
        "confidence_level": experiment.confidence_level,
        "target_sample_size": experiment.target_sample_size,
        "total_samples": total_n,
        "progress": progress,
        "overall_status": overall_status,
        "control_variant_id": control.id,
        "variants": variant_summaries,
        "comparisons": [cmp.__dict__ for cmp in comparisons],
        "winner_variant_id": winner.variant_id if winner else None,
    }
