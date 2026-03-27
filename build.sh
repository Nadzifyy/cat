#!/usr/bin/env bash
set -e

pip install pygbag
python -m pygbag --build .
