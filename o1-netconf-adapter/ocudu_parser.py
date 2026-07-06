"""
parser/ocudu_parser.py — Converts raw OCUDU WebSocket JSON into
ParsedMetricPoint objects, tolerating schema drift.

OCUDU's JSON schema has already changed under us multiple times during
this project's own setup (config field names shifted between versions
during the gNB/UE config debugging). This parser is written assuming that
will keep happening: every field access is defensive, missing fields
produce a logged warning (not an exception), and unknown extra fields are
silently ignored rather than rejected.

If a future OCUDU version renames a field, update the `_FIELD_PATHS`
lookups below — the rest of the pipeline (KPIEngine, exporters) doesn't
need to change, since it only ever sees the normalized ParsedMetricPoint.
"""

import logging
from typing import Any, Optional

from ran_kpi import ParsedMetricPoint

logger = logging.getLogger(__name__)


class OCUDUParser:
    """Stateless parser: one call in, one ParsedMetricPoint out (or None
    if the message contains nothing we recognize)."""

    def parse(self, message: dict) -> Optional[ParsedMetricPoint]:
        if not isinstance(message, dict):
            logger.warning("Received non-dict message, ignoring: %r", type(message))
            return None

        point = ParsedMetricPoint()
        found_anything = False

        if self._parse_ue_metrics(message, point):
            found_anything = True
        if self._parse_cu_cp_metrics(message, point):
            found_anything = True

        if not found_anything:
            logger.debug(
                "Message contained no recognized fields (keys=%s); "
                "this is normal for message types we don't map yet "
                "(e.g. pure DU/MAC latency stats).",
                list(message.keys()),
            )
            return None

        return point

    def _parse_ue_metrics(self, message: dict, point: ParsedMetricPoint) -> bool:
        """Handles per-UE scheduler metrics. OCUDU has nested these
        under slightly different keys across versions/message types
        (`ue_list` at top level, or under `cells[0].ue_list`) — we check
        both rather than assuming one."""
        ue_list = message.get("ue_list")
        if ue_list is None:
            cells = message.get("cells")
            if isinstance(cells, list) and cells:
                ue_list = cells[0].get("ue_list")

        if not isinstance(ue_list, list) or not ue_list:
            return False

        found = False
        for ue in ue_list:
            container: Any = ue.get("ue_container", ue) if isinstance(ue, dict) else None
            if not isinstance(container, dict):
                continue

            if "cqi" in container:
                point.cqi = self._safe_float(container.get("cqi"))
                found = True
            if "dl_nof_ok" in container:
                point.dl_nof_ok = self._safe_int(container.get("dl_nof_ok"))
                point.dl_nof_nok = self._safe_int(container.get("dl_nof_nok"))
                found = True
            if "ul_nof_ok" in container:
                point.ul_nof_ok = self._safe_int(container.get("ul_nof_ok"))
                point.ul_nof_nok = self._safe_int(container.get("ul_nof_nok"))
                found = True
            if container.get("pusch_snr_db") is not None:
                point.pusch_snr_db = self._safe_float(container.get("pusch_snr_db"))
                found = True

            # We only take the first UE with usable data per message —
            # multi-UE aggregation across a single message is out of
            # scope for this KPI set (each UE would need its own
            # snapshot in a multi-UE deployment; this project targets
            # the single simulated UE from the testbed).
            if found:
                break

        return found

    def _parse_cu_cp_metrics(self, message: dict, point: ParsedMetricPoint) -> bool:
        """Handles CU-CP-level NGAP/mobility stats. These are cumulative
        counters as reported by the gNB (not per-interval deltas), which
        is why KPIEngine computes a rate from two cumulative readings
        rather than treating these as interval counts."""
        cu_cp = message.get("cu-cp") or message.get("cu_cp")
        if not isinstance(cu_cp, dict):
            return False

        ngaps = cu_cp.get("ngaps")
        if not isinstance(ngaps, dict):
            logger.debug("cu-cp message present but no 'ngaps' key found")
            return False

        requested = ngaps.get("nof_handover_preparations_requested")
        successful = ngaps.get("nof_successful_handover_preparations")

        if requested is None and successful is None:
            return False

        point.ho_requested_cumulative = self._safe_int(requested)
        point.ho_successful_cumulative = self._safe_int(successful)
        return True

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            logger.warning("Expected numeric value, got %r — dropping this field", value)
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            logger.warning("Expected integer value, got %r — dropping this field", value)
            return None
