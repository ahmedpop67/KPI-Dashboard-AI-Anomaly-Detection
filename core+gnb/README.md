# OCUDU + Open5GS + srsUE Testbed — Ubuntu 20.04 / VirtualBox

This gets you a real, working mini 5G network (no SDR hardware needed) so
the RAN KPI monitoring project has genuine live data to collect, instead of
simulated numbers. Since this is your first time working with RAN software,
**follow the stages in order and confirm each checkpoint before moving on.**
Trying to debug all three components at once is the #1 reason people give
up on this kind of setup.

## Before you start
- Ubuntu 20.04 VM in VirtualBox, with VT-x/nested virtualization enabled,
  at least 4 vCPUs and 8GB RAM assigned
- This is a multi-hour (possibly multi-day) task the first time. That's
  normal for RAN testbeds — it's not a sign something's wrong.

## Stage 1 — Fix the toolchain
```bash
chmod +x scripts/01_install_toolchain.sh
./scripts/01_install_toolchain.sh
```
✅ **Checkpoint:** `cmake --version` shows ≥3.22, `gcc --version` shows 11.

## Stage 2 — Stand up the 5G core (Open5GS)
Follow `docker_open5gs_patch/README_PATCH.md` in full.

✅ **Checkpoint:** `docker compose ps` shows AMF/SMF/UPF running, no
crash-restart loops in `docker compose logs -f amf`.

## Stage 3 — Build OCUDU (the gNB)
```bash
chmod +x scripts/02_install_ocudu.sh
./scripts/02_install_ocudu.sh
```
✅ **Checkpoint:** `~/ocudu/build/apps/gnb/gnb` exists and running
`./gnb --version` (from that directory) prints a version instead of erroring.

## Stage 4 — Point the gNB at your core and start it
Edit `config/gnb_zmq.yaml`: set `amf.addr` to your Open5GS AMF's real IP
address (find it with `docker network inspect <network-name>`).

```bash
sudo ~/ocudu/build/apps/gnb/gnb -c config/gnb_zmq.yaml
```
✅ **Checkpoint:** logs show an **NGSetupResponse** from the AMF — this
means the gNB and core successfully found each other. If instead you see
repeated connection refused/timeout, the core isn't reachable at that IP —
go back to Stage 2 before touching the UE.

## Stage 5 — Build and run srsUE (the simulated phone)
```bash
chmod +x scripts/03_install_srsue.sh
./scripts/03_install_srsue.sh
```
Confirm your subscriber (IMSI/K/OPC) was registered in Open5GS's WebUI
(Stage 2, step 6), then, with the gNB still running:
```bash
sudo ~/srsRAN_4G/build/srsue/src/srsue config/ue_zmq.conf
```
✅ **Checkpoint:** srsUE logs show **RRC Connected**, then a **PDU Session
Establishment successful** message with an assigned IP (e.g. `10.45.0.2`).
This means the UE is now fully attached, end to end.

## Stage 6 — Generate real traffic so KPIs actually move
With everything attached, run some traffic through the UE's assigned IP
(e.g. `iperf3` between the UE's TUN interface and a server on your core's
network) so RSRP/CQI/BLER/PRB actually fluctuate instead of sitting idle.

## Stage 7 — Confirm KPI metrics are being written
```bash
tail -f /tmp/ocudu_gnb_metrics.json
```
✅ **Checkpoint:** you see JSON lines streaming in with fields like `cqi`,
`dl_mcs`, `dl_nof_ok`/`dl_nof_nok`, `pusch_snr_db`, etc.

## What's next
Once you can `tail -f` real metrics from a live UE attach, the project is
back on track for **Weeks 3–4**: a Python collector that tails this JSON
file and writes KPI points into InfluxDB, the same as if we were parsing
O1 PM XML files. Come back and we'll build that collector next.

## If you get stuck
Tell me exactly which checkpoint failed and paste the relevant log lines —
that narrows down which of the three layers (core / gNB / UE) needs
attention, rather than guessing across the whole stack.
