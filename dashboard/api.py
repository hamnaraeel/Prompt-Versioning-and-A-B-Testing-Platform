import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _url(path: str) -> str:
    return f"{BACKEND_URL}{path}"


def get(path: str, **kwargs):
    resp = requests.get(_url(path), timeout=30, **kwargs)
    resp.raise_for_status()
    return resp.json()


def post(path: str, json=None, **kwargs):
    resp = requests.post(_url(path), json=json, timeout=60, **kwargs)
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        st.error(f"{resp.status_code}: {detail}")
        resp.raise_for_status()
    return resp.json()


def list_prompts():
    return get("/prompts")


def get_prompt(prompt_id: str):
    return get(f"/prompts/{prompt_id}")


def list_versions(prompt_id: str):
    return get(f"/prompts/{prompt_id}/versions")


def list_activations(prompt_id: str):
    return get(f"/prompts/{prompt_id}/activations")


def list_experiments():
    return get("/experiments")


def get_experiment_results(experiment_id: str):
    return get(f"/experiments/{experiment_id}/results")


def list_audit_log(limit=200):
    return get("/audit-log", params={"limit": limit})


def list_notifications(limit=50):
    return get("/notifications", params={"limit": limit})
