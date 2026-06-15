"""Prometheus-compatible metrics (stdlib-only counter/gauge registry)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Metric:
    name: str
    help: str
    type: str
    labels: dict[str, str] = field(default_factory=dict)
    value: float = 0.0


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, _Metric] = {}
        self._gauges: dict[str, _Metric] = {}
        self._histograms: dict[str, list[float]] = {}

    def inc(self, name: str, value: float = 1.0, *, labels: dict[str, str] | None = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._counters:
                self._counters[key] = _Metric(name=name, help=name, type="counter", labels=labels or {})
            self._counters[key].value += value

    def set_gauge(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = _Metric(name=name, help=name, type="gauge", labels=labels or {})
            self._gauges[key].value = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms.setdefault(name, []).append(value)

    def _key(self, name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{parts}}}"

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for key, metric in self._counters.items():
                label_str = self._label_str(metric.labels)
                lines.append(f"# TYPE {metric.name} counter")
                lines.append(f"{metric.name}{label_str} {metric.value}")
            for key, metric in self._gauges.items():
                label_str = self._label_str(metric.labels)
                lines.append(f"# TYPE {metric.name} gauge")
                lines.append(f"{metric.name}{label_str} {metric.value}")
            for name, values in self._histograms.items():
                if not values:
                    continue
                lines.append(f"# TYPE {name} summary")
                lines.append(f"{name}_count {len(values)}")
                lines.append(f"{name}_sum {sum(values)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _label_str(labels: dict[str, str]) -> str:
        if not labels:
            return ""
        inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return "{" + inner + "}"


REGISTRY = MetricsRegistry()


class Timer:
    def __init__(self, metric_name: str) -> None:
        self.metric_name = metric_name
        self._start = 0.0

    def __enter__(self) -> Timer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        REGISTRY.observe(self.metric_name, time.monotonic() - self._start)
