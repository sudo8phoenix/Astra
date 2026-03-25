"""Lightweight in-process metrics collector and exporters."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Tuple


LabelKey = Tuple[Tuple[str, str], ...]


def _normalize_labels(labels: Dict[str, str] | None) -> LabelKey:
    if not labels:
        return tuple()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _labels_to_dict(label_key: LabelKey) -> Dict[str, str]:
    return dict(label_key)


def _labels_to_prometheus(label_key: LabelKey) -> str:
    if not label_key:
        return ""
    parts = [f'{k}="{v}"' for k, v in label_key]
    return "{" + ",".join(parts) + "}"


@dataclass
class HistogramStat:
    count: int = 0
    total: float = 0.0
    max_value: float = 0.0

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        if value > self.max_value:
            self.max_value = value

    @property
    def avg(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total / self.count


class MetricsCollector:
    """Thread-safe collector for counters and simple histogram stats."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters = defaultdict(int)
        self._histograms = defaultdict(HistogramStat)

    def increment(self, name: str, labels: Dict[str, str] | None = None, value: int = 1) -> None:
        label_key = _normalize_labels(labels)
        with self._lock:
            self._counters[(name, label_key)] += value

    def observe(self, name: str, value: float, labels: Dict[str, str] | None = None) -> None:
        label_key = _normalize_labels(labels)
        with self._lock:
            self._histograms[(name, label_key)].observe(value)

    def record_http_request(self, path: str, method: str, status_code: int, duration_ms: float) -> None:
        labels = {
            "path": path,
            "method": method.upper(),
            "status": str(status_code),
        }
        self.increment("http_requests_total", labels)
        self.observe("http_request_latency_ms", duration_ms, labels)

    def record_agent_step(self, step: str, status: str, duration_ms: float) -> None:
        labels = {
            "step": step,
            "status": status,
        }
        self.increment("agent_steps_total", labels)
        self.observe("agent_step_latency_ms", duration_ms, labels)

    def record_external_call(
        self,
        service: str,
        operation: str,
        status: str,
        duration_ms: float,
        attempts: int,
    ) -> None:
        labels = {
            "service": service,
            "operation": operation,
            "status": status,
        }
        self.increment("external_api_calls_total", labels)
        self.observe("external_api_latency_ms", duration_ms, labels)
        self.observe("external_api_attempts", float(attempts), labels)

    def record_llm_usage(
        self,
        model: str,
        tokens: int,
        cost_usd: float,
        threshold_exceeded: bool,
    ) -> None:
        labels = {
            "model": model,
            "threshold_exceeded": "true" if threshold_exceeded else "false",
        }
        self.increment("llm_calls_total", labels)
        self.observe("llm_tokens", float(tokens), labels)
        self.observe("llm_cost_usd", cost_usd, labels)

    def dashboard_snapshot(self) -> Dict[str, object]:
        with self._lock:
            counters = [
                {
                    "metric": name,
                    "labels": _labels_to_dict(label_key),
                    "value": value,
                }
                for (name, label_key), value in self._counters.items()
            ]

            histograms = [
                {
                    "metric": name,
                    "labels": _labels_to_dict(label_key),
                    "count": stat.count,
                    "avg": round(stat.avg, 4),
                    "max": round(stat.max_value, 4),
                    "sum": round(stat.total, 4),
                }
                for (name, label_key), stat in self._histograms.items()
            ]

        return {
            "counters": counters,
            "histograms": histograms,
        }

    def render_prometheus(self) -> str:
        lines = []
        with self._lock:
            for (name, label_key), value in sorted(self._counters.items(), key=lambda x: x[0][0]):
                lines.append(f"{name}{_labels_to_prometheus(label_key)} {value}")

            for (name, label_key), stat in sorted(self._histograms.items(), key=lambda x: x[0][0]):
                labels = _labels_to_prometheus(label_key)
                lines.append(f"{name}_count{labels} {stat.count}")
                lines.append(f"{name}_sum{labels} {stat.total:.6f}")
                lines.append(f"{name}_max{labels} {stat.max_value:.6f}")

        return "\n".join(lines) + "\n"


metrics_collector = MetricsCollector()
