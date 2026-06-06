"""LLM proposer: wraps model output as Proposal, kernel verifies before execution."""

from __future__ import annotations

import json
import os
from typing import Any

from worldcup_causal_engine.ir.proposal import Proposal, VerificationResult
from worldcup_causal_engine.kernel import Kernel
from worldcup_causal_engine.proposers.schema import build_proposal_prompt


def proposal_from_dict(
    data: dict[str, Any],
    *,
    proposer: str = "llm",
    default_time: int = 0,
    proposal_id: str | None = None,
) -> Proposal:
    return Proposal(
        id=proposal_id or data.get("id", data.get("proposal_id", "P-llm")),
        kind=data["kind"],
        time=int(data.get("time", default_time)),
        payload=dict(data.get("payload", {})),
        proposer=data.get("proposer", proposer),
        confidence=float(data.get("confidence", 1.0)),
        evidence_refs=list(data.get("evidence_refs", [])),
        priority=int(data.get("priority", 0)),
    )


def normalize_proposal_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize messy LLM JSON into proposal fields."""
    if "intervention" in data and "kind" not in data:
        data["kind"] = data["intervention"]
    if "minute" in data and "time" not in data:
        data["time"] = data["minute"]
    data.setdefault("priority", 0)
    data.setdefault("payload", {})
    data.setdefault("confidence", 0.8)
    if isinstance(data.get("payload"), str):
        data["payload"] = {"note": data["payload"]}
    return data


def _suggested_time(kind: str, context: dict[str, Any]) -> int:
    timing = context.get("intervention_timing", {})
    if kind in timing:
        return int(timing[kind])
    if kind == "platform_rumor_throttle":
        return 80
    for cp in context.get("best_cut_points", []):
        if cp.get("intervention") == kind:
            fork = cp.get("fork_point") or cp.get("before")
            if fork == "transit_delay":
                sched = context.get("event_schedule", {})
                return int(sched.get("transit_delay", 93)) + 3
            if fork in ("rumor_amplified", "offline_mood_shift"):
                return 88
    defaults = {
        "official_clarification": 88,
        "transit_reroute": 96,
        "platform_rumor_throttle": 80,
        "deploy_deescalation": 91,
        "separate_fan_flows": 93,
        "team_captain_message": 85,
    }
    return defaults.get(kind, 88)


def normalize_proposal_timing(raw: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Clamp transit_reroute to post-delay window (fixes same-minute t=93 race)."""
    out = dict(raw)
    if out.get("kind") != "transit_reroute":
        return out
    sched = context.get("event_schedule", {})
    timing = context.get("intervention_timing", {})
    td = sched.get("transit_delay")
    optimal = timing.get("transit_reroute")
    if td is None or optimal is None:
        return out
    proposed = int(out.get("time", optimal))
    if proposed <= td:
        out["time"] = optimal
        out["timing_adjusted_from"] = proposed
    return out


def _risk_improved(
    actual: dict[str, float],
    baseline: dict[str, float],
    *,
    min_delta: float = 0.05,
) -> bool:
    for key in ("verbal_conflict", "panic", "scuffle", "riot"):
        if actual.get(key, 0.0) < baseline.get(key, 0.0) - min_delta:
            return True
    return False


def _default_payload(kind: str, scenario: dict[str, Any]) -> dict[str, Any]:
    if kind == "official_clarification":
        return {"topic": "controversial_call", "credibility": 0.7}
    if kind == "transit_reroute":
        return {"capacity_delta": 200, "zone": "stadium_exit"}
    if kind == "deploy_deescalation":
        return {"target_zone": "fan_zone_A", "team_count": 15}
    if kind == "platform_rumor_throttle":
        return {"strength": 0.8, "scope": "viral_clip"}
    if kind == "separate_fan_flows":
        return {"zone": "stadium_perimeter"}
    if kind == "team_captain_message":
        return {"tone": "calm", "audience": "fans"}
    return {}


