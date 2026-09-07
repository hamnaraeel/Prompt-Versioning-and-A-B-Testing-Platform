import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class ExperimentStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    winner_declared = "winner_declared"
    completed = "completed"
    auto_stopped = "auto_stopped"
    cancelled = "cancelled"


class Prompt(Base):
    __tablename__ = "prompts"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    # Deliberately not a ForeignKey: prompt_versions.prompt_id already points back
    # at prompts.id, and a real FK constraint here would create a circular
    # dependency that breaks Base.metadata.create_all() on Postgres.
    active_version_id = Column(String, nullable=True)

    versions = relationship(
        "PromptVersion", back_populates="prompt", foreign_keys="PromptVersion.prompt_id"
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version_number", name="uq_prompt_version"),)

    id = Column(String, primary_key=True, default=gen_uuid)
    prompt_id = Column(String, ForeignKey("prompts.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    system_prompt = Column(Text, nullable=False)
    few_shot_examples = Column(JSON, default=list)
    model_provider = Column(String, default="mock")
    model_name = Column(String, default="mock-1")
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=512)
    template_variables = Column(JSON, default=list)
    commit_message = Column(Text, default="")
    created_by = Column(String, default="system")
    created_at = Column(DateTime, default=datetime.utcnow)

    prompt = relationship("Prompt", back_populates="versions", foreign_keys=[prompt_id])


class PromptActivation(Base):
    __tablename__ = "prompt_activations"

    id = Column(String, primary_key=True, default=gen_uuid)
    prompt_id = Column(String, ForeignKey("prompts.id"), nullable=False)
    version_id = Column(String, ForeignKey("prompt_versions.id"), nullable=False)
    activated_at = Column(DateTime, default=datetime.utcnow)
    activated_by = Column(String, default="system")
    reason = Column(Text, default="")


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    prompt_id = Column(String, ForeignKey("prompts.id"), nullable=False)
    status = Column(Enum(ExperimentStatus), default=ExperimentStatus.draft)
    primary_metric = Column(String, nullable=False, default="quality_score")
    target_sample_size = Column(Integer, default=200)
    confidence_level = Column(Float, default=0.95)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    # Not a ForeignKey for the same circular-dependency reason as
    # Prompt.active_version_id above (experiment_variants.experiment_id points
    # back at experiments.id).
    winner_variant_id = Column(String, nullable=True)
    winner_declared_at = Column(DateTime, nullable=True)
    promotion_hold_until = Column(DateTime, nullable=True)
    promotion_cancelled = Column(Boolean, default=False)
    auto_promote = Column(Boolean, default=True)
    stop_reason = Column(Text, nullable=True)

    variants = relationship(
        "ExperimentVariant", back_populates="experiment", foreign_keys="ExperimentVariant.experiment_id"
    )


class ExperimentVariant(Base):
    __tablename__ = "experiment_variants"

    id = Column(String, primary_key=True, default=gen_uuid)
    experiment_id = Column(String, ForeignKey("experiments.id"), nullable=False)
    version_id = Column(String, ForeignKey("prompt_versions.id"), nullable=False)
    name = Column(String, nullable=False)
    traffic_pct = Column(Float, nullable=False)
    is_control = Column(Boolean, default=False)

    experiment = relationship("Experiment", back_populates="variants", foreign_keys=[experiment_id])


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("experiment_id", "user_key", name="uq_experiment_user"),)

    id = Column(String, primary_key=True, default=gen_uuid)
    experiment_id = Column(String, ForeignKey("experiments.id"), nullable=False)
    user_key = Column(String, nullable=False)
    variant_id = Column(String, ForeignKey("experiment_variants.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)


class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    prompt_id = Column(String, ForeignKey("prompts.id"), nullable=False)
    version_id = Column(String, ForeignKey("prompt_versions.id"), nullable=False)
    experiment_id = Column(String, ForeignKey("experiments.id"), nullable=True)
    variant_id = Column(String, ForeignKey("experiment_variants.id"), nullable=True)
    user_key = Column(String, nullable=False)
    input_variables = Column(JSON, default=dict)
    rendered_prompt = Column(Text, default="")
    response_text = Column(Text, default="")
    expected_label = Column(String, nullable=True)
    predicted_label = Column(String, nullable=True)
    latency_ms = Column(Float, default=0.0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    error = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    metrics_computed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MetricValue(Base):
    __tablename__ = "metric_values"

    id = Column(String, primary_key=True, default=gen_uuid)
    request_log_id = Column(String, ForeignKey("request_logs.id"), nullable=False)
    experiment_id = Column(String, ForeignKey("experiments.id"), nullable=True)
    variant_id = Column(String, ForeignKey("experiment_variants.id"), nullable=True)
    metric_name = Column(String, nullable=False)
    metric_value = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=gen_uuid)
    experiment_id = Column(String, ForeignKey("experiments.id"), nullable=True)
    level = Column(String, default="info")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    read = Column(Boolean, default=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=True)
    actor = Column(String, default="system")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
