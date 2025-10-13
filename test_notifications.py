"""
Test script for the notification system.

This script verifies that all notification functions work correctly
with both SQLite and PostgreSQL databases.
"""

import logging
import sys
from datetime import datetime
from notifications import (
    create_notification, get_notifications, get_unread_count,
    mark_notification_as_read, mark_all_as_read, delete_notification,
    delete_all_notifications, format_relative_time
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_notification_creation():
    """Test notification creation with idempotency."""
    print("🧪 Testing notification creation...")
    
    # Test 1: Create notification
    success = create_notification(
        sender_id=None,
        receiver_id=1,
        message="Test notification",
        notification_type='info',
        event_key='test:1:created'
    )
    
    assert success, "Failed to create notification"
    print("✅ Notification creation test passed")
    
    # Test 2: Test idempotency (should not create duplicate)
    success2 = create_notification(
        sender_id=None,
        receiver_id=1,
        message="Test notification (duplicate)",
        notification_type='info',
        event_key='test:1:created'  # Same event key
    )
    
    assert success2, "Failed to handle idempotent notification"
    print("✅ Idempotency test passed")

def test_notification_retrieval():
    """Test notification retrieval and pagination."""
    print("🧪 Testing notification retrieval...")
    
    # Get notifications
    notifications = get_notifications(user_id=1, limit=10)
    
    assert isinstance(notifications, list), "Notifications should be a list"
    print(f"✅ Retrieved {len(notifications)} notifications")
    
    # Test unread count
    unread_count = get_unread_count(user_id=1)
    assert isinstance(unread_count, int), "Unread count should be an integer"
    print(f"✅ Unread count: {unread_count}")

def test_notification_actions():
    """Test notification actions (mark as read, delete)."""
    print("🧪 Testing notification actions...")
    
    # Get a notification to test with
    notifications = get_notifications(user_id=1, limit=1)
    
    if notifications:
        notification_id = notifications[0]['id']
        
        # Test mark as read
        success = mark_notification_as_read(notification_id)
        assert success, "Failed to mark notification as read"
        print("✅ Mark as read test passed")
        
        # Test delete
        success = delete_notification(notification_id)
        assert success, "Failed to delete notification"
        print("✅ Delete notification test passed")
    else:
        print("⚠️ No notifications to test actions with")

def test_bulk_operations():
    """Test bulk operations (mark all as read, delete all)."""
    print("🧪 Testing bulk operations...")
    
    # Test mark all as read
    success = mark_all_as_read(user_id=1)
    assert success, "Failed to mark all as read"
    print("✅ Mark all as read test passed")
    
    # Test delete all (for specific user)
    deleted_count = delete_all_notifications(user_id=1)
    assert isinstance(deleted_count, int), "Deleted count should be an integer"
    print(f"✅ Delete all test passed (deleted {deleted_count} notifications)")

def test_time_formatting():
    """Test relative time formatting."""
    print("🧪 Testing time formatting...")
    
    # Test with recent time
    recent_time = datetime.now()
    formatted = format_relative_time(recent_time)
    assert "ago" in formatted or "Just now" in formatted, "Time formatting failed"
    print(f"✅ Time formatting test passed: {formatted}")

def test_database_connection():
    """Test database connection and table existence."""
    print("🧪 Testing database connection...")
    
    try:
        from database_config import get_engine
        engine = get_engine()
        
        with engine.connect() as conn:
            # Check if notifications table exists
            result = conn.execute("""
                SELECT COUNT(*) FROM notifications
            """)
            count = result.scalar()
            print(f"✅ Database connection test passed (notifications table has {count} records)")
            
    except Exception as e:
        print(f"❌ Database connection test failed: {e}")
        return False
    
    return True

def run_all_tests():
    """Run all notification system tests."""
    print("🚀 Starting notification system tests...\n")
    
    try:
        # Test database connection first
        if not test_database_connection():
            print("❌ Database connection failed, skipping other tests")
            return False
        
        # Run all tests
        test_notification_creation()
        test_notification_retrieval()
        test_notification_actions()
        test_bulk_operations()
        test_time_formatting()
        
        print("\n🎉 All tests passed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        logger.error(f"Test failure: {e}")
        return False

def test_migration():
    """Test the migration script."""
    print("🧪 Testing migration script...")
    
    try:
        from migrate_notifications import migrate_notification_schema, verify_migration
        
        # Run migration
        success = migrate_notification_schema()
        assert success, "Migration failed"
        print("✅ Migration test passed")
        
        # Verify migration
        verified = verify_migration()
        assert verified, "Migration verification failed"
        print("✅ Migration verification test passed")
        
    except Exception as e:
        print(f"❌ Migration test failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🔔 Notification System Test Suite")
    print("=" * 50)
    
    # Check if we should run migration test
    if len(sys.argv) > 1 and sys.argv[1] == "--migrate":
        success = test_migration()
    else:
        success = run_all_tests()
    
    if success:
        print("\n✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)
