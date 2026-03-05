#!/bin/bash
# Deploy and submit DecoderTCR expanded scoring job on CB2
# Run this from the project directory once VPN is connected
#
# Scores 35,126 new TCRs (PDAC + VDJdb) x 14 epitopes = 491,764 pairs
# Skips 3,808 TCRAFT TCRs already scored in job 15093399
# Estimated runtime: ~14 hours on RTX 4090

set -e
cd "$(dirname "$0")/.."
PROJECT_DIR=$(pwd)
CB2_DIR=/group/ohahnlab/OHahn/TCR_hackathon

echo "=========================================="
echo "Deploying DecoderTCR Expanded Scoring"
echo "=========================================="

# 1. Verify CB2 connectivity
echo ""
echo "1. Testing CB2 connection..."
ssh -o ConnectTimeout=5 cb2 "echo 'CB2 connected: $(hostname)'" || {
    echo "ERROR: Cannot connect to CB2. Are you on VPN?"
    exit 1
}

# 2. Ensure remote directories exist
echo ""
echo "2. Creating remote directories..."
ssh cb2 "mkdir -p $CB2_DIR/data/processed $CB2_DIR/predictions $CB2_DIR/logs"

# 3. Sync data files
echo ""
echo "3. Syncing tcr_database.parquet to CB2..."
rsync -avP $PROJECT_DIR/data/processed/tcr_database.parquet \
    cb2:$CB2_DIR/data/processed/

# 4. Sync scripts
echo ""
echo "4. Syncing scoring scripts..."
rsync -avP $PROJECT_DIR/scripts/03_decoder_tcr_scoring.py \
    $PROJECT_DIR/scripts/submit_decoder_scoring.sh \
    cb2:$CB2_DIR/scripts/

# 5. Sync existing predictions (so skip-scored works)
echo ""
echo "5. Syncing existing predictions (for skip-scored)..."
rsync -avP $PROJECT_DIR/predictions/decoder_tcr_scores.csv \
    $PROJECT_DIR/predictions/decoder_tcr_scores_long.csv \
    cb2:$CB2_DIR/predictions/

# 6. Submit SLURM job
echo ""
echo "6. Submitting SLURM job..."
JOB_ID=$(ssh cb2 "cd $CB2_DIR && sbatch scripts/submit_decoder_scoring.sh" | grep -o '[0-9]*')
echo "   Job submitted: $JOB_ID"

# 7. Verify
echo ""
echo "7. Verifying job status..."
ssh cb2 "squeue -j $JOB_ID -o '%.18i %.12j %.8T %.10M %.9l %.6D %R'"

echo ""
echo "=========================================="
echo "Job $JOB_ID submitted successfully!"
echo ""
echo "Monitor with:"
echo "  ssh cb2 'squeue -u ohahn'"
echo "  ssh cb2 'tail -f $CB2_DIR/logs/decoder_${JOB_ID}.out'"
echo ""
echo "When done, sync results:"
echo "  bash scripts/sync_predictions.sh"
echo "=========================================="
