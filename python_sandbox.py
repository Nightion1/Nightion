"""
python_sandbox.py — Knowledge-First Code Generator — Nightion

Bug fixes applied:
  BUG 1: Language preference is now LEARNED from memory, not hardcoded.
          _detect_language() reads MemoryCore first; only falls back to
          query-text detection when no preference has been recorded yet.
          If no signal at all, returns None and the caller asks the user.

  BUG 2: Before code generation, memory layer is queried for:
            - preferred language for this topic category
            - similar previously-solved problems (via KnowledgeBase)
          These are injected as context into the generation path.

  BUG 3: After every successful learning event (online OR offline), the
          language+topic pair is immediately persisted to MemoryCore with
          available_offline=1, so offline mode never has stale preferences.
"""

from knowledge_base import KnowledgeBase
from self_trainer import SelfTrainer
from memory_core import MemoryCore
import os


# ---------------------------------------------------------------------------
# Topic-category classifier
# ---------------------------------------------------------------------------

def _classify_topic_category(query: str) -> str:
    """
    Derive a topic category from the query text.
    Never hardcoded to a lang — classifies the *domain*, not the language.

    BUG 3 FIX: All DSA-related topics (sorting, searching, linked list,
    binary search, recursion, etc.) are normalised to the single "DSA"
    category. This prevents a category mismatch when the user phrases the
    same concept differently across queries.
    """
    q = query.lower()
    dsa_signals = [
        # ─ Data structures ────────────────────────────────────
        "array", "linked list", "linked",
        "stack", "queue", "deque", "priority queue",
        "heap", "hash map", "hash table", "hash set", "hash",
        "tree", "binary tree", "bst", "avl", "trie", "segment tree",
        "graph", "adjacency",
        # ─ Algorithms ───────────────────────────────────────
        "sort", "sorting", "search", "searching", "binary search",
        "bfs", "dfs", "depth first", "breadth first",
        "dynamic programming", "dp",
        "recursion", "recursive",
        "backtrack", "backtracking",
        "greedy", "divide and conquer",
        "two pointer", "sliding window",
        # ─ Operations ───────────────────────────────────────
        "reverse", "reversal",
        "traverse", "traversal",
        "merge", "partition", "rotate",
        "insert node", "delete node",
        # ─ DSA context ──────────────────────────────────────
        "palindrome", "anagram", "substring",
        "matrix", "path", "shortest path",
        "node", "edge", "vertex",
        "fibonacci", "factorial",
        "binary",
    ]
    systems_signals = [
        "thread", "mutex", "socket", "memory", "pointer", "kernel",
        "process", "syscall", "ipc", "pipe", "fork", "signal",
    ]
    scripting_signals = [
        "script", "automate", "file", "json", "csv", "parse", "regex",
        "http", "request", "api", "fetch", "crawl", "scrape",
    ]
    if any(s in q for s in dsa_signals):
        return "DSA"
    if any(s in q for s in systems_signals):
        return "systems"
    if any(s in q for s in scripting_signals):
        return "scripting"
    return "general"


