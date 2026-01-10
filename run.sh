#!/bin/bash
# Startup script for AI Voice Dictation System
# Sets correct environment variables for cuDNN libraries

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if TTS Docker container is running, start if not
echo "Checking TTS Docker container..."
if ! docker ps | grep -q pda-voice; then
    echo "Starting PDA Voice TTS container..."
    docker start pda-voice 2>/dev/null || \
    docker run -d -p 5000:5000 --name pda-voice subnautica-pda-voice

    # Wait for container to be ready
    echo "Waiting for TTS to initialize..."
    sleep 2
fi
echo "✓ TTS ready"

# Activate virtual environment
source venv/bin/activate

# Set cuDNN library path - prioritize CTranslate2's bundled cuDNN for Whisper
CTRANSLATE2_LIBS="$SCRIPT_DIR/venv/lib/python3.10/site-packages/ctranslate2.libs"
NVIDIA_CUDNN="$SCRIPT_DIR/venv/lib/python3.10/site-packages/nvidia/cudnn/lib"
export LD_LIBRARY_PATH="$CTRANSLATE2_LIBS:$NVIDIA_CUDNN:$LD_LIBRARY_PATH"

# Suppress warning messages
export TOKENIZERS_PARALLELISM=false
export TF_CPP_MIN_LOG_LEVEL=3

# Run the dictation daemon
python dictation_daemon.py "$@"
