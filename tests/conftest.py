"""
Pytest configuration and fixtures for Istrom Inventory tests
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def mock_streamlit():
    """Mock Streamlit for testing without Streamlit runtime"""
    with patch('streamlit.session_state', new_callable=dict) as mock_state:
        mock_state.update({
            'logged_in': False,
            'user_type': 'admin',
            'project_site': 'Test Site',
            'current_project_site': 'Test Site',
            'user_id': None,
            'username': None,
            'full_name': None
        })
        yield mock_state

@pytest.fixture
def mock_db_engine():
    """Mock database engine for testing"""
    from unittest.mock import MagicMock
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=None)
    engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=None)
    return engine

@pytest.fixture
def sample_item_data():
    """Sample item data for testing"""
    return {
        'id': 1,
        'code': 'MAT001',
        'name': 'Test Material',
        'category': 'materials',
        'unit': 'kg',
        'qty': 100.0,
        'unit_cost': 50.0,
        'budget': 'Budget 1',
        'section': 'materials',
        'grp': 'MATERIAL(IRONS)',
        'building_type': 'Flats',
        'project_site': 'Test Site'
    }

@pytest.fixture
def sample_request_data():
    """Sample request data for testing"""
    return {
        'id': 1,
        'ts': '2025-01-01T10:00:00',
        'section': 'materials',
        'item_id': 1,
        'qty': 10.0,
        'requested_by': 'Test User',
        'note': 'Test request',
        'building_subtype': 'B1',
        'status': 'Pending',
        'approved_by': None
    }