def _adaptive_mock_proposal(
    scenario: dict[str, Any],
    context: dict[str, Any],
    attempt: int,
    rejections: list[dict[str, Any]],
    *,
    mock_kind: str | None,
    mock_time: int,
    checkpoint: int,
) -> dict[str, Any]:
    """Scenario-aware mock that simulates API retry behaviour in tests."""
    sid = scenario.get("scenario_id", "")
    recommended = context.get("recommended_interventions", [])
    last = rejections[-1] if rejections else {}
    reason = last.get("reason_code", "")

    if attempt == 0 and mock_kind:
        return {
            "kind": mock_kind,
            "time": mock_time,
            "priority": 0,
            "payload": _default_payload(mock_kind, scenario),
            "confidence": 0.9,
            "reasoning": "mock proposer first attempt",
            "source": "mock",
        }

    kind = recommended[0] if recommended else "official_clarification"
    time = 88

    if reason == "pre_condition" or "rumor_volume" in str(last.get("detail", "")):
        kind = "official_clarification"
        time = 88
    elif reason == "resource_shortage":
        if "transit_reroute" in recommended:
            kind = "transit_reroute"
        else:
            kind = "deploy_deescalation"
        time = _suggested_time(kind, context)
    elif reason == "ineffective_intervention":
        last_kind = last.get("kind", "")
        if last_kind == "transit_reroute" or "transit_reroute" in recommended:
            kind = "transit_reroute"
            time = _suggested_time("transit_reroute", context)
        elif "platform_rumor_throttle" in recommended:
            kind = "platform_rumor_throttle"
            time = _suggested_time(kind, context)
        elif recommended:
            kind = recommended[0]
            time = _suggested_time(kind, context)
    elif reason == "proposal_too_late":
        kind = recommended[0] if recommended else "official_clarification"
        time = max(checkpoint + 5, _suggested_time(kind, context))

    if "S4" in sid and (attempt >= 1 or reason == "ineffective_intervention"):
        kind = "platform_rumor_throttle"
        time = _suggested_time(kind, context)
        time = _suggested_time("platform_rumor_throttle", context)
        return {
            "kind": kind,
            "time": time,
            "priority": 0,
            "payload": {"strength": 0.85, "scope": "misleading_clip"},
            "confidence": 0.92,
            "reasoning": "mock retry: throttle misinfo spread per engine hint",
            "source": "mock",
        }

    if "S1" in sid and attempt >= 1:
        kind = "official_clarification"
        time = _suggested_time(kind, context)

    if kind == "transit_reroute":
        time = _suggested_time("transit_reroute", context)

    if "S5" in sid and attempt == 0 and mock_kind == "transit_reroute":
        time = mock_time

    return {
        "kind": kind,
        "time": time,
        "priority": 0,
        "payload": _default_payload(kind, scenario),
        "confidence": 0.88,
        "reasoning": f"mock retry attempt {attempt + 1} after {reason or 'initial'}",
        "source": "mock",
    }


