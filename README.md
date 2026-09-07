# Prompt Versioning & A/B Testing Platform

A platform that treats prompts as versioned artifacts (like code), lets teams deploy multiple prompt
variants simultaneously, splits traffic between them, measures performance across custom metrics, and
declares statistically significant winners — bringing the rigor of feature flagging and experimentation
to LLM-powered features.

> "I built a prompt experimentation platform that brings feature-flagging rigor to LLM development.
> Teams can test prompt changes against live traffic and get statistically significant results instead
> of guessing." Positioned as infrastructure, not a toy.

## Tech stack

| Component | Tool / Library |
|---|---|
| Language | Python 3.11+ |
| LLM Provider | OpenAI / Anthropic, with a built-in offline mock provider |
| Storage | PostgreSQL (SQLite supported for tests) |
| Statistics | scipy.stats (Welch's t-test, Mann-Whitney U) |
| API | FastAPI |
| Dashboard | Streamlit |
| Async metrics | standalone polling worker |
| Containerization | Docker + docker-compose |

## Quickstart

```bash
cp .env.example .env   # optional: add OPENAI_API_KEY / ANTHROPIC_API_KEY, or leave blank for the mock provider
docker compose up --build
```

- API: http://localhost:8001 (docs at `/docs`)
- Dashboard: http://localhost:8501
- Postgres: localhost:5433 (user/pass/db: `ppat`)

(Host ports are remapped from the defaults 8000/5432 to 8001/5433 to avoid clashing with other local
projects; the containers still talk to each other internally on 8000/5432.)

Seed the demo scenario (a customer-support email classifier with three prompt variants — zero-shot,
few-shot, chain-of-thought — run as a live experiment over 500+ synthetic requests):

```bash
docker compose --profile seed run --rm seed
```

Then open the dashboard's **Experiments** page and watch the experiment converge to a winner as the
`worker` service scores metrics and re-checks significance on its polling loop. No API keys are
required — the seed script and mock LLM provider run entirely offline.

## Running tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt pytest
pytest tests/
```

## Architecture

```
backend/app/
  models.py            SQLAlchemy schema: prompts, versions, activations, experiments,
                        variants, assignments, request logs, metric values, notifications, audit log
  routers/prompts.py    Prompt registry: create/list prompts & versions, diff, activate/rollback
  routers/experiments.py Experiment lifecycle: create/start/cancel/promote, results
  routers/completions.py POST /v1/completions — the serving endpoint (traffic split + LLM call + logging)
  routers/compare.py    Side-by-side version comparison tool
  routers/audit.py      Audit log + notifications feed
  services/traffic_splitter.py  Consistent hashing so a user always sees the same variant
  services/templates.py Template variable extraction/rendering + validation
  services/llm_provider.py  OpenAI / Anthropic / mock provider abstraction
  services/stats_engine.py  t-test, Mann-Whitney U, CI, minimum detectable effect
  services/results_engine.py  Aggregates metric values into per-variant stats + comparisons
  services/guardrails.py   Auto-stop on error-rate/perf regressions; winner declaration + auto-promotion
  metrics/               Pluggable metric registry (latency, tokens, cost, error rate, task accuracy,
                          quality score) — register your own with @register_metric
worker/worker.py         Polls for unscored requests, runs metric collectors, guardrails, and the
                          winner/auto-promotion lifecycle — kept off the request-serving path
dashboard/                Streamlit app: prompt registry UI, experiment creation/monitoring, compare
                          tool, audit log
seed/seed_demo.py         Seeds the demo scenario end-to-end
```

## Build status

This tracks the phases from the original build guide, so it's easy to see what's done.

### Phase 1 — Prompt Registry
- [x] Versioning schema (id, auto-incrementing version, system prompt, few-shot examples, model
      params, commit message, timestamp) in PostgreSQL
- [x] Registry API: create prompt, create version, list versions, get version, diff endpoint
- [x] Rollback support: any version can be marked active; every activation/deactivation is
      audit-logged with actor + reason
- [x] Template variables (`{{var}}`) — the template is versioned, not the filled prompt; missing
      variables are rejected at serve time (422)

### Phase 2 — Experiment Engine
- [x] Experiment schema: name, prompt, variants, traffic split, primary metric, target sample size,
      status
- [x] Traffic splitter: consistent hashing on `user_key` so the same user always gets the same variant
- [x] Serving endpoint `POST /v1/completions`: resolves active version or experiment variant, fills
      the template, calls the LLM, logs request/response + assignment, returns the response
- [x] Guardrails: auto-stop on error rate > threshold (default 10%) or on a variant performing
      significantly worse than control on the primary metric; owner notified via the notifications feed

### Phase 3 — Metrics & Analysis
- [x] Pluggable metric framework (`@register_metric`); built-ins: latency, token usage, cost, error
      rate; custom: task accuracy / quality score (LLM-as-judge-style, swappable), computed
      asynchronously by the worker
- [x] Statistical significance testing: mean/variance per variant, Welch's t-test + Mann-Whitney U,
      p-value, confidence interval on the difference, minimum detectable effect at current sample size
- [x] Results dashboard: bar chart with error bars, sample-size progress, per-variant table,
      comparison table, winner/no-winner/inconclusive status
- [x] Automated winner declaration at the configured confidence level (default 95%), with a 24h hold
      before auto-promotion (cancellable from the dashboard)

### Phase 4 — Management Interface
- [x] Experiment management UI (Streamlit): create experiments from the registry, configure traffic
      splits/metrics, monitor running experiments, view results, promote winners with one click
- [x] Prompt comparison tool: pick two versions, send the same test inputs, compare outputs +
      predicted labels + latency side by side
- [x] Audit log UI: every prompt/version/experiment/activation/promotion action, filterable by action

### Phase 5 — Integration and Testing
- [x] Demo scenario: customer support email classifier, 3 variants (zero-shot / few-shot /
      chain-of-thought), 540 synthetic requests, converges to a winner via the mock provider's
      strategy-dependent accuracy simulation
- [x] docker-compose: PostgreSQL, FastAPI backend, Streamlit dashboard, worker, seed job (profile)
- [x] Integration tests: versioning + rollback, traffic-split consistency, metric collection accuracy,
      significance correctness (known-distribution tests), auto-stop on error-rate spikes

### Phase 6 — Polish for Portfolio
- [ ] Recorded demo walkthrough (record locally — script is under `seed/seed_demo.py` for a live run)
- [x] Narrative write-up (top of this README)

## API reference (quick)

- `POST /prompts` / `GET /prompts` / `GET /prompts/{id}`
- `POST /prompts/{id}/versions` / `GET /prompts/{id}/versions` / `GET /prompts/{id}/versions/{v}`
- `GET /prompts/{id}/diff/{v1}/{v2}`
- `POST /prompts/{id}/versions/{v}/activate` (rollback is just activating an older version)
- `GET /prompts/{id}/activations`
- `POST /experiments` / `GET /experiments` / `GET /experiments/{id}`
- `POST /experiments/{id}/start` / `.../cancel` / `.../promote` / `.../cancel-promotion`
- `GET /experiments/{id}/results`
- `POST /v1/completions` — the serving endpoint
- `POST /compare` — side-by-side version comparison
- `GET /audit-log`, `GET /notifications`
