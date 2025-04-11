#!/bin/bash

# Activate virtual environment
source ~/cctv-system/venv/bin/activate

# Navigate to cctv-system directory
cd ~/cctv-system

# Create required directories
mkdir -p logs
mkdir -p events

# Start the camera analyzer in the background
python detector/camera_analyzer.py --config config/system.json &
ANALYZER_PID=$!

# Start the web interface
cd webui
python app.py &
WEBUI_PID=$!

# Function to handle script termination
function cleanup {
    echo "Stopping processes..."
    kill $ANALYZER_PID
    kill $WEBUI_PID
    wait
    echo "System stopped"
    exit
}

# Set up signal handling
trap cleanup SIGINT SIGTERM

# Wait for processes
echo "System running. Press Ctrl+C to stop."
wait
