#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 03_install_srsue.sh
#
# OCUDU (like srsRAN Project before it) is a gNB only — it has no UE
# application. The srsUE simulated-phone app still lives in the separate
# srsRAN_4G repo, which was NOT part of the OCUDU migration and remains
# actively maintained on its own. This builds just srsUE with ZMQ support.
# ---------------------------------------------------------------------------
set -e

echo "== Step 1: Install srsRAN_4G build dependencies =="
sudo apt-get update
sudo apt-get install -y \
  cmake make gcc g++ pkg-config \
  libfftw3-dev libmbedtls-dev libboost-program-options-dev \
  libconfig++-dev libsctp-dev \
  libzmq3-dev

echo ""
echo "== Step 2: Clone srsRAN_4G =="
cd "$HOME"
if [ ! -d srsRAN_4G ]; then
  git clone https://github.com/srsran/srsRAN_4G.git
fi
cd srsRAN_4G

echo ""
echo "== Step 3: Build (UE only needs the shared libs + srsue target) =="
mkdir -p build
cd build
cmake ../
make -j"$(nproc)" srsue

echo ""
echo "== Build complete =="
echo "srsUE binary should be at: $HOME/srsRAN_4G/build/srsue/src/srsue"
ls -la "$HOME/srsRAN_4G/build/srsue/src/srsue" 2>/dev/null || \
  echo "WARNING: srsue binary not found where expected — check the build log above for errors."
