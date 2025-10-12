#!/usr/bin/env python3
"""
Test database connection for Render deployment
"""
import os
import psycopg2
from psycopg2 import sql

def test_database_connection():
    """Test if we can connect to the PostgreSQL database"""
    try:
        # Get database URL from environment
        database_url = os.getenv('DATABASE_URL')
        
        if not database_url:
            print("❌ DATABASE_URL not found in environment variables")
            return False
        
        print(f"🔍 Testing connection to: {database_url[:50]}...")
        
        # Test connection
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ Database connection successful!")
        print(f"📊 PostgreSQL version: {version[0]}")
        
        # Test if tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = cursor.fetchall()
        
        if tables:
            print(f"📋 Existing tables: {[table[0] for table in tables]}")
        else:
            print("📋 No tables found - database is empty")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Database Connection...")
    success = test_database_connection()
    
    if success:
        print("🎉 Database connection test PASSED!")
    else:
        print("💥 Database connection test FAILED!")

