import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from api import list_prompts, list_versions, post

st.set_page_config(page_title="Compare Versions", layout="wide", page_icon="⚖️")
st.title("⚖️ Compare Prompt Versions")
st.caption(
    "A quick sanity check before committing to a full experiment: send the same test inputs to "
    "two versions and eyeball the outputs side by side."
)

prompts = list_prompts()
if not prompts:
    st.info("Create a prompt first on the **Prompt Registry** page.")
    st.stop()

names = {p["name"]: p["id"] for p in prompts}
chosen_prompt = st.selectbox("Prompt", list(names.keys()))
prompt_id = names[chosen_prompt]
versions = list_versions(prompt_id)

if len(versions) < 2:
    st.warning("Need at least 2 versions to compare.")
    st.stop()

version_options = {f"v{v['version_number']} — {v['commit_message'] or v['id'][:8]}": v["id"] for v in versions}
c1, c2 = st.columns(2)
label_a = c1.selectbox("Version A", list(version_options.keys()), index=0)
label_b = c2.selectbox("Version B", list(version_options.keys()), index=len(version_options) - 1)

default_cases = json.dumps(
    [
        {"email_text": "I was charged twice for my subscription this month, please refund me.", "expected_label": "billing"},
        {"email_text": "The app keeps crashing when I try to log in.", "expected_label": "technical"},
        {"email_text": "How do I change the email address on my account?", "expected_label": "account"},
    ],
    indent=2,
)
test_inputs_raw = st.text_area("Test inputs (JSON list of variable dicts)", value=default_cases, height=200)

if st.button("Run comparison"):
    try:
        test_inputs = json.loads(test_inputs_raw)
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
        test_inputs = None

    if test_inputs is not None:
        result = post(
            "/compare",
            json={
                "version_id_a": version_options[label_a],
                "version_id_b": version_options[label_b],
                "test_inputs": test_inputs,
            },
        )
        rows = []
        for case in result["cases"]:
            rows.append({
                "input": json.dumps(case["input"]),
                "A: response": case["a"].get("response_text") or case["a"].get("error"),
                "A: predicted": case["a"].get("predicted_label"),
                "A: correct": case["a"].get("correct"),
                "A: latency_ms": case["a"].get("latency_ms"),
                "B: response": case["b"].get("response_text") or case["b"].get("error"),
                "B: predicted": case["b"].get("predicted_label"),
                "B: correct": case["b"].get("correct"),
                "B: latency_ms": case["b"].get("latency_ms"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
