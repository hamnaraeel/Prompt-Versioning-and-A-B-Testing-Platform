"""Built-in metrics (latency, token usage, cost, error rate) plus the demo's
custom task-accuracy metric. Import this module once at startup to populate
the metric registry (see app/main.py and worker/worker.py).
"""
from app.metrics.registry import register_metric


@register_metric("latency_ms", higher_is_better=False, builtin=True)
def latency_ms(request_log):
    return float(request_log.latency_ms or 0.0)


@register_metric("total_tokens", higher_is_better=False, builtin=True)
def total_tokens(request_log):
    return float((request_log.prompt_tokens or 0) + (request_log.completion_tokens or 0))


@register_metric("cost_usd", higher_is_better=False, builtin=True)
def cost_usd(request_log):
    return float(request_log.cost_usd or 0.0)


@register_metric("error_rate", higher_is_better=False, builtin=True)
def error_rate(request_log):
    return 1.0 if request_log.error else 0.0


@register_metric("task_accuracy", higher_is_better=True, builtin=False)
def task_accuracy(request_log):
    """Custom metric: 1.0 if the predicted label matches the known expected
    label, 0.0 otherwise. Only applicable when the caller supplied an
    expected_label (e.g. the labeled demo dataset)."""
    if request_log.expected_label is None:
        return None
    if request_log.error:
        return None
    return 1.0 if request_log.predicted_label == request_log.expected_label else 0.0


@register_metric("quality_score", higher_is_better=True, builtin=False)
def quality_score(request_log):
    """LLM-as-judge style quality proxy. For the demo classifier this is an
    alias of task_accuracy; a real deployment would swap this function for an
    actual judge-model call."""
    return task_accuracy(request_log)
