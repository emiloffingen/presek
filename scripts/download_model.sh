#!/bin/bash
MODEL_DIR="models"
MODEL_FILE="gemma-2-2b-it-Q4_K_M.gguf"
URL="https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf"

mkdir -p $MODEL_DIR

echo "Downloading Gemma 2 2B (Q4_K_M) - ~1.6GB..."
echo "This will take a few minutes depending on your connection."

curl -L -C - "$URL" -o "$MODEL_DIR/$MODEL_FILE"

if [ $? -eq 0 ]; then
    echo "Download complete: $MODEL_DIR/$MODEL_FILE"
    ls -lh "$MODEL_DIR/$MODEL_FILE"
else
    echo "Download failed. Please check your internet connection and try again."
    exit 1
fi
