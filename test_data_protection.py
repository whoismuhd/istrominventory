#!/usr/bin/env python3
"""
Test script to verify data protection is working
"""

import os
from database_config import DATABASE_TYPE

def test_data_protection():
    """Test that data protection is active"""
    print("🛡️ TESTING DATA PROTECTION...")
    
    # Check 1: Database type
    print(f"📊 Database type: {DATABASE_TYPE}")
    
    # Check 2: Environment variables
    disable_migration = os.getenv('DISABLE_MIGRATION', '')
    print(f"🔒 DISABLE_MIGRATION: {disable_migration}")
    
    # Check 3: MIGRATION_DISABLED file
    migration_file_exists = os.path.exists('MIGRATION_DISABLED')
    print(f"📁 MIGRATION_DISABLED file exists: {migration_file_exists}")
    
    # Protection status
    if DATABASE_TYPE == 'postgresql':
        print("✅ PRODUCTION DATABASE DETECTED - PROTECTION ACTIVE")
        return True
    elif disable_migration.lower() in ['true', '1', 'yes']:
        print("✅ MIGRATION DISABLED VIA ENV VAR - PROTECTION ACTIVE")
        return True
    elif migration_file_exists:
        print("✅ MIGRATION DISABLED VIA FILE - PROTECTION ACTIVE")
        return True
    else:
        print("❌ NO PROTECTION DETECTED - MIGRATION COULD OVERWRITE DATA")
        return False

if __name__ == "__main__":
    test_data_protection()
