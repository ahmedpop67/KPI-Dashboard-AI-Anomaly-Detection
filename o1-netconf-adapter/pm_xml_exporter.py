"""
exporters/pm_xml_exporter.py — Writes 3GPP-32.435-style PM XML files.

Each call to `export()` writes one complete PM file for one reporting
interval, then enforces a maximum file count by deleting the oldest files
(rotation) — this file is called once per Scheduler tick as a subscriber.
"""

import logging
from pathlib import Path
from xml.sax.saxutils import escape

from ran_kpi import RanKpiSnapshot

logger = logging.getLogger(__name__)


class PMXMLExporter:
    def __init__(
        self,
        output_dir: str,
        managed_element: str,
        gnb_cu_cp_function: str,
        nr_cell_id: str,
        sender_name: str,
        max_files: int = 500,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._obj_ldn = (
            f"ManagedElement={managed_element},"
            f"GNBCUCPFunction={gnb_cu_cp_function},"
            f"NRCellCU={nr_cell_id}"
        )
        self._sender_name = sender_name
        self._max_files = max_files

    def export(self, snapshot: RanKpiSnapshot) -> None:
        xml_doc = self._build_xml(snapshot)
        filename = f"pm_{snapshot.timestamp.replace(':', '').replace('-', '')}.xml"
        filepath = self._output_dir / filename

        try:
            filepath.write_text(xml_doc)
            logger.info("Wrote PM XML file: %s", filepath)
        except OSError:
            logger.exception("Failed to write PM XML file %s", filepath)
            return

        self._rotate_old_files()

    def _rotate_old_files(self) -> None:
        files = sorted(self._output_dir.glob("pm_*.xml"), key=lambda p: p.stat().st_mtime)
        excess = len(files) - self._max_files
        if excess > 0:
            for old_file in files[:excess]:
                try:
                    old_file.unlink()
                except OSError:
                    logger.warning("Could not delete old PM file %s", old_file)

    def _build_xml(self, snapshot: RanKpiSnapshot) -> str:
        measurements = [
            ("DRB.UECqiDl", snapshot.cqi_avg),
            ("DRB.PktUnsuccDl.BLER", snapshot.dl_bler_percent),
            ("DRB.PktUnsuccUl.BLER", snapshot.ul_bler_percent),
            ("RRU.PrbUsedDl.Proxy", snapshot.prb_utilization_percent_proxy),
            ("MM.HoExeSucc.Rate", snapshot.ho_success_rate_percent),
            ("UE.RsrpProxy.PuschSnrDb", snapshot.rsrp_proxy_pusch_snr_db),
        ]

        meas_types = "\n".join(
            f'      <measType p="{i + 1}">{escape(name)}</measType>'
            for i, (name, _) in enumerate(measurements)
        )
        meas_values = "\n".join(
            f'        <r p="{i + 1}">{"" if val is None else round(val, 3)}</r>'
            for i, (_, val) in enumerate(measurements)
        )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<measCollecFile xmlns="http://www.3gpp.org/ftp/specs/archive/32_series/32.435#measCollec">
  <fileHeader fileFormatVersion="32.435 V16.0" senderName="{escape(self._sender_name)}"
              vendorName="OCUDU-adapter" collectionBeginTime="{snapshot.timestamp}"/>
  <measData>
    <measInfo measInfoId="RAN_KPI_1">
      <granPeriod duration="PT10S" endTime="{snapshot.timestamp}"/>
      <repPeriod duration="PT10S"/>
{meas_types}
      <measValue measObjLdn="{escape(self._obj_ldn)}">
{meas_values}
      </measValue>
    </measInfo>
  </measData>
  <fileFooter>
    <measCollecEndTime endTime="{snapshot.timestamp}"/>
  </fileFooter>
</measCollecFile>
"""
