"""CYNTHERA — Streamlit MVP Frontend.

Provides the main interactive UI for drug repurposing hypothesis evaluation.
Pages: Evaluate, Results, Audit Report, History.
"""
import asyncio
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="CYNTHERA — Drug Repurposing AI",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# Custom CSS — Premium Dark Design
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

:root {
    --bg-primary: #0a0e1a;
    --bg-secondary: #111827;
    --bg-card: #1a2235;
    --border: #2a3a55;
    --accent-blue: #3b82f6;
    --accent-purple: #8b5cf6;
    --accent-cyan: #06b6d4;
    --accent-green: #10b981;
    --accent-amber: #f59e0b;
    --accent-red: #ef4444;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

.main {
    background-color: var(--bg-primary) !important;
    padding: 0 !important;
}

.block-container {
    padding: 2rem 3rem !important;
    max-width: 1400px !important;
}

/* Header */
.cynthera-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border: 1px solid rgba(139, 92, 246, 0.3);
    border-radius: 16px;
    padding: 2rem 3rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}

.cynthera-header::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(ellipse at center, rgba(139, 92, 246, 0.08) 0%, transparent 70%);
    pointer-events: none;
}

.cynthera-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6, #06b6d4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
    line-height: 1.2;
}

.cynthera-subtitle {
    color: var(--text-secondary);
    font-size: 1rem;
    margin-top: 0.5rem;
    font-weight: 400;
}

/* Score Cards */
.score-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    text-align: center;
    transition: all 0.2s ease;
    height: 100%;
}

.score-card:hover {
    border-color: var(--accent-blue);
    box-shadow: 0 0 20px rgba(59, 130, 246, 0.1);
}

.score-value {
    font-size: 2.5rem;
    font-weight: 700;
    font-family: 'Space Grotesk', sans-serif;
}

.score-label {
    font-size: 0.85rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 0.25rem;
}

.score-level {
    font-size: 0.75rem;
    font-weight: 600;
    margin-top: 0.5rem;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    display: inline-block;
}

/* Recommendation Badge */
.rec-badge {
    padding: 0.75rem 2rem;
    border-radius: 50px;
    font-size: 1.1rem;
    font-weight: 700;
    display: inline-block;
    letter-spacing: 0.05em;
    font-family: 'Space Grotesk', sans-serif;
}

.rec-promising {
    background: linear-gradient(135deg, #065f46, #10b981);
    border: 1px solid #10b981;
    color: white;
}

.rec-uncertain {
    background: linear-gradient(135deg, #78350f, #f59e0b);
    border: 1px solid #f59e0b;
    color: white;
}

.rec-not-recommended {
    background: linear-gradient(135deg, #7f1d1d, #ef4444);
    border: 1px solid #ef4444;
    color: white;
}

/* Panels */
.info-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

.info-panel-title {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 1rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 1rem;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label {
    color: var(--text-secondary) !important;
}

/* Streamlit widget overrides */
.stTextInput input, .stSelectbox select {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
}

.stButton button {
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple)) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.5rem 2rem !important;
    transition: all 0.2s ease !important;
}

.stButton button:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}

/* Dividers */
hr {
    border-color: var(--border) !important;
    margin: 1.5rem 0 !important;
}

/* Tables */
.stDataFrame {
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

/* Progress bars */
.stProgress > div > div > div {
    background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple)) !important;
}

/* Expander */
.streamlit-expanderHeader {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
}

/* Alerts */
.stAlert {
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)


