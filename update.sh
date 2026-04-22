#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SERVICE_NAME="uniqlo-alerter"

echo "Pulling latest changes..."
git pull

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing updated dependencies..."
pip install -e . --quiet

if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "Restarting $SERVICE_NAME service..."
    sudo systemctl restart "$SERVICE_NAME"
    echo "Service restarted."
else
    echo "No running $SERVICE_NAME service found — skip restart."
    echo "Start manually with: python -m uniqlo_sales_alerter"
fi

echo "Update complete."
