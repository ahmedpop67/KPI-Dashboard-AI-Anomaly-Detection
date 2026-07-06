#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 01_install_toolchain.sh
#
# Ubuntu 20.04 ships cmake 3.16 and gcc 9 by default. OCUDU (a continuation
# of srsRAN Project) needs a newer CMake and a C++17-capable compiler that's
# been tested more recently. This script brings both up to date WITHOUT
# reinstalling your whole OS.
#
# Safe to re-run.
# ---------------------------------------------------------------------------
set -e

echo "== Checking current versions =="
cmake --version || true
gcc --version || true

echo ""
echo "== Step 1: Add Kitware's official CMake APT repo =="
sudo apt-get update
sudo apt-get install -y ca-certificates gpg wget software-properties-common lsb-release

wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null | \
  gpg --dearmor - | sudo tee /usr/share/keyrings/kitware-archive-keyring.gpg >/dev/null

echo "deb [signed-by=/usr/share/keyrings/kitware-archive-keyring.gpg] https://apt.kitware.com/ubuntu/ focal main" | \
  sudo tee /etc/apt/sources.list.d/kitware.list

sudo apt-get update
sudo apt-get install -y cmake

echo ""
echo "== Step 2: Add ubuntu-toolchain-r PPA for a newer GCC =="
sudo add-apt-repository -y ppa:ubuntu-toolchain-r/test
sudo apt-get update
sudo apt-get install -y gcc-11 g++-11

echo ""
echo "== Step 3: Make gcc-11/g++-11 the default =="
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 110
sudo update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 110
sudo update-alternatives --set gcc /usr/bin/gcc-11
sudo update-alternatives --set g++ /usr/bin/g++-11

echo ""
echo "== Done. New versions: =="
cmake --version
gcc --version
g++ --version

echo ""
echo "If either command above still shows an old version, open a NEW terminal"
echo "(or run 'hash -r') so your shell picks up the updated PATH, then re-check."
