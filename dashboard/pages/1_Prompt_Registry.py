import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from api import get_prompt, list_activations, list_prompts, list_versions, post

st.set_page_config(page_title="Prompt Registry", layout="wide")
st.title("Prompt Registry")

with st.expander("Create a new prompt"):
    with st.form("create_prompt"):
        name = st.text_input("Name")
        description = st.text_area("Description")
        actor = st.text_input("Your name / actor", value="dashboard-user")
        if st.form_submit_button("Create prompt") and name:
            post("/prompts", json={"name": name, "description": description, "actor": actor})
            st.success(f"Created prompt '{name}'")
            st.rerun()

prompts = list_prompts()
if not prompts:
    st.info("No prompts yet.")
    st.stop()

names = {p["name"]: p["id"] for p in prompts}
selected_name = st.selectbox("Select a prompt", list(names.keys()))
prompt_id = names[selected_name]
prompt = get_prompt(prompt_id)

st.subheader(f"{prompt['name']}")
st.caption(prompt["description"])
st.write(f"Active version id: `{prompt['active_version_id']}`")

tab_versions, tab_new, tab_diff, tab_history = st.tabs(
    ["Versions", "New version", "Diff two versions", "Activation history"]
)

versions = list_versions(prompt_id)

with tab_versions:
    for v in sorted(versions, key=lambda x: -x["version_number"]):
        active = " (ACTIVE)" if v["id"] == prompt["active_version_id"] else ""
        with st.expander(f"v{v['version_number']}{active} — {v['commit_message'] or 'no message'}"):
            st.code(v["system_prompt"])
            st.write("Few-shot examples:", v["few_shot_examples"])
            st.write(
                f"Provider: `{v['model_provider']}` · Model: `{v['model_name']}` · "
                f"Temp: {v['temperature']} · Max tokens: {v['max_tokens']}"
            )
            st.write(f"Template variables: {v['template_variables']}")
            st.caption(f"by {v['created_by']} at {v['created_at']}")
            col_a, col_b = st.columns(2)
            reason = col_a.text_input("Activation reason", key=f"reason_{v['id']}")
            actor2 = col_b.text_input("Actor", value="dashboard-user", key=f"actor_{v['id']}")
            if st.button("Activate this version (rollback/promote)", key=f"act_{v['id']}"):
                post(
                    f"/prompts/{prompt_id}/versions/{v['version_number']}/activate",
                    json={"reason": reason, "actor": actor2},
                )
                st.success(f"Activated v{v['version_number']}")
                st.rerun()

with tab_new:
    with st.form("new_version"):
        system_prompt = st.text_area(
            "System prompt (use {{variable}} for template variables)", height=200
        )
        few_shot_raw = st.text_area(
            "Few-shot examples (JSON list of {\"user\":..,\"assistant\":..}, or empty for zero-shot)",
            value="[]",
        )
        provider = st.selectbox("Provider", ["mock", "openai", "anthropic"])
        model_name = st.text_input("Model name", value="mock-1")
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7)
        max_tokens = st.number_input("Max tokens", value=512, step=64)
        commit_message = st.text_input("Commit message")
        actor3 = st.text_input("Actor", value="dashboard-user", key="new_version_actor")
        if st.form_submit_button("Create version"):
            import json

            try:
                few_shot = json.loads(few_shot_raw) if few_shot_raw.strip() else []
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON for few-shot examples: {exc}")
                few_shot = None
            if few_shot is not None:
                post(
                    f"/prompts/{prompt_id}/versions",
                    json={
                        "system_prompt": system_prompt,
                        "few_shot_examples": few_shot,
                        "model_provider": provider,
                        "model_name": model_name,
                        "temperature": temperature,
                        "max_tokens": int(max_tokens),
                        "commit_message": commit_message,
                        "actor": actor3,
                    },
                )
                st.success("Version created")
                st.rerun()

with tab_diff:
    version_numbers = [v["version_number"] for v in versions]
    if len(version_numbers) >= 2:
        c1, c2 = st.columns(2)
        v1 = c1.selectbox("From version", version_numbers, index=0)
        v2 = c2.selectbox("To version", version_numbers, index=len(version_numbers) - 1)
        if st.button("Show diff"):
            from api import get

            diff = get(f"/prompts/{prompt_id}/diff/{v1}/{v2}")
            if not diff["changed_fields"]:
                st.info("No differences between these versions.")
            for field, change in diff["diff"].items():
                st.write(f"**{field}**")
                col_from, col_to = st.columns(2)
                col_from.code(str(change["from"]))
                col_to.code(str(change["to"]))
    else:
        st.info("Need at least two versions to diff.")

with tab_history:
    activations = list_activations(prompt_id)
    for a in activations:
        st.write(f"`{a['activated_at']}` — version `{a['version_id']}` activated by **{a['activated_by']}**")
        if a["reason"]:
            st.caption(a["reason"])