class PythonSandboxWrapper:
    """
    High-level generator that bridges KnowledgeBase and SelfTrainer to
    Sandbox execution.  Ensures zero-stub output for coding queries.
    """

    def __init__(self, knowledge_base: KnowledgeBase, trainer: SelfTrainer):
        self.kb = knowledge_base
        self.trainer = trainer
        self._mem = MemoryCore()   # language preference store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_code_solution(self, query: str, progress_cb=None) -> str:
        """
        Phase 35+: Cache-Only Knowledge-First Pattern.

        Order:
          1. Classify topic category (DSA / scripting / systems / general)
          2. Read language preference from memory (not hardcoded)
          3. Local KnowledgeBase flat-dict lookup (instant, no network)
          4. On miss → return "" so orchestrator's Ollama-first pipeline handles it

        Web-dependent generation (SelfTrainer) has been removed from this path.
        The orchestrator's _generate_code_ollama_first() handles Step 3+ onward.
        """
        topic_category = _classify_topic_category(query)

        # Read language preference from memory + build memory context
        language, memory_context = self._resolve_language_with_context(
            query, topic_category
        )

        if language is None:
            # No preference recorded and no query-text signal → ask user
            return (
                "I don't have a language preference recorded for this topic yet. "
                "**Which language would you prefer?** (e.g. Python, C++, Java, JavaScript)\n\n"
                "_Once you tell me, I'll remember it for future queries in this category._"
            )

        normalized = self._normalize(query, language)

        print(f"--- [Sandbox] Step 1a KnowledgeBase lookup: '{normalized}' in {language} "
              f"(category={topic_category}, from_memory={memory_context['from_memory']})")

        if memory_context["similar_solved"]:
            print(f"--- [Sandbox] Memory context: similar solved problems = "
                  f"{memory_context['similar_solved']}")

        # Check local KnowledgeBase (fastest — no network, no Ollama)
        local_match = self.kb.lookup(normalized, language)
        if local_match:
            print(f"--- [Sandbox] Step 1a HIT: {normalized} ({language})")
            self._persist_language_use(topic_category, language, learned_at="offline")
            return self._format(
                local_match["code"], local_match.get("explanation", ""),
                local_match.get("source_name", "Local"), language,
                from_cache=True, memory_context=memory_context,
            )

        # Cache miss — orchestrator's Ollama-first pipeline handles generation.
        print(f"--- [Sandbox] Step 1a MISS for '{normalized}'. Returning '' for Ollama handoff.")
        return ""

    # ------------------------------------------------------------------
    # BUG 2 FIX: language resolution + memory context injection
    # ------------------------------------------------------------------

    def _resolve_language_with_context(
        self, query: str, topic_category: str
    ) -> tuple[str | None, dict]:
        """
        1. Read preferred language for this topic_category from MemoryCore.
        2. Fall back to query-text detection if memory is empty.
        3. Return None only when there is truly no signal anywhere.
        4. Also return a memory_context dict for prompt injection.

        Never hardcodes "python" or any other language.
        """
        memory_context = {
            "from_memory": False,
            "preferred_language": None,
            "similar_solved": [],
            "all_preferences": {},
        }

        # Step 1: read from memory (highest priority — learned from real history)
        mem_lang = self._mem.get_language_preference(topic_category)
        if mem_lang:
            memory_context["from_memory"] = True
            memory_context["preferred_language"] = mem_lang
            memory_context["all_preferences"] = self._mem.get_all_language_preferences()

            # Look for previously solved similar problems in the same language
            normalized_q = self._normalize(query, mem_lang)
            similar = self.kb.lookup(normalized_q, mem_lang)
            if similar:
                memory_context["similar_solved"].append(normalized_q)

            return mem_lang, memory_context

        # Step 2: detect from query text (no memory yet)
        detected = self._detect_language_from_query(query)
        if detected:
            memory_context["preferred_language"] = detected
            return detected, memory_context

        # Step 3: no signal at all → caller will ask user
        return None, memory_context

    def _detect_language_from_query(self, query: str) -> str | None:
        """
        Pure query-text language detection.
        Returns None when no language is mentioned explicitly — never defaults.
        """
        text = query.lower()
        if "cpp" in text or "c++" in text:
            return "cpp"
        if "java" in text and "javascript" not in text:
            return "java"
        if "javascript" in text or " js " in text or text.endswith(" js"):
            return "javascript"
        if "typescript" in text or " ts " in text:
            return "typescript"
        if "rust" in text:
            return "rust"
        if "python" in text:
            return "python"
        # No explicit mention → return None, not a hardcoded default
        return None

    # ------------------------------------------------------------------
    # BUG 1+3 FIX: persist language use to memory
    # ------------------------------------------------------------------

    def _persist_language_use(
        self, topic_category: str, language: str, learned_at: str = "online"
    ):
        """
        Write language preference to SQLite immediately.
        available_offline is always set to 1 so offline mode never loses it.
        This satisfies BUG 3: online learning syncs to local store right away.
        """
        try:
            self._mem.record_language_use(
                topic_category=topic_category,
                language=language,
                learned_at=learned_at,
            )
            print(
                f"--- [Memory] Persisted language preference: "
                f"category={topic_category}, language={language}, "
                f"learned_at={learned_at}, available_offline=True"
            )
        except Exception as e:
            # Non-fatal — never block code generation on a memory write failure
            print(f"--- [Memory] WARNING: Could not persist language preference: {e}")

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize(self, text: str, language: str = "") -> str:
        """Strip filler words and handle common misspellings/verb forms."""
        text = text.lower()
        stopwords = [
            "write", "code", "for", "a", "an", "the", "algorithm", "of",
            "implement", "create", "in", "python", "give", "me", "show",
            "now", "cpp", "c++", "java",
        ]
        text = text.replace("arrayin", "array in")
        text = (
            text.replace("reversing", "reverse")
                .replace("sorting", "sort")
                .replace("searching", "search")
        )
        words = text.split()
        filtered = [w for w in words if w not in stopwords and w != language]
        return " ".join(filtered)

    # ------------------------------------------------------------------
    # Formatter
    # ------------------------------------------------------------------

    def _format(
        self,
        code: str,
        explanation: str,
        source: str,
        language: str,
        from_cache: bool = False,
        needs_review: bool = False,
        memory_context: dict | None = None,
    ) -> str:
        status = "Verified Knowledge" if not needs_review else f"Learned: {source}"
        cache_indicator = " [Cached]" if from_cache else ""
        header = (
            f"# [{status}]{cache_indicator} Resolved via Multilingual Knowledge Pipeline.\n\n"
        )
        # BUG 2 FIX: inject memory context note when preference came from memory
        if memory_context and memory_context.get("from_memory"):
            pref_lang = memory_context["preferred_language"]
            header += (
                f"_Language selected from your recorded preference: **{pref_lang}** "
                f"(category: {_classify_topic_category('')})_\n\n"
            )
            if memory_context.get("similar_solved"):
                header += (
                    f"_I also found similar problems you've solved before: "
                    f"{', '.join(memory_context['similar_solved'])}_\n\n"
                )
        return f"{header}```{language}\n{code}\n```\n\n/* {explanation} */"
