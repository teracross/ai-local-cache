# ai-local-cache

A local, privacy-first hybrid AI router with semantic caching.

## Project Intent

Cloud AI free tiers are rate-limited. This project caches text answers from cloud models locally so repeated or similar questions never reach the cloud again, preserving free-tier quota. Exact repeats are answered via a Redis hash lookup in O(1); near-duplicates are answered from a local vector database; moderately similar questions are answered by a small local model using the cached snippets as context (RAG). Only genuinely new questions go to the cloud, through Cloudflare AI Gateway's Auto Router.

## Architecture

```
.
├── docker-compose.yml   # Orchestrates all services and startup order
├── .env                 # (you create) Cloudflare credentials
├── client/              # Nginx + static UI (index.html, app.js)
├── server/              # FastAPI orchestrator (main.py)
├── db/                  # ChromaDB vector store
├── embedding/           # Ollama runtime serving qwen3.5:0.8b
└── cache/               # Redis exact-match cache
```

| Folder | Role |
|---|---|
| `client` | Nginx serving a text box + Send button. Proxies `/api/*` to the server and shows a badge with the answer's source. Exposed on http://localhost:8080. |
| `server` | FastAPI backend implementing the routing workflow (below). |
| `db` | ChromaDB (`db:8000`) storing normalised prompt embeddings with their answers. |
| `embedding` | Ollama (`embedding:11434`) that pulls `qwen3.5:0.8b` on boot; used for embeddings and local generation. |
| `cache` | Redis (`cache:6379`), ephemeral, `maxmemory 256mb`, `allkeys-lru`, no persistence. |

Startup order (via healthcheck-based `depends_on`): `db`, `embedding`, `cache` → `server` → `client`.

### Request workflow (`POST /api/chat`)

1. **Redis match** – SHA-256 of the prompt. Hit → `source: "redis_exact_cache"`, TTL reset to 30 days.
2. **Embedding** – `POST embedding:11434/api/embeddings` with `qwen3.5:0.8b`.
3. **Vector DB** – query ChromaDB; its L2 distance is converted to cosine similarity in [0, 1] (vectors are normalised, so `cos = 1 - d/2`).
4. **Threshold routing**
   - `>= 0.90` → `source: "vector_cache"`; the Redis key is populated.
   - `0.70–0.89` → top snippets build a RAG prompt for the local LLM → `source: "local_llm_rag"`; both caches updated in the background.
   - `< 0.70` → Cloudflare Auto Router → `source: "cloud_agent"`; both caches updated in the background.

Notes: Redis has no global max-TTL setting, so the server applies the 30-day TTL to every key it writes. The first start downloads the model, so `embedding` may take a few minutes to become healthy.

## Deployment

Prerequisites: Docker with Compose, and Node.js for Wrangler (`npm i -g wrangler`, then `wrangler login`).

1. Get your account ID: run `wrangler whoami` and copy the Account ID.
2. Get your API token: run `wrangler auth token`.
3. Create a root-level `.env` file (already git-ignored):

   ```
   CLOUDFLARE_ACCOUNT_ID=your_account_id
   CLOUDFLARE_API_TOKEN=your_api_token
   ```

  
4. Start everything:

   ```
   docker compose up --build -d
   ```
5. Open http://localhost:8080.

Stop with `docker compose down` (add `-v` to also delete the model and vector data).

> The server calls `https://gateway.ai.cloudflare.com/v1/<ACCOUNT_ID>/ai-gateway/compat` with model `cloudflare/auto`, so AI Gateway must be enabled on your account.
