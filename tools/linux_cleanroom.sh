#!/bin/sh
set -eu
mkdir -p /results
{
  echo 'Clean OS baseline before application extraction'
  cat /etc/os-release
  uname -sm
  echo 'Installed packages:'
  dpkg-query -W
  echo 'Interpreter commands:'
  for tool in python python3 pip pip3 php node; do
    if command -v "$tool"; then echo "Unexpected installed interpreter: $tool"; exit 1; fi
  done
  echo 'No system Python/PHP/Node interpreter commands found.'
} > /results/baseline.txt
mkdir -p /test
tar -xzf /input/ShogiAnalyzer-v*-linux-amd64.tar.gz -C /test
if [ "${1:-}" = https ]; then
  env -i HOME=/tmp PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 \
    /test/ShogiAnalyzer/ShogiAnalyzer --engine-python /https-probe.py --output /results/https-probe.json
else
  env -i HOME=/tmp PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 \
    /test/ShogiAnalyzer/ShogiAnalyzer --engine-python /probe.py \
    --exe /test/ShogiAnalyzer/ShogiAnalyzer \
    --peer /peer.py --fixture /fixture.kif --output /results/probe.json
fi
{
  echo 'Interpreter commands after test:'
  for tool in python python3 pip pip3 php node; do
    if command -v "$tool"; then echo "Interpreter appeared: $tool"; exit 1; fi
  done
  echo 'No system interpreters were installed by the application.'
} > /results/after.txt
