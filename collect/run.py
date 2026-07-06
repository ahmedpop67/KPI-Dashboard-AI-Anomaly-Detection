#!/usr/bin/env python3
"""
isolation_forest/run.py — Trains (or re-trains) the hybrid Isolation
Forest + z-score detector on a baseline window from InfluxDB, then scores
recent data on a loop, writing flags back to InfluxDB.

See detector.py's module docstring for why this is a hybrid detector,
not pure Isolation Forest — that design decision was verified against
synthetic test data with injected anomalies before being written here.
"""

import argparse
import logging
import time
from pathlib import Path

import yaml

from isolation_forest.detector import IsolationForestDetector
from shared.anomaly_writer import AnomalyWriter
from shared.influx_query import fetch_kpi_history

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolation Forest RAN KPI anomaly detector")
    parser.add_argument("--baseline-lookback", default="-24h",
                         help="History to train on, Flux duration syntax (default: -24h)")
    parser.add_argument("--score-interval-seconds", type=int, default=60,
                         help="How often to fetch new data and score it (default: 60)")
    parser.add_argument("--score-lookback", default="-2m",
                         help="Recent history to score each cycle (default: -2m)")
    parser.add_argument("--retrain-every-n-cycles", type=int, default=60,
                         help="Re-train every N scoring cycles (default: 60)")
    args = parser.parse_args()

    config = load_config()
    configure_logging(config["logging"]["level"])
    logger = logging.getLogger(__name__)

    influx_cfg = config["influxdb"]
    managed_element = config["identity"]["managed_element"]

    def train_detector():
        logger.info("Fetching baseline (lookback=%s) for training...", args.baseline_lookback)
        baseline_df = fetch_kpi_history(
            url=influx_cfg["url"], token=influx_cfg["token"],
            org=influx_cfg["org"], bucket=influx_cfg["bucket"],
            lookback=args.baseline_lookback,
        )
        detector = IsolationForestDetector(contamination=0.05, zscore_threshold=3.0)
        detector.fit(baseline_df)
        return detector

    detector = train_detector()
    writer = AnomalyWriter(
        url=influx_cfg["url"], token=influx_cfg["token"],
        org=influx_cfg["org"], bucket=influx_cfg["bucket"],
        managed_element=managed_element,
    )

    cycle = 0
    try:
        while True:
            time.sleep(args.score_interval_seconds)
            cycle += 1

            if cycle % args.retrain_every_n_cycles == 0:
                try:
                    detector = train_detector()
                except ValueError:
                    logger.exception("Re-training failed, keeping previous model")

            recent_df = fetch_kpi_history(
                url=influx_cfg["url"], token=influx_cfg["token"],
                org=influx_cfg["org"], bucket=influx_cfg["bucket"],
                lookback=args.score_lookback,
            )
            if recent_df.empty:
                logger.warning("No recent data to score this cycle")
                continue

            results = detector.score(recent_df)
            for timestamp, row in results.iterrows():
                if row["anomaly_score"] != row["anomaly_score"]:  # NaN check
                    continue
                writer.write_anomaly(
                    timestamp=timestamp,
                    detector="isolation_forest",
                    is_anomaly=row["is_anomaly"],
                    score=row["anomaly_score"],
                )
                if row["is_anomaly"]:
                    logger.warning(
                        "ANOMALY at %s (source=%s, score=%.4f)",
                        timestamp, row["anomaly_source"], row["anomaly_score"],
                    )

    except KeyboardInterrupt:
        logger.info("Shutting down Isolation Forest detector...")
    finally:
        writer.close()


if __name__ == "__main__":
    main()
