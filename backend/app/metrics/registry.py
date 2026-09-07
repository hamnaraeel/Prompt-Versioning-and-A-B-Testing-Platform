"""Pluggable metric collector framework.

A metric is any callable registered with @register_metric that receives a
RequestLog row and returns a float (or None if not applicable to that
request). Metrics run asynchronously, after the response has already been
returned to the caller (see worker/worker.py), so slow/custom scoring never
adds latency to the serving path.

`higher_is_better` tells the statistics engine which direction counts as a
win when comparing variants.
"""
from dataclasses import dataclass
from typing import Callable, Optional

MetricFn = Callable[["RequestLog"], Optional[float]]  # noqa: F821


@dataclass
class MetricSpec:
    name: str
    fn: MetricFn
    higher_is_better: bool
    builtin: bool = False


_REGISTRY: dict[str, MetricSpec] = {}


def register_metric(name: str, higher_is_better: bool, builtin: bool = False):
    def _decorator(fn: MetricFn):
        _REGISTRY[name] = MetricSpec(name=name, fn=fn, higher_is_better=higher_is_better, builtin=builtin)
        return fn

    return _decorator


def get_metric(name: str) -> MetricSpec | None:
    return _REGISTRY.get(name)


def all_metrics() -> dict[str, MetricSpec]:
    return dict(_REGISTRY)


def higher_is_better(name: str) -> bool:
    spec = _REGISTRY.get(name)
    return spec.higher_is_better if spec else True
