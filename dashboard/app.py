import streamlit as st

from api import list_experiments, list_notifications, list_prompts

st.set_page_config(page_title="Prompt Versioning & A/B Testing", layout="wide")

st.title("Prompt Versioning & A/B Testing Platform")
st.caption("Feature-flagging rigor for LLM prompts: version, deploy, split traffic, measure, and promote winners.")

try:
    notes = list_notifications(limit=10)
except Exception as exc:
    st.error(f"Could not reach backend API. Is it running? ({exc})")
    st.stop()

unread = [n for n in notes if not n["read"]]
if unread:
    with st.container(border=True):
        st.subheader("Recent notifications")
        for n in unread[:5]:
            level = n["level"]
            icon = {"warning": "⚠️", "success": "✅"}.get(level, "ℹ️")
            st.write(f"{icon} {n['message']}")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Prompts")
    prompts = list_prompts()
    if not prompts:
        st.info("No prompts yet. Use the Prompt Registry page to create one, or run the seed demo script.")
    for p in prompts:
        st.write(f"**{p['name']}** — {p['description'] or 'no description'}")
        st.caption(f"id: `{p['id']}` · active version: `{p['active_version_id'] or 'none'}`")

with col2:
    st.subheader("Experiments")
    experiments = list_experiments()
    if not experiments:
        st.info("No experiments yet. Use the Experiments page to launch one.")
    for e in experiments:
        st.write(f"**{e['name']}** — status: `{e['status']}`")
        st.caption(f"primary metric: {e['primary_metric']} · target n: {e['target_sample_size']}")

st.divider()
st.markdown(
    "Use the sidebar to open **Prompt Registry**, **Experiments**, **Compare Versions**, or **Audit Log**."
)
