#!/bin/bash
#SBATCH --job-name=tcr_esm2_embed
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodelist=t04
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=/group/ohahnlab/OHahn/TCR_hackathon/logs/embed_%j.out
#SBATCH --error=/group/ohahnlab/OHahn/TCR_hackathon/logs/embed_%j.err

# ESM-2 Embedding Pipeline for TCR CDR3 Beta Sequences
# Expected: ~14K sequences, <5 minutes on RTX 4090

echo "=========================================="
echo "TCR ESM-2 Embedding Job"
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

# Run embedding script
python scripts/02_compute_embeddings.py \
    --data-dir $PROJECT_DIR/data \
    --output-dir $PROJECT_DIR/embeddings \
    --device cuda:0 \
    --batch-size 64

echo "=========================================="
echo "Job completed: $(date)"
echo "=========================================="
