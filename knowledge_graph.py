"""
knowledge_graph.py — Connector + Memory Writer, Nightion Human-Style Learning Loop

Manages the concept knowledge graph in the existing Nightion SQLite database.

Schema (added to the shared nightion_memory.db):
  knowledge_nodes: id, concept, summary, example, related_topics_json,
                   learned_at, last_used, use_count, confidence, source_url
  knowledge_edges: from_id, to_id, relationship_type, created_at

Connector logic: before saving a new node, it finds existing nodes whose
concepts overlap with the new node's related_topics, and creates bidirectional
edges — building a navigable concept graph over time.

Confidence dynamics (Memory Writer component):
  - On save: confidence = value from Processor (0.2–1.0)
  - On successful use in a response: confidence += 0.1
  - On failed/corrected use: confidence -= 0.2
  - Range clamped to [0.0, 2.0]
"""

import json
import logging
import math
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

log = logging.getLogger("nightion.graph")

# ---------------------------------------------------------------------------
# GAP 3 FIX: dedup config — all thresholds in one place, never hardcoded
# at call sites. Change here and it propagates to save_node_deduped().
# ---------------------------------------------------------------------------
_DEDUP_CONFIG: Dict[str, float] = {
    "skip_threshold":      0.5,   # keep existing if confidence >= this
    "overwrite_threshold": 0.0,   # overwrite existing if confidence < skip_threshold
}


# ---------------------------------------------------------------------------
# DB path — reuse the same SQLite file as MemoryCore
# ---------------------------------------------------------------------------

def _db_path() -> str:
    try:
        from memory_core import MemoryCore
        return MemoryCore().db_path
    except Exception:
        import os
        return os.path.join(os.path.dirname(__file__), "nightion_memory.db")


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def init_schema():
    """
    Create knowledge_nodes and knowledge_edges tables if they don't exist.
    Safe to call on every startup — all statements use IF NOT EXISTS.
    """
    db = _db_path()
    conn = sqlite3.connect(db)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                concept             TEXT    NOT NULL,
                summary             TEXT    NOT NULL,
                example             TEXT    DEFAULT '',
                related_topics_json TEXT    DEFAULT '[]',
                learned_at          TEXT    NOT NULL,
                last_used           TEXT,
                use_count           INTEGER NOT NULL DEFAULT 0,
                confidence          REAL    NOT NULL DEFAULT 1.0,
                source_url          TEXT    DEFAULT ''
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_concept
                ON knowledge_nodes (concept);

            CREATE TABLE IF NOT EXISTS knowledge_edges (
                from_id           INTEGER NOT NULL,
                to_id             INTEGER NOT NULL,
                relationship_type TEXT    NOT NULL DEFAULT 'related',
                created_at        TEXT    NOT NULL,
                PRIMARY KEY (from_id, to_id),
                FOREIGN KEY (from_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (to_id)   REFERENCES knowledge_nodes(id) ON DELETE CASCADE
            );
        """)
        conn.commit()
        log.debug("[Graph] Schema initialized")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Save / link
# ---------------------------------------------------------------------------

def save_node(
    concept: str,
    summary: str,
    example: str = "",
    related_topics: Optional[List[str]] = None,
    confidence: float = 1.0,
    source_url: str = "",
) -> int:
    """
    UPSERT a knowledge node.

    ON CONFLICT (concept):
      - Updates summary/example/source only if the new confidence is >=
        the stored one (we keep the higher-quality version).
      - Always updates related_topics and learned_at timestamp.

    Returns the node id, or -1 on failure.
    """
    init_schema()   # idempotent
    db = _db_path()
    ts = datetime.now(timezone.utc).isoformat()
    rt_json = json.dumps(related_topics or [])

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO knowledge_nodes
                (concept, summary, example, related_topics_json,
                 learned_at, last_used, use_count, confidence, source_url)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(concept) DO UPDATE SET
                summary             = CASE
                    WHEN excluded.confidence >= knowledge_nodes.confidence
                    THEN excluded.summary
                    ELSE knowledge_nodes.summary
                END,
                example             = CASE
                    WHEN excluded.example != ''
                    THEN excluded.example
                    ELSE knowledge_nodes.example
                END,
                related_topics_json = excluded.related_topics_json,
                confidence          = MAX(knowledge_nodes.confidence, excluded.confidence),
                source_url          = excluded.source_url,
                learned_at          = excluded.learned_at
            """,
            (concept, summary, example, rt_json, ts, ts, confidence, source_url),
        )
        conn.commit()

        row = conn.execute(
            "SELECT id FROM knowledge_nodes WHERE concept = ?", (concept,)
        ).fetchone()
        node_id = row[0] if row else -1

        log.info(
            "[Graph] Saved node: id=%d concept='%s' confidence=%.2f",
            node_id, concept, confidence,
        )
        return node_id

    except Exception as exc:
        log.warning("[Graph] save_node failed for '%s': %s", concept, exc)
        return -1
    finally:
        conn.close()


