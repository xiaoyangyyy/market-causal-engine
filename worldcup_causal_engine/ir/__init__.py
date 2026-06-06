"""Causal intermediate representation: contracts and proposals."""

from worldcup_causal_engine.ir.contract import Contract, CONTRACT_INDEX, get_contract
from worldcup_causal_engine.ir.proposal import Proposal, VerificationResult

__all__ = ["Contract", "CONTRACT_INDEX", "get_contract", "Proposal", "VerificationResult"]
