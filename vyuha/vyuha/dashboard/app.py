"""
Vyuha Dashboard — Test Run Summary, Failure Drill-Down, RCA Aggregation, Executive Scorecard
Run with: streamlit run vyuha/dashboard/app.py
"""
from __future__ import annotations

import httpx
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import os
API_BASE = os.getenv("VYUHA_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Vyuha — Voice AI Eval", layout="wide", page_icon="🎙️")

# --- Sidebar ---
st.sidebar.title("Vyuha")
st.sidebar.caption("Voice AI Evaluation System")
page = st.sidebar.radio(
    "Navigation",
    ["Executive Scorecard", "Test Run Summary", "RCA Breakdown", "Failure Drill-Down", "Test Case Manager", "Generate Tests"],
)


def api(path: str) -> dict:
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=10)
        return r.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return {}


# ─────────────────────────────────────────────────────────────
if page == "Executive Scorecard":
    st.title("Executive Scorecard")
    data = api("/reports/executive-scorecard")
    if data and "overall_quality_score" in data:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Quality Score", f"{data['overall_quality_score']}%")
        col2.metric("Pass Rate", f"{data['pass_rate_pct']}%")
        col3.metric("Critical Failures", data["critical_failures"])
        col4.metric("Total Runs", data["total_runs_evaluated"])

        st.subheader("Top 3 Root Causes")
        if data.get("top_3_rca_codes"):
            for item in data["top_3_rca_codes"]:
                st.write(f"**{item['code']}** — {item['count']} failures")
    else:
        st.info("No runs yet. Start by generating and running test cases.")

# ─────────────────────────────────────────────────────────────
elif page == "Test Run Summary":
    st.title("Test Run Summary")
    data = api("/reports/summary")
    if data and "total_runs" in data:
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Runs", data["total_runs"])
        col2.metric("Passed", data["passed"])
        col3.metric("Failed", data["failed"])
        col4.metric("EVA-A", f"{data['avg_eva_a']:.1%}")
        col5.metric("EVA-X", f"{data['avg_eva_x']:.1%}")

        threshold = 0.97
        pr = data["pass_rate"]
        color = "green" if pr >= threshold else "red"
        st.markdown(
            f"**Pass Rate:** <span style='color:{color};font-size:1.4rem'>{pr:.1%}</span> "
            f"({'✓ Above' if pr >= threshold else '✗ Below'} {threshold:.0%} regression threshold)",
            unsafe_allow_html=True,
        )

        if data["critical_failures"] > 0:
            st.error(f"⚠️ {data['critical_failures']} CRITICAL failure(s) detected — release blocked")

        st.metric("P95 Latency", f"{data['avg_latency_p95_ms']:.0f} ms",
                  delta_color="inverse" if data['avg_latency_p95_ms'] > 800 else "normal")
    else:
        st.info("No runs yet.")

# ─────────────────────────────────────────────────────────────
elif page == "RCA Breakdown":
    st.title("RCA Aggregation")
    data = api("/reports/rca-breakdown")
    if data and data.get("breakdown"):
        df = pd.DataFrame(data["breakdown"])
        fig = px.bar(df, x="rca_code", y="count", color="count",
                     color_continuous_scale="Reds",
                     title=f"Failures by RCA Code (Total: {data['total_failure_tags']})",
                     labels={"rca_code": "RCA Code", "count": "Failure Count"})
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No failure data yet.")

