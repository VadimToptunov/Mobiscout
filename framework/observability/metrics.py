"""
Enhanced Observability System

Comprehensive observability with metrics, structured logging,
and distributed tracing for production-grade test execution.

Features:
- Prometheus metrics export
- OpenTelemetry tracing
- Structured JSON logging
- Custom metrics collection
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List


class MetricType(Enum):
    """Metric types"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class Metric:
    """Single metric"""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    help_text: str = ""


class MetricsCollector:
    """
    Collect and export metrics in Prometheus format
    
    Example metrics:
    - test_duration_seconds
    - test_failures_total
    - device_availability
    - healing_success_rate
    """

    def __init__(self):
        self.metrics: Dict[str, Metric] = {}
        self.histograms: Dict[str, List[float]] = {}

    def inc_counter(
            self,
            name: str,
            value: float = 1.0,
            labels: Optional[Dict[str, str]] = None,
            help_text: str = "",
    ) -> None:
        """Increment counter metric"""
        key = self._make_key(name, labels or {})

        if key in self.metrics:
            self.metrics[key].value += value
        else:
            self.metrics[key] = Metric(
                name=name,
                type=MetricType.COUNTER,
                value=value,
                labels=labels or {},
                help_text=help_text,
            )

    def set_gauge(
            self,
            name: str,
            value: float,
            labels: Optional[Dict[str, str]] = None,
            help_text: str = "",
    ) -> None:
        """Set gauge metric"""
        key = self._make_key(name, labels or {})

        self.metrics[key] = Metric(
            name=name,
            type=MetricType.GAUGE,
            value=value,
            labels=labels or {},
            help_text=help_text,
        )

    def observe_histogram(
            self,
            name: str,
            value: float,
            labels: Optional[Dict[str, str]] = None,
            help_text: str = "",
    ) -> None:
        """Record histogram observation"""
        key = self._make_key(name, labels or {})

        if key not in self.histograms:
            self.histograms[key] = []

        self.histograms[key].append(value)

        # Store as metric for export
        self.metrics[key] = Metric(
            name=name,
            type=MetricType.HISTOGRAM,
            value=value,
            labels=labels or {},
            help_text=help_text,
        )

    @staticmethod
    def _make_key(name: str, labels: Dict[str, str]) -> str:
        """Generate unique metric key"""
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}" if label_str else name

    def export_prometheus(self, output_path: Optional[Path] = None) -> str:
        """
        Export metrics in Prometheus format
        
        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        # Group by metric name
        grouped: Dict[str, List[Metric]] = {}
        for metric in self.metrics.values():
            if metric.name not in grouped:
                grouped[metric.name] = []
            grouped[metric.name].append(metric)

        # Generate output
        for name, metrics_list in sorted(grouped.items()):
            # Add HELP and TYPE comments
            first = metrics_list[0]
            if first.help_text:
                lines.append(f"# HELP {name} {first.help_text}")
            lines.append(f"# TYPE {name} {first.type.value}")

            # Add metric values
            for metric in metrics_list:
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{name}{labels_str} {metric.value}")

        output = "\n".join(lines) + "\n"

        # Save to file if requested
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(output)

        return output

    @staticmethod
    def _format_labels(labels: Dict[str, str]) -> str:
        """Format labels for Prometheus"""
        if not labels:
            return ""

        items = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ",".join(items) + "}"

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary as dict"""
        return {
            "total_metrics": len(self.metrics),
            "counters": sum(1 for m in self.metrics.values() if m.type == MetricType.COUNTER),
            "gauges": sum(1 for m in self.metrics.values() if m.type == MetricType.GAUGE),
            "histograms": sum(1 for m in self.metrics.values() if m.type == MetricType.HISTOGRAM),
            "metrics": [
                {
                    "name": m.name,
                    "type": m.type.value,
                    "value": m.value,
                    "labels": m.labels,
                }
                for m in self.metrics.values()
            ],
        }


