"""
tool_router.py — Semantic Intent Router for Nightion
Phase 2: Replaces regex/if-else pattern matching with cosine-similarity
         over embedded intent examples using all-MiniLM-L6-v2.

Hard rules ONLY for things that are truly deterministic:
  - greeting: exact word match (hi, hello, hey)
  - app_control: OS verb + desktop app name
  - search: explicit search/go-online keyword

Everything else: embed the query → cosine similarity → nearest intent.
"""

from __future__ import annotations
import re
import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Union, Awaitable, Dict, Any, Optional

from schemas import StatusEnum, ToolResult, AgentRequest, IntentEnum, RouterDecision
from tool_action_manager import ToolActionManager
from schemas import PatchExecutionContract
from coding_sandbox import CodingSandbox
import time

log = logging.getLogger("nightion.router")

LLMClassifier = Callable[[str, AgentRequest], Union[IntentEnum, str, Awaitable[Union[IntentEnum, str]]]]

@dataclass
class RouterConfig:
    confidence_threshold: float = 0.35   # Minimum cosine similarity to trust
    use_llm_fallback: bool = False        # LLM fallback replaced by vector similarity


# ---------------------------------------------------------------------------
# Canonical intent examples for vector seeding
# These are EXAMPLES the model uses to understand what each intent feels like.
# No hardcoded logic — the embedding model generalises from these.
# ---------------------------------------------------------------------------
INTENT_EXAMPLES: dict[str, list[str]] = {
    "code": [
        # Imperative write/implement/give-code patterns
        "write bubble sort in python",
        "write binary search in Python",
        "write merge sort in C++",
        "write a function to check palindrome",
        "write quicksort in javascript",
        "implement a linked list in Java",
        "implement Dijkstra's algorithm",
        "implement LRU cache in Python",
        "implement a stack in Python",
        "implement binary tree deletion in Python",
        "code a binary tree traversal",
        "code a hash map in C++",
        "give me code for bubble sort",
        "give me code for binary search",
        "give me a quicksort implementation",
        "create a REST API with FastAPI",
        "build a segment tree in Rust",
        "build a graph BFS in Go",
        "make a fibonacci generator",
        "how do I reverse a string in JavaScript",
        "how do I sort an array in Python",
        "show me python code for merge sort",
        "generate code for a linked list",
        "program a binary search tree in python",
    ],
    "dsa": [
        "what is the time complexity of Dijkstra's algorithm",
        "what is the time complexity of quicksort",
        "what is the time complexity of bubble sort",
        "what is the time complexity of segment tree operations",
        "explain the space complexity of merge sort",
        "how does dynamic programming work",
        "what are the properties of a binary search tree",
        "explain Big O notation",
        "what is amortized analysis",
        "compare DFS and BFS",
        "what is the difference between stack and queue",
        "explain cycle detection in graphs",
        "what is the knapsack problem",
        "how does a trie data structure work",
        "explain two-pointer technique",
        "what is sliding window algorithm",
    ],
    "general": [
        "explain how React hooks work",
        "what is a linked list",
        "what is a binary tree",
        "how does TCP/IP work",
        "explain machine learning",
        "what is the difference between SQL and NoSQL",
        "how does garbage collection work",
        "what are microservices",
        "explain Docker containers",
        "what is recursion",
        "how does HTTPS work",
        "what is an API",
        "explain object oriented programming",
        "what is functional programming",
        "how does a database index work",
        # teach-me / explain patterns must NOT go to CODE
        "teach me segment trees",
        "teach me about binary trees",
        "teach me how graphs work",
        "explain to me what a segment tree is",
        # Vague help / assistance queries — must land in GENERAL not app_control
        "help me with this idea",
        "I need help understanding something",
        "can you assist me with a question",
        "help me think through this",
        "what can you do",
        "I have a question",
        "can you help me",
        "I need advice on something",
        "tell me about yourself",
        "what do you know about Python",
        # Science / physics / math formula queries — must NOT go to app_control
        "what is the formula for gravity",
        "write the formula for gravity",
        "what is Newton's second law",
        "explain Einstein's theory of relativity",
        "what is the formula for kinetic energy",
        "what is Ohm's law",
        "explain Pythagoras theorem",
        "what is the speed of light",
        "what is the formula for acceleration",
        "how do you calculate force",
        "what is the gravitational constant",
        "explain photosynthesis",
        "what causes a rainbow",
        "how does gravity work",
        "what is black hole",
        "explain quantum mechanics",
        "what is the periodic table",
        "how does nuclear energy work",
        "what is the formula for area of a circle",
        "calculate the derivative of x squared",
        "what is pi",
        "explain the water cycle",
        "what happened in World War 2",
        "who invented the telephone",
        "what is inflation",
        "explain supply and demand",
    ],
    "app_control": [
        "open notepad",
        "launch chrome",
        "open VS Code",
        "close the calculator",
        "open file explorer",
        "launch spotify",
        "start terminal",
        "open control panel",
        "minimize this window",
        "open task manager",
    ],
    "browser_automation": [
        "navigate to example.com",
        "open google.com and search for python",
        "click the login button on the page",
        "scroll down and find the footer",
        "extract all links from the webpage",
        "fill in the form with my name",
        "open a new browser tab",
        "read the content of this page",
    ],
    "greeting": [
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "howdy",
        "what's up",
        "greetings",
    ],
}

