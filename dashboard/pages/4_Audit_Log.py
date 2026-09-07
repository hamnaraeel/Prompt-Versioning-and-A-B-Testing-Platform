import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from api import list_audit_log, list_notifications

st.set_page_config(page_title="Audit Log", layout="wide", page_icon="📜")
st.title("📜 Audit Log & Notifications")
st.caption(
    "\"Who changed the prompt that broke the feature last Tuesday?\" — this answers that. Every "
    "prompt creation, version change, experiment start/stop, winner promotion, and rollback is recorded here."
)

tab_audit, tab_notif = st.tabs(["Audit log", "Notifications"])

with tab_audit:
    rows = list_audit_log(limit=500)
    if not rows:
        st.info("No audit events yet.")
    else:
        df = pd.DataFrame(rows)
        actions = sorted(df["action"].unique())
        selected_actions = st.multiselect("Filter by action", actions, default=actions)
        df = df[df["action"].isin(selected_actions)]
        st.dataframe(df[["created_at", "action", "entity_type", "entity_id", "actor", "details"]], use_container_width=True)

with tab_notif:
    notes = list_notifications(limit=200)
    if not notes:
        st.info("No notifications yet.")
    for n in notes:
        icon = {"warning": "⚠️", "success": "✅"}.get(n["level"], "ℹ️")
        st.write(f"{icon} `{n['created_at']}` — {n['message']}")
