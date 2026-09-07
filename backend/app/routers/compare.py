from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services import templates
from app.services.llm_provider import provider

router = APIRouter(prefix="/compare", tags=["compare"])


class CompareRequest(BaseModel):
    version_id_a: str
    version_id_b: str
    test_inputs: list[dict]


@router.post("")
def compare_versions(payload: CompareRequest, db: Session = Depends(get_db)):
    va = db.get(models.PromptVersion, payload.version_id_a)
    vb = db.get(models.PromptVersion, payload.version_id_b)
    if not va or not vb:
        raise HTTPException(404, "Version not found")

    results = []
    for case in payload.test_inputs:
        row = {"input": case}
        for label, version in (("a", va), ("b", vb)):
            try:
                rendered = templates.render_template(version.system_prompt, case)
            except templates.MissingTemplateVariables as exc:
                row[label] = {"error": str(exc)}
                continue
            user_input = case.get("email_text") or case.get("input") or ""
            result = provider.complete(
                provider=version.model_provider,
                model_name=version.model_name,
                system_prompt=rendered,
                few_shot_examples=version.few_shot_examples or [],
                user_input=str(user_input),
                temperature=version.temperature,
                max_tokens=version.max_tokens,
            )
            row[label] = {
                "response_text": result.text,
                "predicted_label": result.predicted_label,
                "latency_ms": result.latency_ms,
                "cost_usd": result.cost_usd,
                "correct": (result.predicted_label == case.get("expected_label")) if case.get("expected_label") else None,
            }
        results.append(row)

    return {
        "version_a": {"id": va.id, "version_number": va.version_number, "commit_message": va.commit_message},
        "version_b": {"id": vb.id, "version_number": vb.version_number, "commit_message": vb.commit_message},
        "cases": results,
    }
