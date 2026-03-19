"""
Nightion RAG Engine
Real-time knowledge storage and retrieval using ChromaDB + sentence-transformers.
"""

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import hashlib
import time
import os

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "nightion_memory")

class NightionRAG:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=MEMORY_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="nightion_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        print("[Nightion RAG] Loading embedding model...")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        print("[Nightion RAG] Ready.")

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100):
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
            if i >= len(words):
                break
        return chunks if chunks else [text]

    def learn(self, text: str, source: str = "user") -> int:
        """Store new knowledge. Returns number of chunks stored."""
        chunks = self._chunk_text(text)
        embeddings = self.embedder.encode(chunks).tolist()
        
        ids = []
        for i, chunk in enumerate(chunks):
            uid = hashlib.md5(f"{source}_{chunk}_{time.time()}_{i}".encode()).hexdigest()
            ids.append(uid)
        
        self.collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=ids,
            metadatas=[{"source": source, "timestamp": time.time()} for _ in chunks]
        )
        return len(chunks)

    def retrieve(self, query: str, k: int = 4) -> list[str]:
        """Retrieve top-k relevant chunks for a query."""
        count = self.collection.count()
        if count == 0:
            return []
        k = min(k, count)
        query_embedding = self.embedder.encode([query]).tolist()
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=k
        )
        return results["documents"][0] if results["documents"] else []

    def get_stats(self) -> dict:
        return {
            "total_chunks": self.collection.count(),
            "memory_dir": MEMORY_DIR
        }

    def clear(self):
        self.client.delete_collection("nightion_knowledge")
        self.collection = self.client.get_or_create_collection(
            name="nightion_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