# Hard-rule: OS verbs targeting desktop apps
_APP_CONTROL_VERBS = [
    r"\bopen (?!http)(?!www)(?!browser)(?!tab)(?!url)\b",
    r"\bclose (?!tab)\b",
    r"\blaunch (?!chrome|browser)\b",
    r"\bminimize\b", r"\bmaximize\b",
]
_KNOWN_APPS = [
    "notepad", "chrome", "firefox", "edge", "explorer", "vs code", "vscode",
    "terminal", "cmd", "powershell", "spotify", "discord", "slack", "calculator",
    "control panel", "task manager", "paint", "word", "excel", "outlook",
]

# Hard-rule: browser automation (explicit DOM/page language)
_BROWSER_PATTERNS = [
    r"\bnavigate to\b", r"\bopen http\b", r"\bopen www\b",
    r"\bclick (?:the|a) button\b", r"\bscroll down\b", r"\bfill (the )?form\b",
    r"\bextract (?:the )?(?:element|link|text)\b", r"\bread (the )?page\b",
    r"\binspect page\b", r"\bfill in\b",
]

# Hard-rule: anaphoric/possessive phrases — always skip APP_CONTROL
# e.g. "gravity's formula", "Newton's law", "Python's syntax"
_ANAPHORIC_SKIP_PATTERNS = [
    r"\w+'s\b",   # straight apostrophe possessive  (gravity's)
    r"\w+’s\b",   # curly apostrophe possessive     (gravity’s)
    r"\w+s'\b",   # plural possessive               (developers')
]


