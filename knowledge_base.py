import sqlite3
import hashlib
import os

class KnowledgeBase:
    TRUSTED_SOURCES = [
        "cp-algorithms.com",
        "geeksforgeeks.org",
        "codeforces.com/blog",
        "leetcode.com/discuss",
        "usaco.guide",
        "atcoder.jp",
        "en.wikipedia.org",
    ]

    def __init__(self, db_path="knowledge.db"):
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init()

    def _init(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_hash   TEXT UNIQUE,
                topic        TEXT NOT NULL,
                language     TEXT DEFAULT 'python',
                code         TEXT,
                explanation  TEXT,
                source_url   TEXT,
                source_name  TEXT,
                trusted      INTEGER DEFAULT 1,
                needs_review INTEGER DEFAULT 0,
                use_count    INTEGER DEFAULT 0,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_topic_hash ON knowledge(topic_hash);
        """)
        # Idempotent migrations for existing tables
        for col, definition in [
            ("language",     "TEXT DEFAULT 'python'"),
            ("needs_review", "INTEGER DEFAULT 0"),
            ("use_count",    "INTEGER DEFAULT 0"),
        ]:
            try:
                self.conn.execute(f"ALTER TABLE knowledge ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def _hash(self, topic: str, language: str = 'python') -> str:
        return hashlib.sha256(f"{topic.lower().strip()}:{language.lower().strip()}".encode()).hexdigest()

    def lookup(self, topic: str, language: str = 'python') -> dict | None:
        row = self.conn.execute(
            "SELECT topic, code, explanation, source_url, needs_review, use_count FROM knowledge WHERE topic_hash=?",
            (self._hash(topic, language),)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE knowledge SET use_count = use_count + 1 WHERE topic_hash=?",
                (self._hash(topic, language),)
            )
            self.conn.commit()
            return {
                "topic": row[0],
                "code": row[1],
                "explanation": row[2],
                "source": row[3],
                "needs_review": bool(row[4]),
                "use_count": row[5] + 1
            }
        return None

    def store(self, topic: str, code: str, explanation: str,
              source_url: str, source_name: str, language: str = 'python', needs_review: bool = False):
        """Permanently store learned knowledge."""
        self.conn.execute("""
            INSERT OR REPLACE INTO knowledge
              (topic_hash, topic, language, code, explanation, source_url, source_name, trusted, needs_review)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (self._hash(topic, language), topic, language, code, explanation, source_url, source_name, int(needs_review)))
        self.conn.commit()

    def fuzzy_search(self, query: str, limit: int = 3) -> list:
        """
        Partial keyword search across stored topics — used by the offline fallback
        so Nightion can answer from its KB without needing an exact hash match.
        Strips stopwords and matches any remaining keyword against topic text.
        """
        stopwords = {
            "a", "an", "the", "is", "in", "of", "to", "for", "what", "how",
            "do", "i", "can", "you", "me", "give", "show", "write", "please",
            "are", "does", "did", "was", "were", "will", "be", "been",
        }
        keywords = [w for w in query.lower().split() if w not in stopwords and len(w) > 2]
        if not keywords:
            return []

        conditions = " OR ".join(["LOWER(topic) LIKE ?" for _ in keywords])
        params = [f"%{kw}%" for kw in keywords]

        rows = self.conn.execute(
            f"SELECT topic, code, explanation, source_url, source_name FROM knowledge "
            f"WHERE trusted=1 AND ({conditions}) LIMIT ?",
            params + [limit]
        ).fetchall()

        return [
            {
                "topic": r[0],
                "code": r[1],
                "explanation": r[2],
                "source": r[3] or r[4] or "Knowledge Base",
            }
            for r in rows
        ]

    def is_trusted_source(self, url: str) -> bool:
        return any(s in url for s in self.TRUSTED_SOURCES)

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
