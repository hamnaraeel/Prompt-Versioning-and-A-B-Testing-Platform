from unittest.mock import patch

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.metrics import builtin  # noqa: F401
from app.services import guardrails, metric_compute
from app.services.llm_provider import CompletionResult

client = TestClient(app)


def _setup_experiment(target_n=100):
    prompt = client.post("/prompts", json={"name": "classifier", "actor": "tester"}).json()
    v1 = client.post(
        f"/prompts/{prompt['id']}/versions",
        json={"system_prompt": "classify {{email_text}}", "commit_message": "control"},
    ).json()
    v2 = client.post(
        f"/prompts/{prompt['id']}/versions",
        json={"system_prompt": "classify {{email_text}} carefully", "commit_message": "flaky"},
    ).json()

    exp = client.post(
        "/experiments",
        json={
            "name": "exp",
            "prompt_id": prompt["id"],
            "variants": [
                {"version_id": v1["id"], "name": "control", "traffic_pct": 50, "is_control": True},
                {"version_id": v2["id"], "name": "flaky", "traffic_pct": 50, "is_control": False},
            ],
            "primary_metric": "task_accuracy",
            "target_sample_size": target_n,
            "confidence_level": 0.95,
        },
    ).json()
    client.post(f"/experiments/{exp['id']}/start")
    return prompt, v1, v2, exp


def test_metric_collection_accuracy():
    prompt, v1, v2, exp = _setup_experiment()

    # deterministic mock always predicts "billing" correctly
    fake_result = CompletionResult(
        text="category: billing", predicted_label="billing", prompt_tokens=10,
        completion_tokens=5, cost_usd=0.001, latency_ms=42.0,
    )
    with patch("app.routers.completions.provider.complete", return_value=fake_result):
        for i in range(10):
            r = client.post(
                "/v1/completions",
                json={
                    "prompt_id": prompt["id"],
                    "variables": {"email_text": "I was charged twice"},
                    "user_key": f"user-{i}",
                    "expected_label": "billing",
                },
            )
            assert r.status_code == 200

    db = SessionLocal()
    processed = metric_compute.compute_pending_metrics(db)
    db.commit()
    assert processed == 10

    accuracy_values = (
        db.query(models.MetricValue)
        .filter(models.MetricValue.metric_name == "task_accuracy")
        .all()
    )
    assert len(accuracy_values) == 10
    assert all(v.metric_value == 1.0 for v in accuracy_values)

    latency_values = (
        db.query(models.MetricValue)
        .filter(models.MetricValue.metric_name == "latency_ms")
        .all()
    )
    assert all(v.metric_value == 42.0 for v in latency_values)
    db.close()


def test_auto_stop_on_error_rate_spike():
    prompt, v1, v2, exp = _setup_experiment()

    error_result = CompletionResult(
        text="", predicted_label=None, prompt_tokens=0, completion_tokens=0,
        cost_usd=0.0, latency_ms=10.0, error=True, error_message="simulated failure",
    )
    ok_result = CompletionResult(
        text="category: billing", predicted_label="billing", prompt_tokens=10,
        completion_tokens=5, cost_usd=0.001, latency_ms=10.0,
    )

    db = SessionLocal()
    variants = db.query(models.ExperimentVariant).filter(models.ExperimentVariant.experiment_id == exp["id"]).all()
    flaky_variant = next(v for v in variants if v.name == "flaky")

    # Force 25 requests directly onto the flaky variant, 80% erroring, to blow
    # past the 10% guardrail threshold.
    for i in range(25):
        is_error = i % 5 != 0  # 80% error rate
        result = error_result if is_error else ok_result
        db.add(models.RequestLog(
            prompt_id=prompt["id"], version_id=v2["id"], experiment_id=exp["id"], variant_id=flaky_variant.id,
            user_key=f"u{i}", input_variables={}, response_text=result.text,
            predicted_label=result.predicted_label, expected_label="billing",
            latency_ms=result.latency_ms, prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens, cost_usd=result.cost_usd,
            error=result.error, error_message=result.error_message,
        ))
    db.commit()

    experiment_row = db.get(models.Experiment, exp["id"])
    stopped = guardrails.check_guardrails(db, experiment_row)
    db.commit()

    assert stopped is True
    assert experiment_row.status == models.ExperimentStatus.auto_stopped
    assert "error rate" in experiment_row.stop_reason
    db.close()
