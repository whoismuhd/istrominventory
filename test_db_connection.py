#!/usr/bin/env python3
"""
Test database connection to verify PostgreSQL is working properly
"""

import os
from database_config import get_conn, DATABASE_TYPE, POSTGRES_CONFIG

def test_database_connection():
    """Test database connection and verify it's using PostgreSQL"""
    print("🔍 Testing database connection...")
    print(f"📊 Database type: {DATABASE_TYPE}")
    
    if DATABASE_TYPE == 'postgresql':
        print(f"🔗 PostgreSQL Config: {POSTGRES_CONFIG}")
    else:
        print("❌ Not using PostgreSQL!")
        return False
    
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            
            # Test basic connection
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            print(f"✅ Database connected successfully!")
            print(f"📊 Database version: {version}")
            
            # Test table creation
            cur.execute("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id SERIAL PRIMARY KEY,
                    test_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            print("✅ Table creation works!")
            
            # Test data insertion
            cur.execute("INSERT INTO test_table (test_data) VALUES (?)", ("test_value",))
            conn.commit()
            print("✅ Data insertion works!")
            
            # Test data retrieval
            cur.execute("SELECT * FROM test_table WHERE test_data = ?", ("test_value",))
            result = cur.fetchone()
            if result:
                print("✅ Data retrieval works!")
                print(f"📊 Retrieved data: {result}")
            else:
                print("❌ Data retrieval failed!")
                return False
            
            # Clean up test table
            cur.execute("DROP TABLE IF EXISTS test_table")
            conn.commit()
            print("✅ Cleanup works!")
            
            return True
            
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    success = test_database_connection()
    if success:
        print("🎉 Database connection test PASSED!")
    else:
        print("💥 Database connection test FAILED!")
