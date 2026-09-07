import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api import get_experiment_results, list_experiments, list_prompts, list_versions, post

st.set_page_config(page_title="Experiments", layout="wide")
st.title("Experiments")

tab_create, tab_monitor = st.tabs(["Create experiment", "Monitor / results"])

with tab_create:
    prompts = list_prompts()
    if not prompts:
        st.info("Create a prompt with at least two versions first.")
    else:
        names = {p["name"]: p["id"] for p in prompts}
        chosen_prompt = st.selectbox("Prompt", list(names.keys()))
        prompt_id = names[chosen_prompt]
        versions = list_versions(prompt_id)
        if len(versions) < 2:
            st.warning("This prompt needs at least 2 versions to run an experiment.")
        else:
            with st.form("create_experiment"):
                exp_name = st.text_input("Experiment name")
                n_variants = st.number_input("Number of variants", min_value=2, max_value=len(versions), value=2)
                version_options = {f"v{v['version_number']} — {v['commit_message'] or v['id'][:8]}": v["id"] for v in versions}

                variant_rows = []
                default_pct = round(100 / n_variants, 1)
                for i in range(int(n_variants)):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    label = c1.selectbox(f"Variant {i+1} version", list(version_options.keys()), key=f"vv_{i}")
                    pct = c2.number_input("Traffic %", min_value=0.0, max_value=100.0, value=default_pct, key=f"pct_{i}")
                    is_control = c3.checkbox("Control", value=(i == 0), key=f"ctrl_{i}")
                    variant_rows.append({"version_id": version_options[label], "name": label.split(" — ")[0], "traffic_pct": pct, "is_control": is_control})

                primary_metric = st.selectbox("Primary metric", ["task_accuracy", "quality_score", "latency_ms", "cost_usd", "total_tokens"])
                target_n = st.number_input("Target sample size (per experiment)", min_value=20, value=200, step=20)
                confidence = st.selectbox("Confidence level", [0.90, 0.95, 0.99], index=1)
                auto_promote = st.checkbox("Auto-promote winner after 24h hold", value=True)
                actor = st.text_input("Actor", value="dashboard-user")

                if st.form_submit_button("Create experiment") and exp_name:
                    post(
                        "/experiments",
                        json={
                            "name": exp_name,
                            "prompt_id": prompt_id,
                            "variants": variant_rows,
                            "primary_metric": primary_metric,
                            "target_sample_size": int(target_n),
                            "confidence_level": confidence,
                            "auto_promote": auto_promote,
                            "actor": actor,
                        },
                    )
                    st.success(f"Created experiment '{exp_name}'")
                    st.rerun()

with tab_monitor:
    experiments = list_experiments()
    if not experiments:
        st.info("No experiments yet.")
        st.stop()

    labels = {f"{e['name']} ({e['status']})": e["id"] for e in experiments}
    chosen = st.selectbox("Experiment", list(labels.keys()))
    exp_id = labels[chosen]
    exp = next(e for e in experiments if e["id"] == exp_id)

    col_start, col_cancel, col_promote, col_cancel_promo = st.columns(4)
    if exp["status"] == "draft" and col_start.button("Start experiment"):
        post(f"/experiments/{exp_id}/start")
        st.rerun()
    if exp["status"] in ("draft", "running") and col_cancel.button("Cancel experiment"):
        post(f"/experiments/{exp_id}/cancel")
        st.rerun()
    if exp["status"] == "winner_declared":
        if col_promote.button("Promote winner now"):
            post(f"/experiments/{exp_id}/promote")
            st.rerun()
        if not exp["promotion_cancelled"] and col_cancel_promo.button("Cancel auto-promotion"):
            post(f"/experiments/{exp_id}/cancel-promotion")
            st.rerun()

    st.divider()
    results = get_experiment_results(exp_id)

    st.subheader(f"Status: {results['overall_status'].upper()} — experiment status: {results['status']}")
    st.progress(min(results["progress"], 1.0), text=f"{results['total_samples']} / {results['target_sample_size']} samples")

    if exp.get("stop_reason"):
        st.error(exp["stop_reason"])
    if exp.get("promotion_hold_until") and exp["status"] == "winner_declared":
        st.info(f"Auto-promotion scheduled for {exp['promotion_hold_until']} (cancel above if needed).")

    variants_df = pd.DataFrame(results["variants"])
    if not variants_df.empty:
        fig = go.Figure()
        for _, row in variants_df.iterrows():
            fig.add_trace(go.Bar(
                name=row["name"],
                x=[row["name"]],
                y=[row["mean"]],
                error_y=dict(type="data", array=[row["std"] / max(row["n_metric_samples"], 1) ** 0.5]),
            ))
        fig.update_layout(title=f"{results['primary_metric']} by variant (mean ± SE)", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        variants_df = variants_df.rename(columns={
            "name": "Variant", "is_control": "Control", "n_requests": "Requests",
            "n_metric_samples": "Metric samples", "mean": "Mean", "std": "Std dev", "error_rate": "Error rate",
        })
        st.dataframe(variants_df, use_container_width=True)

    if results["comparisons"]:
        st.subheader("Statistical comparisons vs. control")
        comp_df = pd.DataFrame(results["comparisons"])
        display_cols = [
            "variant_name", "n_variant", "n_control", "mean_variant", "mean_control", "diff",
            "p_value_ttest", "p_value_mannwhitney", "significant", "favors_variant", "minimum_detectable_effect",
        ]
        st.dataframe(comp_df[display_cols], use_container_width=True)
    else:
        st.info("No comparisons yet — waiting for traffic.")
