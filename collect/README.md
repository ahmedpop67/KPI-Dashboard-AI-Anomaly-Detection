# Collecting KPI Data and Viewing it in Grafana

This covers the two final steps that turn the O1/NETCONF adapter's
output into a live Grafana dashboard: running the collector, then
wiring up the dashboard.

## Prerequisites

Before starting, these should already be running:
- Open5GS core, OCUDU gNB, srsUE (attached, generating traffic)
- The O1/NETCONF adapter (`o1-netconf-adapter-v2/main.py`)
- The InfluxDB + Grafana stack (`ran-kpi-monitor/docker-compose.yml`)

## Step 1: Install the collector's files

Copy these into your existing `o1-netconf-adapter-v2/collectors/` folder:
- `collect.py`
- `netconf_reader.py`
- `influx_writer.py`
- `__init__.py`

## Step 2: Run the collector

You can run it either way — both now work correctly:

```bash
# Option A: from inside the collectors/ folder
cd o1-netconf-adapter-v2/collectors
python3 collect.py

# Option B: from the project root, as a module
cd o1-netconf-adapter-v2
python3 -m collectors.collect
```

This polls the adapter's NETCONF `<get>` interface on a fixed interval
(default 10s, set in `config.yaml` under `influxdb.poll_interval_seconds`)
and writes each KPI snapshot into InfluxDB's `ran_kpis` measurement.

Leave this running in its own terminal.

**Verify it's working:**
```bash
docker exec -it ran-influxdb influx query \
  'from(bucket:"ran_kpis") |> range(start: -5m)' \
  --org ran-monitoring --token ran-kpi-super-secret-admin-token
```
You should see rows with real, non-null values for `cqi_avg`,
`dl_bler_percent`, etc. — not just empty results.

## Step 3: Update the Grafana datasource

Replace `ran-kpi-monitor/grafana/provisioning/datasources/influxdb.yml`
with the updated version here — it adds an explicit `uid: influxdb-ran`
field the dashboard needs to reference the datasource reliably.

## Step 4: Add the dashboard

Copy `ran_kpi_dashboard.json` into
`ran-kpi-monitor/grafana/provisioning/dashboards/`.

## Step 5: Restart Grafana so it picks up both files

```bash
cd ran-kpi-monitor
docker compose restart grafana
```

## Step 6: View it

Open `http://localhost:3000` (login: `admin` / whatever you set in
`ran-kpi-monitor/.env`). The **"RAN KPI Monitoring"** dashboard should
appear automatically under Dashboards, with 6 panels:

| Panel | Shows |
|---|---|
| CQI (Average) | Direct from OCUDU |
| DL / UL BLER (%) | Derived from real HARQ counters |
| PRB Utilization (Proxy, %) | Approximated — see main project README |
| HO Success Rate (%) | Aggregate, whole-gNB |
| RSRP Proxy (PUSCH SNR, dB) | Not real RSRP — see main project README |
| Anomaly Alerts | Empty until the ML detectors (next step) are running |

Refresh interval is set to 10s, so panels should update live as long as
the collector keeps running and traffic keeps flowing through the UE.

## If a panel shows "No data"

Most likely causes, in order of likelihood:
1. The collector isn't running, or crashed — check its terminal for errors
2. No traffic is flowing through `tun_srsue` right now (KPIs only get
   written when the gNB has something to schedule) — try `ping -I
   tun_srsue 192.168.100.1 -c 20` and watch the panels update
3. The datasource `uid` in the dashboard JSON (`influxdb-ran`) doesn't
   match what's actually provisioned — check under **Connections → Data
   sources** in Grafana's UI that a datasource with that exact UID exists

## Fixed bug: `FileNotFoundError: config.yaml`

If you see this error running `collect.py`, `main.py`, or either ML
detector script, you have an older copy — a `pathlib` quirk meant
`Path('.').parent` didn't actually climb a directory when a script was
run with a bare relative filename (`python3 collect.py`, as opposed to
`python3 -m collectors.collect`). Fixed by resolving to an absolute path
first (`.resolve()`) before computing parent directories. Re-download the
affected file(s) if you still hit this — both ways of running the
collector now work correctly (see Step 2 above).

## What's next

Once panels are populated with real, moving data, the next step is the
ML anomaly detection layer (`ml-anomaly-detection/`) — its output feeds
the "Anomaly Alerts" panel above.





# RAN KPI Anomaly Detection 

Two complementary anomaly detectors reading from InfluxDB (written by the
Week 3-4 collector) and writing flags back into InfluxDB for Grafana to
display:

- **Isolation Forest** (+ per-KPI z-score) — point anomalies: BLER spikes,
  PRB saturation, HO failure surges
- **LSTM Autoencoder** — drift: gradual degradation that never crosses a
  hard threshold at any single instant

## Prerequisites

The Week 3-4 collector must already be running and writing to InfluxDB's
`ran_kpis` measurement — these detectors read from that data, they don't
generate their own.

## Install

```bash
cd ml-anomaly-detection
pip install -r requirements.txt --break-system-packages
```

(This installs PyTorch — expect a sizeable download.)

## Isolation Forest

### Why this isn't "just" Isolation Forest — an honest finding from testing

