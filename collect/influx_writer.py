"""
collectors/influx_writer.py — Writes KPI snapshot dicts into InfluxDB.

Uses the official influxdb-client library. Write failures are logged and
retried on the next collector cycle rather than crashing the process —
a transient InfluxDB restart shouldn't take down the whole collector.
"""

import logging

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)

_MEASUREMENT = "ran_kpis"

_FIELD_MAP = {
    "cqi_avg": "cqi_avg",
    "dl_bler_percent": "dl_bler_percent",
    "ul_bler_percent": "ul_bler_percent",
    "prb_utilization_percent_proxy": "prb_utilization_percent_proxy",
    "ho_success_rate_percent": "ho_success_rate_percent",
    "rsrp_proxy_pusch_snr_db": "rsrp_proxy_pusch_snr_db",
}


class InfluxWriter:
    def __init__(self, url: str, token: str, org: str, bucket: str, managed_element: str) -> None:
        self._bucket = bucket
        self._org = org
        self._managed_element = managed_element
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

    def write_snapshot(self, snapshot: dict) -> bool:
        """Writes one KPI snapshot dict as a single InfluxDB point.
        Returns True on success, False on failure (already logged)."""
        point = Point(_MEASUREMENT).tag("managed_element", self._managed_element)

        wrote_any_field = False
        for snapshot_key, field_name in _FIELD_MAP.items():
            value = snapshot.get(snapshot_key)
            if value is not None:
                point = point.field(field_name, float(value))
                wrote_any_field = True

        if not wrote_any_field:
            logger.warning(
                "Snapshot had no non-null KPI fields — skipping write "
                "(expected if no traffic was flowing this interval)"
            )
            return False

        timestamp = snapshot.get("timestamp")
        if timestamp:
            point = point.time(timestamp, WritePrecision.S)

        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            logger.info("Wrote KPI point to InfluxDB bucket=%s", self._bucket)
            return True
        except Exception:
            logger.exception("Failed to write point to InfluxDB")
            return False

    def close(self) -> None:
        self._write_api.close()
        self._client.close()
