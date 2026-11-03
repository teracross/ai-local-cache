# Vector database for the semantic cache.
FROM chromadb/chroma:latest

EXPOSE 8000
# Pure-bash TCP probe: no curl/python dependency in the image.
HEALTHCHECK --interval=5s --timeout=3s --retries=20 --start-period=5s \
  CMD bash -c 'echo > /dev/tcp/127.0.0.1/8000' || exit 1
