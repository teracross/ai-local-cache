# Local AI runtime: Ollama serving qwen3.5:0.8b for embeddings and generation.
FROM ollama/ollama:latest

ENV MODEL_NAME=qwen3.5:0.8b
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 11434
# Healthy only once the model has been pulled
HEALTHCHECK --interval=10s --timeout=10s --retries=60 --start-period=20s \
  CMD ollama list | grep -q "qwen3.5:0.8b" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
