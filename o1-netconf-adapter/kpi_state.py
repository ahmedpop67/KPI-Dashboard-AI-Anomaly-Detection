"""
core/kpi_state.py — Thread-safe accumulator for raw counters.

This class has exactly one job: safely accumulate ParsedMetricPoints from
the (async) WebSocket client thread until KPIEngine (running on the
scheduler's timer) drains and resets them. It deliberately does NOT do
any KPI math or track "previous interval" state itself — that's temporal
calculation logic and belongs in KPIEngine (see kpi_engine.py), keeping
"safely collecting data" and "computing KPIs from data" as separate
responsibilities.
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import List, Optional

from ran_kpi import ParsedMetricPoint

logger = logging.getLogger(__name__)


@dataclass
class RawCounters:
    """A snapshot of accumulated raw counters for one reporting interval.
    `ho_requested_cumulative` / `ho_successful_cumulative` are OCUDU's
    running totals as last seen during this interval (not deltas) —
    KPIEngine is responsible for turning these into a rate."""

    cqi_samples: List[float] = field(default_factory=list)
    pusch_snr_samples: List[float] = field(default_factory=list)
    dl_ok: int = 0
    dl_nok: int = 0
    ul_ok: int = 0
    ul_nok: int = 0
    scheduled_intervals: int = 0
    total_intervals: int = 0
    ho_requested_cumulative: Optional[int] = None
    ho_successful_cumulative: Optional[int] = None


class KPIState:
    """Thread-safe holder of raw counters. Safe to call `ingest()` from
    any thread (e.g. the WebSocket client's callback thread) while
    `drain()` is called from a different thread (the scheduler)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters = RawCounters()

    def ingest(self, point: ParsedMetricPoint) -> None:
        """Called once per parsed WebSocket message."""
        with self._lock:
            c = self._counters
            c.total_intervals += 1

            if point.cqi is not None:
                c.cqi_samples.append(point.cqi)
            if point.pusch_snr_db is not None:
                c.pusch_snr_samples.append(point.pusch_snr_db)

            if point.dl_nof_ok is not None:
                c.dl_ok += point.dl_nof_ok
                c.dl_nok += point.dl_nof_nok or 0
            if point.ul_nof_ok is not None:
                c.ul_ok += point.ul_nof_ok
                c.ul_nok += point.ul_nof_nok or 0

            if (point.dl_nof_ok or 0) + (point.dl_nof_nok or 0) > 0:
                c.scheduled_intervals += 1

            if point.ho_requested_cumulative is not None:
                c.ho_requested_cumulative = point.ho_requested_cumulative
            if point.ho_successful_cumulative is not None:
                c.ho_successful_cumulative = point.ho_successful_cumulative

    def drain(self) -> RawCounters:
        """Atomically returns the current counters and resets state for
        the next interval. Called only by the scheduler."""
        with self._lock:
            counters = self._counters
            self._counters = RawCounters()
            return counters
