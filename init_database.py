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
    """Initialize the database for production deployment - SAFE TABLE CREATION ONLY"""
    print("🚀 Initializing database for production deployment...")
    print(f"📊 Database type: {DATABASE_TYPE}")
    
    try:
        # Only create tables if they don't exist - NEVER touch existing data
        print("📋 Creating tables if they don't exist...")
        create_tables()
        print("✅ Database initialization completed successfully!")
        print("🛡️ Your production data is SAFE - only table structure created")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    success = initialize_database()
    sys.exit(0 if success else 1)
