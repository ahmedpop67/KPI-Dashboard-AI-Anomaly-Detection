"""
exporters/netconf_server.py — Minimal, educational NETCONF server.

Implements enough of RFC 6241 to be a genuine, working NETCONF interface
for learning purposes: <hello> handshake, standard ]]>]]> framing, and
<get> / <get-config> / <close-session> operations returning our current
KPI snapshot as XML.

This is NOT a full NETCONF/YANG implementation — no <edit-config>, no
notifications, no real YANG-validated datastore. That scope is explicitly
called out as a limitation in the project README rather than silently
pretended away.

Tested against AsyncSSH 2.14.2 specifically (pinned in requirements.txt)
since asyncssh's process/subsystem APIs have changed across versions —
if you upgrade asyncssh, re-verify this still works before relying on it.
"""

import asyncio
import logging
from typing import Optional

import asyncssh

from scheduler import Scheduler
from ran_kpi import RanKpiSnapshot

logger = logging.getLogger(__name__)

NETCONF_DELIMITER = "]]>]]>"

_HELLO_REPLY = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">\n'
    "  <capabilities>\n"
    "    <capability>urn:ietf:params:netconf:base:1.0</capability>\n"
    "  </capabilities>\n"
    "  <session-id>1</session-id>\n"
    "</hello>\n"
) + NETCONF_DELIMITER


class _PasswordAuthServer(asyncssh.SSHServer):
    """Trivial username/password auth. For anything beyond localhost
    testing, replace with key-based auth or a real credential store."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, username: str, password: str) -> bool:
        return username == self._username and password == self._password


class NetconfServer:
    """Owns the asyncssh listener and answers NETCONF <get> requests using
    whatever snapshot the Scheduler currently has cached — this class
    does not itself track KPI state, it just reads Scheduler's latest
    value on demand (pull, not push), which keeps it decoupled from the
    PM XML exporter's push-based flow.
    """

    def __init__(
        self,
        scheduler: Scheduler,
        bind_addr: str,
        port: int,
        username: str,
        password: str,
        managed_element: str,
        gnb_cu_cp_function: str,
        nr_cell_id: str,
    ) -> None:
        self._scheduler = scheduler
        self._bind_addr = bind_addr
        self._port = port
        self._username = username
        self._password = password
        self._obj_ldn = (
            "ManagedElement=" + managed_element +
            ",GNBCUCPFunction=" + gnb_cu_cp_function +
            ",NRCellCU=" + nr_cell_id
        )

    async def start(self) -> None:
        logger.info(
            "Starting NETCONF server on %s:%s (user=%s)",
            self._bind_addr, self._port, self._username,
        )
        await asyncssh.listen(
            self._bind_addr,
            self._port,
            server_host_keys=[asyncssh.generate_private_key("ssh-rsa")],
            process_factory=self._session_factory,
            password_auth=True,
            server_factory=lambda: _PasswordAuthServer(self._username, self._password),
        )

    def _session_factory(self, process) -> None:
        task = asyncio.ensure_future(
            self._handle_session(process.stdin, process.stdout, process.stderr)
        )
        task.add_done_callback(self._log_task_exception)

    @staticmethod
    def _log_task_exception(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.exception("NETCONF session handler crashed", exc_info=exc)

    async def _handle_session(self, stdin, stdout, _stderr) -> None:
        stdout.write(_HELLO_REPLY)
        buffer = ""

        while True:
            chunk = await stdin.read(4096)
            if not chunk:
                break
            buffer += chunk

            while NETCONF_DELIMITER in buffer:
                frame, buffer = buffer.split(NETCONF_DELIMITER, 1)
                frame = frame.strip()
                if not frame or "<hello" in frame:
                    continue

                message_id = self._extract_message_id(frame)

                if "<get-config" in frame:
                    stdout.write(self._build_get_reply(message_id))
                elif "<get" in frame:
                    stdout.write(self._build_get_reply(message_id))
                elif "<close-session" in frame:
                    stdout.write(self._build_ok_reply(message_id))
                    stdout.close()
                    return
                else:
                    stdout.write(self._build_error_reply(message_id))

    @staticmethod
    def _extract_message_id(frame: str) -> str:
        if 'message-id="' in frame:
            return frame.split('message-id="', 1)[1].split('"', 1)[0]
        return "1"

    def _build_get_reply(self, message_id: str) -> str:
        snapshot = self._scheduler.get_latest_snapshot()

        def val(x):
            return "" if x is None else str(round(x, 3))

        if snapshot is None:
            timestamp = ""
            cqi = dl_bler = ul_bler = prb = ho = rsrp = ""
        else:
            timestamp = snapshot.timestamp
            cqi = val(snapshot.cqi_avg)
            dl_bler = val(snapshot.dl_bler_percent)
            ul_bler = val(snapshot.ul_bler_percent)
            prb = val(snapshot.prb_utilization_percent_proxy)
            ho = val(snapshot.ho_success_rate_percent)
            rsrp = val(snapshot.rsrp_proxy_pusch_snr_db)

        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="' + message_id + '">\n'
            "  <data>\n"
            '    <ran-kpis xmlns="urn:example:ran-kpi-monitor" measObjLdn="' + self._obj_ldn + '">\n'
            "      <timestamp>" + timestamp + "</timestamp>\n"
            "      <cqi-avg>" + cqi + "</cqi-avg>\n"
            "      <dl-bler-percent>" + dl_bler + "</dl-bler-percent>\n"
            "      <ul-bler-percent>" + ul_bler + "</ul-bler-percent>\n"
            "      <prb-utilization-percent-proxy>" + prb + "</prb-utilization-percent-proxy>\n"
            "      <ho-success-rate-percent>" + ho + "</ho-success-rate-percent>\n"
            "      <rsrp-proxy-pusch-snr-db>" + rsrp + "</rsrp-proxy-pusch-snr-db>\n"
            "    </ran-kpis>\n"
            "  </data>\n"
            "</rpc-reply>\n"
        ) + NETCONF_DELIMITER

    @staticmethod
    def _build_ok_reply(message_id: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="' + message_id + '">'
            "<ok/></rpc-reply>\n"
        ) + NETCONF_DELIMITER

    @staticmethod
    def _build_error_reply(message_id: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="' + message_id + '">'
            "<rpc-error><error-message>Only &lt;get&gt;, &lt;get-config&gt;, and "
            "&lt;close-session&gt; are supported by this educational server"
            "</error-message></rpc-error></rpc-reply>\n"
        ) + NETCONF_DELIMITER
