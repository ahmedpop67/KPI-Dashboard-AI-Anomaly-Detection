"""
adapter/metrics_adapter.py — OCUDUClient: connects to a REAL, already
running OCUDU gNB's metrics WebSocket.

This class does not simulate, mock, or generate any metrics. It connects
to whatever `websocket_url` is configured (your actual gNB's
remote_control server), subscribes with the real "metrics_subscribe"
command OCUDU expects, and feeds every real message it receives through
OCUDUParser into KPIState. If the gNB isn't running or the WebSocket URL
is wrong, this will fail to connect and retry — it will never fall back
to fake data.
"""

import json
import logging
import threading
import time
from typing import Optional

import websocket

from kpi_state import KPIState
from ocudu_parser import OCUDUParser

logger = logging.getLogger(__name__)


class OCUDUClient:
    """Wraps `websocket-client`'s WebSocketApp with reconnect logic and
    wires incoming messages through the parser into KPIState.

    Runs its own background thread (websocket-client's run_forever is
    blocking) so it can be started from an asyncio-based main() without
    the two event loops interfering with each other.
    """

    def __init__(
        self,
        websocket_url: str,
        state: KPIState,
        parser: OCUDUParser,
        reconnect_interval_seconds: int = 5,
    ) -> None:
        self._url = websocket_url
        self._state = state
        self._parser = parser
        self._reconnect_interval = reconnect_interval_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the client on a background thread. Non-blocking."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("OCUDUClient started (target=%s)", self._url)

    def stop(self) -> None:
        self._stop_event.set()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            logger.info("Connecting to OCUDU metrics WebSocket at %s ...", self._url)
            try:
                ws_app = websocket.WebSocketApp(
                    self._url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                ws_app.run_forever()
            except Exception:
                logger.exception("Unexpected error in WebSocket client loop")

            if self._stop_event.is_set():
                break

            logger.warning(
                "Disconnected from OCUDU metrics WebSocket. Retrying in %ss...",
                self._reconnect_interval,
            )
            time.sleep(self._reconnect_interval)

    def _on_open(self, ws) -> None:
        logger.info("Connected to OCUDU metrics WebSocket, subscribing...")
        ws.send(json.dumps({"cmd": "metrics_subscribe"}))

    def _on_message(self, _ws, message: str) -> None:
        try:
            parsed_json = json.loads(message)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON message from OCUDU, ignoring")
            return

        if isinstance(parsed_json, dict) and "cmd" in parsed_json:
            return

        point = self._parser.parse(parsed_json)
        if point is not None:
            self._state.ingest(point)

    def _on_error(self, _ws, error) -> None:
        logger.error("OCUDU WebSocket error: %s", error)

    def _on_close(self, _ws, close_status_code, close_msg) -> None:
        logger.info(
            "OCUDU WebSocket closed (code=%s, msg=%s)", close_status_code, close_msg
        )
