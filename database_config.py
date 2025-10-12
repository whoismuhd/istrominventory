# database_config.py
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

def get_conn():
    """
    Get database connection - use PostgreSQL on Render, SQLite locally
    """
    # Use PostgreSQL on Render if DATABASE_URL is set
    database_url = os.getenv('DATABASE_URL', '')
    if database_url and 'postgresql://' in database_url:
        try:
            import psycopg2
            # Parse the DATABASE_URL
            import urllib.parse as urlparse
            url = urlparse.urlparse(database_url)
            
            conn = psycopg2.connect(
                database=url.path[1:],
                user=url.username,
                password=url.password,
                host=url.hostname,
                port=url.port
            )
            return conn
        except Exception as e:
            logger.error("PostgreSQL connection failed: %s", e)
            # Fall back to SQLite
            pass
    
    # Fallback to SQLite for local development
    try:
        # Clean up any WAL files that might be causing issues
        wal_file = 'istrominventory.db-wal'
        shm_file = 'istrominventory.db-shm'
        
        for file_path in [wal_file, shm_file]:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        
        conn = sqlite3.connect('istrominventory.db', timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except Exception as e:
        logger.error("SQLite connection failed: %s", e)
        return None

def create_tables():
    """
    Create all necessary tables for the application
    """
    try:
        with get_conn() as conn:
            if conn is None:
                return False
            
            cursor = conn.cursor()
            
            # Check if database already has data
            try:
                cursor.execute("SELECT COUNT(*) FROM users")
                user_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM items")
                item_count = cursor.fetchone()[0]
                
                # If database has data, don't recreate tables
                if user_count > 0 or item_count > 0:
                    logger.info("DATABASE ALREADY HAS DATA - SKIPPING TABLE CREATION")
                    return False
            except:
                # If tables don't exist, continue with creation
                logger.info("Tables don't exist - creating them...")
                pass
            
            # Create items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    code TEXT,
                    unit_cost REAL,
                    budget TEXT,
                    building_type TEXT,
                    unit TEXT,
                    category TEXT,
                    section TEXT,
                    grp TEXT,
                    project_site TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create requests table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMP,
                    section TEXT,
                    item_id INTEGER,
                    qty REAL,
                    requested_by TEXT,
                    note TEXT,
                    status TEXT DEFAULT 'Pending',
                    approved_by TEXT,
                    current_price REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    user_type TEXT NOT NULL,
                    project_site TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)
            
            # Create project_sites table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_sites (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)
            
            # Create notifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    notification_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    user_id INTEGER,
                    request_id INTEGER,
                    is_read INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create actuals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS actuals (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER,
                    actual_qty REAL,
                    actual_cost REAL,
                    actual_date DATE,
                    recorded_by TEXT,
                    notes TEXT,
                    project_site TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create access_codes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS access_codes (
                    id SERIAL PRIMARY KEY,
                    admin_code TEXT NOT NULL,
                    user_code TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT DEFAULT 'System'
                )
            """)
            
            # Create access_logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS access_logs (
                    id SERIAL PRIMARY KEY,
                    username TEXT,
                    action TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)
            
            conn.commit()
            logger.info("Database tables created successfully!")
            return True
    except Exception as e:
        logger.error("Error creating tables: %s", e)
        return False