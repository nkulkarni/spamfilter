#!/bin/bash

# Load environment variables
# source ~/.zshrc

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate venv and run script
cd "$SCRIPT_DIR"
source .venv/bin/activate
python -m spamfilter.processor
