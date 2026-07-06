#!/usr/bin/env bash
# run.sh — Starts the O1/NETCONF adapter.
#
# Assumes your OCUDU gNB, Open5GS core, and srsUE are already running —
# this script does not start or manage any of those.
set -e
cd "$(dirname "$0")"
python3 main.py
