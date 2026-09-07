from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import templates
from app.services.llm_provider import provider
from app.services.traffic_splitter import choose_variant

router = APIRouter(prefix="/v1", tags=["completions"])


@router.post("/completions", response_model=schemas.CompletionResponse)
def create_completion(payload: schemas.CompletionRequest, db: Session = Depends(get_db)):
    prompt = db.get(models.Prompt, payload.prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    experiment = (
        db.query(models.Experiment)
        .filter(models.Experiment.prompt_id == prompt.id, models.Experiment.status == models.ExperimentStatus.running)
        .first()
    )

    variant = None
    if experiment:
        variants = (
            db.query(models.ExperimentVariant)
            .filter(models.ExperimentVariant.experiment_id == experiment.id)
            .all()
        )
        chosen = choose_variant(
            experiment.id, payload.user_key,
            [{"id": v.id, "traffic_pct": v.traffic_pct} for v in variants],
        )
        variant = next(v for v in variants if v.id == chosen["id"])
        version = db.get(models.PromptVersion, variant.version_id)

        existing = (
            db.query(models.Assignment)
            .filter(models.Assignment.experiment_id == experiment.id, models.Assignment.user_key == payload.user_key)
            .first()
        )
        if not existing:
            db.add(models.Assignment(experiment_id=experiment.id, user_key=payload.user_key, variant_id=variant.id))
    else:
        if not prompt.active_version_id:
            raise HTTPException(400, "Prompt has no active version and no running experiment")
        version = db.get(models.PromptVersion, prompt.active_version_id)

    try:
        rendered = templates.render_template(version.system_prompt, payload.variables)
    except templates.MissingTemplateVariables as exc:
        raise HTTPException(422, str(exc))

    user_input = payload.variables.get("email_text") or payload.variables.get("input") or ""

    result = provider.complete(
        provider=version.model_provider,
        model_name=version.model_name,
        system_prompt=rendered,
        few_shot_examples=version.few_shot_examples or [],
        user_input=str(user_input),
        temperature=version.temperature,
        max_tokens=version.max_tokens,
    )

    log_row = models.RequestLog(
        prompt_id=prompt.id,
        version_id=version.id,
        experiment_id=experiment.id if experiment else None,
        variant_id=variant.id if variant else None,
        user_key=payload.user_key,
        input_variables=payload.variables,
        rendered_prompt=rendered,
        response_text=result.text,
        expected_label=payload.expected_label,
        predicted_label=result.predicted_label,
        latency_ms=result.latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        error=result.error,
        error_message=result.error_message,
    )
    db.add(log_row)
    db.commit()
    db.refresh(log_row)

    return schemas.CompletionResponse(
        request_id=log_row.id,
        response_text=result.text,
        predicted_label=result.predicted_label,
        version_id=version.id,
        variant_id=variant.id if variant else None,
        experiment_id=experiment.id if experiment else None,
        latency_ms=result.latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
    )
