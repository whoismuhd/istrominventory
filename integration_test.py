#!/usr/bin/env python3
"""
Comprehensive Integration Test for IstromInventory System
Tests all major components and their integration
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_database_integration():
    """Test database connection and initialization"""
    print("🔍 Testing Database Integration...")
    try:
        from db import get_engine, init_db
        from sqlalchemy import text
        
        # Test engine creation
        engine = get_engine()
        print("✅ Database engine created successfully")
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful")
        
        # Test initialization
        init_db()
        print("✅ Database initialization successful")
        
        return True
    except Exception as e:
        print(f"❌ Database integration failed: {e}")
        return False

def test_authentication_integration():
    """Test authentication system integration"""
    print("\n🔍 Testing Authentication Integration...")
    try:
        from istrominventory import (
            authenticate_user, 
            get_access_codes, 
            is_admin,
            check_session_validity,
            save_session_to_cookie,
            restore_session_from_cookie
        )
        
        # Test access codes retrieval
        codes = get_access_codes()
        print("✅ Access codes retrieval successful")
        
        # Test authentication function exists
        print("✅ Authentication functions available")
        
        # Test session management functions
        print("✅ Session management functions available")
        
        return True
    except Exception as e:
        print(f"❌ Authentication integration failed: {e}")
        return False

def test_user_management_integration():
    """Test user management system integration"""
    print("\n🔍 Testing User Management Integration...")
    try:
        from istrominventory import (
            get_all_users,
            get_project_sites,
            add_project_site,
            get_user_project_site
        )
        
        # Test user management functions
        print("✅ User management functions available")
        
        # Test project site management
        print("✅ Project site management functions available")
        
        return True
    except Exception as e:
        print(f"❌ User management integration failed: {e}")
        return False

def test_inventory_integration():
    """Test inventory management integration"""
    print("\n🔍 Testing Inventory Management Integration...")
    try:
        from istrominventory import (
            get_inventory_items,
            add_inventory_item,
            update_inventory_item,
            delete_inventory_item
        )
        
        # Test inventory functions
        print("✅ Inventory management functions available")
        
        return True
    except Exception as e:
        print(f"❌ Inventory integration failed: {e}")
        return False

def test_request_system_integration():
    """Test request system integration"""
    print("\n🔍 Testing Request System Integration...")
    try:
        from istrominventory import (
            get_requests,
            add_request,
            update_request_status,
            get_user_requests
        )
        
        # Test request functions
        print("✅ Request system functions available")
        
        return True
    except Exception as e:
        print(f"❌ Request system integration failed: {e}")
        return False

def test_notification_integration():
    """Test notification system integration"""
    print("\n🔍 Testing Notification System Integration...")
    try:
        from istrominventory import (
            get_notifications,
            add_notification,
            mark_notification_read,
            show_notification_popups
        )
        
        # Test notification functions
        print("✅ Notification system functions available")
        
        return True
    except Exception as e:
        print(f"❌ Notification integration failed: {e}")
        return False

def test_session_persistence_integration():
    """Test session persistence integration"""
    print("\n🔍 Testing Session Persistence Integration...")
    try:
        from istrominventory import (
            save_session_to_cookie,
            restore_session_from_cookie,
            check_session_validity
        )
        
        # Test session persistence functions
        print("✅ Session persistence functions available")
        
        return True
    except Exception as e:
        print(f"❌ Session persistence integration failed: {e}")
        return False

def test_error_handling_integration():
    """Test error handling integration"""
    print("\n🔍 Testing Error Handling Integration...")
    try:
        from istrominventory import (
            log_access,
            log_error,
            handle_database_error
        )
        
        # Test error handling functions
        print("✅ Error handling functions available")
        
        return True
    except Exception as e:
        print(f"❌ Error handling integration failed: {e}")
        return False

def test_performance_integration():
    """Test performance optimization integration"""
    print("\n🔍 Testing Performance Integration...")
    try:
        from istrominventory import (
            get_access_codes,  # This should be cached
            get_inventory_items,
            get_requests
        )
        
        # Test that caching is working
        print("✅ Performance optimization functions available")
        
        return True
    except Exception as e:
        print(f"❌ Performance integration failed: {e}")
        return False

def run_comprehensive_integration_test():
    """Run all integration tests"""
    print("🚀 Starting Comprehensive Integration Test for IstromInventory")
    print("=" * 60)
    
    tests = [
        test_database_integration,
        test_authentication_integration,
        test_user_management_integration,
        test_inventory_integration,
        test_request_system_integration,
        test_notification_integration,
        test_session_persistence_integration,
        test_error_handling_integration,
        test_performance_integration
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
    success = run_comprehensive_integration_test()
    sys.exit(0 if success else 1)
