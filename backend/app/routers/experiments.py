from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.services import audit, results_engine

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", response_model=schemas.ExperimentOut)
def create_experiment(payload: schemas.ExperimentCreate, db: Session = Depends(get_db)):
    prompt = db.get(models.Prompt, payload.prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    if len(payload.variants) < 2:
        raise HTTPException(400, "An experiment needs at least two variants")
    total_pct = sum(v.traffic_pct for v in payload.variants)
    if not (99.0 <= total_pct <= 101.0):
        raise HTTPException(400, f"Traffic percentages must sum to ~100 (got {total_pct})")
    if sum(1 for v in payload.variants if v.is_control) != 1:
        raise HTTPException(400, "Exactly one variant must be marked is_control")

    experiment = models.Experiment(
        name=payload.name,
        prompt_id=payload.prompt_id,
        primary_metric=payload.primary_metric,
        target_sample_size=payload.target_sample_size,
        confidence_level=payload.confidence_level,
        auto_promote=payload.auto_promote,
        status=models.ExperimentStatus.draft,
    )
    db.add(experiment)
    db.flush()

    for v in payload.variants:
        version = db.get(models.PromptVersion, v.version_id)
        if not version or version.prompt_id != payload.prompt_id:
            raise HTTPException(400, f"Version {v.version_id} does not belong to prompt {payload.prompt_id}")
        db.add(models.ExperimentVariant(
            experiment_id=experiment.id, version_id=v.version_id, name=v.name,
            traffic_pct=v.traffic_pct, is_control=v.is_control,
        ))

    audit.log(db, "create_experiment", "experiment", experiment.id, payload.actor, {"name": payload.name})
    db.commit()
    return _load(db, experiment.id)


def _load(db: Session, experiment_id: str) -> models.Experiment:
    exp = (
        db.query(models.Experiment)
        .options(joinedload(models.Experiment.variants))
        .filter(models.Experiment.id == experiment_id)
        .first()
    )
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return exp


@router.get("", response_model=list[schemas.ExperimentOut])
def list_experiments(db: Session = Depends(get_db)):
    return (
        db.query(models.Experiment)
        .options(joinedload(models.Experiment.variants))
        .order_by(models.Experiment.created_at.desc())
        .all()
    )


@router.get("/{experiment_id}", response_model=schemas.ExperimentOut)
def get_experiment(experiment_id: str, db: Session = Depends(get_db)):
    return _load(db, experiment_id)


@router.post("/{experiment_id}/start", response_model=schemas.ExperimentOut)
def start_experiment(experiment_id: str, actor: str = "system", db: Session = Depends(get_db)):
    exp = _load(db, experiment_id)
    running = (
        db.query(models.Experiment)
        .filter(
            models.Experiment.prompt_id == exp.prompt_id,
            models.Experiment.status == models.ExperimentStatus.running,
            models.Experiment.id != exp.id,
        )
        .first()
    )
    if running:
        raise HTTPException(400, f"Prompt already has a running experiment ({running.id})")
    exp.status = models.ExperimentStatus.running
    exp.started_at = datetime.utcnow()
    audit.log(db, "start_experiment", "experiment", exp.id, actor, {})
    db.commit()
    return _load(db, experiment_id)


@router.post("/{experiment_id}/cancel", response_model=schemas.ExperimentOut)
def cancel_experiment(experiment_id: str, actor: str = "system", db: Session = Depends(get_db)):
    exp = _load(db, experiment_id)
    exp.status = models.ExperimentStatus.cancelled
    exp.completed_at = datetime.utcnow()
    audit.log(db, "cancel_experiment", "experiment", exp.id, actor, {})
    db.commit()
    return _load(db, experiment_id)


@router.post("/{experiment_id}/cancel-promotion", response_model=schemas.ExperimentOut)
def cancel_promotion(experiment_id: str, actor: str = "system", db: Session = Depends(get_db)):
    exp = _load(db, experiment_id)
    if exp.status != models.ExperimentStatus.winner_declared:
        raise HTTPException(400, "Experiment has no pending auto-promotion")
    exp.promotion_cancelled = True
    audit.log(db, "cancel_promotion", "experiment", exp.id, actor, {})
    db.commit()
    return _load(db, experiment_id)


@router.post("/{experiment_id}/promote", response_model=schemas.PromptOut)
def promote_now(experiment_id: str, actor: str = "system", db: Session = Depends(get_db)):
    exp = _load(db, experiment_id)
    if exp.status != models.ExperimentStatus.winner_declared or not exp.winner_variant_id:
        raise HTTPException(400, "No declared winner to promote")
    variant = next(v for v in exp.variants if v.id == exp.winner_variant_id)
    prompt = db.get(models.Prompt, exp.prompt_id)
    prompt.active_version_id = variant.version_id
    db.add(models.PromptActivation(prompt_id=prompt.id, version_id=variant.version_id, activated_by=actor, reason=f"Manual promotion of experiment '{exp.name}' winner"))
    exp.status = models.ExperimentStatus.completed
    exp.completed_at = datetime.utcnow()
    audit.log(db, "manual_promote", "experiment", exp.id, actor, {"version_id": variant.version_id})
    db.commit()
    db.refresh(prompt)
    return prompt


@router.get("/{experiment_id}/results")
def get_results(experiment_id: str, db: Session = Depends(get_db)):
    exp = _load(db, experiment_id)
    return results_engine.build_results(db, exp)
