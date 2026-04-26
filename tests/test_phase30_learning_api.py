"""
tests/test_phase30_learning_api.py
Phase 30 — Learning Stats Endpoint Tests

Verifies:
1. GET /api/learning-stats returns HTTP 200.
2. Response schema: patterns_learned (int ≥ 0), knowledge_bar (int 0–100), top_strategies (list).
3. After seeding the tracker with 5 records, patterns_learned == 5 and knowledge_bar > 0.
"""
import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from learning_tracker import LearningTracker
import learning_tracker as lt_module


@pytest.fixture(autouse=True)
def isolated_tracker(tmp_path):
    """
    Replace the module-level singleton with a fresh, temp-file-backed tracker
    for each test. Restore the original singleton afterward.
    """
    db_file = str(tmp_path / "test_tracker.db")
    fresh = LearningTracker(db_path=db_file)

    original = lt_module._tracker_instance
    lt_module._tracker_instance = fresh

    yield fresh

    lt_module._tracker_instance = original
    fresh.close()


@pytest.fixture()
def client():
    # Import app AFTER the singleton is patched by isolated_tracker
    from nightion_core import app
    return TestClient(app)


# ── Test 1: Endpoint contract ─────────────────────────────────────────────────

def test_learning_stats_returns_200(client):
    response = client.get("/api/learning-stats")
    assert response.status_code == 200


def test_learning_stats_schema(client):
    data = client.get("/api/learning-stats").json()

    assert "patterns_learned" in data
    assert "knowledge_bar" in data
    assert "top_strategies" in data

    assert isinstance(data["patterns_learned"], int)
    assert isinstance(data["knowledge_bar"], int)
    assert isinstance(data["top_strategies"], list)


def test_patterns_learned_non_negative(client):
    data = client.get("/api/learning-stats").json()
    assert data["patterns_learned"] >= 0


def test_knowledge_bar_in_range(client):
    data = client.get("/api/learning-stats").json()
    assert 0 <= data["knowledge_bar"] <= 100


# ── Test 2: With seeded data ──────────────────────────────────────────────────

def test_seeded_five_records(client, isolated_tracker):
    # Seed 5 events
    for i in range(5):
        isolated_tracker.record(
            source_type="code",
            topic=f"topic_{i}",
            confidence=0.8,
            outcome="success",
        )

    data = client.get("/api/learning-stats").json()
    assert data["patterns_learned"] == 5
    assert data["knowledge_bar"] > 0


def test_seeded_top_strategies_populated(client, isolated_tracker):
    # Insert events across two strategy types
    for _ in range(3):
        isolated_tracker.record(source_type="code", topic="binary search", confidence=0.9)
    for _ in range(2):
        isolated_tracker.record(source_type="search", topic="quicksort", confidence=0.7)

    data = client.get("/api/learning-stats").json()
    strategies = data["top_strategies"]

    assert len(strategies) >= 1
    # Top strategy should be 'code' (3 records) before 'search' (2 records)
    assert strategies[0]["name"] == "code"
    assert strategies[0]["count"] == 3
    assert strategies[0]["rank"] == 1

    # Verify schema of individual strategy dict
    for s in strategies:
        assert "name" in s
        assert "count" in s
        assert "avg_confidence" in s
        assert "rank" in s


def test_knowledge_bar_scales_correctly(client, isolated_tracker):
    """100 events should yield a knowledge_bar of 50 (100/200 * 100)."""
    for i in range(100):
        isolated_tracker.record(source_type="general", topic=f"t{i}", confidence=0.5)

    data = client.get("/api/learning-stats").json()
    assert data["knowledge_bar"] == 50


def test_knowledge_bar_saturates_at_100(client, isolated_tracker):
    """200+ events should always yield knowledge_bar == 100."""
    for i in range(210):
        isolated_tracker.record(source_type="code", topic=f"t{i}", confidence=0.9)

    data = client.get("/api/learning-stats").json()
    assert data["knowledge_bar"] == 100
