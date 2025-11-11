"""
Integration tests for Istrom Inventory System
Tests the integration between different components
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestIntegration:
    """Integration tests for the application"""
    
    def test_database_auth_integration(self):
        """Test integration between database and authentication"""
        from db import get_engine
        from sqlalchemy import text
        from modules.auth import get_all_access_codes
        
        # Database should be accessible
        engine = get_engine()
        assert engine is not None
        
        # Access codes should be retrievable
        codes = get_all_access_codes()
        assert isinstance(codes, dict)
    
    @patch('istrominventory.st.session_state', {
        'user_type': 'admin',
        'current_project_site': 'Test Site',
        'project_site': 'Test Site'
    })
    def test_inventory_request_integration(self):
        """Test integration between inventory and request systems"""
        import istrominventory
        
        # Both functions should exist and work together
        assert hasattr(istrominventory, 'df_items_cached')
        assert hasattr(istrominventory, 'df_requests')
        
        # Functions should be callable
        assert callable(istrominventory.df_items_cached)
        assert callable(istrominventory.df_requests)
    
    def test_notification_request_integration(self):
        """Test integration between notification and request systems"""
        import istrominventory
        
        # Notification functions should exist
        assert hasattr(istrominventory, 'get_admin_notifications')
        assert hasattr(istrominventory, 'get_project_site_notifications')
        
        # Request functions should exist
        assert hasattr(istrominventory, 'set_request_status')
        assert hasattr(istrominventory, 'df_requests')
    
    def test_budget_actuals_integration(self):
        """Test integration between budget summary and actuals"""
        import istrominventory
        
        # Both functions should exist
        assert hasattr(istrominventory, 'get_summary_data')
        assert hasattr(istrominventory, 'get_actuals')
        
        # Functions should be callable
        assert callable(istrominventory.get_summary_data)
        assert callable(istrominventory.get_actuals)
    
    def test_user_project_site_integration(self):
        """Test integration between user management and project sites"""
        import istrominventory
        
        # Functions should exist
        assert hasattr(istrominventory, 'get_all_users')
        assert hasattr(istrominventory, 'get_project_sites')
        
        # Functions should be callable
        assert callable(istrominventory.get_all_users)
        assert callable(istrominventory.get_project_sites)

class TestDataFlow:
    """Test data flow between components"""
    
    def test_request_lifecycle(self):
        """Test complete request lifecycle"""
        import istrominventory
        
        # All request lifecycle functions should exist
        functions = [
            'add_request',
            'set_request_status',
            'df_requests',
            'delete_request',
            'df_deleted_requests'
        ]
        
        for func_name in functions:
            assert hasattr(istrominventory, func_name), f"Missing function: {func_name}"
            assert callable(getattr(istrominventory, func_name)), f"Function not callable: {func_name}"
    
    def test_notification_flow(self):
        """Test notification flow"""
        import istrominventory
        
        # Notification functions should exist
        functions = [
            'get_admin_notifications',
            'get_project_site_notifications',
            'get_all_notifications',
            'delete_notification'
        ]
        
        for func_name in functions:
            assert hasattr(istrominventory, func_name), f"Missing function: {func_name}"
            assert callable(getattr(istrominventory, func_name)), f"Function not callable: {func_name}"

