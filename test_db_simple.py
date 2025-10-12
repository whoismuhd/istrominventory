#!/usr/bin/env python3
"""
Simple database connection test
"""
import os
os.environ['DATABASE_TYPE'] = 'postgresql'
os.environ['DATABASE_URL'] = 'postgresql://istrominventory_db_user:FKYfCmnleXrfhkNo5fiwExU0ARC6onae@dpg-d3l04shr0fns73euk800-a/istrominventory_db'

try:
    from database_config import get_conn, create_tables
    
    print("🔍 Testing database connection...")
    with get_conn() as conn:
        print("✅ Database connection successful!")
        
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()
        print(f"📊 PostgreSQL version: {version[0]}")
        
        # Test table creation
        print("📋 Testing table creation...")
        create_tables()
        print("✅ Table creation test completed!")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
