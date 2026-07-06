"""
main.py — Entry point. Wires OCUDUClient, KPIState, KPIEngine, Scheduler,
PMXMLExporter, and NetconfServer together via dependency injection.

Nothing here simulates data. OCUDUClient connects to your real, already
running OCUDU gNB's WebSocket — if it's not running or unreachable, this
process will log connection errors and keep retrying, not fall back to
fake data.

Run with: python3 main.py   (or: ./run.sh)
"""

import asyncio
import logging
from pathlib import Path

import yaml

from metrics_adapter import OCUDUClient
from kpi_engine import KPIEngine
from kpi_state import KPIState
from scheduler import Scheduler
from netconf_server import NetconfServer
from pm_xml_exporter import PMXMLExporter
from ocudu_parser import OCUDUParser

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def async_main(config: dict) -> None:
    logger = logging.getLogger(__name__)

    # --- Wire dependencies (composition root) ---
    state = KPIState()
    parser = OCUDUParser()
    engine = KPIEngine()
    scheduler = Scheduler(
        state=state,
        engine=engine,
        interval_seconds=config["reporting"]["interval_seconds"],
    )

    pm_exporter = PMXMLExporter(
        output_dir=config["pm_xml"]["output_dir"],
        managed_element=config["identity"]["managed_element"],
        gnb_cu_cp_function=config["identity"]["gnb_cu_cp_function"],
        nr_cell_id=config["identity"]["nr_cell_id"],
        sender_name=config["identity"]["sender_name"],
        max_files=config["pm_xml"]["max_files"],
    )
    scheduler.add_subscriber(pm_exporter.export)

    netconf_server = NetconfServer(
        scheduler=scheduler,
        bind_addr=config["netconf"]["bind_addr"],
        port=config["netconf"]["port"],
        username=config["netconf"]["username"],
        password=config["netconf"]["password"],
        managed_element=config["identity"]["managed_element"],
        gnb_cu_cp_function=config["identity"]["gnb_cu_cp_function"],
        nr_cell_id=config["identity"]["nr_cell_id"],
    )

    ocudu_client = OCUDUClient(
        websocket_url=config["ocudu"]["websocket_url"],
        state=state,
        parser=parser,
        reconnect_interval_seconds=config["ocudu"]["reconnect_interval_seconds"],
    )

    # --- Start everything ---
    logger.info("Starting O1/NETCONF adapter...")
    ocudu_client.start()  # runs on its own background thread
    await netconf_server.start()
    await scheduler.run_forever()  # runs forever, in this event loop


def main() -> None:
    config = load_config()
    configure_logging(config["logging"]["level"])
    asyncio.run(async_main(config))


if __name__ == "__main__":
    main()
