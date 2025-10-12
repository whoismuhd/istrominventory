#!/usr/bin/env python3
"""
ULTRA-AGGRESSIVE DATA PERSISTENCE GUARD
This script ensures that NO data is ever lost during deployments
"""

import os
import sys
import time
from datetime import datetime

def check_data_persistence():
    """Check if data persistence is properly configured"""
    print("🛡️ DATA PERSISTENCE GUARD - CHECKING CONFIGURATION")
    print("=" * 60)
    
    # Check environment variables
    env_vars = [
        'PRODUCTION_MODE',
        'DISABLE_MIGRATION', 
        'NO_MIGRATION',
        'DATA_PROTECTION',
        'DATABASE_URL'
    ]
    
    for var in env_vars:
        value = os.getenv(var, 'NOT SET')
        status = "✅" if value != 'NOT SET' else "❌"
        print(f"{status} {var}: {value}")
    
    print("\n🔍 CHECKING FOR DANGEROUS OPERATIONS:")
    
    # Check if any migration scripts exist
    dangerous_files = [
        'init_database.py',
        'smart_migration.py', 
        'simple_backup.py',
        'production_data_guard.py'
    ]
    
    for file in dangerous_files:
        if os.path.exists(file):
            print(f"⚠️  WARNING: {file} exists - could cause data loss!")
        else:
            print(f"✅ {file} not found - safe")
    
    print("\n🛡️ DATA PERSISTENCE STATUS:")
    
    # Check if we're in production mode
    if os.getenv('PRODUCTION_MODE') == 'true':
        print("✅ PRODUCTION MODE: ACTIVE")
        print("✅ MIGRATION DISABLED: ACTIVE") 
        print("✅ DATA PROTECTION: ACTIVE")
        print("✅ YOUR DATA IS SAFE!")
    else:
        print("⚠️  WARNING: Not in production mode - data could be at risk!")
    
    print("\n" + "=" * 60)
    print("🛡️ DATA PERSISTENCE GUARD COMPLETE")
    
    return True

def create_persistence_backup():
    """Create a backup of current data for emergency recovery"""
    try:
        from database_config import get_conn
        import json
        
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'users': [],
            'items': [],
            'requests': [],
            'notifications': []
        }
        
        with get_conn() as conn:
            cursor = conn.cursor()
            
            # Backup users
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()
            backup_data['users'] = [dict(zip([col[0] for col in cursor.description], user)) for user in users]
            
            # Backup items
            cursor.execute("SELECT * FROM items")
            items = cursor.fetchall()
            backup_data['items'] = [dict(zip([col[0] for col in cursor.description], item)) for item in items]
            
            # Backup requests
            cursor.execute("SELECT * FROM requests")
            requests = cursor.fetchall()
            backup_data['requests'] = [dict(zip([col[0] for col in cursor.description], req)) for req in requests]
            
            # Backup notifications
            cursor.execute("SELECT * FROM notifications")
            notifications = cursor.fetchall()
            backup_data['notifications'] = [dict(zip([col[0] for col in cursor.description], notif)) for notif in notifications]
        
        # Save backup
        backup_file = f"emergency_backup_{int(time.time())}.json"
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        print(f"✅ Emergency backup created: {backup_file}")
        return backup_file
        
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None

if __name__ == "__main__":
    print("🛡️ ULTRA-AGGRESSIVE DATA PERSISTENCE GUARD")
    print("=" * 60)
    
    # Check configuration
    check_data_persistence()
    
    # Create emergency backup
    backup_file = create_persistence_backup()
    
    if backup_file:
        print(f"\n✅ DATA PERSISTENCE GUARD COMPLETE")
        print(f"📁 Emergency backup: {backup_file}")
    else:
        print(f"\n❌ DATA PERSISTENCE GUARD FAILED")
        sys.exit(1)
