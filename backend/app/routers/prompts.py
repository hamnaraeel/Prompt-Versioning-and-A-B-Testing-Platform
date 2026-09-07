from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import audit, templates

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("", response_model=schemas.PromptOut)
def create_prompt(payload: schemas.PromptCreate, db: Session = Depends(get_db)):
    if db.query(models.Prompt).filter(models.Prompt.name == payload.name).first():
        raise HTTPException(400, f"Prompt named '{payload.name}' already exists")
    prompt = models.Prompt(name=payload.name, description=payload.description)
    db.add(prompt)
    db.flush()
    audit.log(db, "create_prompt", "prompt", prompt.id, payload.actor, {"name": payload.name})
    db.commit()
    db.refresh(prompt)
    return prompt


@router.get("", response_model=list[schemas.PromptOut])
def list_prompts(db: Session = Depends(get_db)):
    return db.query(models.Prompt).order_by(models.Prompt.created_at.desc()).all()


@router.get("/{prompt_id}", response_model=schemas.PromptOut)
def get_prompt(prompt_id: str, db: Session = Depends(get_db)):
    prompt = db.get(models.Prompt, prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    return prompt


@router.post("/{prompt_id}/versions", response_model=schemas.PromptVersionOut)
def create_version(prompt_id: str, payload: schemas.PromptVersionCreate, db: Session = Depends(get_db)):
    prompt = db.get(models.Prompt, prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    declared_vars = set(payload.template_variables) or set(templates.extract_variables(payload.system_prompt))

    last = (
        db.query(models.PromptVersion)
        .filter(models.PromptVersion.prompt_id == prompt_id)
        .order_by(models.PromptVersion.version_number.desc())
        .first()
    )
    next_version = (last.version_number + 1) if last else 1

    version = models.PromptVersion(
        prompt_id=prompt_id,
        version_number=next_version,
        system_prompt=payload.system_prompt,
        few_shot_examples=payload.few_shot_examples,
        model_provider=payload.model_provider,
        model_name=payload.model_name,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        template_variables=sorted(declared_vars),
        commit_message=payload.commit_message,
        created_by=payload.actor,
    )
    db.add(version)
    db.flush()

    if not prompt.active_version_id:
        prompt.active_version_id = version.id
        db.add(models.PromptActivation(prompt_id=prompt.id, version_id=version.id, activated_by=payload.actor, reason="First version auto-activated"))

    audit.log(db, "create_version", "prompt_version", version.id, payload.actor, {"prompt_id": prompt_id, "version_number": next_version})
    db.commit()
    db.refresh(version)
    return version


@router.get("/{prompt_id}/versions", response_model=list[schemas.PromptVersionOut])
def list_versions(prompt_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.PromptVersion)
        .filter(models.PromptVersion.prompt_id == prompt_id)
        .order_by(models.PromptVersion.version_number.asc())
        .all()
    )


@router.get("/{prompt_id}/versions/{version_number}", response_model=schemas.PromptVersionOut)
def get_version(prompt_id: str, version_number: int, db: Session = Depends(get_db)):
    version = (
        db.query(models.PromptVersion)
        .filter(models.PromptVersion.prompt_id == prompt_id, models.PromptVersion.version_number == version_number)
        .first()
    )
    if not version:
        raise HTTPException(404, "Version not found")
    return version


@router.get("/{prompt_id}/diff/{v1}/{v2}")
def diff_versions(prompt_id: str, v1: int, v2: int, db: Session = Depends(get_db)):
    def _get(v):
        row = (
            db.query(models.PromptVersion)
            .filter(models.PromptVersion.prompt_id == prompt_id, models.PromptVersion.version_number == v)
            .first()
        )
        if not row:
            raise HTTPException(404, f"Version {v} not found")
        return row

    a, b = _get(v1), _get(v2)
    fields = ["system_prompt", "few_shot_examples", "model_provider", "model_name", "temperature", "max_tokens", "template_variables"]
    diff = {}
    for f in fields:
        av, bv = getattr(a, f), getattr(b, f)
        if av != bv:
            diff[f] = {"from": av, "to": bv}
    return {"prompt_id": prompt_id, "from_version": v1, "to_version": v2, "changed_fields": list(diff.keys()), "diff": diff}


@router.post("/{prompt_id}/versions/{version_number}/activate", response_model=schemas.PromptOut)
def activate_version(prompt_id: str, version_number: int, payload: schemas.ActivateRequest, db: Session = Depends(get_db)):
    prompt = db.get(models.Prompt, prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    version = (
        db.query(models.PromptVersion)
        .filter(models.PromptVersion.prompt_id == prompt_id, models.PromptVersion.version_number == version_number)
        .first()
    )
    if not version:
        raise HTTPException(404, "Version not found")

    previous_version_id = prompt.active_version_id
    previous_version = db.get(models.PromptVersion, previous_version_id) if previous_version_id else None
    prompt.active_version_id = version.id
    db.add(models.PromptActivation(prompt_id=prompt.id, version_id=version.id, activated_by=payload.actor, reason=payload.reason))

    # A "rollback" is specifically activating an older version than the one
    # currently live; activating a newer (or first-ever) version is a normal
    # forward "activate", even though both flip active_version_id the same way.
    is_rollback = previous_version is not None and version.version_number < previous_version.version_number
    action = "rollback" if is_rollback else "activate"
    audit.log(db, action, "prompt", prompt.id, payload.actor, {
        "from_version_id": previous_version_id, "to_version_id": version.id, "reason": payload.reason,
    })
    db.commit()
    db.refresh(prompt)
    return prompt


@router.get("/{prompt_id}/activations")
def list_activations(prompt_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(models.PromptActivation)
        .filter(models.PromptActivation.prompt_id == prompt_id)
        .order_by(models.PromptActivation.activated_at.desc())
        .all()
    )
    return [
        {
            "id": r.id, "version_id": r.version_id, "activated_at": r.activated_at,
            "activated_by": r.activated_by, "reason": r.reason,
        }
        for r in rows
    ]
