#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 02_install_ocudu.sh
#
# Installs build dependencies and builds OCUDU (the project formerly known
# as srsRAN Project) from source, with the ZeroMQ RF driver enabled so you
# can run a gNB without any SDR hardware.
#
# Run 01_install_toolchain.sh FIRST, in a fresh terminal, before this script.
# ---------------------------------------------------------------------------
set -e

echo "== Step 1: Install OCUDU build dependencies =="
sudo apt-get update
sudo apt-get install -y \
  make pkg-config \
  libmbedtls-dev libsctp-dev libyaml-cpp-dev libgtest-dev \
  libfftw3-dev \
  git

echo ""
echo "== Step 2: Install ZeroMQ (RF driver dependency) =="
sudo apt-get install -y libzmq3-dev

# czmq isn't always in the default Ubuntu 20.04 repos at a new enough version,
# so we build it from source to be safe.
if [ ! -d /tmp/czmq-build ]; then
  mkdir -p /tmp/czmq-build
  cd /tmp/czmq-build
  git clone https://github.com/zeromq/czmq.git
  cd czmq
  ./autogen.sh
  ./configure
  make -j"$(nproc)"
  sudo make install
  sudo ldconfig
fi

echo ""
echo "== Step 3: Clone OCUDU =="
cd "$HOME"
if [ ! -d ocudu ]; then
  git clone https://gitlab.com/ocudu/ocudu.git
fi
cd ocudu

echo ""
echo "== Step 4: Build OCUDU with ZMQ + export enabled =="
mkdir -p build
cd build
cmake ../ -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON -DBUILD_TESTING=OFF

echo ""
echo ">>> IMPORTANT: scroll up and check the cmake output above for a line like:"
echo ">>>   -- Found libZEROMQ: /usr/local/include, /usr/local/lib/libzmq.so"
echo ">>> If it instead says 'No package ZeroMQ found', STOP and fix that before"
echo ">>> continuing — the gNB will build but silently lack ZMQ support."
echo ""
read -p "Press Enter once you've confirmed ZMQ was found correctly..."

make -j"$(nproc)"

echo ""
echo "== Build complete =="
echo "gNB binary should be at: $HOME/ocudu/build/apps/gnb/gnb"
ls -la "$HOME/ocudu/build/apps/gnb/gnb" 2>/dev/null || \
  echo "WARNING: gnb binary not found where expected — check the build log above for errors."