class StructuredLogger:
    """
    Structured JSON logger for production
    
    Features:
    - JSON output
    - Context fields
    - Log levels
    - Correlation IDs
    """

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or Path("logs/observe.json")
        self.context: Dict[str, Any] = {}

    def add_context(self, **kwargs: Any) -> None:
        """Add fields to logging context"""
        self.context.update(kwargs)

    def clear_context(self) -> None:
        """Clear logging context"""
        self.context = {}

    def log(
            self,
            level: str,
            message: str,
            **kwargs: Any,
    ) -> None:
        """Log structured message"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.upper(),
            "message": message,
            **self.context,
            **kwargs,
        }

        # Write to file
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message"""
        self.log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message"""
        self.log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message"""
        self.log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message"""
        self.log("ERROR", message, **kwargs)


class TracingContext:
    """
    OpenTelemetry-compatible tracing context
    
    Simplified tracing for test execution flows.
    """

    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or self._generate_trace_id()
        self.spans: List[Dict[str, Any]] = []
        self.current_span: Optional[str] = None

    @staticmethod
    def _generate_trace_id() -> str:
        """Generate random trace ID"""
        import uuid
        return str(uuid.uuid4())

    def start_span(self, name: str, **attributes: Any) -> str:
        """Start a new span"""
        span_id = f"{name}_{int(time.time() * 1000)}"

        span = {
            "span_id": span_id,
            "name": name,
            "trace_id": self.trace_id,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "duration_ms": None,
            "attributes": attributes,
            "parent_span": self.current_span,
        }

        self.spans.append(span)
        self.current_span = span_id

        return span_id

    def end_span(self, span_id: str, **attributes: Any) -> None:
        """End a span"""
        for span in self.spans:
            if span["span_id"] == span_id:
                end_time = datetime.now()
                span["end_time"] = end_time.isoformat()

                # Calculate duration
                start_time = datetime.fromisoformat(span["start_time"])
                span["duration_ms"] = (end_time - start_time).total_seconds() * 1000

                # Add attributes
                span["attributes"].update(attributes)

                # Reset current span to parent
                self.current_span = span["parent_span"]
                break

    def export_json(self, output_path: Path) -> None:
        """Export traces to JSON"""
        data = {
            "trace_id": self.trace_id,
            "spans": self.spans,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)


class ObservabilityManager:
    """
    Central observability manager
    
    Coordinates metrics, logging, and tracing.
    """

    _instance: Optional["ObservabilityManager"] = None

    def __init__(self):
        self.metrics = MetricsCollector()
        self.logger = StructuredLogger()
        self.tracing: Optional[TracingContext] = None

    @classmethod
    def get_instance(cls) -> "ObservabilityManager":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_trace(self, trace_id: Optional[str] = None) -> TracingContext:
        """Start a new trace"""
        self.tracing = TracingContext(trace_id)
        return self.tracing

    def get_trace(self) -> Optional[TracingContext]:
        """Get current trace"""
        return self.tracing

    def record_test_start(self, test_name: str) -> None:
        """Record test start"""
        self.metrics.inc_counter(
            "tests_started_total",
            labels={"test": test_name},
            help_text="Total tests started",
        )
        self.logger.info("Test started", test_name=test_name)

        if self.tracing:
            self.tracing.start_span("test_execution", test_name=test_name)

    def record_test_end(
            self,
            test_name: str,
            status: str,
            duration: float,
    ) -> None:
        """Record test completion"""
        self.metrics.inc_counter(
            f"tests_{status}_total",
            labels={"test": test_name},
            help_text=f"Total tests {status}",
        )

        self.metrics.observe_histogram(
            "test_duration_seconds",
            duration,
            labels={"test": test_name, "status": status},
            help_text="Test execution duration",
        )

        self.logger.info(
            "Test completed",
            test_name=test_name,
            status=status,
            duration=duration,
        )

        if self.tracing and self.tracing.current_span:
            self.tracing.end_span(
                self.tracing.current_span,
                status=status,
                duration=duration,
            )
