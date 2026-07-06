# RAN KPI Monitor — Weeks 1–2: InfluxDB + Grafana Stack

This stands up the storage + visualization foundation for the project:
**InfluxDB 2.7** (time-series storage) + **Grafana 10** (dashboards), pre-wired
together so Grafana can query InfluxDB with zero manual UI setup.

## Prerequisites
- Docker Desktop (or Docker Engine) installed
- Docker Compose v2 (`docker compose`, bundled with modern Docker Desktop)

## 1. Start the stack

```bash
cd ran-kpi-monitor
docker compose up -d
```

This will:
- Pull `influxdb:2.7` and `grafana/grafana:10.4.2`
- Auto-initialize InfluxDB with an org, bucket, and admin token (from `.env`)
- Auto-provision Grafana with an InfluxDB data source already configured

## 2. Verify it's running

```bash
docker compose ps
```

Both `ran-influxdb` and `ran-grafana` should show `healthy`/`running`.

## 3. Log in

| Service   | URL                     | Username | Password (from `.env`) |
|-----------|-------------------------|----------|-------------------------|
| InfluxDB  | http://localhost:8086   | admin    | changeme123             |
| Grafana   | http://localhost:3000   | admin    | changeme123             |

In Grafana, go to **Connections → Data sources** — you should already see
**InfluxDB-RAN** listed and connected. No setup needed there.

## 4. Change default credentials (recommended)

Before doing anything beyond local testing, edit `.env` and change:
- `INFLUXDB_PASSWORD`
- `INFLUXDB_ADMIN_TOKEN`
- `GRAFANA_PASSWORD`

Then restart: `docker compose down && docker compose up -d`

## 5. Where data lives

- `./data/influxdb` — InfluxDB's on-disk time-series data
- `./data/grafana` — Grafana's dashboards/users/settings DB

Both are bind-mounted so your data survives `docker compose down` (but not
if you delete the `./data` folder).

## 6. Stopping

```bash
docker compose down        # stop containers, keep data
docker compose down -v     # stop and wipe volumes (fresh start)
```

## Project structure

```
ran-kpi-monitor/
├── docker-compose.yml
├── .env                                  # credentials & config
├── data/
│   ├── influxdb/                         # InfluxDB data (gitignored)
│   └── grafana/                          # Grafana data (gitignored)
└── grafana/
    └── provisioning/
        ├── datasources/influxdb.yml      # auto-connects Grafana → InfluxDB
        └── dashboards/dashboards.yml     # auto-loads dashboards dropped here later
```

## What's next (Weeks 3–4)

Once this is up and you can log into both UIs, the next step is writing the
Python KPI collector that parses srsRAN O1 PM XML files and writes points
into the `ran_kpis` bucket using `influxdb-client`. Let me know when you're
ready and we'll build that.
