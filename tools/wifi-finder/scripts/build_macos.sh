#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
.build-venv/bin/python scripts/build_native.py
