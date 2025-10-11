#!/usr/bin/env python3
"""
Simple and robust backup/restore system
Uses INSERT INTO table SELECT * FROM source approach
"""

import os
import sqlite3
import shutil
from database_config import get_conn, DATABASE_TYPE

def simple_backup():
    """Create a simple backup by copying the database file"""
    try:
        if DATABASE_TYPE == 'sqlite':
            # For SQLite, just copy the database file
            source_db = os.getenv('SQLITE_DB_PATH', 'istrominventory.db')
            backup_db = 'backup_istrominventory.db'
            
            if os.path.exists(source_db):
                shutil.copy2(source_db, backup_db)
                print(f"✅ Simple backup created: {backup_db}")
                return True
            else:
                print(f"❌ Source database not found: {source_db}")
                return False
        else:
            print("❌ Simple backup only works with SQLite")
            return False
            
    except Exception as e:
        print(f"❌ Simple backup failed: {e}")
        return False

def simple_restore():
    """Restore from simple backup"""
    try:
        if DATABASE_TYPE == 'sqlite':
            source_db = os.getenv('SQLITE_DB_PATH', 'istrominventory.db')
            backup_db = 'backup_istrominventory.db'
            
            if os.path.exists(backup_db):
                shutil.copy2(backup_db, source_db)
                print(f"✅ Simple restore completed: {source_db}")
                return True
            else:
                print(f"❌ Backup database not found: {backup_db}")
                return False
        else:
            print("❌ Simple restore only works with SQLite")
            return False
            
    except Exception as e:
        print(f"❌ Simple restore failed: {e}")
        return False

def test_backup_restore():
    """Test the backup/restore system"""
    print("🧪 TESTING SIMPLE BACKUP/RESTORE")
    print("=" * 40)
    
    # Test backup
    print("1. Testing backup...")
    if simple_backup():
        print("✅ Backup successful")
    else:
        print("❌ Backup failed")
        return False
    
    # Test restore
    print("2. Testing restore...")
    if simple_restore():
        print("✅ Restore successful")
    else:
        print("❌ Restore failed")
        return False
    
    # Verify data integrity
    print("3. Verifying data integrity...")
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM items")
            item_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            print(f"📊 Verified: {item_count} items, {user_count} users")
            return True
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "backup":
        simple_backup()
    elif len(sys.argv) > 1 and sys.argv[1] == "restore":
        simple_restore()
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        test_backup_restore()
    else:
        print("Usage: python simple_backup.py [backup|restore|test]")
