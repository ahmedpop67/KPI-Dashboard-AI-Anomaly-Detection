"""
collectors/netconf_reader.py — Polls the O1/NETCONF adapter's <get>
interface and parses the reply into a plain dict of KPI values.

Implementation note: this uses asyncssh directly rather than the more
common `ncclient` library. During development, `ncclient` was tried
first and failed with message-id mismatch errors against our server —
a known category of compatibility issue between ncclient's internal
session/capability negotiation and minimal (non-fully-featured) NETCONF
server implementations like ours. Rather than ship an integration that
was observed failing, this uses asyncssh directly — the same library our
own NetconfServer is built on, and the same pattern already verified
working end-to-end in this project's own testing (see the project README
for that verification). If you want to swap in ncclient later against a
more complete NETCONF server (e.g. a real sysrepo/netopeer2 backend),
this module is the only place that would need to change.
"""

import asyncio
import logging
from typing import Optional
from xml.etree import ElementTree

import asyncssh

logger = logging.getLogger(__name__)

_NETCONF_DELIMITER = "]]>]]>"
_NS = {"kpi": "urn:example:ran-kpi-monitor"}


class NetconfKpiReader:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._message_id = 0

    async def read_snapshot_async(self) -> Optional[dict]:
        """Performs one <get> against the adapter and returns a plain
        dict of KPI values, or None if the read failed."""
        try:
            async with asyncssh.connect(
                self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                known_hosts=None,
                login_timeout=10,
            ) as conn:
                async with conn.create_process(
                    subsystem="netconf", encoding="utf-8"
                ) as process:
                    # Consume the server's hello (we don't need to send
                    # our own — this minimal server doesn't require it,
                    # matching what we verified in end-to-end testing).
                    await asyncio.wait_for(
                        process.stdout.readuntil(_NETCONF_DELIMITER), timeout=10
                    )

                    self._message_id += 1
                    request = (
                        '<?xml version="1.0" encoding="UTF-8"?>'
                        f'<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" '
                        f'message-id="{self._message_id}"><get/></rpc>'
                        + _NETCONF_DELIMITER
                    )
                    process.stdin.write(request)

                    reply = await asyncio.wait_for(
                        process.stdout.readuntil(_NETCONF_DELIMITER), timeout=10
                    )
                    return self._parse_reply(reply)

        except asyncio.TimeoutError:
            logger.error(
                "Timed out waiting for NETCONF adapter at %s:%s", self._host, self._port
            )
            return None
        except (asyncssh.Error, ConnectionError, OSError) as exc:
            logger.error(
                "Could not connect to NETCONF adapter at %s:%s (%s) — is it running?",
                self._host, self._port, exc,
            )
            return None
        except Exception:
            logger.exception("Unexpected error reading from NETCONF adapter")
            return None

    def read_snapshot(self) -> Optional[dict]:
        """Synchronous wrapper, for use from non-async collector code."""
        return asyncio.run(self.read_snapshot_async())

    @staticmethod
    def _parse_reply(reply_xml: str) -> Optional[dict]:
        xml_only = reply_xml.replace(_NETCONF_DELIMITER, "").strip()
        try:
            root = ElementTree.fromstring(xml_only)
        except ElementTree.ParseError:
            logger.error("NETCONF reply was not valid XML: %r", xml_only[:200])
            return None

        kpi_elem = root.find(".//kpi:ran-kpis", _NS)
        if kpi_elem is None:
            logger.warning("NETCONF reply had no <ran-kpis> element")
            return None

        def field(name: str):
            el = kpi_elem.find(f"kpi:{name}", _NS)
            if el is None or el.text is None or el.text == "":
                return None
            try:
                return float(el.text)
            except ValueError:
                return el.text  # e.g. the timestamp field, non-numeric

        return {
            "timestamp": field("timestamp"),
            "cqi_avg": field("cqi-avg"),
            "dl_bler_percent": field("dl-bler-percent"),
            "ul_bler_percent": field("ul-bler-percent"),
            "prb_utilization_percent_proxy": field("prb-utilization-percent-proxy"),
            "ho_success_rate_percent": field("ho-success-rate-percent"),
            "rsrp_proxy_pusch_snr_db": field("rsrp-proxy-pusch-snr-db"),
        }