# ─────────────────────────────────────────────────────────────
elif page == "Failure Drill-Down":
    st.title("Failure Drill-Down")
    run_id = st.text_input("Run ID")
    if run_id:
        run = api(f"/runs/{run_id}")
        if run and "verdict" in run:
            st.write(f"**Verdict:** {run['verdict']}")
            cola, colb = st.columns(2)
            with cola:
                st.subheader("EVA-A (Accuracy)")
                st.metric("Task Completion", f"{run['eva_a']['task_completion']:.1%}")
                st.metric("Faithfulness", f"{run['eva_a']['faithfulness']:.1%}")
                st.metric("Speech Fidelity", f"{run['eva_a']['speech_fidelity']:.1%}")
                st.metric("Composite", f"{(run['eva_a']['task_completion']*0.5 + run['eva_a']['faithfulness']*0.3 + run['eva_a']['speech_fidelity']*0.2):.1%}")
            with colb:
                st.subheader("EVA-X (Experience)")
                st.metric("Conciseness", f"{run['eva_x']['conciseness']:.1%}")
                st.metric("Progression", f"{run['eva_x']['conversation_progression']:.1%}")
                st.metric("Turn-Taking", f"{run['eva_x']['turn_taking']:.1%}")

            if run.get("failure_report"):
                st.error(f"**Failed criterion:** {run['failure_report']['failed_criterion']}")
                st.write(f"**Failure at turn {run['failure_report']['failure_turn_index']}:** "
                         f"_{run['failure_report']['failure_excerpt']}_")
                if run["failure_report"]["rca_tags"]:
                    st.subheader("RCA Tags")
                    for tag in run["failure_report"]["rca_tags"]:
                        label = "🚨 CRITICAL" if tag["code"] == "RCA-SAFE-01" else "⚠️"
                        st.write(f"{label} **{tag['code']}** ({tag['confidence']:.0%} confidence) — {tag['description']}")
                        st.caption(f"Fix: {tag['suggested_fix']}")

            if run.get("turns"):
                st.subheader("Conversation Transcript")
                for turn in run["turns"]:
                    with st.expander(f"Turn {turn['turn_index']} — {turn['latency_ms']:.0f}ms"):
                        st.write(f"**User:** {turn['user_utterance']}")
                        st.write(f"**Agent:** {turn['agent_response']}")
        else:
            st.warning("Run not found.")

# ─────────────────────────────────────────────────────────────
elif page == "Test Case Manager":
    st.title("Test Case Manager")
    cases = api("/test-cases/")
    if isinstance(cases, list) and cases:
        df = pd.DataFrame([
            {
                "ID": c["test_id"],
                "Title": c["title"],
                "Category": c["category"],
                "Language": c["persona_config"]["language"],
                "Noise": c["persona_config"]["noise_profile"],
                "Tags": ", ".join(c.get("tags", [])),
            }
            for c in cases
        ])
        st.dataframe(df, use_container_width=True)

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            cat_filter = st.selectbox("Filter by Category", ["All", "HAPPY_PATH", "EDGE_CASE", "FAILURE_MODE", "CRITICAL"])
        with col_f2:
            lang_filter = st.selectbox("Filter by Language", ["All", "hi", "te", "ta", "or", "kn", "ml", "mr", "bn", "en-IN"])
    else:
        st.info("No test cases yet. Use 'Generate Tests' to create some.")

# ─────────────────────────────────────────────────────────────
elif page == "Generate Tests":
    st.title("Auto-Generate Test Cases")
    st.caption("Paste your voice agent's system prompt to generate 50 test scenarios automatically.")

    with st.form("gen_form"):
        system_prompt = st.text_area("System Prompt *", height=200, placeholder="Paste the agent's system prompt here...")
        knowledge_base = st.text_area("Knowledge Base (optional)", height=100)
        flow_description = st.text_area("Conversation Flow Description (optional)", height=80)
        language = st.selectbox("Primary Language", ["en-IN", "hi", "te", "ta", "or", "kn", "ml", "mr", "bn"])
        use_cases = st.text_input("Use Cases", placeholder="e.g. debt collection, appointment booking")
        count = st.slider("Number of Test Cases", min_value=10, max_value=100, value=50, step=5)
        submitted = st.form_submit_button("Generate")

    if submitted and system_prompt:
        with st.spinner(f"Generating {count} test cases with Claude Sonnet 4.6..."):
            try:
                resp = httpx.post(
                    f"{API_BASE}/generate/from-prompt",
                    json={
                        "system_prompt": system_prompt,
                        "knowledge_base": knowledge_base,
                        "flow_description": flow_description,
                        "language": language,
                        "use_cases": use_cases,
                        "count": count,
                    },
                    timeout=120,
                )
                if resp.status_code == 200:
                    cases = resp.json()
                    st.success(f"Generated {len(cases)} test cases!")

                    cats = pd.Series([c["category"] for c in cases]).value_counts()
                    fig = px.pie(values=cats.values, names=cats.index, title="Category Distribution")
                    st.plotly_chart(fig)

                    df = pd.DataFrame([{"ID": c["test_id"], "Title": c["title"], "Category": c["category"]} for c in cases])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.error(f"Generation failed: {resp.text}")
            except Exception as exc:
                st.error(f"Error: {exc}")
