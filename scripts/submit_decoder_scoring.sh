#!/bin/bash
#SBATCH --job-name=tcr_decoder
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodelist=t04
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=/group/ohahnlab/OHahn/TCR_hackathon/logs/decoder_%j.out
#SBATCH --error=/group/ohahnlab/OHahn/TCR_hackathon/logs/decoder_%j.err

# DecoderTCR Scoring: ~35,126 new TCRs x 14 epitopes = ~492K pairs
# (skipping 3,808 TCRAFT TCRs already scored in job 15093399)
# Expected: ~14 hours on RTX 4090 at ~10 pairs/sec
# Checkpoints saved every 1000 TCRs for crash recovery

echo "=========================================="
echo "DecoderTCR Scoring Job (Expanded Dataset)"
echo "Date: $(date)"
echo "Node: $(hostname)"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
echo "=========================================="

# Activate environment
eval "$(conda shell.bash hook)"
conda activate tcr-embed

# Set paths
PROJECT_DIR=/group/ohahnlab/OHahn/TCR_hackathon
cd $PROJECT_DIR

# Ensure log directory exists
mkdir -p $PROJECT_DIR/logs

# Set torch hub dir for ESM model caching
export TORCH_HUB_DIR=$PROJECT_DIR/models/torch_hub

# Run scoring with skip-scored to avoid re-scoring TCRAFT TCRs
python scripts/03_decoder_tcr_scoring.py \
    --data-dir $PROJECT_DIR/data \
    --output-dir $PROJECT_DIR/predictions \
    --checkpoint $PROJECT_DIR/models/650M_DecoderTCR.ckpt \
    --device cuda:0 \
    --skip-scored \
    --checkpoint-interval 1000

echo "=========================================="
echo "Job completed: $(date)"
echo "=========================================="
