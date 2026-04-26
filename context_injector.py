"""
context_injector.py — Injector Component, Nightion Human-Style Learning Loop

On every query:
  1. Searches knowledge_nodes for relevant concepts
  2. Ranks by: keyword_matches × confidence × log(1 + use_count)
  3. Injects top 3 entries into the LLM prompt as learned context
  4. After the response, updates confidence based on a 3-level signal

GAP 1 FIX: update_used_knowledge() now accepts a signal string:
  "success" → confidence += CONFIDENCE_DELTAS["success"]  (+0.1)
  "ignored" → confidence += CONFIDENCE_DELTAS["ignored"]  (-0.2)
  "failed"  → confidence += CONFIDENCE_DELTAS["failed"]   (-0.1)

Deltas are read from a config dict — never hardcoded at call sites.
Signal is inferred from the generated response (concepts present/absent).
"""

import logging
from typing import List, Dict, Optional, Tuple

log = logging.getLogger("nightion.injector")

_TOP_K = 3        # max knowledge entries to inject per query
_MIN_SCORE = 0.05  # minimum relevance score; below this is filtered out

# ---------------------------------------------------------------------------
# GAP 1 FIX: confidence delta config — change here, propagates everywhere.
# Never repeating these values at call sites.
# ---------------------------------------------------------------------------
CONFIDENCE_DELTAS: Dict[str, float] = {
    "success": +0.1,   # injected knowledge was referenced / consistent with response
    "ignored": -0.2,   # injected knowledge was relevant but contradicted/ignored
    "failed":  -0.1,   # code generation failed entirely — may have been wrong context
}

# Minimum words that must appear in the generated response for a "success" signal
_MIN_CONCEPT_OVERLAP_WORDS = 1


def _infer_signal(entries: List[Dict], response_text: str) -> str:
    """
    Infer the quality signal for injected knowledge based on the response.

    Rules:
      - If response_text is empty / error message → "failed"
      - If any injected concept keyword appears in response_text → "success"
      - Otherwise (knowledge was injected but not referenced) → "ignored"

    This lets the system automatically penalise knowledge that confused
    the model without requiring external feedback.
    """
    if not response_text or not response_text.strip():
        return "failed"

    _ERROR_SIGNALS = ["encountered an issue", "please retry", "error generating"]
    if any(sig in response_text.lower() for sig in _ERROR_SIGNALS):
        return "failed"

    resp_lower = response_text.lower()
    for entry in entries:
        concept_words = entry.get("concept", "").lower().split()
        matches = sum(1 for w in concept_words if len(w) > 2 and w in resp_lower)
        if matches >= _MIN_CONCEPT_OVERLAP_WORDS:
            return "success"

    return "ignored"


# ---------------------------------------------------------------------------
# Core get / format / enrich
# ---------------------------------------------------------------------------

def get_relevant_knowledge(query: str, top_k: int = _TOP_K) -> List[Dict]:
    """
    Search knowledge_nodes for concepts relevant to `query`.
    Returns top_k entries ranked by keyword_matches × confidence × log(use_count+1).
    Returns [] on any failure (non-fatal — pipeline continues without injection).
    """
    try:
        from knowledge_graph import search_nodes, init_schema
        init_schema()
        results = search_nodes(query, limit=top_k * 2)
        filtered = [r for r in results if r.get("score", 0) >= _MIN_SCORE][:top_k]
        log.info(
            "[Injector] Found %d relevant entries for query: '%.50s'",
            len(filtered), query,
        )
        return filtered
    except Exception as exc:
        log.warning("[Injector] Knowledge search failed (non-fatal): %s", exc)
        return []


def format_for_prompt(entries: List[Dict]) -> str:
    """
    Format knowledge entries as a structured context block for injection.
    Returns empty string if no entries.
    """
    if not entries:
        return ""

    lines = ["### Nightion's Learned Knowledge (use this to inform your answer):\n"]
    for entry in entries:
        concept = entry.get("concept", "").strip()
        summary = entry.get("summary", "").strip()
        example = entry.get("example", "").strip()
        confidence = float(entry.get("confidence", 1.0))

        if not concept or not summary:
            continue

        lines.append(f"**{concept}** (confidence: {confidence:.1f})")
        lines.append(f"  {summary}")
        if example:
            lines.append(f"  Example: {example}")
        lines.append("")

    return "\n".join(lines)


def build_injected_context(query: str) -> Tuple[str, List[Dict]]:
    """
    Build the knowledge context block for a query.
    Returns (context_string, knowledge_entries_used).
    """
    entries = get_relevant_knowledge(query)
    context = format_for_prompt(entries)
    return context, entries


def enrich_context(query: str, existing_context: str) -> Tuple[str, List[Dict]]:
    """
    Prepend learned knowledge to an existing context string.
    Returns (enriched_context, entries_used) for later confidence update.
    """
    knowledge_ctx, entries = build_injected_context(query)
    # BUG 2 LOG 5: explicit count so we can confirm injector found saved nodes
    log.info(
        "[Injector] enrich_context found %d knowledge nodes for query: '%.60s'",
        len(entries), query,
    )
    if knowledge_ctx:
        enriched = f"{knowledge_ctx}\n\n{existing_context}" if existing_context else knowledge_ctx
    else:
        enriched = existing_context
    return enriched, entries


# ---------------------------------------------------------------------------
# GAP 1 FIX: update_used_knowledge with 3-level signal
# ---------------------------------------------------------------------------

def update_used_knowledge(
    entries: List[Dict],
    signal: str = "success",
    response_text: str = "",
):
    """
    Update confidence for knowledge nodes based on how well they contributed.

    Args:
        entries:       list of knowledge dicts returned by get_relevant_knowledge()
        signal:        "success" | "ignored" | "failed" | "auto"
                       Use "auto" to let the injector infer from response_text.
        response_text: the generated response (needed when signal="auto")

    Delta values come from CONFIDENCE_DELTAS config dict — not hardcoded here.

    Non-fatal: any DB failure is logged and swallowed.
    """
    if not entries:
        return

    # Auto-infer signal from the actual response when caller passes "auto"
    effective_signal = signal
    if signal == "auto":
        effective_signal = _infer_signal(entries, response_text)

    delta = CONFIDENCE_DELTAS.get(effective_signal, 0.0)

    log.info(
        "[Injector] update_used_knowledge: signal=%s → delta=%.2f nodes=%d",
        effective_signal, delta, len(entries),
    )

    if delta == 0.0:
        return  # no-op for unknown signals

    try:
        from knowledge_graph import update_node_confidence
        for entry in entries:
            node_id = entry.get("id")
            if node_id:
                update_node_confidence(node_id, delta)
                log.debug(
                    "[Injector] Node %d confidence updated: delta=%.2f signal=%s",
                    node_id, delta, effective_signal,
                )
    except Exception as exc:
        log.warning("[Injector] Confidence update failed (non-fatal): %s", exc)
