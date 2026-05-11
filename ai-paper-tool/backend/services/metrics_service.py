"""
Metrics Service — token counting, API logging, and error monitoring.
Tracks LLM usage patterns for operational insights.
"""
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

METRICS_DIR = Path(__file__).parent.parent.parent / "metrics"
METRICS_FILE = METRICS_DIR / "api_calls.jsonl"


def _ensure_metrics_dir():
    """Ensure metrics directory exists."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class APICallRecord:
    """Single API call record."""
    timestamp: str
    agent: str  # writer, reviewer, editor, researcher
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    success: bool = True
    error: str = ""
    max_tokens_requested: int = 0


@dataclass
class MetricsSummary:
    """Summary statistics for a session."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_duration_ms: int = 0
    calls_by_agent: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class MetricsService:
    """
    Singleton service for tracking LLM API calls and errors.
    Writes to JSONL file for later analysis.
    """

    _instance: Optional["MetricsService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._ensure_metrics_dir()
        self._session_start = datetime.now()
        self._session_id = self._session_start.strftime("%Y%m%d_%H%M%S")
        logger.info(f"MetricsService initialized, session={self._session_id}")

    def _ensure_metrics_dir(self):
        _ensure_metrics_dir()

    def log_call(self, record: APICallRecord) -> None:
        """Log a single API call to the metrics file."""
        try:
            with open(METRICS_FILE, "a") as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            logger.debug(f"Logged API call: {record.agent} {record.input_tokens}+{record.output_tokens} tokens, {record.duration_ms}ms")
        except Exception as e:
            logger.error(f"Failed to log API call: {e}")

    def get_session_summary(self) -> MetricsSummary:
        """Aggregate metrics for the current session."""
        summary = MetricsSummary()
        try:
            if not METRICS_FILE.exists():
                return summary

            with open(METRICS_FILE, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        # Only count records from current session
                        if record.get("timestamp", "").startswith(self._session_start.strftime("%Y-%m-%d")):
                            summary.total_calls += 1
                            if record.get("success"):
                                summary.successful_calls += 1
                            else:
                                summary.failed_calls += 1
                                if record.get("error"):
                                    summary.errors.append(record["error"])

                            summary.total_input_tokens += record.get("input_tokens", 0)
                            summary.total_output_tokens += record.get("output_tokens", 0)
                            summary.total_tokens += record.get("total_tokens", 0)
                            summary.total_duration_ms += record.get("duration_ms", 0)

                            agent = record.get("agent", "unknown")
                            if agent not in summary.calls_by_agent:
                                summary.calls_by_agent[agent] = {"calls": 0, "tokens": 0}
                            summary.calls_by_agent[agent]["calls"] += 1
                            summary.calls_by_agent[agent]["tokens"] += record.get("total_tokens", 0)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to read metrics: {e}")

        return summary

    def format_summary_for_display(self, summary: Optional[MetricsSummary] = None) -> str:
        """Format metrics summary as human-readable string."""
        if summary is None:
            summary = self.get_session_summary()

        lines = [
            "=== API Usage Summary ===",
            f"Session: {self._session_id}",
            f"Total Calls: {summary.total_calls}",
            f"  Successful: {summary.successful_calls}",
            f"  Failed: {summary.failed_calls}",
            f"Total Tokens: {summary.total_tokens:,}",
            f"  Input: {summary.total_input_tokens:,}",
            f"  Output: {summary.total_output_tokens:,}",
            f"Total Duration: {summary.total_duration_ms/1000:.1f}s",
            "",
            "By Agent:",
        ]

        for agent, stats in sorted(summary.calls_by_agent.items()):
            lines.append(f"  {agent}: {stats['calls']} calls, {stats['tokens']:,} tokens")

        if summary.errors:
            lines.append("")
            lines.append(f"Errors ({len(summary.errors)}):")
            for err in summary.errors[:5]:  # Show first 5 errors
                lines.append(f"  - {err[:100]}")

        return "\n".join(lines)


class Timer:
    """Context manager for timing operations."""

    def __init__(self):
        self.start_time = None
        self.duration_ms = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.duration_ms = int((time.perf_counter() - self.start_time) * 1000)
