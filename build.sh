#!/usr/bin/env bash
set -e

pip install pygbag
python -m pygbag --template custom.tmpl --build .
