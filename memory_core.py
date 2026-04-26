import sqlite3
import os
from datetime import datetime, timezone
import json
from typing import Dict, List, Any, Optional

class MemoryCore:
    """
    Phase 18 SQLite Truth Graph.
    Ensures safe, atomic memory insertion mapping strongly typed parameters avoiding semantic blob spam.
    """
    
    def __init__(self, db_path: str = None):
        if not db_path:
            db_dir = os.path.join(os.path.dirname(__file__), "memory")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "nightion_memory.db")
            
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS episodic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    task_summary TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    confidence REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    pattern_type TEXT NOT NULL,
                    strategy_description TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    confidence REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    constraint_rule TEXT NOT NULL,
                    confidence REAL NOT NULL
                )
            """)
            # 4. Verified Facts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    fact_statement TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    inject INTEGER DEFAULT 1
                )
            """)
            # 5. UI Session Immutable Replays (Phase 19)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_chat (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    trace_id_reference TEXT
                )
            """)
            # 6. Language Preferences (Bug 1 / Bug 3 fix)
            #    Stores per-topic language preference derived from real query history.
            #    Never hardcoded — all values come from actual user interactions.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS language_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_category TEXT NOT NULL,
                    language TEXT NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 1,
                    last_used TEXT NOT NULL,
                    learned_at TEXT NOT NULL DEFAULT 'online',
                    available_offline INTEGER NOT NULL DEFAULT 1
                )
            """)
            # BUG 3 FIX: create the unique index in the SAME transaction as the
            # table so it is guaranteed to exist before any UPSERT runs.
            # Using IF NOT EXISTS is idempotent — safe to run on every startup.
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_lang_pref
                ON language_preferences (topic_category, language)
            """)
            conn.commit()
        finally:
            conn.close()

    def record_language_use(
        self,
        topic_category: str,
        language: str,
        learned_at: str = "online",
    ):
        """
        Record that `language` was used for `topic_category`.
        Increments use_count if the row exists, inserts otherwise.
        Always marks available_offline=1 so offline mode can read it.
        Never hardcodes language values — they come from actual queries.

        BUG 3 FIX: The UPSERT target is the composite (topic_category, language)
        unique index.  Both columns must conflict together for use_count to
        increment rather than insert a new row.
        """
        import logging as _log
        _log.getLogger("nightion.memory").info(
            "[Memory] record_language_use: category=%s language=%s learned_at=%s",
            topic_category, language, learned_at,
        )
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO language_preferences
                    (topic_category, language, use_count, last_used, learned_at, available_offline)
                VALUES (?, ?, 1, ?, ?, 1)
                ON CONFLICT(topic_category, language) DO UPDATE SET
                    use_count         = language_preferences.use_count + 1,
                    last_used         = excluded.last_used,
                    learned_at        = excluded.learned_at,
                    available_offline = 1
                """,
                (topic_category, language, ts, learned_at),
            )
            conn.commit()
            # Diagnostic: log the current use_count after the write
            cur = conn.execute(
                "SELECT use_count FROM language_preferences "
                "WHERE topic_category=? AND language=?",
                (topic_category, language),
            )
            row = cur.fetchone()
            _log.getLogger("nightion.memory").info(
                "[Memory] After UPSERT: category=%s language=%s use_count=%s",
                topic_category, language, row[0] if row else "?",
            )
        finally:
            conn.close()

    def get_language_preference(self, topic_category: str) -> Optional[str]:
        """
        Return the most-used language for `topic_category`, or None if no
        preference has been recorded yet.

        Returns None (not a hardcoded default) so callers can ask the user
        when no preference exists, as per the project rule.
        """
        import logging as _log
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT language, use_count FROM language_preferences
                WHERE topic_category = ?
                ORDER BY use_count DESC, last_used DESC
                LIMIT 1
                """,
                (topic_category,),
            ).fetchone()
            result = row["language"] if row else None
            _log.getLogger("nightion.memory").info(
                "[Memory] get_language_preference: category=%s → %s (use_count=%s)",
                topic_category,
                result,
                row["use_count"] if row else 0,
            )
            return result
        finally:
            conn.close()

    def get_all_language_preferences(self) -> dict:
        """
        Return the full user_language_preference map:
        {
            "DSA": "cpp",
            "general": "python",
            "last_used": "cpp",    # across all categories
            ...
        }
        Returns an empty dict if no preferences exist yet.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT topic_category, language, use_count, last_used
                FROM language_preferences
                ORDER BY use_count DESC, last_used DESC
                """
            ).fetchall()
            result: dict = {}
            overall_last_used = None
            overall_last_ts = ""
            for r in rows:
                cat = r["topic_category"]
                if cat not in result:
                    result[cat] = r["language"]
                if r["last_used"] > overall_last_ts:
                    overall_last_ts = r["last_used"]
                    overall_last_used = r["language"]
            if overall_last_used:
                result["last_used"] = overall_last_used
            return result
        finally:
            conn.close()

    def add_episodic_trace(self, trace_id: str, summary: str, success: bool, confidence: float):
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.cursor().execute(
                "INSERT INTO episodic (trace_id, timestamp, task_summary, success, confidence) VALUES (?, ?, ?, ?, ?)",
                (trace_id, ts, summary, success, confidence)
            )
            conn.commit()
        finally:
            conn.close()

    def add_tool_pattern(self, trace_id: str, pattern_type: str, strategy: str, success: bool, confidence: float):
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.cursor().execute(
                "INSERT INTO patterns (trace_id, timestamp, pattern_type, strategy_description, success, confidence) VALUES (?, ?, ?, ?, ?, ?)",
                (trace_id, ts, pattern_type, strategy, success, confidence)
            )
            conn.commit()
        finally:
            conn.close()

    def add_preference(self, trace_id: str, rule: str, confidence: float):
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.cursor().execute(
                "INSERT INTO preferences (trace_id, timestamp, constraint_rule, confidence) VALUES (?, ?, ?, ?)",
                (trace_id, ts, rule, confidence)
            )
            conn.commit()
        finally:
            conn.close()

    def add_verified_fact(self, trace_id: str, source: str, fact: str, confidence: float, inject: int = 1):
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.cursor().execute(
                "INSERT INTO facts (trace_id, timestamp, source, fact_statement, confidence, inject) VALUES (?, ?, ?, ?, ?, ?)",
                (trace_id, ts, source, fact, confidence, inject)
            )
            conn.commit()
        finally:
            conn.close()

    def log_chat_event(self, session_id: str, role: str, content: str, trace_id: Optional[str] = None):
        """ Immutable append-only log capturing exact semantic boundaries tracking UI UI states perfectly cleanly offline natively. """
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.cursor().execute(
                "INSERT INTO session_chat (session_id, timestamp, role, content, trace_id_reference) VALUES (?, ?, ?, ?, ?)",
                (session_id, ts, role, content, trace_id)
            )
            conn.commit()
        finally:
            conn.close()
            
    def fetch_session_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        """ Rehydrates UI chat bounds extracting raw sequence offline gracefully. """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM session_chat WHERE session_id = ? ORDER BY sequence_id ASC LIMIT ?", (session_id, limit))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
            
    def fetch_recent_patterns(self, limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patterns ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def fetch_active_preferences(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM preferences ORDER BY confidence DESC, timestamp DESC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def fetch_all_facts(self, only_injected: bool = False) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if only_injected:
                cursor.execute("SELECT * FROM facts WHERE inject = 1 ORDER BY confidence DESC")
            else:
                cursor.execute("SELECT * FROM facts ORDER BY confidence DESC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
