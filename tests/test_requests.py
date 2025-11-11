"""
Unit tests for request management functions
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestRequestFunctions:
    """Test request-related functions"""
    
    @patch('istrominventory.st.session_state', {'user_type': 'admin', 'current_project_site': None})
    def test_df_requests_function_exists(self):
        """Test that df_requests function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'df_requests')
        assert callable(getattr(istrominventory, 'df_requests', None))
    
    @patch('istrominventory.st.session_state', {'user_type': 'admin', 'current_project_site': None})
    def test_df_deleted_requests_function_exists(self):
        """Test that df_deleted_requests function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'df_deleted_requests')
        assert callable(getattr(istrominventory, 'df_deleted_requests', None))
    
    def test_set_request_status_function_exists(self):
        """Test that set_request_status function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'set_request_status')
        assert callable(getattr(istrominventory, 'set_request_status', None))
    
    def test_delete_request_function_exists(self):
        """Test that delete_request function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'delete_request')
        assert callable(getattr(istrominventory, 'delete_request', None))
    
    def test_add_request_function_exists(self):
        """Test that add_request function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'add_request')
        assert callable(getattr(istrominventory, 'add_request', None))

