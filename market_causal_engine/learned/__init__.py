"""Learned components replacing rule-based heuristics."""

from market_causal_engine.learned.compiler_scorer import score_rule, select_best_rule
from market_causal_engine.learned.direction import infer_direction
from market_causal_engine.learned.magnitude import infer_magnitude, infer_return_pct
from market_causal_engine.learned.propagation import scale_patch
from market_causal_engine.learned.severity import estimate_severity
from market_causal_engine.learned.store import learned_available, load_learned_store, reload_learned_store

__all__ = [
    "infer_direction",
    "infer_magnitude",
    "infer_return_pct",
    "learned_available",
    "load_learned_store",
    "reload_learned_store",
    "scale_patch",
    "score_rule",
    "select_best_rule",
    "estimate_severity",
]
