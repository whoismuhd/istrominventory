"""
Unit tests for authentication and user management
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestAuthentication:
    """Test authentication functions"""
    
    @patch('modules.auth.st.session_state', new_callable=dict)
    def test_get_all_access_codes(self, mock_state):
        """Test access codes retrieval"""
        from modules.auth import get_all_access_codes
        
        codes = get_all_access_codes()
        assert isinstance(codes, dict)
        assert 'admin_code' in codes or 'site_codes' in codes
    
    @patch('modules.auth.st.session_state', new_callable=dict)
    def test_authenticate_user_invalid_code(self, mock_state):
        """Test authentication with invalid access code"""
        from modules.auth import authenticate_user
        
        result = authenticate_user("INVALID_CODE_12345")
        # Should return None for invalid codes
        assert result is None
    
    @patch('modules.auth.st.session_state', new_callable=dict)
    def test_is_admin_function_exists(self, mock_state):
        """Test that is_admin function exists and is callable"""
        from modules.auth import is_admin
        
        assert callable(is_admin)
        # Test with different session states
        mock_state['user_type'] = 'admin'
        result = is_admin()
        assert isinstance(result, bool)
    
    def test_log_access_function(self):
        """Test log_access function"""
        from modules.auth import log_access
        
        # Should not raise exception
        try:
            log_access("TEST_CODE", success=True, user_name="Test User", role="admin")
            assert True
        except Exception as e:
            pytest.fail(f"log_access raised exception: {e}")

class TestUserManagement:
    """Test user management functions"""
    
    def test_get_all_users_function_exists(self):
        """Test that get_all_users function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'get_all_users')
        assert callable(getattr(istrominventory, 'get_all_users', None))
    
    def test_get_project_sites_function_exists(self):
        """Test that get_project_sites function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'get_project_sites')
        assert callable(getattr(istrominventory, 'get_project_sites', None))

