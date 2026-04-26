import os
import time
import pytest
import asyncio
from schemas import MissionClass, TaskQueueStatus
from task_queue_db import TaskQueueDb
from scheduler_daemon import SchedulerDaemon

TEST_QUEUE_DB = "test_queue.db"

def setup_function():
    if os.path.exists(TEST_QUEUE_DB): os.remove(TEST_QUEUE_DB)

def teardown_function():
    try:
        if os.path.exists(TEST_QUEUE_DB): os.remove(TEST_QUEUE_DB)
    except PermissionError: pass

async def _run_async_test():
    queue = TaskQueueDb(db_path=TEST_QUEUE_DB)
    daemon = SchedulerDaemon(queue_db=queue)

    # 1. Enqueue Safe Maintenance Chron Task
    safe_q_id = queue.enqueue_mission(MissionClass.MAINTENANCE, "clean_disk_cache", time.time() - 10)
    
    # 2. Enqueue Risky Admin Chron Task
    risky_q_id = queue.enqueue_mission(MissionClass.LOCAL_ADMIN, "migrate_sqlite", time.time() - 10)
    
    # Run the daemon loop momentarily
    daemon_task = asyncio.create_task(daemon.run_loop())
    await asyncio.sleep(0.5) 
    daemon.stop()
    await daemon_task
    
    # 3. Assert Maintenance finished securely unsupervised natively
    import sqlite3
    conn = sqlite3.connect(TEST_QUEUE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute('SELECT status FROM queued_missions WHERE queue_id = ?', (safe_q_id,))
    safe_status = cur.fetchone()['status']
    assert safe_status == TaskQueueStatus.COMPLETED.value, "Safe MAINTENANCE execution failed to fire cleanly unsupervised!"
    
    # 4. Assert Admin suspended securely waiting Human gates actively natively
    cur.execute('SELECT status FROM queued_missions WHERE queue_id = ?', (risky_q_id,))
    risky_status = cur.fetchone()['status']
    assert risky_status == TaskQueueStatus.AWAITING_APPROVAL.value, "DAEMON CRITICAL FAULT: Bypassed LOCAL_ADMIN risk halts autonomously unsupervised!"
    
    print("Phase 27 Benchmark Suite -> Unattended Daemon Lease integrity Passed perfectly!")

def test_scheduler_daemon_unattended_bounds():
    asyncio.run(_run_async_test())
