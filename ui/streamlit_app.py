"""
Streamlit web interface for the Cynthera drug repurposing system.
Provides an interactive UI for hypothesis generation and visualization.
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import json
from datetime import datetime
import plotly.graph_objects as go
from typing import Optional

from models.data_models import DrugInput, DiseaseInput, HypothesisReport
from orchestrator.orchestrator import MasterOrchestrator
from utils.logger import get_logger

logger = get_logger(__name__)

# Page configuration
st.set_page_config(
    page_title="Cynthera - Drug Repurposing AI",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #6366f1;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #94a3b8;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #1e293b;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #6366f1;
    }
    .evidence-item {
        background-color: #1e293b;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


def render_header():
    """Render the application header."""
    st.markdown('<div class="main-header">🧬 Cynthera</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Agentic AI for Mechanism-Grounded Drug Repurposing</div>',
        unsafe_allow_html=True
    )


def render_input_form():
    """Render the input form for drug and disease."""
    st.sidebar.header("📋 Input Parameters")
    
    # Drug input
    st.sidebar.subheader("Drug Information")
    drug_name = st.sidebar.text_input(
        "Drug Name",
        placeholder="e.g., Metformin",
        help="Enter the name of the drug to evaluate"
    )
    
    pubchem_cid = st.sidebar.text_input(
        "PubChem CID (Optional)",
        placeholder="e.g., 4091",
        help="PubChem Compound ID for more accurate results"
    )
    
    # Disease input
    st.sidebar.subheader("Disease Information")
    disease_name = st.sidebar.text_input(
        "Disease Name",
        placeholder="e.g., Alzheimer's disease",
        help="Enter the disease name to evaluate"
    )
    
    # Submit button
    submit = st.sidebar.button("🚀 Generate Hypothesis", type="primary", use_container_width=True)
    
    return drug_name, pubchem_cid, disease_name, submit


def render_confidence_gauge(confidence_value: float, title: str = "Overall Confidence"):
    """Render a confidence score gauge chart."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=confidence_value * 100,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title, 'font': {'size': 20}},
        number={'suffix': "%", 'font': {'size': 40}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1},
            'bar': {'color': "#6366f1"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 25], 'color': '#ef4444'},
                {'range': [25, 50], 'color': '#f59e0b'},
                {'range': [50, 75], 'color': '#eab308'},
                {'range': [75, 100], 'color': '#22c55e'}
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': confidence_value * 100
            }
        }
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'color': "white", 'family': "Arial"}
    )
    
    return fig


