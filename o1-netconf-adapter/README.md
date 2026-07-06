# O1/NETCONF Adapter for OCUDU

A modular, production-structured adapter that bridges OCUDU's native
WebSocket JSON metrics into two O1-inspired management interfaces:
3GPP-32.435-style PM XML files and a NETCONF `<get>` server.

**This connects to YOUR real, already-running OCUDU gNB.** It does not
simulate, mock, or generate any metrics — if the gNB isn't running or
unreachable, this adapter will log connection errors and keep retrying,
never fall back to fake data.

## Architecture

```
OCUDU gNB (real WebSocket) → OCUDUClient → OCUDUParser → KPIState
                                                              │
                                                        (Scheduler tick)
                                                              │
                                                          KPIEngine
                                                              │
                                              ┌───────────────┴───────────────┐
                                       PMXMLExporter                  NetconfServer
                                              │                               │
                                       O1 PM XML files              NETCONF <get>
```

Each layer has one responsibility:

| Module | Responsibility |
|---|---|
| `adapter/metrics_adapter.py` | `OCUDUClient` — real WebSocket connection, reconnect logic |
| `parser/ocudu_parser.py` | `OCUDUParser` — tolerant JSON → typed `ParsedMetricPoint` |
| `core/kpi_state.py` | `KPIState` — thread-safe raw counter accumulation only |
| `core/kpi_engine.py` | `KPIEngine` — pure KPI math (BLER, HO rate, etc.) |
| `core/scheduler.py` | `Scheduler` — periodic tick, notifies subscribers |
| `exporters/pm_xml_exporter.py` | `PMXMLExporter` — PM XML files with rotation |
| `exporters/netconf_server.py` | `NetconfServer` — NETCONF `<get>` over SSH |
| `models/ran_kpi.py` | Shared typed dataclasses used across all layers |
| `main.py` | Composition root — wires everything via dependency injection |

No circular imports: `core/` and `models/` know nothing about
`exporters/` or `adapter/`; `main.py` is the only place that imports
everything and wires it together.

## Prerequisites

Your existing deployment must already be running:
- Open5GS core
- OCUDU gNB (with `remote_control.enabled: true`, matching your existing
  `gnb_zmq.yaml`)
- srsUE, attached

This adapter is only responsible for consuming metrics from your gNB — it
does not start, manage, or replace any of these.

## Install

```bash
cd o1-netconf-adapter
pip install -r requirements.txt --break-system-packages
```

## Configure

Edit `config.yaml` — in particular confirm `ocudu.websocket_url` matches
your gNB's actual `remote_control` address (default: `ws://127.0.0.1:8001`,
matching the setup from earlier in this project).

## Run

```bash
chmod +x run.sh
./run.sh
```

or directly: `python3 main.py`

You'll see structured log output (via Python's `logging` module, not
`print`) as it connects, subscribes, and starts producing snapshots every
`reporting.interval_seconds`.

## Verify it's working

**PM XML files:**
```bash
ls -la /tmp/o1_pm_files/
cat /tmp/o1_pm_files/$(ls -t /tmp/o1_pm_files/ | head -1)
```

**NETCONF `<get>`** (raw SSH subsystem test, no extra client library needed):
```bash
{
  printf '<?xml version="1.0" encoding="UTF-8"?>\n<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"><capabilities><capability>urn:ietf:params:netconf:base:1.0</capability></capabilities></hello>\n]]>]]>'
  sleep 1
  printf '<?xml version="1.0" encoding="UTF-8"?>\n<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="1"><get/></rpc>\n]]>]]>'
  sleep 1
} | ssh -s admin@127.0.0.1 -p 8830 netconf
```
(password: `admin`, matching `config.yaml`)

**Or with `ncclient`** (a proper NETCONF Python client, useful for
scripting):
```bash
pip install ncclient --break-system-packages
python3 -c "
from ncclient import manager
with manager.connect(host='127.0.0.1', port=8830, username='admin',
                      password='admin', hostkey_verify=False,
                      device_params={'name': 'default'}) as m:
    print(m.get())
"
```

## Generate traffic so KPIs actually move

Same as earlier in the project:
```bash
ping -I tun_srsue 192.168.100.1 -c 50
```

## KPI mapping — what's real vs. approximated

Read `core/kpi_engine.py`'s module docstring for the full explanation.
Summary:

| KPI | Status |
|---|---|
| CQI | Direct from OCUDU |
| DL/UL BLER | Derived from real HARQ ok/nok counters |
| HO Success Rate | Derived from real cumulative NGAP counters (aggregate, not per-UE) |
| PRB utilization | **Approximated proxy** — based on scheduling activity, not a true PRB-count counter |
| RSRP | **Not real RSRP** — proxy using PUSCH SNR, since true RSRP needs UE measurement reports not present in this metrics stream |

If a future OCUDU version renames a JSON field, update
`parser/ocudu_parser.py`'s `_parse_ue_metrics()` / `_parse_cu_cp_metrics()`
— nothing else in the pipeline needs to change, since every other layer
only ever sees the normalized `ParsedMetricPoint` / `RanKpiSnapshot` types.

## Known limitations (intentional scope decisions)

This project intentionally does **not** include, given the scope of a
solo learning/portfolio project:

- **Full YANG-validated datastore** — the NETCONF server supports `<get>`,
  `<get-config>`, and `<close-session>` against an in-memory snapshot, not
  a real `<edit-config>`-capable YANG datastore (e.g. via sysrepo).
- **Docker packaging** — this runs as a plain Python process alongside
  your existing native OCUDU/Open5GS/srsUE setup, not containerized.
- **pytest suite** — validated via manual integration testing during
  development (see below), not an automated test suite.
- **Multi-UE aggregation** — targets the single simulated UE from this
  project's testbed, not a multi-UE production deployment.

If you want any of these added, they're realistic follow-ups — just ask.

## What was actually tested before delivery

Rather than ship untested code, every layer here was verified working
end-to-end before being handed off:
- Parser tested against real OCUDU-shaped JSON (including malformed and
  unrecognized message types, confirming it degrades gracefully rather
  than crashing)
- KPI math verified against hand-computed expected values
- PM XML output validated as well-formed
- **NETCONF server tested with a real SSH client performing a full
  `<hello>` → `<get>` → `<close-session>` round trip** over actual SSH
  transport (not just unit-level string checks) — this caught and fixed
  a real asyncssh API incompatibility (`process_factory` receives a
  single `SSHServerProcess` object in the installed asyncssh version,
  not separate `stdin`/`stdout`/`stderr` arguments) before you'd have
  hit it yourself.

## What's next

Once you've confirmed PM XML files and NETCONF `<get>` return real, moving
KPI values from your gNB, we're ready for the actual Week 3-4 deliverable:
a Python collector that reads from *this* adapter and writes points into
InfluxDB — the `collectors/influx_collector.py` piece, intentionally
built as its own next step rather than bundled in here.