class LLMProposer:
    """Submit proposals to kernel; never calls commit/acquire directly."""

    def __init__(self, proposer_id: str = "llm"):
        self.proposer_id = proposer_id
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"P-{self.proposer_id}-{self._counter}"

    def from_intervention_json(self, raw: dict[str, Any]) -> Proposal:
        return Proposal(
            id=self._next_id(),
            kind=raw["kind"],
            time=int(raw["time"]),
            payload=dict(raw.get("payload", {})),
            proposer=self.proposer_id,
            priority=int(raw.get("priority", 0)),
        )

    def propose(self, kernel: Kernel, proposal: Proposal) -> VerificationResult:
        return kernel.propose(proposal)

    def propose_kind(
        self,
        kernel: Kernel,
        kind: str,
        *,
        time: int,
        payload: dict[str, Any] | None = None,
    ) -> VerificationResult:
        return self.propose(
            kernel,
            Proposal(
                id=self._next_id(),
                kind=kind,
                time=time,
                payload=dict(payload or {}),
                proposer=self.proposer_id,
                priority=0,
            ),
        )

    def build_prompt(
        self,
        scenario: dict[str, Any],
        kernel: Kernel,
        context: dict[str, Any] | None = None,
        rejections: list[dict[str, Any]] | None = None,
    ) -> str:
        ctx = context or {"checkpoint_minute": 55, "baseline_w0": {}, "best_cut_points": []}
        return build_proposal_prompt(scenario, kernel, ctx, rejections=rejections)

    @staticmethod
    def parse_llm_json(text: str) -> dict[str, Any]:
        """Best-effort parse of LLM JSON (may be wrapped in markdown)."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return normalize_proposal_dict(json.loads(text))

    def call_api(
        self,
        prompt: str,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> dict[str, Any]:
        import urllib.request

        api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ZHISUAN_API_KEY")
        base = base_url or os.environ.get("OPENAI_BASE_URL") or "https://ai.azya.top/v1"
        model = model or os.environ.get("OPENAI_MODEL") or "qwen3.5"

        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "Respond with valid JSON only. No markdown fences."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{base.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"].strip()
        parsed = self.parse_llm_json(content)
        parsed["source"] = "api"
        return parsed

    def propose_with_retries(
        self,
        kernel: Kernel,
        scenario: dict[str, Any],
        context: dict[str, Any],
        *,
        use_api: bool = True,
        max_attempts: int = 3,
        mock_kind: str | None = None,
        mock_time: int = 87,
        **api_kwargs: Any,
    ) -> tuple[Proposal | None, VerificationResult | None, list[dict[str, Any]]]:
        """Multi-round propose loop with VM feedback until accepted or max attempts."""
        rejections: list[dict[str, Any]] = []
        attempts_log: list[dict[str, Any]] = []
        checkpoint = int(context.get("checkpoint_minute", 55))

        for attempt in range(max_attempts):
            prompt = self.build_prompt(scenario, kernel, context, rejections=rejections)

            if use_api and (
                api_kwargs.get("api_key")
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("ZHISUAN_API_KEY")
            ):
                raw = self.call_api(prompt, **api_kwargs)
            else:
                raw = _adaptive_mock_proposal(
                    scenario,
                    context,
                    attempt,
                    rejections,
                    mock_kind=mock_kind,
                    mock_time=mock_time,
                    checkpoint=checkpoint,
                )

            raw = normalize_proposal_timing(raw, context)
            proposal = proposal_from_dict(
                raw,
                proposer=self.proposer_id,
                proposal_id=self._next_id(),
            )
            vr = kernel._verify_proposal_at_time(proposal)

            attempt_record = {
                "attempt": attempt + 1,
                "llm_raw": raw,
                "llm_proposal": proposal.to_dict(),
                "proposal_verification": vr.to_dict(),
            }

            if vr.accepted:
                baseline_risk = context.get("baseline_w0", {}).get("final_risk", {})
                sim = kernel.clone(for_simulation=True)
                sim.propose(proposal)
                sim.run(until=120)
                projected = sim.to_result(
                    scenario_id=scenario.get("scenario_id", ""),
                    world_id="proposal_sim",
                )
                attempt_record["projected_final_risk"] = projected.get("final_risk", {})
                if baseline_risk and not _risk_improved(
                    projected.get("final_risk", {}), baseline_risk
                ):
                    vr_ineff = VerificationResult(
                        proposal_id=proposal.id,
                        kind=proposal.kind,
                        accepted=False,
                        reason_code="ineffective_intervention",
                        detail=(
                            "accepted_but_no_risk_reduction_vs_w0:"
                            f"projected={projected.get('final_risk')}"
                        ),
                    )
                    attempt_record["proposal_verification"] = vr_ineff.to_dict()
                    attempts_log.append(attempt_record)
                    rejections.append({
                        "kind": proposal.kind,
                        "time": proposal.time,
                        "reason_code": "ineffective_intervention",
                        "detail": vr_ineff.detail,
                    })
                    continue

                exec_vr = self.propose(kernel, proposal)
                attempt_record["proposal_verification"] = exec_vr.to_dict()
                attempts_log.append(attempt_record)
                return proposal, exec_vr, attempts_log

            attempts_log.append(attempt_record)
            rejections.append({
                "kind": proposal.kind,
                "time": proposal.time,
                "reason_code": vr.reason_code,
                "detail": vr.detail,
                "failed_pre": vr.failed_pre,
                "missing_resources": vr.missing_resources,
            })

        return None, None, attempts_log

    def propose_via_api(
        self,
        kernel: Kernel,
        scenario: dict[str, Any],
        *,
        use_api: bool = True,
        context: dict[str, Any] | None = None,
        max_attempts: int = 3,
        mock_kind: str | None = None,
        mock_time: int = 87,
        **api_kwargs: Any,
    ) -> tuple[Proposal, VerificationResult, dict[str, Any], list[dict[str, Any]]]:
        """Backward-compatible wrapper; uses multi-round internally."""
        ctx = context or {"checkpoint_minute": 55, "baseline_w0": {}, "best_cut_points": []}
        proposal, vr, attempts = self.propose_with_retries(
            kernel,
            scenario,
            ctx,
            use_api=use_api,
            max_attempts=max_attempts,
            mock_kind=mock_kind,
            mock_time=mock_time,
            **api_kwargs,
        )
        if proposal is None or vr is None:
            last = attempts[-1]
            proposal = proposal_from_dict(
                last["llm_proposal"],
                proposer=self.proposer_id,
            )
            vd = last["proposal_verification"]
            vr = VerificationResult(
                proposal_id=vd["proposal_id"],
                kind=vd["kind"],
                accepted=vd["accepted"],
                reason_code=vd["reason_code"],
                detail=vd.get("detail", ""),
                missing_flags=vd.get("missing_flags", []),
                missing_resources=vd.get("missing_resources", {}),
                failed_pre=vd.get("failed_pre", []),
            )
            raw = dict(last["llm_raw"])
            raw["all_attempts_exhausted"] = True
            return proposal, vr, raw, attempts

        raw = dict(attempts[-1]["llm_raw"])
        raw["attempts_count"] = len(attempts)
        return proposal, vr, raw, attempts

