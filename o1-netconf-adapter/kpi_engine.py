"""
core/kpi_engine.py — Pure(ish) KPI calculation logic.

Takes a drained RawCounters snapshot and produces a RanKpiSnapshot. The
only piece of state this class keeps across calls is the previous HO
cumulative reading, needed because OCUDU reports handover counts as
running totals rather than per-interval deltas — everything else here is
a straightforward calculation from the counters it's given.

--- KPI mapping notes (read this before trusting the numbers) ---

CQI                  -> DIRECT. Mean of OCUDU's reported per-UE "cqi"
                        values seen during the interval.

BLER (DL and UL)     -> DERIVED. OCUDU gives HARQ ok/nok counters
                        directly; BLER = nok / (ok + nok), the standard
                        definition.

HO Success Rate      -> DERIVED from cumulative counters. rate =
                        (successful_delta / requested_delta) * 100,
                        computed from the change in OCUDU's running
                        totals between this interval and the last one.
                        This is aggregate (whole gNB), not per-UE, since
                        that's the granularity OCUDU exposes it at.

PRB utilization      -> APPROXIMATED PROXY. OCUDU's per-UE metrics don't
                        expose a direct "PRBs used" counter in the schema
                        this project observed. We approximate using the
                        fraction of intervals where the UE had any
                        scheduled DL activity (ok+nok > 0) as a rough
                        stand-in for "the cell was scheduling this UE" —
                        this is NOT a true RRU.PrbUsedDl-style counter.

RSRP                 -> NOT REAL RSRP. Real RSRP comes from UE measurement
                        reports (RRC layer), which aren't present in this
                        metrics stream. We surface "pusch_snr_db" (uplink
                        PUSCH SNR) instead, under a clearly-labeled proxy
                        field — never presented as real RSRP.
"""

import logging
import time
from typing import Optional

from kpi_state import RawCounters
from ran_kpi import RanKpiSnapshot

logger = logging.getLogger(__name__)


class KPIEngine:
    """Computes a RanKpiSnapshot from drained raw counters. One instance
    per adapter process — holds the running "previous HO reading" needed
    for rate calculation across intervals."""

    def __init__(self) -> None:
        self._prev_ho_requested: Optional[int] = None
        self._prev_ho_successful: Optional[int] = None

    def compute_snapshot(self, counters: RawCounters) -> RanKpiSnapshot:
        cqi_avg = self._mean(counters.cqi_samples)
        rsrp_proxy = self._mean(counters.pusch_snr_samples)

        dl_bler = self._bler(counters.dl_ok, counters.dl_nok)
        ul_bler = self._bler(counters.ul_ok, counters.ul_nok)

        prb_proxy = (
            counters.scheduled_intervals / counters.total_intervals * 100
            if counters.total_intervals > 0
            else None
        )

        ho_rate = self._ho_success_rate(
            counters.ho_requested_cumulative, counters.ho_successful_cumulative
        )

        snapshot = RanKpiSnapshot(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            cqi_avg=cqi_avg,
            dl_bler_percent=dl_bler,
            ul_bler_percent=ul_bler,
            prb_utilization_percent_proxy=prb_proxy,
            ho_success_rate_percent=ho_rate,
            rsrp_proxy_pusch_snr_db=rsrp_proxy,
        )

        logger.debug("Computed KPI snapshot: %s", snapshot)
        return snapshot

    def _ho_success_rate(self, requested_cumulative, successful_cumulative):
        if requested_cumulative is None or successful_cumulative is None:
            return None

        rate = None
        if self._prev_ho_requested is not None and self._prev_ho_successful is not None:
            requested_delta = requested_cumulative - self._prev_ho_requested
            successful_delta = successful_cumulative - self._prev_ho_successful
            if requested_delta > 0:
                rate = successful_delta / requested_delta * 100
            elif requested_delta == 0:
                # No new HO attempts this interval — not the same as a
                # 0% success rate. Report None rather than a misleading 0.
                rate = None

        self._prev_ho_requested = requested_cumulative
        self._prev_ho_successful = successful_cumulative
        return rate

    @staticmethod
    def _bler(ok: int, nok: int):
        total = ok + nok
        return (nok / total * 100) if total > 0 else None

    @staticmethod
    def _mean(samples):
        return (sum(samples) / len(samples)) if samples else None
