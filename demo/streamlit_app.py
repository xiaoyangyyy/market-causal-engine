"""Streamlit killer demo — NFLX 2022 Q1 earnings forensics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install demo extras: pip install -e '.[demo]'") from exc

from market_causal_engine.demo.killer_demo import DEFAULT_DEMO_CASE, build_killer_demo

st.set_page_config(page_title="Market Causal Engine Demo", layout="wide")
st.title("Event Intelligence — Killer Demo")
st.caption("Point-in-time forensics · not a trading signal")

case_id = st.sidebar.selectbox(
    "Case study",
    [DEFAULT_DEMO_CASE, "snap_2022q3_earnings", "meta_2022q4_earnings"],
    index=0,
)
as_of = st.sidebar.slider("As-of (minutes from release)", 30, 180, 120, 15)

with st.spinner("Running causal replay…"):
    demo = build_killer_demo(case_id, as_of=as_of)

hero = demo["hero"]
st.header(hero["title"])
st.write(hero["tagline"])

col1, col2, col3, col4 = st.columns(4)
obs = demo["counterfactual"]["observed"]
mod = demo["counterfactual"]["model"]
es = demo["counterfactual"].get("event_study") or demo["counterfactual"]["outcome_causal"].get("event_study") or {}
col1.metric("Observed AH", f"{obs.get('after_hours_return_pct', '—')}%")
col2.metric("CAR", f"{es.get('CAR_pct', '—')}%")
col3.metric("Sim direction", mod.get("simulated_direction", "—"))
col4.metric("Dominant channel", demo.get("dominant_channel") or "—")

left, right = st.columns(2)
with left:
    st.subheader("Mechanism path")
    for step in demo["mechanism_path"].get("narrative") or []:
        st.markdown(f"- {step}")
    st.subheader("Mechanism contributions")
    st.json(demo["mechanism_path"].get("mechanism_contributions") or {})

with right:
    st.subheader("Channel ablation (marginal CAR)")
    st.json(demo.get("channel_ablation") or {})
    st.subheader("Similar cases")
    st.dataframe(demo.get("benchmark_neighbors") or [], hide_index=True)

st.subheader("Evidence timeline (PIT admissible at as_of)")
for atom in demo.get("event_timeline") or []:
    with st.expander(f"t={atom['minute']} · {atom['source']} · {atom['atom_id']}"):
        st.caption(atom.get("published_time_iso", ""))
        st.write(atom.get("text", ""))
        st.code(atom.get("source_hash", ""), language=None)

st.subheader("Limitations")
for line in demo.get("limitations") or []:
    st.markdown(f"- {line}")

with st.expander("Raw demo JSON"):
    st.code(json.dumps(demo, indent=2, ensure_ascii=False), language="json")
