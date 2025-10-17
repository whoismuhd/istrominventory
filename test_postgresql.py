#!/usr/bin/env python3
"""
Test PostgreSQL connection for Render deployment
"""
import os
import psycopg2
import urllib.parse as urlparse

def test_postgresql_connection():
    """Test PostgreSQL connection with detailed debugging"""
    database_url = os.getenv('DATABASE_URL', '')
    
    print("🔍 Testing PostgreSQL connection...")
    print(f"🔍 DATABASE_URL: {database_url}")
    
    if not database_url:
        print("❌ No DATABASE_URL found")
        return False
    
    if 'postgresql://' not in database_url:
        print("❌ DATABASE_URL is not a PostgreSQL URL")
        return False
    
    try:
        # Parse the URL
        url = urlparse.urlparse(database_url)
        print(f"🔍 Parsed URL:")
        print(f"  - Host: {url.hostname}")
        print(f"  - Port: {url.port}")
        print(f"  - Database: {url.path[1:]}")
        print(f"  - User: {url.username}")
        print(f"  - Password: {'*' * len(url.password) if url.password else 'None'}")
        
        # Try direct connection
        print("🔄 Trying direct connection...")
        conn = psycopg2.connect(database_url)
        print("✅ Direct connection successful!")
        
        # Test the connection
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()
        print(f"🔍 PostgreSQL version: {version[0]}")
        
        # Test basic operations
        cur.execute("SELECT current_database();")
        db_name = cur.fetchone()
        print(f"🔍 Current database: {db_name[0]}")
        
        cur.execute("SELECT current_user;")
        user = cur.fetchone()
        print(f"🔍 Current user: {user[0]}")
        
        cur.close()
        conn.close()
        
        print("✅ PostgreSQL connection test successful!")
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    test_postgresql_connection()
