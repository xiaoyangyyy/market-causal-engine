"""Untrusted proposers — proposals only, never direct state commit."""

from worldcup_causal_engine.proposers.llm import LLMProposer, proposal_from_dict

__all__ = ["LLMProposer", "proposal_from_dict"]
