#!/usr/bin/env python3
"""
Database initialization script for Render deployment
This ensures PostgreSQL database is properly set up with all tables and data
"""

import os
import sys
import time
from database_config import create_tables, migrate_from_sqlite, get_conn, DATABASE_TYPE
from simple_backup import simple_backup, simple_restore
from smart_migration import smart_migrate
from production_data_guard import should_migrate

def initialize_database():
    """Initialize the database for production deployment"""
    print("🚀 Initializing database for production deployment...")
    print(f"📊 Database type: {DATABASE_TYPE}")
    
    # SMART PROTECTION: Only migrate if production database is empty
    if DATABASE_TYPE == 'postgresql':
        print("🛡️ PRODUCTION ENVIRONMENT DETECTED - Checking if migration is safe...")
        
        # Check if production database has any data
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                
                # Check if any data exists in production
                cur.execute("SELECT COUNT(*) FROM users")
                user_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM items") 
                item_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM requests")
                request_count = cur.fetchone()[0]
                
                total_data = user_count + item_count + request_count
                
                if total_data > 0:
                    print(f"📊 Production database has {total_data} records (Users: {user_count}, Items: {item_count}, Requests: {request_count})")
                    print("🚫 MIGRATION BLOCKED - Production data exists")
                    print("✅ Your deployed app data is PROTECTED")
                    print("✅ Code changes will deploy, but data will NOT be overwritten")
                    return True
                else:
                    print("📭 Production database is empty - Safe to migrate")
                    print("🔄 Proceeding with migration...")
        except Exception as e:
            print(f"⚠️ Could not check production data: {e}")
            print("🚫 MIGRATION BLOCKED - Cannot verify production data safety")
            return True
    
    # Check if migration is disabled - MULTIPLE CHECKS
    migration_disabled = False
    
    # Check 1: MIGRATION_DISABLED file
    if os.path.exists('MIGRATION_DISABLED'):
        migration_disabled = True
        print("🚫 MIGRATION DISABLED - File found")
    
    # Check 2: Environment variable
    if os.getenv('DISABLE_MIGRATION', '').lower() in ['true', '1', 'yes']:
        migration_disabled = True
        print("🚫 MIGRATION DISABLED - Environment variable set")
    
    # Check 3: Force disable for production
    if DATABASE_TYPE == 'postgresql':
        migration_disabled = True
        print("🚫 MIGRATION DISABLED - Production database detected")
    
    if migration_disabled:
        print("🚫 MIGRATION DISABLED - Production data is sacred, skipping all migration")
        print("✅ ALL production data will be preserved (users, items, requests, notifications, etc.)")
        print("✅ Your deployed app changes will NEVER be overwritten")
        print("🛡️ PRODUCTION DATA PROTECTION ACTIVE")
        return True
    
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
            
            # NEVER MIGRATE - Production data is sacred
            print("🚫 MIGRATION COMPLETELY DISABLED")
            print("✅ Production data is sacred and will never be touched")
            print("✅ All your deployed app changes will persist forever")
            return True
        
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
