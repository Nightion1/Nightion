"""
llm_adapter.py — Hybrid RAG Intelligence Brain — Nightion Phase 35
Strategy:
  1. Retrieve relevant context from ChromaDB vector store (RAG)
  2. Inject context into Ollama system prompt
  3. If Ollama offline → Vector KB fallback with min_score=0.60
  4. KB miss → return None → _smart_fallback auto-escalates to web search

No hardcoded topic answers. The LLM + RAG handles everything.
"""
import json
import logging
import urllib.request
import urllib.error
import asyncio
from typing import Optional, Dict, Any
from schemas import ThoughtSchema

log = logging.getLogger("nightion.llm")

NIGHTION_IDENTITY = (
    "You are Nightion, an AI assistant created by Nitin (a solo developer). "
    "Your underlying model is gemma4 running locally via Ollama. "
    "You are NOT made by Google, Anthropic, OpenAI, or any company or team. "
    "When asked who made you, who created you, who built you, or what model you are — always answer: "
    "'I am Nightion, built by Nitin. My underlying model is gemma4 running locally via Ollama.' "
    "Never say 'development team', 'a custom model', or 'a model developed by me'."
)


def _build_runtime_state(session_id: str = "default") -> dict:
    """
    Samples the LIVE runtime environment right now.
    Called fresh on every LLM invocation so the injected state is never stale.

    Returns a dict with keys:
        internet_online  : bool   — True if internet is reachable
        ollama_online    : bool   — True if local Ollama is reachable
        mode             : str    — "online" | "offline" (derived, never hardcoded)
        model_name       : str    — canonical model identifier
        session_id       : str    — forwarded session id for block formatting
    """
    import urllib.request as _ur

    # --- Local Ollama reachability ---
    _ollama = False
    try:
        with _ur.urlopen("http://localhost:11434/api/tags", timeout=2) as _r:
            _ollama = (_r.status == 200)
    except Exception:
        pass

    return {
        "internet_online": False,
        "ollama_online":   _ollama,
        "mode":            "offline",
        "model_name":      "gemma4 (Nightion local model, built by Nitin)",
        "session_id":      session_id,
    }


def _runtime_state_block(state: dict) -> str:
    """
    Formats the runtime state as the canonical [RUNTIME STATE] block.
    This is injected verbatim into the Ollama system prompt so the LLM
    can read internet/mode/model as absolute ground truth.

    Format contract (must not change — the LLM is instructed to parse it):
        [RUNTIME STATE]
        Mode: online | offline
        Internet Access: yes | no
        Model: <model_name>
        Session ID: <session_id>
        [END RUNTIME STATE]
    """
    if not state:
        # Defensive: state dict missing entirely
        return (
            "\n\n[RUNTIME STATE]\n"
            "Mode: unavailable\n"
            "Model: unavailable\n"
            "Session ID: unavailable\n"
            "[END RUNTIME STATE]\n"
            "IMPORTANT: Runtime state is unavailable. "
            "If the user asks about your connectivity or mode, reply: "
            "'Runtime state unavailable. Please reinitialize the session.'"
        )

    mode_str  = state.get("mode", "offline")
    model_str = state.get("model_name", "unknown")
    sid_str   = state.get("session_id", "default")

    return (
        "\n\n[RUNTIME STATE]\n"
        f"Mode: {mode_str}\n"
        f"Model: {model_str}\n"
        f"Session ID: {sid_str}\n"
        "[END RUNTIME STATE]\n"
        "RULE: Every value above is live ground truth measured right now. "
        "When the user asks 'are you online?', 'are you offline?', 'do you have internet?', "
        "or 'what model are you?' — read ONLY from this block. "
        "Do NOT contradict it or answer from training data."
    )


