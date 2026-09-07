from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app import models  # noqa: F401 ensures models are registered before create_all
from app.metrics import builtin  # noqa: F401 populates the metric registry
from app.routers import audit, compare, completions, experiments, prompts

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Prompt Versioning & A/B Testing Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(prompts.router)
app.include_router(experiments.router)
app.include_router(completions.router)
app.include_router(compare.router)
app.include_router(audit.router)


@app.get("/health")
def health():
    return {"status": "ok"}
