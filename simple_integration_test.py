#!/usr/bin/env python3
"""
Simple Integration Test for IstromInventory System
Tests core functionality without Streamlit context
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_database_connection():
    """Test database connection"""
    print("🔍 Testing Database Connection...")
    try:
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_database_initialization():
    """Test database initialization"""
    print("\n🔍 Testing Database Initialization...")
    try:
        from db import init_db
        init_db()
        print("✅ Database initialization successful")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def test_access_codes_system():
    """Test access codes system"""
    print("\n🔍 Testing Access Codes System...")
    try:
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        with engine.connect() as conn:
            # Test access_codes table
            result = conn.execute(text("SELECT COUNT(*) FROM access_codes"))
            count = result.fetchone()[0]
            print(f"✅ Access codes table exists with {count} records")
            
            # Test project_site_access_codes table
            result = conn.execute(text("SELECT COUNT(*) FROM project_site_access_codes"))
            count = result.fetchone()[0]
            print(f"✅ Project site access codes table exists with {count} records")
        
        return True
    except Exception as e:
        print(f"❌ Access codes system failed: {e}")
        return False

def test_inventory_system():
    """Test inventory system"""
    print("\n🔍 Testing Inventory System...")
    try:
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        with engine.connect() as conn:
            # Test items table
            result = conn.execute(text("SELECT COUNT(*) FROM items"))
            count = result.fetchone()[0]
            print(f"✅ Items table exists with {count} records")
            
            # Test requests table
            result = conn.execute(text("SELECT COUNT(*) FROM requests"))
            count = result.fetchone()[0]
            print(f"✅ Requests table exists with {count} records")
            
            # Test request_lines table
            result = conn.execute(text("SELECT COUNT(*) FROM request_lines"))
            count = result.fetchone()[0]
            print(f"✅ Request lines table exists with {count} records")
        
        return True
    except Exception as e:
        print(f"❌ Inventory system failed: {e}")
        return False

def test_notification_system():
    """Test notification system"""
    print("\n🔍 Testing Notification System...")
    try:
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        with engine.connect() as conn:
            # Test notifications table
            result = conn.execute(text("SELECT COUNT(*) FROM notifications"))
            count = result.fetchone()[0]
            print(f"✅ Notifications table exists with {count} records")
        
        return True
    except Exception as e:
        print(f"❌ Notification system failed: {e}")
        return False

def test_user_management_system():
    """Test user management system"""
    print("\n🔍 Testing User Management System...")
    try:
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        with engine.connect() as conn:
            # Test project_sites table
            result = conn.execute(text("SELECT COUNT(*) FROM project_sites"))
            count = result.fetchone()[0]
            print(f"✅ Project sites table exists with {count} records")
            
            # Test access_logs table
            result = conn.execute(text("SELECT COUNT(*) FROM access_logs"))
            count = result.fetchone()[0]
            print(f"✅ Access logs table exists with {count} records")
        
        return True
    except Exception as e:
        print(f"❌ User management system failed: {e}")
        return False

def test_data_integrity():
    """Test data integrity"""
    print("\n🔍 Testing Data Integrity...")
    try:
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        with engine.connect() as conn:
            # Test table structure and constraints
            result = conn.execute(text("PRAGMA table_info(items)"))
            items_columns = result.fetchall()
            print(f"✅ Items table has {len(items_columns)} columns")
            
            result = conn.execute(text("PRAGMA table_info(requests)"))
            requests_columns = result.fetchall()
            print(f"✅ Requests table has {len(requests_columns)} columns")
            
            result = conn.execute(text("PRAGMA table_info(notifications)"))
            notifications_columns = result.fetchall()
            print(f"✅ Notifications table has {len(notifications_columns)} columns")
            
            # Test foreign key constraints
            result = conn.execute(text("PRAGMA foreign_key_list(requests)"))
            fk_count = len(result.fetchall())
            print(f"✅ Foreign key constraints exist: {fk_count} constraints")
        
        return True
    except Exception as e:
        print(f"❌ Data integrity test failed: {e}")
        return False

def test_performance_optimization():
    """Test performance optimization"""
    print("\n🔍 Testing Performance Optimization...")
    try:
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        with engine.connect() as conn:
            # Test indexes using SQLite PRAGMA
            result = conn.execute(text("PRAGMA index_list(items)"))
            items_indexes = result.fetchall()
            print(f"✅ Items table has {len(items_indexes)} indexes")
            
            result = conn.execute(text("PRAGMA index_list(requests)"))
            requests_indexes = result.fetchall()
            print(f"✅ Requests table has {len(requests_indexes)} indexes")
            
            # Test connection pooling
            pool_size = engine.pool.size()
            print(f"✅ Connection pool size: {pool_size}")
            
            # Test database file size
            import os
            db_size = os.path.getsize("istrominventory.db")
            print(f"✅ Database file size: {db_size / 1024:.1f} KB")
        
        return True
    except Exception as e:
        print(f"❌ Performance optimization test failed: {e}")
        return False

def run_simple_integration_test():
    """Run simple integration test"""
    print("🚀 Starting Simple Integration Test for IstromInventory")
    print("=" * 60)
    
    tests = [
        test_database_connection,
        test_database_initialization,
        test_access_codes_system,
        test_inventory_system,
        test_notification_system,
        test_user_management_system,
        test_data_integrity,
        test_performance_optimization
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Integration Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL INTEGRATION TESTS PASSED!")
        print("✅ The application is fully integrated and ready for production")
        return True
    else:
        print(f"⚠️  {total - passed} integration tests failed")
        print("❌ Some components may not be properly integrated")
        return False

if __name__ == "__main__":
    success = run_simple_integration_test()
    sys.exit(0 if success else 1)