def render_report(report: HypothesisReport):
    """Render the hypothesis report."""
    
    # Executive Summary
    st.header("📊 Executive Summary")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Drug", report.drug)
    
    with col2:
        st.metric("Disease", report.disease)
    
    with col3:
        recommendation_emoji = {
            "promising": "✅",
            "uncertain": "⚠️",
            "not_recommended": "❌"
        }
        st.metric(
            "Recommendation",
            f"{recommendation_emoji.get(report.recommendation, '❓')} {report.recommendation.replace('_', ' ').title()}"
        )
    
    st.markdown("---")
    st.write(report.summary)
    
    # Confidence Score
    st.header("🎯 Confidence Assessment")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.plotly_chart(
            render_confidence_gauge(report.overall_confidence.value),
            use_container_width=True
        )
    
    with col2:
        st.subheader("Confidence Details")
        st.write(f"**Level:** {report.overall_confidence.level.value.upper()}")
        st.write(f"**Rationale:** {report.overall_confidence.rationale}")
        
        if report.processing_time_seconds:
            st.write(f"**Processing Time:** {report.processing_time_seconds:.2f} seconds")
    
    # Mechanisms of Action
    st.header("🔬 Mechanisms of Action")
    
    if report.moa_chains:
        for i, chain in enumerate(report.moa_chains, 1):
            with st.expander(f"MoA Chain {i}: {chain.mechanism_description}", expanded=True):
                st.write(f"**Confidence:** {chain.confidence.value:.2f} ({chain.confidence.level.value})")
                st.write(f"**Rationale:** {chain.confidence.rationale}")
                
                # Targets
                st.subheader("Drug Targets")
                for target in chain.targets:
                    st.write(f"- **{target.name}** ({target.target_type})")
                    if target.activity:
                        st.write(f"  - Activity: {target.activity}")
                
                # Pathways
                if chain.pathways:
                    st.subheader("Affected Pathways")
                    for pathway in chain.pathways:
                        st.write(f"- **{pathway.name}** ({pathway.database})")
                        if pathway.relevance_score:
                            st.write(f"  - Relevance: {pathway.relevance_score:.2f}")
    else:
        st.warning("No mechanisms of action identified")
    
    # Disease Relevance
    if report.disease_relevance:
        st.header("🎯 Disease Relevance")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Relevance Score", f"{report.disease_relevance.relevance_score:.2f}")
            st.metric("Directionality", report.disease_relevance.directionality.title())
        
        with col2:
            st.write("**Rationale:**")
            st.write(report.disease_relevance.rationale)
        
        if report.disease_relevance.pathway_overlap:
            st.subheader("Pathway Overlaps")
            for pathway in report.disease_relevance.pathway_overlap:
                st.write(f"- {pathway}")
    
    # Uncertainties & Conflicts
    st.header("⚠️ Uncertainties & Limitations")
    
    if report.uncertainties:
        for uncertainty in report.uncertainties:
            st.warning(uncertainty)
    else:
        st.success("No major uncertainties identified")
    
    if report.conflicts:
        st.subheader("Conflicting Evidence")
        for conflict in report.conflicts:
            st.error(f"**Conflict:** {conflict.claim_a} vs {conflict.claim_b}")
            st.write(f"Impact: {conflict.confidence_impact}")
    
    # Evidence
    st.header("📚 Supporting Evidence")
    
    if report.all_evidence:
        st.write(f"Total evidence items: {len(report.all_evidence)}")
        
        with st.expander("View All Evidence", expanded=False):
            for i, evidence in enumerate(report.all_evidence, 1):
                st.markdown(f"""
                <div class="evidence-item">
                    <strong>{i}. {evidence.database}</strong> ({evidence.source.value})<br>
                    {evidence.description}<br>
                    <small>Confidence: {evidence.confidence.value:.2f} | 
                    <a href="{evidence.url}" target="_blank">View Source</a></small>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No evidence available")
    
    # Next Steps
    st.header("🚀 Suggested Next Steps")
    
    if report.suggested_next_steps:
        for step in report.suggested_next_steps:
            priority_color = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢"
            }
            
            with st.expander(f"{priority_color.get(step.priority, '⚪')} {step.description}", expanded=False):
                st.write(f"**Type:** {step.step_type.title()}")
                st.write(f"**Priority:** {step.priority.upper()}")
                st.write(f"**Rationale:** {step.rationale}")
    else:
        st.info("No specific next steps recommended")
    
    # Export Options
    st.header("💾 Export Report")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Export as JSON
        json_data = report.model_dump_json(indent=2)
        st.download_button(
            label="📥 Download as JSON",
            data=json_data,
            file_name=f"cynthera_report_{report.drug}_{report.disease}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    
    with col2:
        # Export as text summary
        text_summary = f"""
CYNTHERA DRUG REPURPOSING REPORT
================================

Drug: {report.drug}
Disease: {report.disease}
Recommendation: {report.recommendation}
Overall Confidence: {report.overall_confidence.value:.2f} ({report.overall_confidence.level.value})

SUMMARY
-------
{report.summary}

CONFIDENCE RATIONALE
-------------------
{report.overall_confidence.rationale}

Generated: {report.generated_at}
        """
        
        st.download_button(
            label="📥 Download as Text",
            data=text_summary,
            file_name=f"cynthera_summary_{report.drug}_{report.disease}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )


def main():
    """Main application function."""
    render_header()
    
    # Sidebar inputs
    drug_name, pubchem_cid, disease_name, submit = render_input_form()
    
    # About section in sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### About Cynthera")
    st.sidebar.info(
        "Cynthera uses mechanism-driven reasoning to evaluate drug repurposing opportunities. "
        "It prioritizes biological plausibility over similarity matching and treats uncertainty "
        "as a first-class output."
    )
    
    # Main content area
    if submit:
        if not drug_name or not disease_name:
            st.error("⚠️ Please provide both drug name and disease name")
            return
        
        # Create input objects
        drug_input = DrugInput(
            name=drug_name,
            pubchem_cid=int(pubchem_cid) if pubchem_cid else None
        )
        
        disease_input = DiseaseInput(
            name=disease_name
        )
        
        # Process with orchestrator
        with st.spinner("🔬 Generating hypothesis... This may take a minute."):
            try:
                orchestrator = MasterOrchestrator()
                report = orchestrator.process(drug_input, disease_input)
                
                # Store in session state
                st.session_state['report'] = report
                
            except Exception as e:
                st.error(f"❌ Error generating hypothesis: {str(e)}")
                logger.error(f"Error in Streamlit app: {e}", exc_info=True)
                return
    
    # Display report if available
    if 'report' in st.session_state:
        render_report(st.session_state['report'])
    else:
        # Welcome message
        st.info(
            "👈 Enter a drug and disease in the sidebar to generate a mechanism-based "
            "hypothesis for drug repurposing."
        )
        
        st.subheader("Example Queries")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **Known Repurposing:**
            - Drug: Sildenafil
            - Disease: Pulmonary Hypertension
            """)
        
        with col2:
            st.markdown("""
            **Controversial Case:**
            - Drug: Metformin
            - Disease: Alzheimer's disease
            """)


if __name__ == "__main__":
    main()
