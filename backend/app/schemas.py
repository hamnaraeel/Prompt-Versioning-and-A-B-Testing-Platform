from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Prompts ----------

class PromptCreate(BaseModel):
    name: str
    description: str = ""
    actor: str = "system"


class PromptOut(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    active_version_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PromptVersionCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    system_prompt: str
    few_shot_examples: list[dict] = Field(default_factory=list)
    model_provider: str = "mock"
    model_name: str = "mock-1"
    temperature: float = 0.7
    max_tokens: int = 512
    template_variables: list[str] = Field(default_factory=list)
    commit_message: str = ""
    actor: str = "system"


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)

    id: str
    prompt_id: str
    version_number: int
    system_prompt: str
    few_shot_examples: list
    model_provider: str
    model_name: str
    temperature: float
    max_tokens: int
    template_variables: list
    commit_message: str
    created_by: str
    created_at: datetime


class ActivateRequest(BaseModel):
    reason: str = ""
    actor: str = "system"


# ---------- Experiments ----------

class VariantCreate(BaseModel):
    version_id: str
    name: str
    traffic_pct: float
    is_control: bool = False


class ExperimentCreate(BaseModel):
    name: str
    prompt_id: str
    variants: list[VariantCreate]
    primary_metric: str = "quality_score"
    target_sample_size: int = 200
    confidence_level: float = 0.95
    auto_promote: bool = True
    actor: str = "system"


class ExperimentVariantOut(BaseModel):
    id: str
    version_id: str
    name: str
    traffic_pct: float
    is_control: bool

    model_config = ConfigDict(from_attributes=True)


class ExperimentOut(BaseModel):
    id: str
    name: str
    prompt_id: str
    status: str
    primary_metric: str
    target_sample_size: int
    confidence_level: float
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    winner_variant_id: Optional[str] = None
    winner_declared_at: Optional[datetime] = None
    promotion_hold_until: Optional[datetime] = None
    promotion_cancelled: bool
    auto_promote: bool
    stop_reason: Optional[str] = None
    variants: list[ExperimentVariantOut]

    model_config = ConfigDict(from_attributes=True)


class CompletionRequest(BaseModel):
    prompt_id: str
    variables: dict[str, Any] = Field(default_factory=dict)
    user_key: str
    expected_label: Optional[str] = None


class CompletionResponse(BaseModel):
    request_id: str
    response_text: str
    predicted_label: Optional[str] = None
    version_id: str
    variant_id: Optional[str] = None
    experiment_id: Optional[str] = None
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
