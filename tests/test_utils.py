"""
Unit tests for utility functions and helpers
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestUtilityFunctions:
    """Test utility and helper functions"""
    
    def test_get_nigerian_time_function(self):
        """Test get_nigerian_time function"""
        import istrominventory
        
        assert hasattr(istrominventory, 'get_nigerian_time')
        assert callable(istrominventory.get_nigerian_time)
        
        # Should return datetime object
        from datetime import datetime
        result = istrominventory.get_nigerian_time()
        assert isinstance(result, datetime)
    
    def test_get_nigerian_time_iso_function(self):
        """Test get_nigerian_time_iso function"""
        import istrominventory
        
        assert hasattr(istrominventory, 'get_nigerian_time_iso')
        assert callable(istrominventory.get_nigerian_time_iso)
        
        # Should return ISO format string
        result = istrominventory.get_nigerian_time_iso()
        assert isinstance(result, str)
        assert 'T' in result or len(result) > 10
    
    def test_clear_cache_function(self):
        """Test clear_cache function"""
        import istrominventory
        
        assert hasattr(istrominventory, 'clear_cache')
        assert callable(istrominventory.clear_cache)
        
        # Should not raise exception
        try:
            istrominventory.clear_cache()
            assert True
        except Exception as e:
            pytest.fail(f"clear_cache raised exception: {e}")
    
    def test_preserve_current_tab_function(self):
        """Test preserve_current_tab function"""
        import istrominventory
        
        assert hasattr(istrominventory, 'preserve_current_tab')
        assert callable(istrominventory.preserve_current_tab)
    
    def test_to_number_function(self):
        """Test to_number utility function"""
        import istrominventory
        
        assert hasattr(istrominventory, 'to_number')
        assert callable(istrominventory.to_number)
        
        # Test with valid numbers
        assert istrominventory.to_number("123") == 123
        assert istrominventory.to_number("123.45") == 123.45
        assert istrominventory.to_number("abc") is None
        assert istrominventory.to_number(None) is None

class TestConstants:
    """Test application constants"""
    
    def test_property_types_defined(self):
        """Test PROPERTY_TYPES constant"""
        import istrominventory
        
        assert hasattr(istrominventory, 'PROPERTY_TYPES')
        assert isinstance(istrominventory.PROPERTY_TYPES, list)
        assert len(istrominventory.PROPERTY_TYPES) >= 4  # Flats, Terraces, Semi-detached, Fully-detached
    
    def test_building_subtype_options_defined(self):
        """Test BUILDING_SUBTYPE_OPTIONS constant"""
        import istrominventory
        
        assert hasattr(istrominventory, 'BUILDING_SUBTYPE_OPTIONS')
        assert isinstance(istrominventory.BUILDING_SUBTYPE_OPTIONS, dict)
        
        # Check Flats has correct blocks
        if 'Flats' in istrominventory.BUILDING_SUBTYPE_OPTIONS:
            flats = istrominventory.BUILDING_SUBTYPE_OPTIONS['Flats']
            assert len(flats) == 13  # B1-B13
            assert all(f'B{i}' in flats for i in range(1, 14))
    
    def test_building_subtype_labels_defined(self):
        """Test BUILDING_SUBTYPE_LABELS constant"""
        import istrominventory
        
        assert hasattr(istrominventory, 'BUILDING_SUBTYPE_LABELS')
        assert isinstance(istrominventory.BUILDING_SUBTYPE_LABELS, dict)

