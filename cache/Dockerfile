# Exact-match cache: ephemeral Redis, no persistence, LRU eviction, 256 MB cap.
FROM redis:alpine

# Redis has no global "max TTL" setting; the 30-day TTL is applied by the server
# on every SET/refresh (see server/main.py, CACHE_TTL_SECONDS).
EXPOSE 6379
HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD redis-cli ping | grep -q PONG || exit 1

# --save "" and --appendonly no => strictly ephemeral (nothing written to disk)
CMD ["redis-server", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru", "--save", "", "--appendonly", "no"]
