#!/bin/bash

# Activate virtual environment
source ~/cctv-system/venv/bin/activate

# Navigate to cctv-system directory
cd ~/cctv-system

# Create logs directory if it doesn't exist
mkdir -p logs

# Run camera analyzer
python detector/camera_analyzer.py --config config/system.json
