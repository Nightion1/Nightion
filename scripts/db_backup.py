import sqlite3
import shutil
import os
import time

from config import config

def create_backup(source_db=config.MEMORY_DB_PATH, backup_dir=config.BACKUP_DIR) -> str:
    """ Generates atomic SQLite `.bak` snapshots bypassing active WAL loops explicitly gracefully. """
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        
    timestamp = int(time.time() * 1000)
    backup_path = os.path.join(backup_dir, f"memory_core_{timestamp}.bak")
    
    if not os.path.exists(source_db):
        return backup_path # Nothing to backup yet
        
    try:
        # We use python sqlite3 iter-backup natively to securely lock-bypass WAL writes securely
        src = sqlite3.connect(source_db)
        dst = sqlite3.connect(backup_path)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        print(f"[BACKUP] Atomic snapshot captured: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"[BACKUP ERROR] Failed SQLite drop natively: {str(e)}")
        raise e

if __name__ == "__main__":
    create_backup()
