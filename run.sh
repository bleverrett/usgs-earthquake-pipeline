#!/bin/bash
set -e
if [ -z "$API_KEY" ]; then
    echo "[ERROR] API_KEY environment variable is not set."
    exit 1
fi
echo "Initializing Sandbox Virtual Environment..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "Running Test Suite..."
pytest
echo "Launching Master Workflow Process..."
python main.py
