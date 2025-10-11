#!/usr/bin/env python3
"""
Production Data Guard - Prevents migration when production has data
This ensures production data is never overwritten by local state
"""

import os
from database_config import get_conn

def has_production_data():
    """Check if production database has any data"""
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            
            # Check for any data in key tables
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM items")
            item_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM requests")
            request_count = cursor.fetchone()[0]
            
            total_data = user_count + item_count + request_count
            
            if total_data > 0:
                print(f"🛡️ Production has data: {user_count} users, {item_count} items, {request_count} requests")
                return True
            else:
                print("📭 Production is empty")
                return False
                
    except Exception as e:
        print(f"❌ Error checking production data: {e}")
        return False

def should_migrate():
    """Determine if migration should proceed"""
    if has_production_data():
        print("🚫 Migration blocked - Production has data that would be overwritten")
        print("✅ Production data will be preserved")
        return False
    else:
        print("✅ Production is empty - Migration can proceed")
        return True

if __name__ == "__main__":
    should_migrate()
