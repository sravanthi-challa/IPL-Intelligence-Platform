import os
import sys
import uuid
import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from typing import Dict, Any, List, Optional

# Setup paths to import backend and RAG modules directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from orchestrator import ConversationalOrchestrator
from metrics import CricketAnalytics

# Page configuration
st.set_page_config(
    page_title="IPL Intelligence | Conversational Cricket Analytics",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for modern executive cricket analytics UI
st.markdown("""
<style>
    /* Main Layout Aesthetics */
    .main-header {
        font-size: 2.1rem;
        font-weight: 800;
        letter-spacing: -0.025em;
        color: #0F172A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 1.25rem;
    }
    
    /* Route Badges */
    .route-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.25rem 0.75rem;
        font-size: 0.75rem;
        font-weight: 600;
        border-radius: 9999px;
        margin-bottom: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-sql { background-color: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; }
    .badge-rag { background-color: #EFF6FF; color: #1E40AF; border: 1px solid #BFDBFE; }
    .badge-hybrid { background-color: #FAF5FF; color: #6B21A8; border: 1px solid #E9D5FF; }
    .badge-clarify { background-color: #FEFCE8; color: #854D0E; border: 1px solid #FEF08A; }
    .badge-oos { background-color: #F8FAFC; color: #475569; border: 1px solid #E2E8F0; }

    /* KPI Summary Card Container */
    .kpi-container {
        display: flex;
        gap: 0.75rem;
        margin-bottom: 1rem;
    }
    .kpi-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 0.5rem;
        padding: 0.75rem 1rem;
        flex: 1;
    }
    .kpi-label {
        font-size: 0.7rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
    }
    .kpi-value {
        font-size: 1.25rem;
        color: #0F172A;
        font-weight: 700;
        margin-top: 0.15rem;
    }
    .kpi-subtext {
        font-size: 0.75rem;
        color: #10B981;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = ConversationalOrchestrator()

# Header
st.markdown('<div class="main-header">🏏 IPL INTELLIGENCE PLATFORM</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AI-Powered Conversational Cricket Analytics & Intelligence • 295,258 Deliveries • 1,241 Matches (2008–2024)</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("📊 Dataset Overview")
    st.markdown("""
    * **Coverage**: IPL 2008 – 2024
    * **Total Matches**: 1,241
    * **Total Deliveries**: 295,258
    * **Players Indexed**: 966
    * **Source**: Cricsheet Historical Match JSON
    """)

    st.markdown("---")
    st.header("💡 Suggested Questions")
    sample_queries = [
        "Who scored the most runs in 2016?",
        "Compare CSK and MI head-to-head",
        "Who took the most wickets in IPL history?",
        "Explain the cricket rules for tie and super overs",
        "Who has the highest death-overs strike rate?",
        "How did Kohli perform against CSK?"
    ]

    for q in sample_queries:
        if st.button(q, key=f"btn_{q}"):
            st.session_state.active_prompt = q

    st.markdown("---")
    if st.button("🗑️ Clear Conversation"):
        st.session_state.messages.clear()
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# ----------------------------------------------------
# VISUALIZATION & KPI HELPERS
# ----------------------------------------------------
def render_kpis(data: Any):
    """Renders executive KPI metric tiles for bowling, batting, or H2H data."""
    if not data:
        return

    try:
        # Head-to-Head KPIs
        if isinstance(data, dict) and "team1" in data and "team2" in data:
            col1, col2, col3 = st.columns(3)
            tot = data.get("total_matches", 0)
            t1 = data.get("team1")
            t2 = data.get("team2")
            w1 = data.get("team1_wins", 0)
            w2 = data.get("team2_wins", 0)
            leader = t1 if w1 > w2 else (t2 if w2 > w1 else "Tied")
            lead_wins = max(w1, w2)
            
            with col1:
                st.metric("Total Encounters", f"{tot} Matches")
            with col2:
                st.metric("Historical Leader", f"{leader}", f"{lead_wins} Wins")
            with col3:
                ties = data.get("ties_or_no_result", 0)
                st.metric("Ties / No Result", f"{ties} Matches")
            return

        # Leaderboard KPIs
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            df = pd.DataFrame(data)
            
            # Bowling Leaderboard KPIs
            if "wickets" in df.columns:
                top = df.iloc[0]
                pname = top.get("player_name", "N/A")
                wkts = top.get("wickets", 0)
                econ = top.get("economy_rate", 0.0)
                
                # Best economy among top 5
                best_econ_row = df.head(5).sort_values("economy_rate").iloc[0]
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🏆 Leading Bowler", f"{pname}", f"{wkts} Wickets")
                with col2:
                    st.metric("Top Bowler Economy", f"{econ:.2f} rpo", f"{top.get('overs_bowled', 0)} Overs")
                with col3:
                    st.metric("Best Economy (Top 5)", f"{best_econ_row.get('player_name')}", f"{best_econ_row.get('economy_rate'):.2f} rpo")

            # Batting Leaderboard KPIs
            elif "total_runs" in df.columns:
                top = df.iloc[0]
                pname = top.get("player_name") or top.get("batter_name") or "N/A"
                runs = top.get("total_runs", 0)
                sr = top.get("strike_rate", 0.0)
                sixes = top.get("sixes", 0)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🏆 Leading Run-Scorer", f"{pname}", f"{runs} Runs")
                with col2:
                    st.metric("Strike Rate", f"{sr:.1f}", f"{top.get('matches_batted', '')} Innings")
                with col3:
                    st.metric("Boundary Sixes", f"{sixes} Sixes", f"{top.get('fours', 0)} Fours")
    except Exception as e:
        pass

def render_visualization(data: Any):
    """Renders interactive Plotly visual charts."""
    if not data:
        return

    try:
        # Head-to-Head Donut Chart
        if isinstance(data, dict) and "team1" in data and "team2" in data:
            t1 = data.get("team1")
            t2 = data.get("team2")
            w1 = data.get("team1_wins", 0)
            w2 = data.get("team2_wins", 0)
            ties = data.get("ties_or_no_result", 0)

            fig = go.Figure(data=[go.Pie(
                labels=[t1, t2, "Ties/No Result"],
                values=[w1, w2, ties],
                hole=0.45,
                marker=dict(colors=["#1D4ED8", "#F59E0B", "#94A3B8"]),
                textinfo="label+percent+value",
                hoverinfo="label+value"
            )])
            fig.update_layout(
                title=f"<b>Head-to-Head Win Distribution: {t1} vs {t2}</b>",
                showlegend=True,
                height=350,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)

        # Leaderboard Visualizations
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            df = pd.DataFrame(data).head(10)

            # Wicket Takers Horizontal Bar Chart
            if "wickets" in df.columns and "player_name" in df.columns:
                df_sorted = df.sort_values("wickets", ascending=True)
                fig = px.bar(
                    df_sorted,
                    x="wickets",
                    y="player_name",
                    orientation="h",
                    text="wickets",
                    title="<b>Top Wicket Takers in IPL History</b>",
                    color="wickets",
                    color_continuous_scale="Tealgrn"
                )
                fig.update_layout(
                    xaxis_title="Total Wickets",
                    yaxis_title="",
                    height=380,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                fig.update_traces(textposition="outside")
                st.plotly_chart(fig, use_container_width=True)

            # Run Scorers Horizontal Bar Chart
            elif "total_runs" in df.columns:
                name_col = "player_name" if "player_name" in df.columns else "batter_name"
                if name_col in df.columns:
                    df_sorted = df.sort_values("total_runs", ascending=True)
                    fig = px.bar(
                        df_sorted,
                        x="total_runs",
                        y=name_col,
                        orientation="h",
                        text="total_runs",
                        title="<b>Top Run Scorers</b>",
                        color="total_runs",
                        color_continuous_scale="Blues"
                    )
                    fig.update_layout(
                        xaxis_title="Runs Scored",
                        yaxis_title="",
                        height=380,
                        margin=dict(l=20, r=20, t=40, b=20)
                    )
                    fig.update_traces(textposition="outside")
                    st.plotly_chart(fig, use_container_width=True)

            # Death Overs Strike Rate Bar Chart
            elif "phase_strike_rate" in df.columns and "player_name" in df.columns:
                df_sorted = df.sort_values("phase_strike_rate", ascending=True)
                fig = px.bar(
                    df_sorted,
                    x="phase_strike_rate",
                    y="player_name",
                    orientation="h",
                    text="phase_strike_rate",
                    title="<b>Highest Strike Rate in Death Overs (Overs 16–20)</b>",
                    color="phase_strike_rate",
                    color_continuous_scale="Oranges"
                )
                fig.update_layout(
                    xaxis_title="Strike Rate",
                    yaxis_title="",
                    height=380,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                fig.update_traces(textposition="outside")
                st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"Note on visualization: {e}")

# Helper to render route badge
def render_route_badge(route: str):
    if route == "SQL_ONLY":
        return '<span class="route-badge badge-sql">⚡ Route: SQL Analytics Engine (Verified Calculation)</span>'
    elif "RAG" in route:
        return '<span class="route-badge badge-rag">📖 Route: Hybrid Semantic Retrieval (RAG)</span>'
    elif route == "HYBRID":
        return '<span class="route-badge badge-hybrid">🔀 Route: Hybrid (Dual SQL + Semantic Retrieval)</span>'
    elif route == "CLARIFICATION":
        return '<span class="route-badge badge-clarify">❓ Route: Clarification Requested</span>'
    else:
        return '<span class="route-badge badge-oos">🚫 Route: Domain Boundary Refusal</span>'

# Render chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            route = msg.get("route", "")
            if route:
                st.markdown(render_route_badge(route), unsafe_allow_html=True)
            st.markdown(msg["content"])

            # Render SQL Metrics, Charts & Data Table
            if msg.get("sql_data"):
                data = msg["sql_data"]
                render_kpis(data)
                render_visualization(data)

                # Data Table with CSV Export
                if isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data)
                    st.markdown("##### 📋 Verified Database Records")
                    st.dataframe(df, use_container_width=True)
                    csv_bytes = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📥 Download Data as CSV",
                        data=csv_bytes,
                        file_name="ipl_analytics_export.csv",
                        mime="text/csv",
                        key=f"dl_{msg.get('msg_id', str(uuid.uuid4()))}"
                    )
                elif isinstance(data, dict):
                    st.json(data)

            # Render Retrieved Evidence Drawer
            sources = msg.get("sources", [])
            chunks = msg.get("retrieved_chunks", [])
            if sources or chunks:
                with st.expander(f"🔍 Inspect Retrieved Evidence & Provenance ({len(sources)} sources cited)"):
                    if sources:
                        st.markdown("**Cited Sources:**")
                        for s in sources:
                            st.markdown(f"- **{s.get('title')}** (`{s.get('doc_id')}`)")
                    if chunks:
                        st.markdown("**Retrieved Context Snippets:**")
                        for c in chunks:
                            score_info = f"(Score: {c.get('score')})" if c.get('score') is not None else ""
                            st.markdown(f"> **{c.get('title')}** {score_info}\n\n>{c.get('doc_id')}")
        else:
            st.markdown(msg["content"])

# User Input
prompt = st.chat_input("Ask a question about IPL history, teams, players, statistics, or matches...")

# Handle sample button triggers
if "active_prompt" in st.session_state and st.session_state.active_prompt:
    prompt = st.session_state.active_prompt
    st.session_state.active_prompt = None

if prompt:
    # Append user turn
    msg_id = str(uuid.uuid4())
    st.session_state.messages.append({"role": "user", "content": prompt, "msg_id": msg_id})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process via Conversational Orchestrator
    with st.chat_message("assistant"):
        with st.spinner("Analyzing cricket intelligence..."):
            response = st.session_state.orchestrator.chat(
                message=prompt,
                session_id=st.session_state.session_id
            )

            # Display route badge
            st.markdown(render_route_badge(response["route"]), unsafe_allow_html=True)
            st.markdown(response["answer"])

            # Render SQL Metrics, Charts & Data Table
            if response.get("sql_data"):
                data = response["sql_data"]
                render_kpis(data)
                render_visualization(data)

                # Data Table with CSV Export
                if isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data)
                    st.markdown("##### 📋 Verified Database Records")
                    st.dataframe(df, use_container_width=True)
                    csv_bytes = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📥 Download Data as CSV",
                        data=csv_bytes,
                        file_name="ipl_analytics_export.csv",
                        mime="text/csv",
                        key=f"dl_live_{msg_id}"
                    )
                elif isinstance(data, dict):
                    st.json(data)

            # Render Evidence Inspector
            sources = response.get("sources", [])
            chunks = response.get("retrieved_chunks", [])
            if sources or chunks:
                with st.expander(f"🔍 Inspect Retrieved Evidence & Provenance ({len(sources)} sources cited)"):
                    if sources:
                        st.markdown("**Cited Sources:**")
                        for s in sources:
                            st.markdown(f"- **{s.get('title')}** (`{s.get('doc_id')}`)")
                    if chunks:
                        st.markdown("**Retrieved Context Snippets:**")
                        for c in chunks:
                            score_info = f"(Score: {c.get('score')})" if c.get('score') is not None else ""
                            st.markdown(f"> **{c.get('title')}** {score_info}\n\n>{c.get('doc_id')}")

    # Append assistant turn to session state
    st.session_state.messages.append({
        "role": "assistant",
        "content": response["answer"],
        "route": response["route"],
        "sql_data": response.get("sql_data"),
        "sources": response.get("sources", []),
        "retrieved_chunks": response.get("retrieved_chunks", []),
        "msg_id": msg_id
    })
