#!/bin/sh
# Boot Ollama in the background, pull the model, then keep the service in the foreground.
set -e

ollama serve &
SERVER_PID=$!

# Wait for the API to accept requests
until ollama list >/dev/null 2>&1; do
  sleep 1
done

echo "Pulling ${MODEL_NAME}..."
ollama pull "${MODEL_NAME}"
echo "Model ready."

# Keep the container alive for as long as the Ollama service runs
wait "$SERVER_PID"
