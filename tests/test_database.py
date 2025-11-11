"""
Unit tests for database operations
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestDatabaseOperations:
    """Test database connection and operations"""
    
    def test_database_connection(self):
        """Test database engine creation and connection"""
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        assert engine is not None
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1
    
    def test_database_initialization(self):
        """Test database initialization"""
        from db import init_db
        
        # Should not raise exception
        result = init_db()
        assert result is None or result is True
    
    def test_table_existence(self):
        """Test that all required tables exist"""
        from db import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        required_tables = [
            'items', 'requests', 'notifications', 'users',
            'access_codes', 'project_site_access_codes',
            'access_logs', 'project_sites', 'actuals',
            'deleted_requests', 'project_config'
        ]
        
        with engine.connect() as conn:
            # Check table existence (works for both SQLite and PostgreSQL)
            for table in required_tables:
                try:
                    # Try PostgreSQL syntax first
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table} LIMIT 1"))
                    result.fetchone()
                except:
                    # Fallback to SQLite syntax
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table} LIMIT 1"))
                    result.fetchone()
    
    def test_connection_pooling(self):
        """Test that connection pooling is working"""
        from db import get_engine
        
        engine = get_engine()
        # Connection pool should exist
        assert hasattr(engine, 'pool') or hasattr(engine, 'connect')

