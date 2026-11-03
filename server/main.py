"""Hybrid AI router with exact (Redis) and semantic (ChromaDB) caching."""
import hashlib
import logging
import math
import os

import chromadb
import redis
import requests
from fastapi import BackgroundTasks, FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("router")

MODEL = "qwen3.5:0.8b"
CLOUDFLARE_AI_MODEL = os.getenv("CLOUDFLARE_AI_MODEL")
OLLAMA_URL = "http://embedding:11434"
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
HIT_THRESHOLD = 0.90   # >= : serve straight from vector cache
RAG_THRESHOLD = 0.70   # >= : local LLM with RAG; below: cloud
RAG_TOP_K = 3
COLLECTION_NAME = "qa_cache"
CHROMA_PORT = 8000
REDIS_PORT = 6379

app = FastAPI(title="ai-local-cache")

redis_client = redis.Redis(host="cache", port=REDIS_PORT, decode_responses=True)
chroma_client = chromadb.HttpClient(host="db", port=CHROMA_PORT)


def get_collection():
    # Embeddings are normalised before storage, so L2 distance maps to cosine similarity.
    return chroma_client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "l2"}
    )


class ChatRequest(BaseModel):
    prompt: str


class ChatResponse(BaseModel):
    answer: str
    source: str


# ---------------------------------------------------------------- helpers
def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def get_embedding(prompt: str) -> list[float]:
    """STEP 2: fetch the qwen3.5:0.8b embedding from Ollama and L2-normalise it."""
    r = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": MODEL, "prompt": prompt},
        timeout=120,
    )
    r.raise_for_status()
    vec = r.json()["embedding"]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def l2_to_cosine(distance: float) -> float:
    """Chroma returns squared L2. For unit vectors: d = 2 - 2*cos => cos = 1 - d/2."""
    return max(0.0, min(1.0, 1.0 - distance / 2.0))


def call_local_llm(prompt: str) -> str:
    """Generate a response with the local Ollama model (non-streaming)."""
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": MODEL, "prompt": prompt, "stream": False},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["response"]


def call_cloud_agent(prompt: str) -> str:
    """Route through Cloudflare AI Gateway's Auto Router."""
    client = OpenAI(
        api_key=os.getenv("CLOUDFLARE_API_TOKEN"),
        base_url=f"https://gateway.ai.cloudflare.com/v1/{os.getenv('CLOUDFLARE_ACCOUNT_ID')}/ai-gateway/compat",
    )
    response = client.chat.completions.create(
        model=CLOUDFLARE_AI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def build_rag_prompt(question: str, snippets: list[str]) -> str:
    context = "\n\n".join(f"- {s}" for s in snippets)
    return (
        "Use the following previously answered snippets as context to answer "
        "the question. If the context is not relevant, answer from your own knowledge.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
    )


def store_redis(prompt: str, answer: str) -> None:
    redis_client.set(prompt_hash(prompt), answer, ex=CACHE_TTL_SECONDS)


def store_chroma(prompt: str, answer: str, embedding: list[float]) -> None:
    get_collection().upsert(
        ids=[prompt_hash(prompt)],
        embeddings=[embedding],
        documents=[answer],
        metadatas=[{"prompt": prompt}],
    )


def store_both(prompt: str, answer: str, embedding: list[float]) -> None:
    """Background task: update both cache layers; failures must not affect the response."""
    try:
        store_redis(prompt, answer)
        store_chroma(prompt, answer, embedding)
    except Exception:
        log.exception("Failed to update caches")


# ---------------------------------------------------------------- routes
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, background: BackgroundTasks):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt must not be empty")

    # STEP 1: exact match; a hit refreshes the 30-day TTL.
    key = prompt_hash(prompt)
    try:
        cached = redis_client.get(key)
        if cached is not None:
            redis_client.expire(key, CACHE_TTL_SECONDS)
            return ChatResponse(answer=cached, source="redis_exact_cache")
    except redis.RedisError:
        log.exception("Redis unavailable; continuing without exact cache")

    # STEP 2: embed the prompt.
    try:
        embedding = get_embedding(prompt)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Embedding service error: {e}")

    # STEP 3: nearest neighbours in ChromaDB, converted to cosine similarity.
    similarity, snippets = 0.0, []
    try:
        collection = get_collection()
        if collection.count() > 0:
            res = collection.query(
                query_embeddings=[embedding],
                n_results=min(RAG_TOP_K, collection.count()),
                include=["documents", "distances"],
            )
            snippets = res["documents"][0]
            similarity = l2_to_cosine(res["distances"][0][0])
    except Exception:
        log.exception("Vector DB query failed; treating as miss")
        similarity, snippets = 0.0, []

    log.info("Top similarity: %.3f", similarity)

    # STEP 4: threshold routing.
    if similarity >= HIT_THRESHOLD:
        answer = snippets[0]
        try:
            store_redis(prompt, answer)  # populate the missing exact-match key
        except redis.RedisError:
            log.exception("Failed to populate Redis")
        return ChatResponse(answer=answer, source="vector_cache")

    if similarity >= RAG_THRESHOLD:
        try:
            answer = call_local_llm(build_rag_prompt(prompt, snippets))
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Local LLM error: {e}")
        background.add_task(store_both, prompt, answer, embedding)
        return ChatResponse(answer=answer, source="local_llm_rag")

    try:
        answer = call_cloud_agent(prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Cloud agent error: {e}")
    background.add_task(store_both, prompt, answer, embedding)
    return ChatResponse(answer=answer, source="cloud_agent")
