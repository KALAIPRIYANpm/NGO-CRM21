#!/bin/sh
cd "$(dirname "$0")"
echo "Sample data: open http://127.0.0.1:8021  (admin / ChangeMe123)"
python3 run.py --demo --port 8021
