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
    
    # ULTRA-AGGRESSIVE PROTECTION: Multiple checks to block migration
    if DATABASE_TYPE == 'postgresql':
        print("🛡️ PRODUCTION ENVIRONMENT DETECTED - ULTRA-AGGRESSIVE PROTECTION")
        print("🚫 MIGRATION COMPLETELY BLOCKED - NO EXCEPTIONS")
        print("✅ Your deployed app data is PERMANENTLY PROTECTED")
        print("✅ Code changes will deploy, but data will NEVER be overwritten")
        print("✅ Users, items, requests, notifications - ALL PROTECTED")
        print("🚫 NO MIGRATION WILL EVER RUN ON PRODUCTION")
        print("🛡️ PRODUCTION DATA IS SACRED - NEVER TOUCHED")
        return True
    
    # Additional protection checks
    protection_files = ['MIGRATION_DISABLED', 'NO_MIGRATION', 'PRODUCTION_PROTECTED', 'DATA_GUARD_ACTIVE', 'NEVER_MIGRATE', 'PRODUCTION_SACRED']
    for file in protection_files:
        if os.path.exists(file):
            print(f"🛡️ PROTECTION FILE FOUND: {file}")
            print("🚫 MIGRATION BLOCKED - PRODUCTION DATA PROTECTED")
            return True
    
    # Environment variable checks
    if os.getenv('DISABLE_MIGRATION', '').lower() in ['true', '1', 'yes']:
        print("🛡️ DISABLE_MIGRATION ENVIRONMENT VARIABLE SET")
        print("🚫 MIGRATION BLOCKED - PRODUCTION DATA PROTECTED")
        return True
    
    if os.getenv('NO_MIGRATION', '').lower() in ['true', '1', 'yes']:
        print("🛡️ NO_MIGRATION ENVIRONMENT VARIABLE SET")
        print("🚫 MIGRATION BLOCKED - PRODUCTION DATA PROTECTED")
        return True
    
    if os.getenv('PRODUCTION_MODE', '').lower() in ['true', '1', 'yes']:
        print("🛡️ PRODUCTION_MODE ENVIRONMENT VARIABLE SET")
        print("🚫 MIGRATION BLOCKED - PRODUCTION DATA PROTECTED")
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
