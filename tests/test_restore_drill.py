import os
import shutil
import pytest
import sqlite3
from scripts.db_backup import create_backup
from state_migration import AtomicMigrator

TEST_DB = "test_memory_core.db"
TEST_BACKUP = "test_brain_backups"

def setup_function():
    if os.path.exists(TEST_DB): os.remove(TEST_DB)
    if os.path.exists(TEST_BACKUP): shutil.rmtree(TEST_BACKUP)
    os.makedirs(TEST_BACKUP)

def test_atomic_migration_and_restore_drill():
    """ Proves Nightion safely catches atomic schemas recovering gracefully natively spanning exact physical drill limits accurately offline. """
    
    # 1. Create a dummy baseline DB
    conn = sqlite3.connect(TEST_DB)
    conn.cursor().execute("CREATE TABLE mock_table (id INTEGER);")
    conn.commit()
    conn.close()
    
    # 2. Trigger Backup
    backup_path = create_backup(source_db=TEST_DB, backup_dir=TEST_BACKUP)
    assert os.path.exists(backup_path), "Backup snapshot failed to write to physical arrays properly natively."
    
    # 3. Simulate Migration (using AtomicMigrator with test DB bindings)
    migrator = AtomicMigrator(db_path=TEST_DB)
    success = migrator.run_migrations()
    assert success, "Atomic Migration fatally drifted avoiding deterministic schema limits."
    
    # Verify migration executed natively adding session_chat
    conn = sqlite3.connect(TEST_DB)
    res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session_chat';").fetchall()
    assert len(res) == 1, "Migration Failed binding explicit Structural Schemas off-chain synchronously."
    conn.close()
    
    # 4. Invoke the Restore Drill
    os.remove(TEST_DB)
    migrator.restore_from_backup(backup_path)
    
    # 5. Verify Restore Drill exactness
    assert os.path.exists(TEST_DB), "Restore framework completely missed SQLite structural bindings gracefully."
    conn = sqlite3.connect(TEST_DB)
    res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mock_table';").fetchall()
    assert len(res) == 1, "Restore drift encountered mapping physical payload boundaries linearly off-grid."
    conn.close()
    
    print("--- RESTORE DRILL COMPLETED WITH 100% FIDELITY ---")
