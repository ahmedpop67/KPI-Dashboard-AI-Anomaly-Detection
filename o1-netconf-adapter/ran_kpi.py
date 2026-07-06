"""
models/ran_kpi.py — Typed data models for RAN KPI values.

These dataclasses are the shared "contract" between the parser, the KPI
engine, and the exporters — every layer speaks in these types rather than
raw dicts, so a schema change in one layer can't silently corrupt another.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ParsedMetricPoint:
    """A single normalized measurement extracted from one OCUDU WebSocket
    message. All fields are Optional because OCUDU's schema may omit any
    of them depending on message type (UE-scheduler messages vs. CU-CP
    mobility messages vs. cell-level messages) — the parser fills in
    whatever it finds and leaves the rest as None, rather than guessing.
    """

    cqi: Optional[float] = None
    dl_nof_ok: Optional[int] = None
    dl_nof_nok: Optional[int] = None
    ul_nof_ok: Optional[int] = None
    ul_nof_nok: Optional[int] = None
    pusch_snr_db: Optional[float] = None
    ho_requested_cumulative: Optional[int] = None
    ho_successful_cumulative: Optional[int] = None


@dataclass
class RanKpiSnapshot:
    """The 5 target KPIs (plus timestamp), as actually computed from
    accumulated ParsedMetricPoints over one reporting interval.

    See core/kpi_engine.py's module docstring for exactly which of these
    are direct OCUDU values vs. derived vs. approximated proxies — that
    mapping is documented once, at the point where it's computed, rather
    than repeated here.
    """

    timestamp: str
    cqi_avg: Optional[float] = None
    dl_bler_percent: Optional[float] = None
    ul_bler_percent: Optional[float] = None
    prb_utilization_percent_proxy: Optional[float] = None
    ho_success_rate_percent: Optional[float] = None
    rsrp_proxy_pusch_snr_db: Optional[float] = None

    def to_dict(self) -> dict:
        """Plain-dict form, used by both exporters so XML-building code
        doesn't need to know about dataclasses at all."""
        return asdict(self)
