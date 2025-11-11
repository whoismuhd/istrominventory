"""
Unit tests for inventory management functions
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestInventoryFunctions:
    """Test inventory-related functions"""
    
    @patch('istrominventory.st.session_state', {'current_project_site': 'Test Site'})
    @patch('istrominventory.get_engine')
    def test_df_items_cached_function_exists(self, mock_engine):
        """Test that df_items_cached function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'df_items_cached')
        assert callable(getattr(istrominventory, 'df_items_cached', None))
    
    @patch('istrominventory.st.session_state', {'current_project_site': 'Test Site'})
    def test_get_summary_data_function_exists(self):
        """Test that get_summary_data function exists"""
        import istrominventory
        
        assert hasattr(istrominventory, 'get_summary_data')
        assert callable(getattr(istrominventory, 'get_summary_data', None))
    
    def test_property_types_constant(self):
        """Test PROPERTY_TYPES constant"""
        import istrominventory
        
        assert hasattr(istrominventory, 'PROPERTY_TYPES')
        assert isinstance(istrominventory.PROPERTY_TYPES, list)
        assert len(istrominventory.PROPERTY_TYPES) > 0
    
    def test_building_subtype_options_constant(self):
        """Test BUILDING_SUBTYPE_OPTIONS constant"""
        import istrominventory
        
        assert hasattr(istrominventory, 'BUILDING_SUBTYPE_OPTIONS')
        assert isinstance(istrominventory.BUILDING_SUBTYPE_OPTIONS, dict)
        # Check that Flats has B1-B13
        if 'Flats' in istrominventory.BUILDING_SUBTYPE_OPTIONS:
            flats_blocks = istrominventory.BUILDING_SUBTYPE_OPTIONS['Flats']
            assert len(flats_blocks) == 13  # B1-B13
            assert 'B1' in flats_blocks
            assert 'B13' in flats_blocks

