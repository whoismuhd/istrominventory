#!/usr/bin/env python3
"""
Database initialization script for Render deployment
This ensures PostgreSQL database is properly set up with all tables and data
"""

import os
import sys
from database_config import create_tables, migrate_from_sqlite, get_conn

def initialize_database():
    """Initialize the database for production deployment"""
    print("🚀 Initializing database for production deployment...")
    
    try:
        # Create all tables
        print("📋 Creating database tables...")
        create_tables()
        
        # Migrate data from SQLite if it exists
        print("🔄 Migrating data from SQLite...")
        migrate_from_sqlite()
        
        # Verify database connection
        print("✅ Verifying database connection...")
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM items")
            item_count = cursor.fetchone()[0]
            print(f"📊 Database initialized with {item_count} items")
        
        print("🎉 Database initialization completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    success = initialize_database()
    sys.exit(0 if success else 1)