During development, pure multivariate Isolation Forest across all 6 KPI
dimensions was tested against synthetic data with deliberately injected
single-KPI spikes (BLER jumping from ~2% to 45%, all other KPIs held
normal). **It reliably failed to flag these as anomalies.**

This isn't a bug — it's verified as a genuine, documented characteristic
of Isolation Forest: with many features where only one is extreme, random
per-split feature selection "dilutes" the isolation signal. This was
confirmed by direct tree-path-length inspection (the outlier's average
path length across 200 trees was only marginally shorter than a normal
point's — 7.30 vs 7.99, both near the same depth ceiling), and by testing
the same feature in isolation (correctly flagged as anomalous alone).
Extensive hyperparameter search did not fix this — the effect is
structural, related to the curse of dimensionality, not a tuning problem.

**The fix**, and standard practice in real telecom/RAN anomaly detection
for exactly this reason: combine Isolation Forest (for genuine
correlated/joint shifts across multiple KPIs — its actual strength) with
simple per-KPI z-score thresholds (for single-metric spikes). This hybrid
was tested against the same synthetic scenario that broke pure Isolation
Forest and **correctly caught all 3 injected anomalies (BLER spike, PRB
saturation, HO failure surge) with zero false positives** among 17
genuinely normal points. It was also verified to catch a genuine joint
anomaly (low CQI + high PRB utilization simultaneously, each individually
within normal range) that a pure z-score approach alone would miss.

See `isolation_forest/detector.py`'s module docstring for the full
technical explanation.

### Run

```bash
python3 -m isolation_forest.run
```

Options (see `--help` for all): `--baseline-lookback` (default 24h),
`--score-interval-seconds` (default 60), `--retrain-every-n-cycles`
(default 60, so the model adapts to slow legitimate changes over time).

First run needs enough baseline history in InfluxDB — if you've only just
started the collector, either wait or use a shorter `--baseline-lookback`
to match what you actually have (e.g. `--baseline-lookback -30m`).

## LSTM Autoencoder

### Verified behavior

Tested on synthetic data before being wired to InfluxDB: trained on a
stable baseline pattern (mild realistic noise around a periodic signal),
then scored against two scenarios:
- **Normal continuation** (same pattern): 0% flagged as drift, mean
  reconstruction error 0.72 — well below the computed threshold of 1.28
- **Gradual drift** (PRB utilization slowly climbing to saturation over
  ~15 minutes): reconstruction error climbed smoothly from 0.85 to 21 as
  the drift progressed, correctly crossing the mu+3sigma threshold
  partway through, with 100% of the final 20 windows correctly flagged
  as drift

This confirms the detector distinguishes "normal variation" from
"genuine gradual degradation" as intended, not just reacting to noise.

### Run

```bash
python3 -m lstm_autoencoder.run
```

Options: `--sequence-length` (default 12 samples = 2min at 10s
intervals), `--epochs` (default 50), `--score-lookback` (default 10min —
needs enough samples for at least one full window).

## What gets written back to InfluxDB

Both detectors write to a `ran_kpi_anomalies` measurement, tagged by
`detector` (`isolation_forest` or `lstm_autoencoder`) so you can tell
point anomalies apart from drift without needing separate measurements.
The Grafana dashboard's "Anomaly Alerts" panel already queries this
measurement.

| Field | Meaning |
|---|---|
| `is_anomaly` | boolean flag |
| `score` | Isolation Forest: decision function value (more negative = more anomalous). LSTM: reconstruction error (higher = more anomalous) |

## Architecture

```
InfluxDB (ran_kpis)
        |
   +----+-----+
   v          v
Isolation   LSTM
Forest      Autoencoder
   |          |
   +----+-----+
        v
InfluxDB (ran_kpi_anomalies)
        |
        v
    Grafana (Anomaly Alerts panel)
```

`shared/influx_query.py` and `shared/anomaly_writer.py` are used by both
detectors, so the InfluxDB read/write logic stays in one place.

## What was actually tested before delivery

- Isolation Forest: tree-path-length inspection to diagnose a real
  limitation, then hybrid approach verified against injected single-KPI
  spikes AND a genuine joint anomaly, with zero false positives on normal
  data
- LSTM Autoencoder: verified against both normal continuation (should
  NOT flag) and synthetic gradual drift (SHOULD flag, with error climbing
  smoothly as designed)
- Both detectors' NaN/missing-data handling tested explicitly

## Known limitations

- HO Success Rate is aggregate (whole gNB), not per-UE — inherited from
  what OCUDU exposes (see the O1/NETCONF adapter's README)
- PRB utilization and RSRP are approximated proxies, not true values —
  same inherited limitation
- The LSTM Autoencoder's `--retrain-every-n-cycles` re-trains on a fresh
  baseline window periodically, but there's no drift-in-the-baseline-
  itself protection — if genuinely bad behavior persists long enough to
  dominate a new baseline window, it could get "normalized" into the
  model. For a portfolio/learning project this is an acceptable and
  worth-explaining limitation; a production system would want a
  human-reviewed baseline approval step before each re-train.

## What's next

This completes all 8 weeks of the original project plan: storage/
visualization -> real KPI collection via O1/NETCONF -> point anomaly
detection -> drift detection. From here, natural extensions (not built,
but realistic next steps if you want them): an alerting layer
(Email/Slack/Webhook) triggered off the `ran_kpi_anomalies` measurement,
and a Grafana alert rule wired to the same data.
