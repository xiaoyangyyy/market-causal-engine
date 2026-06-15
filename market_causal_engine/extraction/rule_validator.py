"""Schema and policy validation for proposed causal claims."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from market_causal_engine.evidence import MarketAtom
from market_causal_engine.lookahead import LookAheadPolicy

VALID_MECHANISMS = frozenset(
    {"fundamental", "sentiment", "liquidity", "macro", "regulatory", "trust", "intervention"}
)

REQUIRED_FIELDS = ("cause", "effect", "mechanism", "severity", "evidence_span", "source_id", "published_at")

DOMAIN_MECHANISMS: dict[str, frozenset[str]] = {
    "earnings": frozenset({"fundamental", "sentiment", "liquidity", "macro"}),
    "short_report": frozenset({"trust", "sentiment", "liquidity", "regulatory", "fundamental"}),
    "macro": frozenset({"macro", "liquidity", "sentiment", "fundamental"}),
}


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "errors": self.errors, "warnings": self.warnings}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_claim_schema(claim: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    for key in REQUIRED_FIELDS:
        if key not in claim:
            errors.append(f"missing_field:{key}")

    cause = str(claim.get("cause", "")).strip()
    effect = str(claim.get("effect", "")).strip()
    if cause and len(cause) < 3:
        errors.append("cause_too_short")
    if effect and len(effect) < 3:
        errors.append("effect_too_short")
    if cause and len(cause) > 200:
        errors.append("cause_too_long")
    if effect and len(effect) > 200:
        errors.append("effect_too_long")

    mechanism = str(claim.get("mechanism", "")).strip().lower()
    if mechanism and mechanism not in VALID_MECHANISMS:
        errors.append(f"invalid_mechanism:{mechanism}")

    severity = claim.get("severity")
    if severity is not None:
        if not _is_number(severity):
            errors.append("severity_not_numeric")
        elif not 0.0 <= float(severity) <= 1.0:
            errors.append("severity_out_of_range")

    span = str(claim.get("evidence_span", "")).strip()
    if span and len(span) < 8:
        errors.append("evidence_span_too_short")

    published_at = claim.get("published_at")
    if published_at is not None and not _is_number(published_at):
        errors.append("published_at_not_numeric")
    elif published_at is not None and float(published_at) < 0:
        errors.append("published_at_negative")

    return ValidationResult(passed=not errors, errors=errors)


def validate_claim_against_atom(claim: dict[str, Any], atom: MarketAtom) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    source_id = str(claim.get("source_id", ""))
    if source_id and source_id != atom.atom_id:
        errors.append("source_id_mismatch")

    published_at = claim.get("published_at")
    if published_at is not None and int(published_at) != atom.effective_time():
        errors.append("published_at_mismatch")

    span = str(claim.get("evidence_span", "")).strip()
    if span and span.lower() not in atom.text.lower():
        errors.append("evidence_span_not_in_atom_text")

    if atom.metadata.get("uses_future_price"):
        errors.append("atom_uses_future_price")

    forbidden = {"post_hoc_analysis", "analyst_retrospective"}
    source_class = str(atom.metadata.get("source_class", ""))
    if source_class in forbidden:
        errors.append(f"forbidden_source_class:{source_class}")

    return ValidationResult(passed=not errors, errors=errors, warnings=warnings)


def validate_domain_mechanism(claim: dict[str, Any], domain: str) -> ValidationResult:
    allowed = DOMAIN_MECHANISMS.get(domain)
    if not allowed:
        return ValidationResult(passed=True)
    mechanism = str(claim.get("mechanism", "")).strip().lower()
    if mechanism and mechanism not in allowed:
        return ValidationResult(
            passed=False,
            errors=[f"mechanism_not_allowed_for_domain:{mechanism}:{domain}"],
        )
    return ValidationResult(passed=True)


def validate_claim_timing(
    claim: dict[str, Any],
    *,
    as_of: int,
    policy: LookAheadPolicy | None = None,
) -> ValidationResult:
    policy = policy or LookAheadPolicy(strict=True)
    published_at = claim.get("published_at")
    if published_at is None:
        return ValidationResult(passed=False, errors=["missing_published_at"])
    if policy.strict and int(published_at) > as_of:
        return ValidationResult(passed=False, errors=["lookahead_violation"])
    return ValidationResult(passed=True)


def validate_claim(
    claim: dict[str, Any],
    atom: MarketAtom,
    *,
    domain: str = "earnings",
    as_of: int | None = None,
    policy: LookAheadPolicy | None = None,
) -> ValidationResult:
    results = [
        validate_claim_schema(claim),
        validate_claim_against_atom(claim, atom),
        validate_domain_mechanism(claim, domain),
    ]
    if as_of is not None:
        results.append(validate_claim_timing(claim, as_of=as_of, policy=policy))

    errors: list[str] = []
    warnings: list[str] = []
    for result in results:
        errors.extend(result.errors)
        warnings.extend(result.warnings)

    return ValidationResult(passed=not errors, errors=errors, warnings=warnings)


def normalize_claim(claim: dict[str, Any], atom: MarketAtom) -> dict[str, Any]:
    """Coerce LLM output into canonical claim shape."""
    out = dict(claim)
    out["cause"] = re.sub(r"\s+", " ", str(out.get("cause", "")).strip())
    out["effect"] = re.sub(r"\s+", " ", str(out.get("effect", "")).strip())
    out["mechanism"] = str(out.get("mechanism", "fundamental")).strip().lower()
    out["severity"] = round(float(out.get("severity", atom.metadata.get("severity", 0.7))), 3)
    out["evidence_span"] = str(out.get("evidence_span", "")).strip()
    out["source_id"] = str(out.get("source_id", atom.atom_id))
    out["published_at"] = int(out.get("published_at", atom.effective_time()))
    return out
