"""LLM provider abstraction.

Supports real calls to OpenAI/Anthropic when API keys are configured, and a
built-in "mock" provider used by default so the platform (and its demo
scenario) runs fully offline with no API cost. The mock provider implements a
believable customer-support email classifier whose accuracy/latency/cost vary
by prompting strategy (zero-shot vs few-shot vs chain-of-thought), which is
what lets the seeded demo experiment converge to a statistically significant
winner without hitting a real model.
"""
import random
import time
from dataclasses import dataclass

from app.config import settings

CATEGORIES = ["billing", "technical", "account", "other"]

_KEYWORDS = {
    "billing": ["invoice", "charge", "refund", "payment", "billing", "subscription", "price"],
    "technical": ["error", "bug", "crash", "not working", "broken", "issue", "login", "password reset"],
    "account": ["account", "profile", "email address", "delete my account", "username", "access"],
}


@dataclass
class CompletionResult:
    text: str
    predicted_label: str | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: float
    error: bool = False
    error_message: str | None = None


def _true_label(email_text: str) -> str:
    lowered = email_text.lower()
    scores = {cat: sum(1 for kw in kws if kw in lowered) for cat, kws in _KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def _classify_mock(system_prompt: str, few_shot_examples: list, email_text: str) -> tuple[str, float, int]:
    """Returns (predicted_label, extra_latency_ms, extra_completion_tokens)."""
    lowered = system_prompt.lower()
    is_cot = any(k in lowered for k in ["step by step", "step-by-step", "chain of thought", "chain-of-thought"])
    has_few_shot = len(few_shot_examples) > 0

    if is_cot:
        error_rate, extra_latency, extra_tokens = 0.10, 550.0, 180
    elif has_few_shot:
        error_rate, extra_latency, extra_tokens = 0.18, 220.0, 60
    else:
        error_rate, extra_latency, extra_tokens = 0.32, 80.0, 20

    true_label = _true_label(email_text)
    if random.random() < error_rate:
        predicted = random.choice([c for c in CATEGORIES if c != true_label])
    else:
        predicted = true_label
    return predicted, extra_latency, extra_tokens


class LLMProvider:
    def complete(
        self,
        *,
        provider: str,
        model_name: str,
        system_prompt: str,
        few_shot_examples: list,
        user_input: str,
        temperature: float,
        max_tokens: int,
    ) -> CompletionResult:
        if provider == "openai" and settings.openai_api_key:
            return self._complete_openai(model_name, system_prompt, few_shot_examples, user_input, temperature, max_tokens)
        if provider == "anthropic" and settings.anthropic_api_key:
            return self._complete_anthropic(model_name, system_prompt, few_shot_examples, user_input, temperature, max_tokens)
        return self._complete_mock(system_prompt, few_shot_examples, user_input)

    def _complete_mock(self, system_prompt: str, few_shot_examples: list, user_input: str) -> CompletionResult:
        start = time.perf_counter()
        predicted, extra_latency, extra_tokens = _classify_mock(system_prompt, few_shot_examples, user_input)
        base_latency = random.uniform(60, 140)
        latency_ms = base_latency + extra_latency + random.uniform(-15, 15)

        prompt_tokens = len(system_prompt.split()) + sum(len(str(ex).split()) for ex in few_shot_examples) + len(user_input.split())
        completion_tokens = 8 + extra_tokens + random.randint(-5, 5)
        completion_tokens = max(completion_tokens, 1)
        cost_usd = prompt_tokens * 0.000003 + completion_tokens * 0.000006

        elapsed_ms = (time.perf_counter() - start) * 1000
        return CompletionResult(
            text=f"category: {predicted}",
            predicted_label=predicted,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=round(cost_usd, 6),
            latency_ms=round(latency_ms + elapsed_ms, 2),
        )

    def _complete_openai(self, model_name, system_prompt, few_shot_examples, user_input, temperature, max_tokens) -> CompletionResult:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        messages = [{"role": "system", "content": system_prompt}]
        for ex in few_shot_examples:
            if "user" in ex:
                messages.append({"role": "user", "content": ex["user"]})
            if "assistant" in ex:
                messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": user_input})

        start = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model_name, messages=messages, temperature=temperature, max_tokens=max_tokens
            )
            latency_ms = (time.perf_counter() - start) * 1000
            text = resp.choices[0].message.content or ""
            usage = resp.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            cost_usd = prompt_tokens * 0.000005 + completion_tokens * 0.000015
            return CompletionResult(
                text=text,
                predicted_label=_extract_label(text),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 6),
                latency_ms=round(latency_ms, 2),
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.perf_counter() - start) * 1000
            return CompletionResult(
                text="", predicted_label=None, prompt_tokens=0, completion_tokens=0,
                cost_usd=0.0, latency_ms=round(latency_ms, 2), error=True, error_message=str(exc),
            )

    def _complete_anthropic(self, model_name, system_prompt, few_shot_examples, user_input, temperature, max_tokens) -> CompletionResult:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        messages = []
        for ex in few_shot_examples:
            if "user" in ex:
                messages.append({"role": "user", "content": ex["user"]})
            if "assistant" in ex:
                messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": user_input})

        start = time.perf_counter()
        try:
            resp = client.messages.create(
                model=model_name, system=system_prompt, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            text = "".join(block.text for block in resp.content if hasattr(block, "text"))
            prompt_tokens = resp.usage.input_tokens
            completion_tokens = resp.usage.output_tokens
            cost_usd = prompt_tokens * 0.000003 + completion_tokens * 0.000015
            return CompletionResult(
                text=text,
                predicted_label=_extract_label(text),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 6),
                latency_ms=round(latency_ms, 2),
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.perf_counter() - start) * 1000
            return CompletionResult(
                text="", predicted_label=None, prompt_tokens=0, completion_tokens=0,
                cost_usd=0.0, latency_ms=round(latency_ms, 2), error=True, error_message=str(exc),
            )


def _extract_label(text: str) -> str | None:
    lowered = text.lower()
    for cat in CATEGORIES:
        if cat in lowered:
            return cat
    return None


provider = LLMProvider()