class ToolRouter:
    """
    Semantic intent router for Nightion.

    Classification pipeline:
      1. Hard rules (greeting, app_control, browser, explicit search) — deterministic
      2. Vector similarity over INTENT_EXAMPLES — replaces all regex pattern lists
      3. Final fallback: GENERAL

    The vector store is seeded on first use (lazy init) so startup is instant.
    """

    def __init__(
        self,
        llm_classifier: Optional[LLMClassifier] = None,
        config: Optional[RouterConfig] = None,
    ):
        self.llm_classifier = llm_classifier
        self.config = config or RouterConfig()
        self._vs = None          # Lazy-loaded VectorStore
        self._intents_seeded = False

    def _get_vs(self):
        """Lazy-load the VectorStore so it only initialises when first needed."""
        if self._vs is None:
            from vector_store import get_vector_store
            self._vs = get_vector_store()
            self._seed_intents()
        return self._vs

    def _seed_intents(self):
        """Seed canonical intent examples into the vector store (idempotent)."""
        if self._intents_seeded:
            return
        vs = self._vs
        current  = vs.count("intents")
        expected = sum(len(v) for v in INTENT_EXAMPLES.values())

        if current != expected:
            # Examples changed — delete old ones and re-seed
            log.info(
                f"[Router] Intent examples mismatch (stored={current}, expected={expected}). Re-seeding..."
            )
            # Delete all existing intent vectors by their known IDs
            from chromadb import PersistentClient
            from chromadb.config import Settings
            import os
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
            for intent_label, examples in INTENT_EXAMPLES.items():
                for i in range(max(current, expected) + 10):
                    try:
                        vs._intents.delete(ids=[f"intent_{intent_label}_{i}"])
                    except Exception:
                        pass
            vs.seed_intents(INTENT_EXAMPLES)
        else:
            log.info(f"[Router] Intent examples already seeded ({current} vectors).")
        self._intents_seeded = True

    # ------------------------------------------------------------------
    # Main routing entry point
    # ------------------------------------------------------------------

    async def route(self, request: AgentRequest) -> RouterDecision:
        query = (request.query or "").strip()
        lowered = query.lower()

        # ── Hard Rule 1: Greeting ──────────────────────────────────────
        greeting_words = {"hi", "hello", "hey", "howdy", "greetings",
                          "good morning", "good afternoon", "good evening", "what's up"}
        if lowered in greeting_words or any(lowered.startswith(g + " ") for g in greeting_words):
            return self._decision(request, IntentEnum.GREETING, 0.99,
                                  "Greeting keyword matched (hard rule).")


        # ── Hard Rule 3: Browser automation ──────────────────────────
        if any(re.search(p, lowered) for p in _BROWSER_PATTERNS):
            return self._decision(request, IntentEnum.BROWSER_AUTOMATION, 0.92,
                                  "Browser DOM/navigation keyword detected (hard rule).")

        # ── Hard Rule 4: App control (OS verb + known app) ───────────
        # Strip possessive apostrophes before checking, so "gravity's formula"
        # or "Newton's law" never falsely triggers APP_CONTROL.
        if any(re.search(p, lowered) for p in _ANAPHORIC_SKIP_PATTERNS):
            pass  # possessive phrase — skip APP_CONTROL hard rule entirely
        else:
            clean_query = lowered.replace("'s", "").replace("’s", "").replace("s'", "")
            has_app_verb = any(re.search(p, clean_query) for p in _APP_CONTROL_VERBS)
            has_app_name = any(app in clean_query for app in _KNOWN_APPS)
            if has_app_verb and has_app_name:
                return self._decision(request, IntentEnum.APP_CONTROL, 0.95,
                                      "OS verb + app name detected (hard rule).")

        # ── Semantic classification via vector similarity ────────────
        intent_label, score = await asyncio.to_thread(
            self._get_vs().classify_intent, query, self.config.confidence_threshold
        )
        if score >= self.config.confidence_threshold:
            intent_enum = self._label_to_enum(intent_label)

            # Safety net: if the vector model predicted APP_CONTROL but the query
            # has no OS verb AND no known app name, it is a false positive
            # (e.g. "write the formula for gravity" → misclassified as app_control).
            # Downgrade to GENERAL so the LLM handles it conversationally.
            if intent_enum == IntentEnum.APP_CONTROL:
                clean_q = lowered.replace("'s", "").replace("\u2019s", "")
                has_verb = any(re.search(p, clean_q) for p in _APP_CONTROL_VERBS)
                has_app  = any(app in clean_q for app in _KNOWN_APPS)
                if not (has_verb and has_app):
                    log.info(
                        f"[Router] APP_CONTROL false-positive blocked for: '{query}' "
                        f"(score={score:.3f}). Downgrading to GENERAL."
                    )
                    return self._decision(
                        request, IntentEnum.GENERAL, score,
                        f"APP_CONTROL false-positive downgraded to GENERAL (no verb+app): score={score:.3f}"
                    )

            return self._decision(
                request, intent_enum, score,
                f"Semantic similarity: '{intent_label}' (score={score:.3f})"
            )

        # ── Final fallback ────────────────────────────────────────────
        return self._decision(request, IntentEnum.GENERAL, 0.35,
                              "No strong intent signal; defaulted to GENERAL.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _decision(self, request, intent, confidence, reasoning) -> RouterDecision:
        return RouterDecision(
            trace_id=request.trace_id,
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            status=StatusEnum.OK,
        )

    def _label_to_enum(self, label: str) -> IntentEnum:
        mapping = {
            "code":               IntentEnum.CODE,
            "dsa":                IntentEnum.DSA,
            "general":            IntentEnum.GENERAL,
            "app_control":        IntentEnum.APP_CONTROL,
            "browser_automation": IntentEnum.BROWSER_AUTOMATION,
            "greeting":           IntentEnum.GREETING,
        }
        return mapping.get(label, IntentEnum.GENERAL)

    def is_destructive_action(self, query: str) -> bool:
        destructive = [
            r"\bdelete\b", r"\berase\b", r"\bformat\b", r"\boverwrite\b",
            r"\buninstall\b", r"\bremove permanently\b",
            r"\bsubmit\b", r"\bsend\b", r"\bpurchase\b", r"\bpay\b",
        ]
        return any(re.search(p, query, flags=re.IGNORECASE) for p in destructive)

    # ------------------------------------------------------------------
    # Legacy helpers kept for backward compat with other modules
    # ------------------------------------------------------------------


    async def _run_apply_code_patch(self, params: dict) -> ToolResult:
        try:
            target_f  = params.get("target_file")
            search_str   = params.get("search_string", "")
            replace_str  = params.get("replacement_string", "")
            test_cmd     = params.get("test_command", "")
            patch = PatchExecutionContract(
                target_file=target_f, search_string=search_str, replacement_string=replace_str
            )
            sandbox = CodingSandbox(allowed_files=[target_f])
            success, msg = sandbox.apply_patch(patch)
            if not success:
                return ToolResult(status=StatusEnum.FAILED, output=msg)
            if test_cmd:
                test_ok, test_msg = sandbox.run_tests(test_cmd)
                if not test_ok:
                    return ToolResult(status=StatusEnum.FAILED, output=test_msg)
            return ToolResult(status=StatusEnum.OK, output=f"Patch applied. {msg}")
        except Exception as e:
            return ToolResult(status=StatusEnum.FAILED, output=f"Patch error: {e}")