def link_related(node_id: int, related_topics: List[str]):
    """
    For each topic in related_topics, find matching knowledge_nodes
    (by LIKE on concept) and create bidirectional edges.

    This builds the knowledge graph organically — no manual wiring.
    """
    if not related_topics or node_id < 0:
        return

    db = _db_path()
    ts = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db)
    edges_created = 0

    try:
        for topic in related_topics:
            topic = topic.strip().lower()
            if not topic:
                continue
            rows = conn.execute(
                """
                SELECT id FROM knowledge_nodes
                WHERE LOWER(concept) LIKE ? AND id != ?
                """,
                (f"%{topic}%", node_id),
            ).fetchall()

            for (related_id,) in rows:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_edges
                        (from_id, to_id, relationship_type, created_at)
                    VALUES (?, ?, 'related', ?)
                    """,
                    (node_id, related_id, ts),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_edges
                        (from_id, to_id, relationship_type, created_at)
                    VALUES (?, ?, 'related', ?)
                    """,
                    (related_id, node_id, ts),
                )
                edges_created += 1

        conn.commit()
        if edges_created:
            log.info("[Graph] Created %d bidirectional edges for node %d", edges_created, node_id)
    except Exception as exc:
        log.warning("[Graph] link_related failed for node %d: %s", node_id, exc)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Search / retrieval
# ---------------------------------------------------------------------------

