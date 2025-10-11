#!/usr/bin/env python3
"""
Test Render PostgreSQL database connection
"""
import os
import psycopg2
from psycopg2 import sql

def test_render_database():
    """Test connection to Render PostgreSQL database"""
    print("🚀 Testing Render PostgreSQL Database Connection...")
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        print("💡 Make sure to set DATABASE_URL in your render.yaml")
        return False
    
    print(f"🔍 Connecting to: {database_url[:50]}...")
    
    try:
        # Test connection
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ Database connection successful!")
        print(f"📊 PostgreSQL version: {version[0]}")
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = cursor.fetchall()
        
        if tables:
            print(f"📋 Existing tables: {[table[0] for table in tables]}")
        else:
            print("📋 No tables found - database is empty (this is normal for first deployment)")
        
        cursor.close()
        conn.close()
        
        print("🎉 Database connection test PASSED!")
        print("✅ Your data will now persist between deployments!")
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("💡 Check your DATABASE_URL in render.yaml")
        return False

if __name__ == "__main__":
    test_render_database()
