"""
shared/influx_query.py — Pulls historical KPI data from InfluxDB into a
pandas DataFrame, for both the Isolation Forest and LSTM Autoencoder
detectors to consume.

Both detectors read the same "ran_kpis" measurement written by the
Week 3-4 collector — this module is the single place that knows how to
query it, so both ML scripts stay in sync if the schema changes.
"""

import logging

import pandas as pd
from influxdb_client import InfluxDBClient

logger = logging.getLogger(__name__)

_KPI_FIELDS = [
    "cqi_avg",
    "dl_bler_percent",
    "ul_bler_percent",
    "prb_utilization_percent_proxy",
    "ho_success_rate_percent",
    "rsrp_proxy_pusch_snr_db",
]


def fetch_kpi_history(url: str, token: str, org: str, bucket: str, lookback: str = "-1h") -> pd.DataFrame:
    """Returns a DataFrame indexed by time, one column per KPI field.
    Missing values (a field not written in a given interval) become NaN
    — callers should decide how to handle those (e.g. dropna, ffill)
    rather than this function silently choosing for them."""
    field_filter = " or ".join(f'r._field == "{f}"' for f in _KPI_FIELDS)
    flux_query = f"""
    from(bucket: "{bucket}")
      |> range(start: {lookback})
      |> filter(fn: (r) => r._measurement == "ran_kpis")
      |> filter(fn: (r) => {field_filter})
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    """

    client = InfluxDBClient(url=url, token=token, org=org)
    try:
        query_api = client.query_api()
        df = query_api.query_data_frame(flux_query)
    finally:
        client.close()

    if isinstance(df, list):
        df = pd.concat(df, ignore_index=True) if df else pd.DataFrame()

    if df.empty:
        logger.warning("No KPI data returned for lookback=%s — is the collector running?", lookback)
        return pd.DataFrame(columns=_KPI_FIELDS)

    df = df.set_index("_time")
    available_cols = [c for c in _KPI_FIELDS if c in df.columns]
    return df[available_cols]
