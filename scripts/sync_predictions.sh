#!/bin/bash
# Sync DecoderTCR predictions from CB2 and regenerate frontend data
# Run this after the scoring job completes on CB2

set -e
cd "$(dirname "$0")/.."

echo "Syncing DecoderTCR predictions from CB2..."
rsync -avP cb2:/group/ohahnlab/OHahn/TCR_hackathon/predictions/ predictions/

echo ""
echo "Regenerating frontend data with predictions..."
source venv/bin/activate
python scripts/05_export_frontend_data.py

echo ""
echo "Done! Predictions integrated into frontend."
echo "Restart the frontend to see predictions."
