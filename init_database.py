#!/usr/bin/env python3
"""
Database initialization script for Render deployment
This ensures PostgreSQL database is properly set up with all tables and data
"""

import os
import sys
import time
from database_config import create_tables, migrate_from_sqlite, get_conn, DATABASE_TYPE
from backup_data import backup_to_json, restore_from_json

def initialize_database():
    """Initialize the database for production deployment"""
    print("🚀 Initializing database for production deployment...")
    print(f"📊 Database type: {DATABASE_TYPE}")
    
    try:
        # Wait for database to be ready (Render sometimes needs a moment)
        print("⏳ Waiting for database connection...")
        max_retries = 10
        for attempt in range(max_retries):
            try:
                with get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    print("✅ Database connection successful!")
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⏳ Attempt {attempt + 1}/{max_retries}: Database not ready, retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    raise e
        
        # Create all tables
        print("📋 Creating database tables...")
        create_tables()
        
        # Check if we need to migrate data
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM items")
            item_count = cursor.fetchone()[0]
            
            if item_count == 0:
                print("🔄 No data found, attempting to restore from backup...")
                if not restore_from_json():
                    print("🔄 No backup found, migrating from SQLite...")
                    migrate_from_sqlite()
                else:
                    print("✅ Data restored from backup")
            else:
                print(f"📊 Database already has {item_count} items, creating backup...")
                backup_to_json()
        
        # Final verification
        print("✅ Final verification...")
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM items")
            item_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            print(f"📊 Database ready with {item_count} items and {user_count} users")
        
        print("🎉 Database initialization completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = initialize_database()
    sys.exit(0 if success else 1)
