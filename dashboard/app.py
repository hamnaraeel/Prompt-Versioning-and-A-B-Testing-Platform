import streamlit as st

from api import get_experiment_results, list_experiments, list_notifications, list_prompts

st.set_page_config(page_title="Prompt Versioning & A/B Testing", layout="wide", page_icon="🧪")

STATUS_LABELS = {
    "draft": ("📝", "Draft — not started yet"),
    "running": ("🏃", "Running — collecting traffic"),
    "winner_declared": ("🏆", "Winner found — pending auto-promotion"),
    "completed": ("✅", "Completed — winner promoted"),
    "auto_stopped": ("⚠️", "Auto-stopped — a variant underperformed"),
    "cancelled": ("⏹️", "Cancelled"),
}


def status_badge(status: str) -> str:
    icon, label = STATUS_LABELS.get(status, ("•", status))
    return f"{icon} {label}"


st.title("🧪 Prompt Versioning & A/B Testing Platform")
st.markdown(
    "Treat your LLM prompts like code: **save every version**, **test a few at once on real "
    "traffic**, and let statistics — not guesswork — tell you which one to keep."
)

try:
    notes = list_notifications(limit=10)
    prompts = list_prompts()
    experiments = list_experiments()
except Exception as exc:
    st.error(
        f"Can't reach the backend API — is it running? (`{exc}`)\n\n"
        "If you're running this locally, start the stack with `docker compose up --build`."
    )
    st.stop()

# ---------- First-time-user onboarding ----------
if not prompts and not experiments:
    st.info(
        "👋 **Looks like this is a fresh install — nothing here yet.** Follow the steps below to "
        "get your first test running, or load the built-in demo."
    )

with st.expander("📖 How this works (4 steps)", expanded=not prompts):
    st.markdown(
        """
1. **Create a prompt** on the *Prompt Registry* page — this is a named slot for one task
   (e.g. "support-email-classifier"). Give it a first version: the instruction text itself.
2. **Add more versions** as you improve the wording — every version is saved, nothing is
   overwritten, and you can roll back anytime.
3. **Launch an experiment** on the *Experiments* page — pick 2+ versions to test at once and
   what percentage of traffic each gets.
4. **Watch it converge** — as real requests come in, the platform scores each variant and
   tells you, with statistical confidence, which one actually performs better. It can even
   auto-promote the winner after a safety waiting period.
        """
    )
    st.caption(
        "No prompts yet? Run the seeded demo to see all of this working end-to-end: "
        "`docker compose --profile seed run --rm seed`"
    )

unread = [n for n in notes if not n["read"]]
if unread:
    with st.container(border=True):
        st.subheader("🔔 Recent notifications")
        for n in unread[:5]:
            level = n["level"]
            icon = {"warning": "⚠️", "success": "✅"}.get(level, "ℹ️")
            st.write(f"{icon} {n['message']}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("📚 Prompts")
    if not prompts:
        st.info("No prompts yet — create one on the **Prompt Registry** page.")
    for p in prompts:
        with st.container(border=True):
            st.markdown(f"**{p['name']}**")
            st.caption(p["description"] or "No description")
            st.write("✅ Has an active (live) version" if p["active_version_id"] else "⚪ No active version yet")
            with st.expander("Technical details"):
                st.code(f"prompt id: {p['id']}\nactive version id: {p['active_version_id'] or 'none'}")

with col2:
    st.subheader("🔬 Experiments")
    if not experiments:
        st.info("No experiments yet — launch one on the **Experiments** page.")
    for e in experiments:
        with st.container(border=True):
            st.markdown(f"**{e['name']}**")
            st.write(status_badge(e["status"]))
            st.caption(f"Measuring: {e['primary_metric'].replace('_', ' ')} · target sample size: {e['target_sample_size']}")
            if e["status"] in ("winner_declared", "completed"):
                try:
                    results = get_experiment_results(e["id"])
                    winner = next((v for v in results["variants"] if v["variant_id"] == results.get("winner_variant_id")), None)
                    if winner:
                        st.success(f"Winner: **{winner['name']}** (mean {winner['mean']:.2f} on {e['primary_metric']})")
                except Exception:
                    pass

st.divider()
st.markdown(
    "**Use the sidebar** to open a page: 📚 *Prompt Registry* (create/version/rollback prompts), "
    "🔬 *Experiments* (launch and monitor tests), ⚖️ *Compare Versions* (quick side-by-side sanity check), "
    "📜 *Audit Log* (who changed what, and when)."
)
