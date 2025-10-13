"""
PostgreSQL Database Configuration for Istrom Inventory Management System

This module provides a complete PostgreSQL implementation that replaces all SQLite dependencies.
It uses SQLAlchemy for database abstraction and supports both local development and production deployment.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

logger = logging.getLogger(__name__)

# Global engine instance
_engine: Optional[Engine] = None

def get_engine() -> Engine:
    """
    Get SQLAlchemy engine for PostgreSQL connection.
    Uses DATABASE_URL environment variable for production, falls back to local SQLite for development.
    """
    global _engine
    
    if _engine is None:
        database_url = os.getenv('DATABASE_URL')
        
        if database_url and 'postgresql://' in database_url:
            # Production PostgreSQL connection
            _engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=False  # Set to True for SQL debugging
            )
            logger.info("Connected to PostgreSQL database")
        else:
            # Fallback to SQLite for local development
            sqlite_url = "sqlite:///istrominventory.db"
            _engine = create_engine(
                sqlite_url,
                pool_pre_ping=True,
                echo=False
            )
            logger.info("Connected to SQLite database (local development)")
    
    return _engine

@contextmanager
def get_conn():
    """
    Context manager for database connections.
    Ensures proper connection cleanup and error handling.
    """
    engine = get_engine()
    conn = None
    try:
        conn = engine.connect()
        yield conn
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def create_tables() -> bool:
    """
    Create all required tables for the inventory management system.
    This function is idempotent and can be run multiple times safely.
    """
    try:
        engine = get_engine()
        
        # Define table schemas
        table_definitions = [
            # Users table
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                user_type TEXT CHECK(user_type IN ('admin', 'user')) NOT NULL DEFAULT 'user',
                project_site TEXT DEFAULT 'Lifecamp Kafe',
                admin_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
            """,
            
            # Project sites table
            """
            CREATE TABLE IF NOT EXISTS project_sites (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
            """,
            
            # Items table
            """
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                category TEXT,
                unit TEXT,
                qty NUMERIC(14,3) DEFAULT 0,
                unit_cost NUMERIC(14,2) DEFAULT 0,
                budget TEXT,
                section TEXT,
                grp TEXT,
                building_type TEXT,
                project_site TEXT DEFAULT 'Lifecamp Kafe',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Requests table
            """
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                item_id INTEGER,
                item_name TEXT,
                requested_by TEXT,
                requested_qty NUMERIC(14,3),
                current_price NUMERIC(14,2),
                status TEXT DEFAULT 'pending',
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_by TEXT,
                approved_at TIMESTAMP,
                rejected_by TEXT,
                rejected_at TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
            """,
            
            # Request lines table (for detailed request tracking)
            """
            CREATE TABLE IF NOT EXISTS request_lines (
                id SERIAL PRIMARY KEY,
                request_id INTEGER NOT NULL,
                item_id INTEGER,
                qty_requested NUMERIC(14,3) NOT NULL DEFAULT 0,
                unit_cost_snapshot NUMERIC(14,2) NOT NULL DEFAULT 0,
                qty_approved NUMERIC(14,3),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
            )
            """,
            
            # Notifications table (improved schema)
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                sender_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                receiver_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                message TEXT NOT NULL,
                type TEXT CHECK(type IN ('info','success','warning','error','new_request','request_approved','request_rejected')) DEFAULT 'info',
                is_read BOOLEAN DEFAULT FALSE,
                event_key TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Actuals table
            """
            CREATE TABLE IF NOT EXISTS actuals (
                id SERIAL PRIMARY KEY,
                item_id INTEGER,
                actual_qty NUMERIC(14,3),
                actual_cost NUMERIC(14,2),
                actual_date DATE,
                recorded_by TEXT,
                notes TEXT,
                project_site TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
            """,
            
            # Access codes table
            """
            CREATE TABLE IF NOT EXISTS access_codes (
                id SERIAL PRIMARY KEY,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT DEFAULT 'System'
            )
            """,
            
            # Access logs table
            """
            CREATE TABLE IF NOT EXISTS access_logs (
                id SERIAL PRIMARY KEY,
                username TEXT,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                user_agent TEXT
            )
            """,
            
            # Project site access codes table
            """
            CREATE TABLE IF NOT EXISTS project_site_access_codes (
                id SERIAL PRIMARY KEY,
                project_site TEXT NOT NULL,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_site)
            )
            """
        ]
        
        # Create tables
        with engine.begin() as conn:
            for table_sql in table_definitions:
                conn.execute(text(table_sql))
            
            # Create indexes for performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_items_budget ON items(budget)",
                "CREATE INDEX IF NOT EXISTS idx_items_section ON items(section)",
                "CREATE INDEX IF NOT EXISTS idx_items_building_type ON items(building_type)",
                "CREATE INDEX IF NOT EXISTS idx_items_category ON items(category)",
                "CREATE INDEX IF NOT EXISTS idx_items_name ON items(name)",
                "CREATE INDEX IF NOT EXISTS idx_items_code ON items(code)",
                "CREATE INDEX IF NOT EXISTS idx_items_project_site ON items(project_site)",
                "CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)",
                "CREATE INDEX IF NOT EXISTS idx_requests_item_id ON requests(item_id)",
                "CREATE INDEX IF NOT EXISTS idx_requests_requested_by ON requests(requested_by)",
                "CREATE INDEX IF NOT EXISTS idx_notifications_receiver_read_created ON notifications(receiver_id, is_read, created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_notifications_sender_created ON notifications(sender_id, created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_notifications_event_key ON notifications(event_key) WHERE event_key IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_access_logs_timestamp ON access_logs(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_access_logs_username ON access_logs(username)"
            ]
            
            for index_sql in indexes:
                conn.execute(text(index_sql))
        
        logger.info("Database tables created successfully")
        return True
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to create tables: {e}")
        return False

def execute_query(query: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """
    Execute a SQL query and return results as a pandas DataFrame.
    Uses SQLAlchemy's text() for safe parameter binding.
    """
    try:
        with get_conn() as conn:
            return pd.read_sql_query(text(query), conn, params=params or {})
    except SQLAlchemyError as e:
        logger.error(f"Query execution failed: {e}")
        return pd.DataFrame()

def execute_update(query: str, params: Optional[Dict[str, Any]] = None) -> int:
    """
    Execute an UPDATE, INSERT, or DELETE query and return the number of affected rows.
    """
    try:
        with get_conn() as conn:
            result = conn.execute(text(query), params or {})
            conn.commit()
            return result.rowcount
    except SQLAlchemyError as e:
        logger.error(f"Update execution failed: {e}")
        return 0

def execute_insert(query: str, params: Optional[Dict[str, Any]] = None) -> int:
    """
    Execute an INSERT query and return the ID of the inserted row.
    """
    try:
        with get_conn() as conn:
            result = conn.execute(text(query), params or {})
            conn.commit()
            return result.inserted_primary_key[0] if result.inserted_primary_key else 0
    except SQLAlchemyError as e:
        logger.error(f"Insert execution failed: {e}")
        return 0

def get_table_info(table_name: str) -> List[Dict[str, Any]]:
    """
    Get information about a table's columns and structure.
    """
    try:
        engine = get_engine()
        if 'postgresql' in str(engine.url):
            query = """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = :table_name
                ORDER BY ordinal_position
            """
        else:
            query = "PRAGMA table_info(:table_name)"
        
        return execute_query(query, {"table_name": table_name}).to_dict('records')
    except SQLAlchemyError as e:
        logger.error(f"Failed to get table info: {e}")
        return []

def check_database_health() -> Dict[str, Any]:
    """
    Check database connection health and return status information.
    """
    try:
        engine = get_engine()
        
        with get_conn() as conn:
            # Test basic connectivity
            result = conn.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            
            # Get database info
            if 'postgresql' in str(engine.url):
                db_info = conn.execute(text("SELECT current_database() as db_name, version() as version")).fetchone()
                return {
                    "status": "healthy",
                    "database_type": "PostgreSQL",
                    "database_name": db_info[0],
                    "version": db_info[1],
                    "test_query": test_value
                }
            else:
                return {
                    "status": "healthy",
                    "database_type": "SQLite",
                    "database_name": "istrominventory.db",
                    "test_query": test_value
                }
                
    except SQLAlchemyError as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "database_type": "unknown"
        }

def initialize_database() -> bool:
    """
    Initialize the database with tables and default data.
    This function should be called once during application startup.
    """
    try:
        # Create tables
        if not create_tables():
            return False
        
        # Insert default data if tables are empty
        with get_conn() as conn:
            # Check if access_codes table is empty
            result = conn.execute(text("SELECT COUNT(*) FROM access_codes"))
            if result.scalar() == 0:
                # Insert default access codes
                conn.execute(text("""
                    INSERT INTO access_codes (admin_code, user_code, updated_by)
                    VALUES ('Istrom2026', 'USER2026', 'System')
                """))
                conn.commit()
                logger.info("Default access codes inserted")
            
            # Check if project_sites table is empty
            result = conn.execute(text("SELECT COUNT(*) FROM project_sites"))
            if result.scalar() == 0:
                # Insert default project site
                conn.execute(text("""
                    INSERT INTO project_sites (name, description)
                    VALUES ('Lifecamp Kafe', 'Default project site')
                """))
                conn.commit()
                logger.info("Default project site inserted")
        
        logger.info("Database initialization completed successfully")
        return True
        
    except SQLAlchemyError as e:
        logger.error(f"Database initialization failed: {e}")
        return False

def get_connection_string() -> str:
    """
    Get the current database connection string for debugging.
    """
    engine = get_engine()
    return str(engine.url)

# Compatibility functions for existing code
def get_sql_placeholder() -> str:
    """
    Get the appropriate SQL placeholder for the current database.
    Returns '?' for SQLite and '%s' for PostgreSQL.
    """
    engine = get_engine()
    if 'postgresql' in str(engine.url):
        return '%s'
    else:
        return '?'

def execute_sql_with_placeholder(query: str, params: tuple) -> pd.DataFrame:
    """
    Execute SQL with automatic placeholder conversion.
    Converts '?' placeholders to named parameters for PostgreSQL.
    """
    engine = get_engine()
    
    if 'postgresql' in str(engine.url):
        # Convert ? placeholders to named parameters
        param_names = [f"param_{i}" for i in range(len(params))]
        converted_query = query
        for i, param_name in enumerate(param_names):
            converted_query = converted_query.replace('?', f":{param_name}", 1)
        
        param_dict = {name: value for name, value in zip(param_names, params)}
        return execute_query(converted_query, param_dict)
    else:
        # Use original query for SQLite
        return execute_query(query, dict(zip([f"param_{i}" for i in range(len(params))], params)))
