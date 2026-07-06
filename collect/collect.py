#!/usr/bin/env python3
"""
collectors/collect.py — Polls the O1/NETCONF adapter and writes each KPI
snapshot into InfluxDB. This is the actual Week 3-4 project deliverable:
"Python KPI collector" -> "KPI time-series in DB".

Run this AFTER main.py (the O1/NETCONF adapter) is already running,
which itself requires your OCUDU gNB/Open5GS/srsUE stack to be up.

    OCUDU gNB -> adapter (main.py) -> NETCONF <get> -> THIS COLLECTOR -> InfluxDB
"""

import logging
import time
from pathlib import Path

import yaml

from influx_writer import InfluxWriter
from netconf_reader import NetconfKpiReader

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    config = load_config()
    configure_logging(config["logging"]["level"])
    logger = logging.getLogger(__name__)

    nc_cfg = config["netconf"]
    influx_cfg = config["influxdb"]

    reader = NetconfKpiReader(
        host=nc_cfg["bind_addr"],
        port=nc_cfg["port"],
        username=nc_cfg["username"],
        password=nc_cfg["password"],
    )
    writer = InfluxWriter(
        url=influx_cfg["url"],
        token=influx_cfg["token"],
        org=influx_cfg["org"],
        bucket=influx_cfg["bucket"],
        managed_element=config["identity"]["managed_element"],
    )

    poll_interval = influx_cfg["poll_interval_seconds"]
    logger.info(
        "Starting KPI collector: polling NETCONF every %ss, writing to InfluxDB bucket=%s",
        poll_interval, influx_cfg["bucket"],
    )

    consecutive_failures = 0
    try:
        while True:
            time.sleep(poll_interval)

            snapshot = reader.read_snapshot()
            if snapshot is None:
                consecutive_failures += 1
                logger.warning("No snapshot this cycle (failure #%d in a row)", consecutive_failures)
                if consecutive_failures >= 5:
                    logger.error(
                        "5+ consecutive failures reading from the NETCONF adapter — "
                        "check that main.py (the adapter) and your OCUDU gNB are running."
                    )
                continue

            consecutive_failures = 0
            success = writer.write_snapshot(snapshot)
            if not success:
                logger.warning("Snapshot read OK but write to InfluxDB failed")

    except KeyboardInterrupt:
        logger.info("Shutting down collector...")
    finally:
        writer.close()


if __name__ == "__main__":
    main()
