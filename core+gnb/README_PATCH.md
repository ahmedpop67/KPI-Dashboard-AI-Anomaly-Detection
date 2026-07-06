# Setting up the Open5GS 5G Core

OCUDU only builds the gNB. For the UE to attach and generate real traffic
(and therefore real KPIs), you need a 5G core network. The most reliable
path for a first-timer is the community "docker_open5gs" project, which
bundles Core + RAN build scripts + UE together over Docker.

## 1. Get the repo

```bash
git clone https://github.com/herlesupreeth/docker_open5gs
cd docker_open5gs
```

## 2. Patch it to use OCUDU instead of the archived srsRAN_Project

This repo predates the OCUDU rename, so its `srsran/Dockerfile` still
points at the old, archived `github.com/srsran/srsRAN_Project`. Edit
`srsran/Dockerfile` and change the git source:

```diff
- git clone https://github.com/srsran/srsRAN_Project.git
+ git clone https://gitlab.com/ocudu/ocudu.git
```

Also confirm the build command in that same Dockerfile includes:
```
cmake ../ -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON
```

## 3. Build the core network image only (skip RAN/UE images for now)

```bash
cd base
docker build --no-cache --force-rm -t docker_open5gs .
cd ..
```

We're building the core by itself first, deliberately, so you can confirm
it comes up healthy before adding the gNB or UE into the mix.

## 4. Configure `.env`

Copy the sample `.env` in the repo root and set at minimum:
- `MCC` = `001`, `MNC` = `01` (must match `plmn: "00101"` in `gnb_zmq.yaml`)
- `DOCKER_HOST_IP` = your VM's IP (check with `ip addr`)

## 5. Bring up just the core

```bash
docker compose -f sa-deploy.yaml up -d 5gc   # adjust service name if it differs
docker compose ps
```

Check logs for the AMF, SMF, and UPF specifically — you want to see them
report as running/healthy with no crash loops before moving on:

```bash
docker compose logs -f amf
```

## 6. Register your test subscriber

Open the WebUI (`http://<DOCKER_HOST_IP>:9999`, login `admin`/`1423`) and
add a subscriber with the **same** IMSI/K/OPC values used in
`config/ue_zmq.conf`:
- IMSI: `001010123456789`
- K: `00112233445566778899aabbccddeeff`
- OPC: `63bfa50ee6523365ff14c1f45f88737d`

## 7. Only once the core is confirmed healthy

Move on to building OCUDU (`scripts/02_install_ocudu.sh`) and pointing
`config/gnb_zmq.yaml`'s `amf.addr` at your core's actual AMF IP (replace
the placeholder `10.53.1.2` if your Docker network assigns something else
— check with `docker network inspect`).

Do NOT try to bring up core + gNB + UE all at once on your first attempt.
Verify each layer is alive on its own first — it's the only way to know
which layer to debug if something doesn't connect.
