"""Mechanism registration and lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from worldcup_causal_engine.kernel import Event, Kernel

MechanismHandler = Callable[["Kernel", "Event"], None]


@dataclass(frozen=True)
class MechanismSpec:
    kind: str
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    waits: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    version: str = "v0.1"


MECHANISM_INDEX: dict[str, MechanismSpec] = {}
_HANDLER_INDEX: dict[str, MechanismHandler] = {}


def mechanism(
    *,
    kind: str,
    reads: list[str] | None = None,
    writes: list[str] | None = None,
    waits: list[str] | None = None,
    resources: list[str] | None = None,
    emits: list[str] | None = None,
    version: str = "v0.1",
):
    """Register a mechanism handler with causal metadata."""

    def decorator(fn: MechanismHandler) -> MechanismHandler:
        spec = MechanismSpec(
            kind=kind,
            reads=tuple(reads or ()),
            writes=tuple(writes or ()),
            waits=tuple(waits or ()),
            resources=tuple(resources or ()),
            emits=tuple(emits or ()),
            version=version,
        )
        MECHANISM_INDEX[kind] = spec
        _HANDLER_INDEX[kind] = fn
        return fn

    return decorator


def get_handler(kind: str) -> MechanismHandler | None:
    return _HANDLER_INDEX.get(kind)


def get_spec(kind: str) -> MechanismSpec | None:
    return MECHANISM_INDEX.get(kind)


def register_all_mechanisms() -> None:
    """Import mechanism modules to populate the registry."""
    from worldcup_causal_engine.mechanisms import (  # noqa: F401
        city,
        crowd,
        intervention,
        match,
        media,
        security,
        social,
    )
