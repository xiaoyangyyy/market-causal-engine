"""MDG queries and explanations."""

from __future__ import annotations

from collections import deque
from typing import Any

from worldcup_causal_engine.mdg.graph import EventMDG
from worldcup_causal_engine.vm.verifier import MechanismVerifier


def downstream(mdg: EventMDG, kind: str, max_depth: int = 6) -> list[str]:
    seen = set([kind])
    q: deque[tuple[str, int]] = deque([(kind, 0)])
    out: list[str] = []
    while q:
        cur, d = q.popleft()
        if d >= max_depth:
            continue
        for (src, dst), edge in mdg.edges.items():
            if src != cur:
                continue
            if dst in seen:
                continue
            seen.add(dst)
            out.append(dst)
            q.append((dst, d + 1))
    return out


def upstream(mdg: EventMDG, kind: str, max_depth: int = 6) -> list[str]:
    seen = set([kind])
    q: deque[tuple[str, int]] = deque([(kind, 0)])
    out: list[str] = []
    while q:
        cur, d = q.popleft()
        if d >= max_depth:
            continue
        for (src, dst), edge in mdg.edges.items():
            if dst != cur:
                continue
            if src in seen:
                continue
            seen.add(src)
            out.append(src)
            q.append((src, d + 1))
    return out


def explain_why_not(
    *,
    kernel_like: Any,
    mdg: EventMDG,
    target_kind: str,
) -> dict[str, Any]:
    """Explain blockage for a not-happened kind using verifier + MDG context.

    `kernel_like` must have `.state`, `.flags`, `.resources`, `.config`.
    """
    v = MechanismVerifier(
        use_contracts=getattr(kernel_like.config, "use_contracts", True),
        use_flags=getattr(kernel_like.config, "use_flags", True),
        use_resources=getattr(kernel_like.config, "use_resources", True),
    )
    proposal = type("P", (), {"id": "P-explain", "kind": target_kind})  # minimal shim
    result = v._verify(  # noqa: SLF001 - deliberate internal use for explanation
        kernel_like,
        kind=target_kind,
        proposal_id="P-explain",
        resource_amounts=v._contract_resources(target_kind),  # noqa: SLF001
    )
    node = mdg.nodes.get(target_kind)
    return {
        "target_kind": target_kind,
        "verifier": result.to_dict(),
        "mdg_node": node.to_dict() if node else None,
        "upstream": upstream(mdg, target_kind, max_depth=3),
        "downstream": downstream(mdg, target_kind, max_depth=3),
    }