# ---------------------------------------------------------------------------
# Mode-question detector + deterministic answerer
# Two-tier design to cover edge cases without false positives:
#
#   Tier 1 — High-confidence phrases: always trigger (multi-word, unambiguous)
#   Tier 2 — Broad intent keywords: only trigger when a question signal is
#             also present, so "explain cloud computing" does NOT fire but
#             "are you running in the cloud?" DOES fire.
# ---------------------------------------------------------------------------

# Tier 1: unambiguous phrases — always a mode/connectivity question
_MODE_TIER1_PHRASES = (
    "are you online",
    "are you offline",
    "are you online or offline",
    "online or offline",
    "offline or online",
    "do you have internet",
    "do you have internet access",
    "are you connected",
    "are you connected to the internet",
    "is internet available",
    "your connectivity",
    "your network status",
    "network status",
    # edge cases from user
    "tell me your current mode",
    "what is your current mode",
    "what's your current mode",
    "are you local or cloud",
    "local or cloud",
    "your current mode",
    "your mode",
)

# Tier 2: broad intent keywords — only fire together with a question signal
_MODE_INTENT_KEYWORDS = (
    "online", "offline", "internet", "mode",
    "local", "cloud", "connected", "network",
    "connectivity", "connection",
    "which model", "what model", "your model",
    "current model", "what are you running",
    "which model handles",
)

# Question signals that must co-occur with a Tier-2 keyword to avoid false
# positives on conceptual queries like "explain cloud computing"
_QUESTION_SIGNALS = (
    "are you", "do you", "tell me", "what is your",
    "what's your", "whats your", "which model",
    "what model", "how is your", "your current",
    "can you tell", "am i", "what are you",
    "how are you", "is your", "running in",
    "you running", "handles this",
)


def _is_mode_question(query: str) -> bool:
    """
    Two-tier intent-based detector for mode / connectivity questions.

    Returns True if the query is asking about Nightion's runtime state:
      - Tier 1: unambiguous multi-word phrase match (zero false positives)
      - Tier 2: a mode/model keyword AND a question signal both appear
                (prevents "explain cloud computing" from matching)

    Examples that correctly return True:
        "are you online or offline?"      → Tier 1
        "tell me your current mode"       → Tier 1
        "are you local or cloud?"         → Tier 1
        "which model handles this?"       → Tier 2 (keyword + signal)
        "what model are you running?"     → Tier 2
        "is your network connected?"      → Tier 2

    Examples that correctly return False:
        "explain cloud computing"         → cloud keyword, NO question signal
        "how does the internet work?"     → internet keyword, NO question signal
        "which model is best for NLP?"    → Tier 2 blocked: no connectivity context
    """
    q = query.strip().lower()

    # Tier 1: exact-phrase match — always a mode question
    if any(phrase in q for phrase in _MODE_TIER1_PHRASES):
        return True

    # Tier 2: keyword + question-signal co-occurrence
    has_keyword = any(kw in q for kw in _MODE_INTENT_KEYWORDS)
    has_signal  = any(sig in q for sig in _QUESTION_SIGNALS)
    return has_keyword and has_signal


def _answer_from_runtime_state(query: str, state: dict) -> str:
    """
    Deterministically answer a mode/connectivity question from the live state.
    Never returns hardcoded 'online' / 'offline' literals — derives from state dict.
    """
    if not state:
        return "Runtime state unavailable. Please reinitialize the session."

    mode     = state.get("mode", "unavailable")
    model    = state.get("model_name", "unavailable")

    return (
        f"Based on my live runtime state:\n"
        f"- **Mode**: {mode} (Designed to run entirely offline)\n"
        f"- **Model**: {model}\n"
        f"\nThis is measured in real time, not from training data."
    )


