#!/usr/bin/env bash
# Downloads the Intuit QuickBooks hackathon dataset and extracts it to data/raw/hackathon-100
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw
if [ ! -d data/raw/hackathon-100 ]; then
  curl -sL -o data/hackathon-100-participant.tar.gz \
    "https://huggingface.co/datasets/CL251215/QuickBooks-Hackathon-2026/resolve/main/hackathon-100-participant.tar.gz"
  tar -xzf data/hackathon-100-participant.tar.gz -C data/raw
fi
echo "dataset at data/raw/hackathon-100 ($(ls data/raw/hackathon-100 | grep -c company-) companies)"
