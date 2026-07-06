"""
core/scheduler.py — Periodic timer that ties KPIState + KPIEngine +
exporters together.

Uses a simple observer pattern: exporters register a callback via
`add_subscriber()`, and the scheduler calls each one with the fresh
RanKpiSnapshot every `interval_seconds`. This means the scheduler never
imports the exporter classes directly (no circular imports between
core/ and exporters/) — main.py is the only place that wires them
together.
"""

import asyncio
import logging
from typing import Callable, List, Optional

from kpi_engine import KPIEngine
from kpi_state import KPIState
from ran_kpi import RanKpiSnapshot

logger = logging.getLogger(__name__)

SnapshotSubscriber = Callable[[RanKpiSnapshot], None]


class Scheduler:
    """Drives the "drain state -> compute snapshot -> notify subscribers"
    cycle on a fixed interval, as an asyncio task."""

    def __init__(self, state: KPIState, engine: KPIEngine, interval_seconds: int) -> None:
        self._state = state
        self._engine = engine
        self._interval_seconds = interval_seconds
        self._subscribers: List[SnapshotSubscriber] = []
        self._latest_snapshot: Optional[RanKpiSnapshot] = None  # populated after first tick

    def add_subscriber(self, callback: SnapshotSubscriber) -> None:
        """Register a callback to be invoked with each new snapshot.
        Exporters call this during wiring in main.py."""
        self._subscribers.append(callback)

    def get_latest_snapshot(self) -> Optional[RanKpiSnapshot]:
        """Used by the NETCONF server to answer <get> requests with the
        most recent snapshot, independent of the exporter notification
        flow."""
        return self._latest_snapshot

    async def run_forever(self) -> None:
        logger.info(
            "Scheduler started, reporting interval = %ss", self._interval_seconds
        )
        while True:
            await asyncio.sleep(self._interval_seconds)
            try:
                counters = self._state.drain()
                snapshot = self._engine.compute_snapshot(counters)
                self._latest_snapshot = snapshot

                for subscriber in self._subscribers:
                    try:
                        subscriber(snapshot)
                    except Exception:
                        logger.exception(
                            "Subscriber %s raised an exception; continuing "
                            "with remaining subscribers", subscriber
                        )
            except Exception:
                logger.exception(
                    "Error computing KPI snapshot this interval; will retry "
                    "next interval rather than crash the scheduler"
                )