def render_header() -> None:
    """Render the CYNTHERA header banner."""
    st.markdown("""
    <div class="cynthera-header">
        <div class="cynthera-title">🧬 CYNTHERA</div>
        <div class="cynthera-subtitle">
            Contradiction-Aware Mechanistic Reasoning for Explainable Drug Repurposing
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_score_card(
    label: str,
    score: float,
    level: str,
    color: str,
    icon: str,
) -> None:
    """Render a score card widget.

    Args:
        label: Card label (e.g., 'Support Score').
        score: Float score value [0.0, 1.0].
        level: Categorical level string.
        color: Hex color for the score value.
        icon: Emoji icon.
    """
    level_colors = {
        "HIGH": "#10b981", "MEDIUM": "#f59e0b",
        "LOW": "#ef4444", "NONE": "#64748b",
    }
    badge_color = level_colors.get(level.upper(), "#64748b")
    st.markdown(f"""
    <div class="score-card">
        <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">{icon}</div>
        <div class="score-value" style="color: {color};">{score:.3f}</div>
        <div class="score-label">{label}</div>
        <div class="score-level" style="background: {badge_color}22; color: {badge_color}; border: 1px solid {badge_color}55;">
            {level}
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_recommendation_badge(status: str) -> None:
    """Render the recommendation status badge.

    Args:
        status: 'PROMISING', 'UNCERTAIN', or 'NOT_RECOMMENDED'.
    """
    config = {
        "PROMISING": ("🟢", "rec-promising", "PROMISING — Proceed with Validation"),
        "UNCERTAIN": ("🟡", "rec-uncertain", "UNCERTAIN — Additional Evidence Needed"),
        "NOT_RECOMMENDED": ("🔴", "rec-not-recommended", "NOT RECOMMENDED"),
    }
    icon, css_class, label = config.get(status, ("⚪", "rec-uncertain", status))
    st.markdown(f"""
    <div style="text-align: center; padding: 1.5rem 0;">
        <div class="rec-badge {css_class}">
            {icon} &nbsp; {label}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Session State Initialization
# ─────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "history" not in st.session_state:
    st.session_state.history = []
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "evaluate"

# ─────────────────────────────────────────────
# Sidebar Navigation
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🧬 CYNTHERA")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["🔬 Evaluate", "📊 Results", "📋 Audit Report", "🕐 History"],
        index=0,
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.markdown("**Configuration**")
    policy = st.selectbox(
        "Retrieval Policy",
        ["STANDARD", "FAST", "COMPREHENSIVE"],
        help="Controls depth and scope of data retrieval",
    )
    st.markdown("---")
    st.markdown(
        "<small style='color: #64748b;'>CYNTHERA v1.0 | Rule Set v1.0</small>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
# Render Header
# ─────────────────────────────────────────────
render_header()

# ─────────────────────────────────────────────
# Page: Evaluate
# ─────────────────────────────────────────────
if page == "🔬 Evaluate":
    st.markdown("## Hypothesis Evaluation")
    st.markdown(
        "<p style='color: #94a3b8;'>Enter a drug-disease pair to evaluate repurposing potential using multi-source biomedical evidence.</p>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        drug_name = st.text_input(
            "💊 Drug Name",
            placeholder="e.g., Sildenafil, Metformin, Aspirin",
            help="Enter the common name of the drug to evaluate",
        )
    with col2:
        disease_name = st.text_input(
            "🏥 Disease Name",
            placeholder="e.g., Pulmonary Arterial Hypertension, Type 2 Diabetes",
            help="Enter the disease name to evaluate as the target indication",
        )

    col_btn, col_ex = st.columns([1, 3])
    with col_btn:
        run_button = st.button("🚀 Run Evaluation", use_container_width=True)
    with col_ex:
        st.markdown(
            "<div style='padding: 0.6rem 0; color: #64748b; font-size: 0.9rem;'>"
            "⚡ Try: <b>Sildenafil</b> → <b>Pulmonary Arterial Hypertension</b>"
            "</div>",
            unsafe_allow_html=True,
        )

    if run_button:
        if not drug_name or not disease_name:
            st.error("⚠️ Please enter both a drug name and a disease name.")
        else:
            with st.spinner(f"🔬 Evaluating **{drug_name}** → **{disease_name}**..."):
                try:
                    # Import and run the evaluation
                    from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
                    from backend.core.enums.retrieval_policy import RetrievalPolicy

                    policy_map = {
                        "STANDARD": RetrievalPolicy.STANDARD,
                        "FAST": RetrievalPolicy.FAST,
                        "COMPREHENSIVE": RetrievalPolicy.COMPREHENSIVE,
                    }

                    orchestrator = MasterOrchestrator(
                        llm_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
                    )

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    hypothesis, pkg, result = loop.run_until_complete(
                        orchestrator.evaluate(
                            drug_name,
                            disease_name,
                            policy=policy_map.get(policy, RetrievalPolicy.STANDARD),
                        )
                    )
                    loop.close()

                    st.session_state.results = {
                        "drug": drug_name,
                        "disease": disease_name,
                        "hypothesis": hypothesis,
                        "package": pkg,
                        "result": result,
                    }
                    st.session_state.history.append({
                        "drug": drug_name,
                        "disease": disease_name,
                        "recommendation": result.recommendation_status.value,
                        "ss": result.support_assessment.score,
                        "ms": result.mechanistic_assessment.score,
                        "rs": result.risk_assessment.score,
                    })
                    st.success("✅ Evaluation complete! Navigate to **Results** to view the full report.")
                    st.rerun()

                except Exception as exc:
                    st.error(f"❌ Evaluation failed: {exc}")
                    st.exception(exc)

    # Example cards
    st.markdown("---")
    st.markdown("### 💡 Example Queries")
    ex_cols = st.columns(3)
    examples = [
        ("Sildenafil", "Pulmonary Arterial Hypertension", "Known repurposing success (PAH)"),
        ("Metformin", "Type 2 Diabetes", "Well-established primary indication"),
        ("Aspirin", "Pancreatic Cancer", "Negative control — not recommended"),
    ]
    for i, (drug, disease, desc) in enumerate(examples):
        with ex_cols[i]:
            st.markdown(f"""
            <div class="info-panel" style="cursor: pointer;">
                <div style="font-weight: 600; margin-bottom: 0.25rem;">{drug}</div>
                <div style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 0.5rem;">→ {disease}</div>
                <div style="color: #64748b; font-size: 0.75rem;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Page: Results
# ─────────────────────────────────────────────
elif page == "📊 Results":
    if not st.session_state.results:
        st.info("No evaluation results yet. Go to **🔬 Evaluate** to run an analysis.")
    else:
        r = st.session_state.results
        result = r["result"]
        pkg = r["package"]

        st.markdown(f"## Results: {r['drug']} → {r['disease']}")

        # Recommendation badge
        render_recommendation_badge(result.recommendation_status.value)

        # Score cards
        st.markdown("### 📐 Three-Dimensional Scores")
        col1, col2, col3 = st.columns(3)
        with col1:
            render_score_card(
                "Support Score (SS)",
                result.support_assessment.score,
                result.support_assessment.level,
                "#3b82f6",
                "📚",
            )
        with col2:
            render_score_card(
                "Mechanistic Score (MS)",
                result.mechanistic_assessment.score,
                result.mechanistic_assessment.level,
                "#8b5cf6",
                "🔗",
            )
        with col3:
            render_score_card(
                "Risk Score (RS)",
                result.risk_assessment.score,
                result.risk_assessment.level,
                "#ef4444",
                "⚠️",
            )

        st.markdown("---")

        # Evidence summary
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("### 📊 Evidence Summary")
            st.markdown(f"""
            <div class="info-panel">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                    <div><div style="font-size: 1.8rem; font-weight: 700; color: #3b82f6;">{len(pkg.evidence_records)}</div><div style="color: #94a3b8; font-size: 0.8rem;">Evidence Records</div></div>
                    <div><div style="font-size: 1.8rem; font-weight: 700; color: #8b5cf6;">{len(pkg.targets)}</div><div style="color: #94a3b8; font-size: 0.8rem;">Drug Targets</div></div>
                    <div><div style="font-size: 1.8rem; font-weight: 700; color: #06b6d4;">{len(pkg.clinical_trials)}</div><div style="color: #94a3b8; font-size: 0.8rem;">Clinical Trials</div></div>
                    <div><div style="font-size: 1.8rem; font-weight: 700; color: #10b981;">{len(result.contradictions)}</div><div style="color: #94a3b8; font-size: 0.8rem;">Contradictions</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with col_b:
            st.markdown("### 🌐 Data Sources")
            st.markdown(f"""
            <div class="info-panel">
                <div style="margin-bottom: 0.5rem;"><span style="color: #10b981;">✓</span> <b>Queried:</b> {', '.join(pkg.sources_queried) or 'None'}</div>
                <div><span style="color: #ef4444;">✗</span> <b>Failed:</b> {', '.join(pkg.sources_failed) or 'None'}</div>
                <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #2a3a55;">
                    <b>Retrieval Confidence:</b>
                    <span style="color: {'#10b981' if pkg.retrieval_confidence == 'HIGH' else '#f59e0b' if pkg.retrieval_confidence == 'MEDIUM' else '#ef4444'};">
                        {pkg.retrieval_confidence}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Mechanistic chain
        if result.mechanistic_assessment.mechanistic_chain:
            st.markdown("### 🔗 Mechanistic Chain")
            chain = result.mechanistic_assessment.mechanistic_chain
            chain_html = " → ".join(
                f'<span style="background: #1a2235; border: 1px solid #2a3a55; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.85rem;">{node}</span>'
                for node in chain
            )
            st.markdown(
                f'<div class="info-panel"><div style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;">{chain_html}</div></div>',
                unsafe_allow_html=True,
            )

        # Contradictions
        if result.contradictions:
            st.markdown("### ⚔️ Contradictions Detected")
            for c in result.contradictions[:5]:
                st.markdown(f"""
                <div class="info-panel" style="border-left: 3px solid #ef4444;">
                    <div style="font-weight: 600; color: #ef4444;">Score: {c.contradiction_score:.3f}</div>
                    <div style="color: #94a3b8; margin-top: 0.25rem;">{c.explanation}</div>
                </div>
                """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Page: Audit Report
# ─────────────────────────────────────────────
elif page == "📋 Audit Report":
    if not st.session_state.results:
        st.info("No evaluation results yet. Go to **🔬 Evaluate** to run an analysis.")
    else:
        r = st.session_state.results
        result = r["result"]
        audit = result.audit_report

        st.markdown(f"## Scientific Audit Report")
        st.markdown(f"**Drug:** {r['drug']} | **Disease:** {r['disease']}")
        st.markdown("---")

        st.markdown("### 📝 Executive Summary")
        st.markdown(f"""
        <div class="info-panel">
            <p style="line-height: 1.7; color: #cbd5e1;">{audit.summary}</p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### ✅ Key Supporting Claims")
            if audit.key_supporting_claim_ids:
                for cid in audit.key_supporting_claim_ids[:5]:
                    st.markdown(f"• `{cid[:8]}...`")
            else:
                st.markdown("_No supporting claims recorded._")

        with col2:
            st.markdown("### ❌ Key Contradicting Claims")
            if audit.key_contradicting_claim_ids:
                for cid in audit.key_contradicting_claim_ids[:5]:
                    st.markdown(f"• `{cid[:8]}...`")
            else:
                st.markdown("_No contradicting claims recorded._")

        if audit.data_gaps:
            st.markdown("### 🔍 Data Gaps Identified")
            for gap in audit.data_gaps:
                st.warning(f"⚠️ {gap}")

        with st.expander("📜 Recommendation Rule Trace"):
            st.markdown(f"""
            ```
            {audit.recommendation_rationale}
            ```
            """)

        with st.expander("📈 Confidence Narrative"):
            st.markdown(audit.confidence_narrative)

        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Rule Set Version", result.rule_set_version)
        with col_b:
            st.metric("Reasoning Duration", f"{result.reasoning_duration_ms:.0f} ms")
        with col_c:
            st.metric("Completed At", result.completed_at.strftime("%Y-%m-%d %H:%M UTC"))

# ─────────────────────────────────────────────
# Page: History
# ─────────────────────────────────────────────
elif page == "🕐 History":
    st.markdown("## Evaluation History")
    st.markdown("Past evaluations are loaded from the persistent SQLite database.")

    import pandas as pd
    from backend.storage.repository import StorageRepository

    _repo = StorageRepository(db_path="data/cynthera.db")
    evaluations = _repo.list_evaluations(limit=100)

    if not evaluations:
        st.info("No evaluations yet. Go to **🔬 Evaluate** to run your first analysis.")
    else:
        rows = []
        for ev in evaluations:
            rows.append({
                "Hypothesis ID": ev.get("hypothesis_id", "")[:12] + "...",
                "Drug": ev.get("drug_name", ""),
                "Disease": ev.get("disease_name", ""),
                "Recommendation": ev.get("recommendation", ""),
                "Support Score": round(float(ev.get("support_score", 0)), 3),
                "Mech. Score": round(float(ev.get("mechanistic_score", 0)), 3),
                "Risk Score": round(float(ev.get("risk_score", 0)), 3),
                "Retrieval Confidence": ev.get("retrieval_confidence", ""),
                "Completed At": ev.get("completed_at", ""),
            })
        df = pd.DataFrame(rows)

        def color_rec(val: str) -> str:
            colors = {
                "PROMISING": "color: #10b981; font-weight: 600",
                "UNCERTAIN": "color: #f59e0b; font-weight: 600",
                "NOT_RECOMMENDED": "color: #ef4444; font-weight: 600",
            }
            return colors.get(val, "")

        styled = df.style.applymap(color_rec, subset=["Recommendation"])
        st.dataframe(styled, use_container_width=True)

        st.caption(f"Showing {len(rows)} evaluation(s) from persistent storage.")

        col_dl, _ = st.columns([1, 3])
        with col_dl:
            csv = df.to_csv(index=False)
            st.download_button(
                "📥 Export CSV",
                data=csv,
                file_name="cynthera_history.csv",
                mime="text/csv",
            )