def search_nodes(query: str, limit: int = 5, min_confidence: float = 0.0) -> List[Dict]:
    """
    Search knowledge_nodes for concepts/summaries relevant to `query`.

    GAP 2 FIX: added `min_confidence` parameter so callers can filter out
    low-quality matches when determining whether a topic is truly "known".

    Ranking formula:
        score = keyword_matches × confidence × (1 + log(1 + use_count))

    Returns list of dicts ranked by score descending.
    Returns [] if no matches or if DB/schema not yet initialized.
    """
    try:
        init_schema()
    except Exception:
        return []

    db = _db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    try:
        words = [w.strip().lower() for w in query.split() if len(w) > 2]
        if not words:
            return []

        or_clauses = " OR ".join(
            "(LOWER(concept) LIKE ? OR LOWER(summary) LIKE ?)" for _ in words
        )
        params = []
        for w in words:
            params.extend([f"%{w}%", f"%{w}%"])
        # NOTE: do NOT append limit here — it is passed via params + [min_confidence, limit * 4] below

        rows = conn.execute(
            f"""
            SELECT id, concept, summary, example, related_topics_json,
                   use_count, confidence, last_used, source_url
            FROM knowledge_nodes
            WHERE {or_clauses} AND confidence >= ?
            ORDER BY confidence DESC, use_count DESC
            LIMIT ?
            """,
            params + [min_confidence, limit * 4],
        ).fetchall()

        results = []
        for row in rows:
            text = f"{row['concept']} {row['summary']}".lower()
            match_count = sum(1 for w in words if w in text)
            score = (
                match_count
                * row["confidence"]
                * (1.0 + math.log1p(row["use_count"]))
            )
            results.append({
                "id": row["id"],
                "concept": row["concept"],
                "summary": row["summary"],
                "example": row["example"] or "",
                "related_topics": json.loads(row["related_topics_json"] or "[]"),
                "use_count": row["use_count"],
                "confidence": row["confidence"],
                "source_url": row["source_url"] or "",
                "score": score,
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    except Exception as exc:
        log.warning("[Graph] search_nodes failed: %s", exc)
        return []
    finally:
        conn.close()


def is_unknown_topic(query: str, threshold: float = 0.5) -> bool:
    """
    GAP 2 FIX: Return True if knowledge_nodes has NO confident entry for query.

    A topic is considered "known" only if search_nodes returns at least one
    result whose confidence >= threshold.  This prevents stale low-confidence
    nodes from suppressing re-learning.

    Args:
        query:     the user query or topic string
        threshold: minimum confidence to consider a node as "known"
                   (default 0.5 — read from caller, not hardcoded here)

    Used by orchestrator to decide whether to trigger the learning loop.
    """
    results = search_nodes(query, limit=1, min_confidence=threshold)
    known = len(results) > 0 and results[0].get("score", 0) > 0.3
    log.info(
        "[Graph] is_unknown_topic: query='%.50s' threshold=%.2f → unknown=%s",
        query, threshold, not known,
    )
    return not known


# ---------------------------------------------------------------------------
# Confidence updates (Memory Writer dynamics)
# ---------------------------------------------------------------------------

def update_node_confidence(node_id: int, delta: float):
    """
    Adjust confidence for node_id and increment use_count.
    Clamped to [0.0, 2.0].

    delta > 0: successful use in a response  (from CONFIDENCE_DELTAS config)
    delta < 0: failed/corrected use          (from CONFIDENCE_DELTAS config)
    """
    db = _db_path()
    ts = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            UPDATE knowledge_nodes
            SET confidence = MIN(2.0, MAX(0.0, confidence + ?)),
                last_used  = ?,
                use_count  = use_count + 1
            WHERE id = ?
            """,
            (delta, ts, node_id),
        )
        conn.commit()
        log.debug("[Graph] Confidence updated: node=%d delta=%.2f", node_id, delta)
    except Exception as exc:
        log.warning("[Graph] update_node_confidence failed for node %d: %s", node_id, exc)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GAP 3 FIX: deduplication helpers + save_node_deduped
# ---------------------------------------------------------------------------

def find_node_by_concept(concept: str) -> Optional[Dict]:
    """
    Exact-match lookup for a concept string.
    Returns the node dict or None if not found.
    """
    db = _db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, concept, summary, confidence, use_count, last_used
            FROM knowledge_nodes
            WHERE LOWER(concept) = LOWER(?)
            LIMIT 1
            """,
            (concept,),
        ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        log.warning("[Graph] find_node_by_concept failed for '%s': %s", concept, exc)
        return None
    finally:
        conn.close()


def update_last_seen(node_id: int):
    """
    Bump last_used timestamp and use_count without changing confidence.
    Called when we skip saving a known-good node (confidence >= skip_threshold).
    """
    db = _db_path()
    ts = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "UPDATE knowledge_nodes SET last_used = ?, use_count = use_count + 1 WHERE id = ?",
            (ts, node_id),
        )
        conn.commit()
        log.debug("[Graph] last_seen updated for node %d", node_id)
    except Exception as exc:
        log.warning("[Graph] update_last_seen failed for node %d: %s", node_id, exc)
    finally:
        conn.close()


def overwrite_node(
    node_id: int,
    summary: str,
    example: str,
    related_topics: Optional[List[str]] = None,
    confidence: float = 1.0,
    source_url: str = "",
):
    """
    Replace summary/example/related_topics for a node whose existing
    confidence was below the skip_threshold (stale/wrong knowledge).
    """
    db = _db_path()
    ts = datetime.now(timezone.utc).isoformat()
    rt_json = json.dumps(related_topics or [])
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            UPDATE knowledge_nodes
            SET summary             = ?,
                example             = ?,
                related_topics_json = ?,
                confidence          = ?,
                source_url          = ?,
                learned_at          = ?,
                last_used           = ?
            WHERE id = ?
            """,
            (summary, example, rt_json, confidence, source_url, ts, ts, node_id),
        )
        conn.commit()
        log.info(
            "[Graph] Node %d overwritten (low confidence) new_confidence=%.2f",
            node_id, confidence,
        )
    except Exception as exc:
        log.warning("[Graph] overwrite_node failed for node %d: %s", node_id, exc)
    finally:
        conn.close()


def save_node_deduped(
    concept: str,
    summary: str,
    example: str = "",
    related_topics: Optional[List[str]] = None,
    confidence: float = 1.0,
    source_url: str = "",
) -> int:
    """
    GAP 3 FIX: Smart deduplication before saving.

    Three-path logic (thresholds from _DEDUP_CONFIG — not hardcoded):

    Path A — Concept exists AND existing.confidence >= skip_threshold (0.5):
        → We already have good knowledge. Just bump last_seen.
        → Return existing node_id.

    Path B — Concept exists AND existing.confidence < skip_threshold:
        → Existing knowledge is stale or wrong. Overwrite it.
        → Return existing node_id.

    Path C — Concept not found:
        → Save as new node.
        → Return new node_id.
    """
    skip_threshold = _DEDUP_CONFIG["skip_threshold"]

    existing = find_node_by_concept(concept)

    if existing:
        node_id = existing["id"]
        existing_conf = float(existing.get("confidence", 0.0))

        if existing_conf >= skip_threshold:
            # Path A: high-confidence existing — keep it, just refresh timestamp
            log.info(
                "[Graph] Dedup PATH A: concept='%s' already known "
                "(confidence=%.2f >= %.2f) — updating last_seen only",
                concept, existing_conf, skip_threshold,
            )
            update_last_seen(node_id)
            return node_id
        else:
            # Path B: low-confidence existing — overwrite with fresher knowledge
            log.info(
                "[Graph] Dedup PATH B: concept='%s' stale "
                "(confidence=%.2f < %.2f) — overwriting",
                concept, existing_conf, skip_threshold,
            )
            overwrite_node(
                node_id,
                summary=summary,
                example=example,
                related_topics=related_topics,
                confidence=confidence,
                source_url=source_url,
            )
            return node_id
    else:
        # Path C: truly new concept
        log.info("[Graph] Dedup PATH C: new concept='%s' — saving", concept)
        return save_node(
            concept=concept,
            summary=summary,
            example=example,
            related_topics=related_topics,
            confidence=confidence,
            source_url=source_url,
        )


# ---------------------------------------------------------------------------
# BUG 1 + BUG 2 FIX: Live DB counters — never hardcoded, never cached
# ---------------------------------------------------------------------------

def get_learned_patterns_count() -> int:
    """
    Return count of knowledge_nodes with confidence > 0.3.
    Called on every UI response — always reflects the true DB state.
    Threshold 0.3 matches the user-visible 'patterns learned' meaning:
    any concept Nightion extracted with at least minimal confidence.
    """
    try:
        init_schema()
        db = _db_path()
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM knowledge_nodes WHERE confidence > 0.3"
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except Exception as exc:
        log.warning("[Graph] get_learned_patterns_count failed: %s", exc)
        return 0


def get_total_chunks() -> int:
    """
    Return total number of rows in knowledge_nodes (all confidence levels).
    Used for the Memory Sync chunk counter in the UI.
    Called on every UI response — always reflects the true DB state.
    """
    try:
        init_schema()
        db = _db_path()
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM knowledge_nodes"
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except Exception as exc:
        log.warning("[Graph] get_total_chunks failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Graph traversal
# ---------------------------------------------------------------------------

def get_connected_nodes(node_id: int) -> List[Dict]:
    """
    Return all knowledge nodes directly connected to node_id via edges.
    Useful for related-topic expansion.
    """
    db = _db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT n.id, n.concept, n.summary, n.confidence, e.relationship_type
            FROM knowledge_edges e
            JOIN knowledge_nodes n ON n.id = e.to_id
            WHERE e.from_id = ?
            ORDER BY n.confidence DESC
            """,
            (node_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("[Graph] get_connected_nodes failed for node %d: %s", node_id, exc)
        return []
    finally:
        conn.close()
