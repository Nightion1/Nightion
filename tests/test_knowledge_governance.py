import os
import time
import pytest
import sqlite3
from schemas import DomainPack, MissionClass
from domain_governance import DomainGovernanceDb
from retrieval_governor import RetrievalGovernor

TEST_DB = "test_domain_knowledge.db"

def setup_function():
    if os.path.exists(TEST_DB): os.remove(TEST_DB)

def teardown_function():
    try:
        if os.path.exists(TEST_DB): os.remove(TEST_DB)
    except PermissionError:
        pass # Handle Windows SQLite OS physical lock jitter cleanly offline

def test_governance_versioning_and_retrieval():
    gov_db = DomainGovernanceDb(db_path=TEST_DB)
    governor = RetrievalGovernor(governance_db=gov_db)

    # 1. Propose Low Confidence Pack - Should be rejected by Verifier Gate
    bad_pack = DomainPack(
        pack_id="coding_style_pep8",
        mission_class=MissionClass.CODING,
        version=1,
        ruleset="Don't use classes. Only functions.",
        source_author="unverified_agent",
        confidence=0.50, # Below 0.85 threshold natively
        last_verified=time.time()
    )
    success = gov_db.propose_pack_update(bad_pack)
    assert not success, "Governance Engine failed to block inherently low-confidence inputs structurally!"

    # 2. Propose Valid V1 Pack
    v1_pack = DomainPack(
        pack_id="coding_style_pep8",
        mission_class=MissionClass.CODING,
        version=1,
        ruleset="Use Type Hints.",
        source_author="core_admin",
        confidence=0.99,
        last_verified=time.time()
    )
    assert gov_db.propose_pack_update(v1_pack)
    
    # 3. Propose Valid V2 Pack
    v2_pack = DomainPack(
        pack_id="coding_style_pep8",
        mission_class=MissionClass.CODING,
        version=2,
        ruleset="Use Type Hints AND Docstrings.",
        source_author="core_admin",
        confidence=0.95,
        last_verified=time.time()
    )
    assert gov_db.propose_pack_update(v2_pack)
    
    # 4. Assert Retrieval selects V2 via Newest-Wins Rule structurally
    context = governor.retrieve_domain_context(MissionClass.CODING, "coding_style_pep8")
    assert "Version: v2" in context
    assert "Docstrings" in context

    # 5. Insert V1 Authoritative Override pack
    v1_auth_pack = DomainPack(
        pack_id="coding_style_pep8",
        mission_class=MissionClass.CODING,
        version=1,
        ruleset="Use Type Hints.",
        source_author="core_admin",
        confidence=0.99,
        last_verified=time.time(),
        is_authoritative=True # Explicit Override mapping offline limits
    )
    gov_db.propose_pack_update(v1_auth_pack)
    
    # 6. Assert Retrieval selects V1 now because it's Authoritative mathematically!
    context2 = governor.retrieve_domain_context(MissionClass.CODING, "coding_style_pep8")
    assert "Version: v1" in context2
    assert "Authoritative: True" in context2

    print("Phase 25 Benchmark Suite -> Versioned Governance Integrity Passed!")
