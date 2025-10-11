#!/usr/bin/env python3
"""
Manual migration script for when you want to sync local data to production
Use this only when you explicitly want to override production with local data
"""

import os
import sys
from database_config import migrate_from_sqlite, get_conn

def manual_migrate():
    """Manually migrate local data to production"""
    print("⚠️ MANUAL MIGRATION - This will override production data with local data")
    print("=" * 70)
    
    # Check local database
    local_db = os.getenv('SQLITE_DB_PATH', 'istrominventory.db')
    if not os.path.exists(local_db):
        print("❌ Local database not found")
        return False
    
    # Get local data counts
    import sqlite3
    conn = sqlite3.connect(local_db)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    local_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM items")
    local_items = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM requests")
    local_requests = cursor.fetchone()[0]
    conn.close()
    
    print(f"📊 Local database has:")
    print(f"  - {local_users} users")
    print(f"  - {local_items} items")
    print(f"  - {local_requests} requests")
    
    # Get production data counts
    try:
        with get_conn() as prod_conn:
            cursor = prod_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            prod_users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM items")
            prod_items = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM requests")
            prod_requests = cursor.fetchone()[0]
        
        print(f"📊 Production database has:")
        print(f"  - {prod_users} users")
        print(f"  - {prod_items} items")
        print(f"  - {prod_requests} requests")
        
        if prod_users > 0 or prod_items > 0 or prod_requests > 0:
            print("⚠️ WARNING: Production has existing data that will be overwritten!")
            print("This migration will replace production data with local data.")
            
            # Ask for confirmation
            response = input("Are you sure you want to proceed? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Migration cancelled")
                return False
        
        print("🔄 Starting migration...")
        migrate_from_sqlite()
        print("✅ Migration completed!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    manual_migrate()
