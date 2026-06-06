"""Proposal-Verification: untrusted proposals must pass contract checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from market_causal_engine.ir.contract import Contract, get_contract
from market_causal_engine.ir.proposal import Proposal, VerificationResult
from market_causal_engine.registry import get_handler, get_spec

if TYPE_CHECKING:
    from market_causal_engine.kernel import Event, Kernel


class MechanismVerifier:
    """Verify proposals and events against mechanism contracts."""

    def __init__(self, use_contracts: bool = True, use_flags: bool = True, use_resources: bool = True):
        self.use_contracts = use_contracts
        self.use_flags = use_flags
        self.use_resources = use_resources

    def verify_proposal(self, kernel: Kernel, proposal: Proposal) -> VerificationResult:
        return self._verify(
            kernel,
            kind=proposal.kind,
            proposal_id=proposal.id,
            resource_amounts=self._contract_resources(proposal.kind),
        )

    def verify_event(self, kernel: Kernel, event: Event) -> VerificationResult:
        return self._verify(
            kernel,
            kind=event.kind,
            proposal_id=event.id,
            resource_amounts=self._contract_resources(event.kind),
        )

    def _contract_resources(self, kind: str) -> list[tuple[str, float]]:
        contract = get_contract(kind)
        if contract and contract.resources:
            return list(contract.resources)
        spec = get_spec(kind)
        if spec and spec.resources:
            return [(r, 1.0) for r in spec.resources]
        return []

    def _verify(
        self,
        kernel: Kernel,
        *,
        kind: str,
        proposal_id: str,
        resource_amounts: list[tuple[str, float]],
    ) -> VerificationResult:
        if get_handler(kind) is None:
            return VerificationResult(
                proposal_id=proposal_id,
                kind=kind,
                accepted=False,
                reason_code="unknown_kind",
                detail=f"No handler for {kind}",
            )

        contract = get_contract(kind) if self.use_contracts else None
        spec = get_spec(kind)

        waits: tuple[str, ...] = ()
        if contract:
            waits = contract.waits
        elif spec:
            waits = spec.waits

        if self.use_flags and waits:
            missing = [f for f in waits if f not in kernel.flags]
            if missing:
                return VerificationResult(
                    proposal_id=proposal_id,
                    kind=kind,
                    accepted=False,
                    reason_code="missing_flags",
                    detail=f"missing_flags:{','.join(missing)}",
                    missing_flags=missing,
                )

        if contract and contract.pre:
            failed = [c.describe() for c in contract.pre if not c.check(kernel.state)]
            if failed:
                return VerificationResult(
                    proposal_id=proposal_id,
                    kind=kind,
                    accepted=False,
                    reason_code="pre_condition",
                    detail=f"pre_failed:{';'.join(failed)}",
                    failed_pre=failed,
                )

        if self.use_resources and resource_amounts:
            missing_res: dict[str, float] = {}
            for name, amount in resource_amounts:
                if kernel.resources.get(name, 0.0) < amount:
                    missing_res[name] = amount
            if missing_res:
                first = next(iter(missing_res))
                return VerificationResult(
                    proposal_id=proposal_id,
                    kind=kind,
                    accepted=False,
                    reason_code="resource_shortage",
                    detail=f"resource_shortage:{first}",
                    missing_resources=missing_res,
                )

        return VerificationResult(
            proposal_id=proposal_id,
            kind=kind,
            accepted=True,
            reason_code="accepted",
            detail="contract_satisfied",
        )

    def check_post(self, kernel: Kernel, kind: str, state_before: dict[str, float]) -> VerificationResult | None:
        """Optional post-condition check after handler runs."""
        contract = get_contract(kind)
        if not contract or not contract.post:
            return None
        failed = [c.describe() for c in contract.post if not c.check(kernel.state)]
        if failed:
            return VerificationResult(
                proposal_id=kind,
                kind=kind,
                accepted=False,
                reason_code="post_condition",
                detail=f"post_failed:{';'.join(failed)}",
                failed_pre=failed,
            )
        return None


def verify_event(kernel: Kernel, event: Event, use_contracts: bool = True) -> VerificationResult:
    v = MechanismVerifier(
        use_contracts=use_contracts,
        use_flags=kernel.config.use_flags,
        use_resources=kernel.config.use_resources,
    )
    return v.verify_event(kernel, event)
