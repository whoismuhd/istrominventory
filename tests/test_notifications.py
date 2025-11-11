"""
Unit tests for notification functions
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestNotificationFunctions:
    """Test notification-related functions"""
    
    @patch('istrominventory.st.session_state', {'user_type': 'admin', 'current_project_site': None})
    def test_get_admin_notifications_function_exists(self):
        """Test that get_admin_notifications function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'get_admin_notifications')
        assert callable(getattr(istrominventory, 'get_admin_notifications', None))
    
    @patch('istrominventory.st.session_state', {'user_type': 'admin', 'current_project_site': None})
    def test_get_all_notifications_function_exists(self):
        """Test that get_all_notifications function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'get_all_notifications')
        assert callable(getattr(istrominventory, 'get_all_notifications', None))
    
    @patch('istrominventory.st.session_state', {'user_type': 'project_site', 'project_site': 'Test Site'})
    def test_get_project_site_notifications_function_exists(self):
        """Test that get_project_site_notifications function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'get_project_site_notifications')
        assert callable(getattr(istrominventory, 'get_project_site_notifications', None))
    
    def test_delete_notification_function_exists(self):
        """Test that delete_notification function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'delete_notification')
        assert callable(getattr(istrominventory, 'delete_notification', None))

