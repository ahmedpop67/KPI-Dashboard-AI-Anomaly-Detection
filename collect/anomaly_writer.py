"""
shared/anomaly_writer.py — Writes anomaly detection results back into
InfluxDB, in a measurement the Grafana dashboard's "Anomaly Alerts" panel
already queries (ran_kpi_anomalies / is_anomaly).

Both the Isolation Forest and LSTM Autoencoder detectors use this same
writer with a "detector" tag distinguishing which one flagged it.
"""

import logging

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)

_MEASUREMENT = "ran_kpi_anomalies"


class AnomalyWriter:
    def __init__(self, url: str, token: str, org: str, bucket: str, managed_element: str) -> None:
        self._bucket = bucket
        self._org = org
        self._managed_element = managed_element
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

    def write_anomaly(self, timestamp, detector: str, is_anomaly: bool, score: float) -> bool:
        """`detector` should be 'isolation_forest' or 'lstm_autoencoder'.
        `score` is the anomaly score (Isolation Forest) or reconstruction
        error (LSTM) — kept even for non-anomalies, so you can see how
        close a normal point was to the threshold."""
        point = (
            Point(_MEASUREMENT)
            .tag("managed_element", self._managed_element)
            .tag("detector", detector)
            .field("is_anomaly", bool(is_anomaly))
            .field("score", float(score))
            .time(timestamp, WritePrecision.S)
        )

        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            return True
        except Exception:
            logger.exception("Failed to write anomaly point to InfluxDB")
            return False

    def close(self) -> None:
        self._write_api.close()
        self._client.close()
