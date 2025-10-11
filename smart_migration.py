#!/usr/bin/env python3
"""
Smart migration system that only migrates current data
Prevents old deleted data from being restored
"""

import os
import time
import sqlite3
from database_config import get_conn, DATABASE_TYPE

def should_migrate_data():
    """Check if we should migrate data based on timestamps"""
    try:
        # Check if local SQLite database exists and is recent
        local_db = os.getenv('SQLITE_DB_PATH', 'istrominventory.db')
        if not os.path.exists(local_db):
            print("📭 No local SQLite database found")
            return False
        
        # Check local database modification time
        local_mtime = os.path.getmtime(local_db)
        local_age = time.time() - local_mtime
        
        # Only migrate if local database is recent (less than 24 hours old)
        if local_age > 86400:  # 24 hours
            print(f"⚠️ Local database is {local_age/3600:.1f} hours old, skipping migration")
            return False
        
        print(f"✅ Local database is {local_age/3600:.1f} hours old, proceeding with migration")
        return True
        
    except Exception as e:
        print(f"❌ Error checking migration eligibility: {e}")
        return False

def get_current_user_count():
    """Get current user count from local database"""
    try:
        local_db = os.getenv('SQLITE_DB_PATH', 'istrominventory.db')
        if not os.path.exists(local_db):
            return 0
        
        conn = sqlite3.connect(local_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"❌ Error getting user count: {e}")
        return 0

def smart_migrate():
    """Perform smart migration that respects current state"""
    print("🧠 Smart migration starting...")
    
    # Check if we should migrate
    if not should_migrate_data():
        print("⏭️ Skipping migration - local data is too old or doesn't exist")
        return True
    
    # Get current user count
    local_user_count = get_current_user_count()
    print(f"📊 Local database has {local_user_count} users")
    
    # Check production database
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            prod_user_count = cursor.fetchone()[0]
            print(f"📊 Production database has {prod_user_count} users")
            
            # If production has more users than local, don't migrate
            if prod_user_count > local_user_count:
                print("⚠️ Production has more users than local - skipping migration to preserve data")
                return True
            
            # If production has same or fewer users, proceed with migration
            if prod_user_count <= local_user_count:
                print("✅ Proceeding with migration to sync current local state")
                from database_config import migrate_from_sqlite
                migrate_from_sqlite()
                return True
                
    except Exception as e:
        print(f"❌ Error checking production database: {e}")
        return False

if __name__ == "__main__":
    smart_migrate()
