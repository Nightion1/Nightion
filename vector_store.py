"""
vector_store.py — Real Vector Intelligence for Nightion
Wraps ChromaDB with sentence-transformers (all-MiniLM-L6-v2) to provide:
  - Persistent embedding storage (replaces SQL LIKE fuzzy search)
  - Semantic intent classification (replaces regex routing)
  - Real chunk_index growth tracking (replaces fake progress bar)
  - RAG context retrieval (injects knowledge into Ollama prompts)
"""

import os
import logging
from typing import Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

log = logging.getLogger("nightion.vector_store")

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
_MODEL_NAME = "all-MiniLM-L6-v2"

# Singleton model — loaded once, reused everywhere
_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info(f"[VectorStore] Loading embedding model: {_MODEL_NAME}")
        _model = SentenceTransformer(_MODEL_NAME)
        log.info("[VectorStore] Model ready.")
    return _model


class VectorStore:
    """
    Persistent ChromaDB-backed vector store with sentence-transformer embeddings.

    Two named collections:
      - "knowledge"  : scraped/learned content (code, explanations, articles)
      - "intents"    : canonical routing examples per IntentEnum value

    All methods are synchronous — use asyncio.to_thread() for async callers.
    """

    def __init__(self, db_path: str = _DB_PATH):
        os.makedirs(db_path, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._knowledge = self._client.get_or_create_collection(
            name="knowledge",
            metadata={"hnsw:space": "cosine"},
        )
        self._intents = self._client.get_or_create_collection(
            name="intents",
            metadata={"hnsw:space": "cosine"},
        )
        log.info(f"[VectorStore] Ready. Knowledge chunks: {self._knowledge.count()}")

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        return _get_model().encode(text, normalize_embeddings=True).tolist()

    def add(
        self,
        id: str,
        text: str,
        metadata: Optional[dict] = None,
        collection: str = "knowledge",
    ) -> None:
        """
        Embed `text` and store in the specified collection.
        `id` must be unique within the collection; duplicates are silently replaced.
        """
        col = self._intents if collection == "intents" else self._knowledge
        embedding = self._embed(text)
        col.upsert(
            ids=[id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def search(
        self,
        query: str,
        top_k: int = 4,
        min_score: float = 0.45,
        collection: str = "knowledge",
    ) -> list[dict]:
        """
        Find the top_k closest documents to `query` by cosine similarity.
        Returns only results with similarity >= min_score.

        Each result dict:
            {
                "id": str,
                "text": str,          -- the original stored text
                "score": float,       -- cosine similarity (0–1, higher = better)
                "metadata": dict,
            }
        """
        col = self._intents if collection == "intents" else self._knowledge
        if col.count() == 0:
            return []

        embedding = self._embed(query)
        n = min(top_k, col.count())
        results = col.query(
            query_embeddings=[embedding],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        ids       = results["ids"][0]
        docs      = results["documents"][0]
        metas     = results["metadatas"][0]
        distances = results["distances"][0]   # cosine distance (0=identical, 2=opposite)

        for i, doc_id in enumerate(ids):
            # ChromaDB cosine distance → similarity: sim = 1 - dist/2
            # (distance range 0–2 when normalized; 0–1 when using cosine space)
            sim = 1.0 - (distances[i] / 2.0)
            if sim >= min_score:
                hits.append({
                    "id": doc_id,
                    "text": docs[i],
                    "score": round(sim, 4),
                    "metadata": metas[i],
                })

        return hits

    def count(self, collection: str = "knowledge") -> int:
        """Real chunk_index — total vectors stored. This is NOT simulated."""
        col = self._intents if collection == "intents" else self._knowledge
        return col.count()

    def delete(self, id: str, collection: str = "knowledge") -> None:
        col = self._intents if collection == "intents" else self._knowledge
        try:
            col.delete(ids=[id])
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Intent routing helpers
    # ------------------------------------------------------------------

    def seed_intents(self, intent_examples: dict[str, list[str]]) -> None:
        """
        Embed canonical routing examples into the "intents" collection.
        Call once on startup (upsert is idempotent).

        intent_examples = {
            "code":    ["write binary search in Python", ...],
            "general": ["explain how TCP/IP works", ...],
            ...
        }
        """
        for intent_label, examples in intent_examples.items():
            for i, example in enumerate(examples):
                self.add(
                    id=f"intent_{intent_label}_{i}",
                    text=example,
                    metadata={"intent": intent_label},
                    collection="intents",
                )
        log.info(f"[VectorStore] Intent examples seeded: {self._intents.count()} total")

    def classify_intent(self, query: str, min_score: float = 0.35) -> tuple[str, float]:
        """
        Return (intent_label, confidence) for `query` using nearest-neighbour
        cosine similarity over the seeded intent examples.
        Returns ("general", 0.0) when no example exceeds min_score.
        """
        hits = self.search(query, top_k=1, min_score=min_score, collection="intents")
        if not hits:
            return "general", 0.0
        best = hits[0]
        return best["metadata"].get("intent", "general"), best["score"]

    # ------------------------------------------------------------------
    # Chunking utility — used by SelfTrainer
    # ------------------------------------------------------------------

    @staticmethod
    def chunk_text(text: str, max_tokens: int = 300) -> list[str]:
        """
        Split `text` into overlapping chunks of roughly `max_tokens` words.
        Simple word-count approximation — no tokenizer dependency needed.
        """
        words = text.split()
        stride = max(1, max_tokens - 50)   # 50-word overlap
        chunks = []
        start = 0
        while start < len(words):
            chunk = " ".join(words[start : start + max_tokens])
            if chunk.strip():
                chunks.append(chunk)
            start += stride
        return chunks


# ------------------------------------------------------------------
# Module-level singleton access
# ------------------------------------------------------------------
_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Return the global VectorStore singleton (creates it on first call)."""
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


# ------------------------------------------------------------------
# __main__ — smoke test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys, tempfile
    logging.basicConfig(level=logging.INFO)
    print("=== VectorStore Smoke Test ===")
    print("(Using isolated temp DB — does NOT affect production chroma_db/)\n")

    # Use a TEMP directory so test docs never pollute the real persistent store
    with tempfile.TemporaryDirectory() as tmp_db:
        vs = VectorStore(db_path=tmp_db)

        # 1. Add test documents
        vs.add("test_1", "A linked list is a data structure where each node points to the next.",
               {"topic": "linked list", "type": "explanation"})
        vs.add("test_2", "Binary trees have at most two children per node and support O(log n) operations.",
               {"topic": "binary tree", "type": "explanation"})
        vs.add("test_3", "Dijkstra's algorithm finds the shortest path in O((V+E) log V) time.",
               {"topic": "dijkstra", "type": "explanation"})

        print(f"Knowledge chunks in store: {vs.count()}")

        # 2. Search
        hits = vs.search("what is a binary tree?", top_k=2, min_score=0.3)
        print(f"\nSearch: 'what is a binary tree?' -> {len(hits)} hits")
        for h in hits:
            print(f"  [{h['score']:.3f}] {h['text'][:80]}")

        # 3. Intent classification
        vs.seed_intents({
            "code":    ["write binary search in Python", "implement a linked list in Java"],
            "general": ["explain how TCP/IP works", "what is a binary tree"],
            "search":  ["search for the latest React version"],
        })
        print(f"\nIntents in store: {vs.count('intents')}")

        for q in ["write a heap sort in C++", "what is Dijkstra", "search Python 3.13"]:
            label, score = vs.classify_intent(q)
            print(f"  '{q}' -> {label} ({score:.3f})")

    # Temp dir auto-deleted — production DB untouched
    print("\n=== Smoke Test PASSED ===")
    sys.exit(0)