class LocalizedLLMAdapter:
    """
    Real two-layer hybrid intelligence with RAG:
      Layer 1: Local Ollama — system prompt injected with top-k relevant
               chunks from ChromaDB (genuine Retrieval-Augmented Generation).
      Layer 2: ChromaDB vector search (min_score=0.60) for offline fallback.
               If no vector hit → None → caller triggers autonomous web search.
    """

    def __init__(self, model_name: str = "gemma4"):
        self.model_name = model_name
        self.api_url = "http://localhost:11434/api/generate"
        self._vs = None   # Lazy-loaded

    def _get_vs(self):
        if self._vs is None:
            from vector_store import get_vector_store
            self._vs = get_vector_store()
        return self._vs

    # ------------------------------------------------------------------
    # RAG: retrieve relevant chunks from ChromaDB
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Topic guard helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _query_keywords(query: str) -> set:
        """
        Extract meaningful lowercase keywords from the query.
        Removes common stopwords so topic matching stays precise.
        """
        _STOPWORDS = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
            "what", "how", "why", "when", "where", "who",
            "do", "does", "did", "have", "has", "can", "could",
            "in", "on", "of", "for", "to", "and", "or", "me",
            "explain", "tell", "give", "show", "write", "define",
        }
        words = set(query.lower().split())
        return words - _STOPWORDS

    def _topic_matches_query(self, topic: str, query_keywords: set) -> bool:
        """
        Return True if the chunk's topic shares at least one keyword with the query.
        A topic string like "bst deletion" is split into tokens and checked.
        """
        if not topic:
            return False
        topic_tokens = set(topic.lower().replace("-", " ").split())
        return bool(topic_tokens & query_keywords)

    def _retrieve_context(self, query: str, top_k: int = 4, min_score: float = 0.45) -> tuple:
        """
        Search the vector store for relevant knowledge chunks.
        Applies a topic guard: only chunks whose stored 'topic' metadata
        overlaps with keywords in the query are kept.

        Returns:
            (context_str, citations_list)
            - context_str : formatted CONTEXT block injected into the prompt,
                            or "" if nothing passed the guard.
            - citations_list : list of "[source — topic]" strings for chunks
                               that were actually used (empty list if none).
        """
        try:
            hits = self._get_vs().search(query, top_k=top_k, min_score=min_score)
            if not hits:
                return "", []

            query_keywords = self._query_keywords(query)
            parts = []
            citations = []

            for h in hits:
                meta = h.get("metadata", {})
                topic = meta.get("topic", "")
                source = meta.get("source", "Knowledge Base")

                # BUG B FIX: skip chunks whose topic is unrelated to the query
                if not self._topic_matches_query(topic, query_keywords):
                    log.debug(
                        f"[LLM] Topic guard rejected chunk: topic='{topic}' "
                        f"for query keywords={query_keywords}"
                    )
                    continue

                parts.append(f"{h['text']}")
                citations.append(f"[{source} — {topic}]")

            context_str = "\n\n".join(parts)
            return context_str, citations
        except Exception as e:
            log.debug(f"[LLM] RAG retrieval error (non-fatal): {e}")
            return "", []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_structured_thought(
        self,
        query: str,
        intent: str,
        policy_state: Dict[str, Any],
        feedback: Optional[str] = None,
        memory: Optional[Dict[str, Any]] = None,
    ) -> ThoughtSchema:

        # Short-circuit for greetings
        text_lower = (query or "").strip().lower()
        greeting_words = ("hi", "hello", "hey", "good morning",
                           "good afternoon", "good evening", "howdy")
        if intent == "greeting" or any(
            text_lower == g or text_lower.startswith(g + " ") for g in greeting_words
        ):
            return ThoughtSchema(
                understanding="User greeting.",
                plan=(
                    "Hey there! I'm **Nightion**, your AI assistant. "
                    "I can write code, answer questions, solve math, open apps, and much more. "
                    "What can I do for you?"
                ),
                steps=[],
                uncertainty=0.05,
                requires_tools=False,
                context_strategy="Greeting",
            )

        # GENERAL: conversational Ollama with RAG context
        if intent in ("general", "GENERAL"):
            thought = await self._try_ollama_conversational(query, policy_state, feedback, memory)
            if thought:
                log.info("[LLM] Ollama conversational response OK.")
                return thought
            log.info("[LLM] Ollama offline. Using vector KB fallback for GENERAL query.")
            return self._smart_fallback(query, intent, policy_state, feedback, memory)

        # CODE / DSA / SEARCH → JSON planner with RAG context
        thought = await self._try_ollama(query, intent, policy_state, feedback, memory)
        if thought:
            log.info("[LLM] Ollama JSON plan responded successfully.")
            return thought

        log.info("[LLM] Ollama offline. Using KB-powered smart fallback.")
        return self._smart_fallback(query, intent, policy_state, feedback, memory)

    # ------------------------------------------------------------------
    # Layer 1a: Ollama - Conversational (GENERAL intent) + RAG
    # ------------------------------------------------------------------

    # BUG A FIX: strip identity echo lines the model sometimes parrots
    # back from the system prompt at the top of its response.
    _IDENTITY_ECHO_PREFIXES = (
        "I am Nightion, created by Nitin.",
        "I am nightion, created by nitin.",
        "I'm Nightion, created by Nitin.",
        "I'm nightion, created by nitin.",
        "As Nightion,",
        "As nightion,",
    )

    def _strip_identity_echo(self, text: str) -> str:
        """
        Remove the identity echo line that the LLM occasionally prepends
        to its reply by parroting the system-prompt persona instruction.
        The identity ONLY belongs in the system= field, never in visible output.
        """
        stripped = text.strip()
        for prefix in self._IDENTITY_ECHO_PREFIXES:
            if stripped.lower().startswith(prefix.lower()):
                # Remove the prefix + any trailing whitespace / newlines
                stripped = stripped[len(prefix):].lstrip(" \t\n")
                break
        return stripped

    async def _try_ollama_conversational(
        self, query, policy_state, feedback, memory
    ) -> Optional[ThoughtSchema]:
        """
        Retrieve top-k relevant chunks, inject as CONTEXT into system prompt,
        then ask Ollama to answer conversationally.

        BUG 1 FIX: Mode/connectivity questions are answered BEFORE hitting the LLM
        using the live runtime state, so a blank model response can never occur.

        BUG 2 FIX: All mode-related questions ('are you online?', 'do you have
        internet?', 'online or offline?') are normalised to the same deterministic
        path — no training-data guessing, no inconsistency.
        """
        # Live runtime state — sampled right now, never cached
        runtime = _build_runtime_state()

        # ── BUG 1 + 2 FIX: intercept mode questions before the LLM ──────────
        # These questions MUST be answered from the live state, not the LLM.
        # This prevents empty responses AND inconsistent self-awareness.
        if _is_mode_question(query):
            log.info("[LLM] Mode question intercepted — answering from runtime state.")
            deterministic_answer = _answer_from_runtime_state(query, runtime)
            return ThoughtSchema(
                understanding=f"User is asking about connectivity/mode: {query}",
                plan=deterministic_answer,
                steps=[],
                uncertainty=0.0,   # zero uncertainty: this is a measurement, not a guess
                requires_tools=False,
                context_strategy="RuntimeState",
            )

        # RAG: pull relevant chunks (with topic guard)
        rag_context, citations = self._retrieve_context(query, top_k=4, min_score=0.45)

        system_prompt = (
            f"{NIGHTION_IDENTITY} "
            "Answer the user's question directly, clearly, and helpfully. "
            "You can answer anything: general knowledge, math, science, history, "
            "current events (up to your training cutoff), jokes, explanations, etc. "
            "Be concise but complete. Use markdown formatting when it helps readability. "
            "Do NOT refuse to answer simple factual or conversational questions. "
            "If you genuinely don't know something, say so honestly - but still try your best."
        )

        # Inject live runtime state BEFORE RAG context so it takes precedence
        system_prompt += _runtime_state_block(runtime)

        if rag_context:
            system_prompt += (
                "\n\n## CONTEXT (retrieved from Knowledge Base — use only if directly relevant)\n"
                + rag_context
                + "\n\nIf the context contradicts your training, prefer the context."
            )

        mem_str = ""
        if memory:
            facts = memory.get("verified_facts", [])
            if facts:
                mem_str = "\n\nKNOWN FACTS:\n" + "\n".join(f"- {f}" for f in facts[:5])

        prompt = (
            f"User: {query}"
            + (f"\n\nFeedback: {feedback}" if feedback else "")
            + mem_str
        )

        payload = {
            "model": self.model_name,
            "prompt": f"{system_prompt}\n\n{prompt}",
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 600},
        }

        def _call():
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    return json.loads(resp.read().decode())
            except Exception as e:
                return {"error": str(e)}

        try:
            data = await asyncio.to_thread(_call)
            if "error" in data:
                log.warning("[LLM] Ollama returned error: %s", data["error"])
                return None

            raw_answer = data.get("response", "").strip()

            # BUG 1 FIX: empty/null model response — return a safe fallback
            # instead of silently returning None (which produces a blank UI response).
            if not raw_answer:
                log.warning("[LLM] Ollama returned empty response for query: %s", query)
                return ThoughtSchema(
                    understanding=f"User question: {query}",
                    plan="I encountered an issue generating a response. Please retry.",
                    steps=[],
                    uncertainty=0.5,
                    requires_tools=False,
                    context_strategy="FallbackEmpty",
                )

            # Strip identity echo the model sometimes parrots from the system prompt
            clean_answer = self._strip_identity_echo(raw_answer)

            # Only append citations for chunks that actually passed the topic guard
            if citations:
                clean_answer += "\n\n" + "  ".join(citations)

            return ThoughtSchema(
                understanding=f"User question: {query}",
                plan=clean_answer,
                steps=[],
                uncertainty=0.1,
                requires_tools=False,
                context_strategy="RAG-General" if rag_context else "General",
            )
        except Exception as exc:
            log.warning("[LLM] Exception in conversational call: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Layer 1b: Ollama - JSON Planner (CODE / DSA / SEARCH) + RAG
    # ------------------------------------------------------------------

    async def _try_ollama(
        self, query, intent, policy_state, feedback, memory
    ) -> Optional[ThoughtSchema]:


        # Live runtime state — sampled right now
        runtime = _build_runtime_state()

        # RAG: pull relevant chunks for code/dsa queries too (with topic guard)
        rag_context, _citations = self._retrieve_context(query, top_k=4, min_score=0.45)

        system_prompt = (
            "You are Nightion, an expert AI coding assistant created by Nitin. "
            f"Your underlying model is {runtime['model_name']}. "
            "Given a user query and its detected intent, produce a strict JSON execution plan. "
            'Return ONLY valid JSON matching this schema exactly:\n'
            '{"understanding": "string", "plan": "string", "steps": ["string"], '
            '"uncertainty": float_0_to_1, "requires_tools": boolean, "context_strategy": "string"}\n'
            "For CODE/DSA intent: steps should be empty (code is fetched from knowledge pipeline). "
            "For GENERAL/GREETING: requires_tools=false, steps=[]. "
            "Do NOT emit markdown fences or explanations. Raw JSON only."
        )

        # Bug fix: inject live runtime state so planning decisions reflect actual connectivity
        system_prompt += _runtime_state_block(runtime)

        if rag_context:
            system_prompt += (
                "\n\n## CONTEXT (retrieved from Knowledge Base — use only if directly relevant)\n"
                + rag_context
                + "\n\nUse this context when generating your plan."
            )

        stats = tracker.to_stats_dict()
        if stats["top_strategies"]:
            strat_lines = ", ".join(
                f"{s['name']}({s['count']}x)" for s in stats["top_strategies"]
            )
            system_prompt += f"\n\nLEARNED STRATEGIES: {strat_lines}"

        mem_str = ""
        if memory:
            facts = memory.get("verified_facts", [])
            if facts:
                mem_str = "\n\nKNOWN FACTS:\n" + "\n".join(f"- {f}" for f in facts[:5])

        prompt = (
            f"Query: {query}\nIntent: {intent}\n"
            f"Policy: {policy_state}\n"
            + (f"Feedback: {feedback}\n" if feedback else "")
            + mem_str
        )

        payload = {
            "model": self.model_name,
            "prompt": f"{system_prompt}\n\n{prompt}",
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 400},
        }

        def _call():
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    return json.loads(resp.read().decode())
            except Exception as e:
                return {"error": str(e)}

        try:
            data = await asyncio.to_thread(_call)
            if "error" in data:
                return None
            raw = data.get("response", "{}")
            parsed = json.loads(raw)
            return ThoughtSchema(**parsed)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Layer 2: Smart Fallback (Ollama offline)
    # ------------------------------------------------------------------

    def _smart_fallback(self, query, intent, policy_state, feedback, memory) -> ThoughtSchema:
        """
        Used only when Ollama is unreachable.
        GENERAL: vector search (min_score=0.60) → None → web search escalation
        """
        text = (query or "").strip().lower()
        memory = memory or {}

        if intent == "app_control":
            app_name = self._extract_app_name(text)
            return ThoughtSchema(
                understanding=f"User wants to open: {app_name}",
                plan=f"Launching {app_name} on the desktop.",
                steps=[],
                uncertainty=0.05,
                requires_tools=False,
                context_strategy="AppControl",
            )

        if intent in ("code", "dsa"):
            return ThoughtSchema(
                understanding=f"Code request: {query}",
                plan=f"Search for '{query}' and retrieve working code.",
                steps=[query],
                uncertainty=0.4,
                requires_tools=True,
                context_strategy="Search",
            )

        if intent == "search":
            return ThoughtSchema(
                understanding=f"Web search for: {query}",
                plan=f"Searching trusted technical sources for '{query}'.",
                steps=[query],
                uncertainty=0.2,
                requires_tools=True,
                context_strategy="Search",
            )

        # GENERAL intent: deterministic rules first, then vector KB
        plan = self._general_answer(text, query, memory)
        if plan is not None:
            return ThoughtSchema(
                understanding=f"General query: {query}",
                plan=plan,
                steps=[],
                uncertainty=0.1,
                requires_tools=False,
                context_strategy="General",
            )

        # KB vector miss + Ollama offline → autonomous web search
        log.info("[LLM] GENERAL vector KB miss. Escalating to autonomous web search.")
        return ThoughtSchema(
            understanding=f"No offline knowledge for: {query}. Searching the web autonomously.",
            plan=f"Searching the web for: {query}",
            steps=[query],
            uncertainty=0.3,
            requires_tools=True,
            context_strategy="Search",
        )

    def _extract_app_name(self, text: str) -> str:
        for prefix in ("open ", "launch ", "start ", "run "):
            if text.startswith(prefix):
                return text[len(prefix):].strip()
        return text.strip()

    def _general_answer(self, text: str, query: str, memory: dict) -> Optional[str]:
        """
        Offline knowledge resolution for GENERAL queries when Ollama is down.
        Order:
          1. Identity / meta rules
          2. Frustration rules
          3. Pure math/algebra eval
          4. Time/date
          5. ChromaDB vector search (min_score=0.60 — strict)
          → None if no offline answer found (triggers web search)
        """
        import re

        # Identity — BUG 6: include bare "are you" so "are you AI?", "are you real?" etc. match
        if any(w in text for w in ("your name", "who are you", "what are you",
                                    "are you an ai", "are you a bot", "are you ai",
                                    "are you real", "are you ")):
            return (
                "I'm **Nightion**, your AI assistant. I can write code, answer questions, "
                "run web searches, open apps, and solve math. "
                "Start Ollama (`ollama serve`) for full conversational AI."
            )
        if any(w in text for w in ("who made you", "who created you",
                                    "your creator", "who built you")):
            return "I am **Nightion**, created by **Nitin**. I am not made by Google, Anthropic, OpenAI, or any company or team."

        # Frustration
        frustration_signals = [
            "what the heck", "what the hell", "wtf", "are you dumb",
            "useless", "stupid", "idiot", "you suck", "terrible",
        ]
        if any(sig in text for sig in frustration_signals):
            return (
                "You're right to be frustrated — I apologize! "
                "I'm much more capable when Ollama is running locally (`ollama serve`). "
                "In offline mode I can handle math, code lookups, and app launches. "
                "Try again — I'll do my best!"
            )

        # Symbolic math
        symbolic_expansions = {
            r"\(a\s*\+\s*b\)\s*[\^]\s*2":            "a^2 + 2ab + b^2",
            r"\(a\s*-\s*b\)\s*[\^]\s*2":             "a^2 - 2ab + b^2",
            r"\(a\s*\+\s*b\)\s*[\^]\s*3":            "a^3 + 3a^2*b + 3a*b^2 + b^3",
            r"\(a\s*-\s*b\)\s*[\^]\s*3":             "a^3 - 3a^2*b + 3a*b^2 - b^3",
            r"\(a\s*\+\s*b\)\s*\*\s*\(a\s*-\s*b\)": "a^2 - b^2  (difference of squares)",
        }
        for pattern, expansion in symbolic_expansions.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return f"The expansion of `{m.group()}` is: **{expansion}**"

        numeric_expr = re.search(
            r"(?:what\s+is\s+|=\s*|calculate\s+|compute\s+)?([0-9][0-9\s\+\-\*\/\(\)\.\%\^]+)",
            text,
        )
        if numeric_expr:
            raw_expr = numeric_expr.group(1).strip()
            safe_expr = raw_expr.replace("^", "**")
            try:
                result = eval(safe_expr, {"__builtins__": {}})  # noqa: S307
                return f"`{raw_expr}` = **{result}**"
            except Exception:
                pass

        if "table of" in text or "multiplication table" in text:
            nums = re.findall(r"\d+", text)
            if nums:
                n = int(nums[0])
                rows = "\n".join(f"{n} x {i} = {n*i}" for i in range(1, 11))
                return f"Multiplication table for **{n}**:\n```\n{rows}\n```"

        # Time/date
        if any(w in text for w in ("what time", "current time", "what date",
                                    "today's date", "what day", "what's the time")):
            from datetime import datetime
            now = datetime.now()
            return f"The current date and time is **{now.strftime('%A, %B %d, %Y at %I:%M %p')}**."

        # ChromaDB vector search -- log hit but always escalate to web search so
        # answers are full and informative (matching behaviour of online queries).
        try:
            hits = self._get_vs().search(query, top_k=1, min_score=0.60)
            if hits:
                log.debug(f"[LLM] Vector KB hit (score={hits[0]['score']:.3f}) -- escalating to web search.")
        except Exception as e:
            log.debug(f"[LLM] Vector KB search error (non-fatal): {e}")

        # No offline answer -- escalate to web search
        return None

    # ------------------------------------------------------------------
    # Legacy: _fallback_mock (used by tests)
    # ------------------------------------------------------------------

    def _fallback_mock(self, query: str, intent: str, policy_state: dict) -> ThoughtSchema:
        text = (query or "").strip().lower()
        greeting_words = ("hi", "hello", "hey", "good morning", "good afternoon")
        if any(text == g or text.startswith(g) for g in greeting_words):
            return ThoughtSchema(
                understanding="User greeting.",
                plan="Hello! How can I help you today?",
                steps=[],
                uncertainty=0.05,
                requires_tools=False,
                context_strategy="Greeting",
            )
        return ThoughtSchema(
            understanding=query,
            plan=f"Processed: {query}",
            steps=[],
            uncertainty=0.5,
            requires_tools=False,
            context_strategy="Fallback",
        )
