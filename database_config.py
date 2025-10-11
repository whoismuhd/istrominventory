"""
Database Configuration for Istrom Inventory System
Supports both SQLite (local development) and PostgreSQL (production hosting)
"""

import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from contextlib import contextmanager

# Database configuration
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'sqlite')  # 'sqlite' or 'postgresql'

# SQLite configuration (local development)
SQLITE_DB_PATH = os.getenv('SQLITE_DB_PATH', 'istrominventory.db')

# PostgreSQL configuration (production hosting)
# Auto-detect Render database URL
DATABASE_URL = os.getenv('DATABASE_URL')  # Render provides this automatically

if DATABASE_URL and 'postgres' in DATABASE_URL:
    # Parse DATABASE_URL for Render PostgreSQL
    import urllib.parse as urlparse
    url = urlparse.urlparse(DATABASE_URL)
    POSTGRES_CONFIG = {
        'host': url.hostname,
        'port': url.port,
        'database': url.path[1:],  # Remove leading slash
        'user': url.username,
        'password': url.password
    }
    DATABASE_TYPE = 'postgresql'
    print(f"🔗 Using Render PostgreSQL database: {url.hostname}")
    print(f"🔗 Database URL detected: {DATABASE_URL[:20]}...")
else:
    # Fallback configuration
    POSTGRES_CONFIG = {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432'),
        'database': os.getenv('POSTGRES_DB', 'istrominventory'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', '')
    }

def get_database_connection():
    """
    Get database connection based on environment configuration
    Returns: Database connection object
    """
    print(f"🔍 DATABASE_TYPE: {DATABASE_TYPE}")
    print(f"🔍 DATABASE_URL: {DATABASE_URL}")
    print(f"🔍 POSTGRES_CONFIG: {POSTGRES_CONFIG}")
    
    if DATABASE_TYPE == 'postgresql':
        try:
            print("🔗 Attempting PostgreSQL connection...")
            conn = psycopg2.connect(**POSTGRES_CONFIG)
            print("✅ PostgreSQL connection successful!")
            return conn
        except Exception as e:
            print(f"❌ PostgreSQL connection failed: {e}")
            print("⚠️ Falling back to SQLite...")
            return sqlite3.connect(SQLITE_DB_PATH)
    else:
        print("🔗 Using SQLite connection...")
        return sqlite3.connect(SQLITE_DB_PATH)

@contextmanager
def get_conn():
    """
    Context manager for database connections
    Usage: with get_conn() as conn: ...
    """
    conn = None
    try:
        conn = get_database_connection()
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

def execute_query(query, params=None, fetch=False):
    """
    Execute a database query
    Args:
        query: SQL query string
        params: Query parameters
        fetch: Whether to fetch results
    Returns: Query results if fetch=True, otherwise None
    """
    with get_conn() as conn:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if fetch:
            if DATABASE_TYPE == 'postgresql':
                # For PostgreSQL, return as list of dictionaries
                columns = [desc[0] for desc in cursor.description]
                results = cursor.fetchall()
                return [dict(zip(columns, row)) for row in results]
            else:
                # For SQLite, return as list of tuples
                return cursor.fetchall()
        else:
            conn.commit()
            return cursor.lastrowid if hasattr(cursor, 'lastrowid') else None

def create_tables():
    """
    Create all necessary tables for the application
    """
    with get_conn() as conn:
        cursor = conn.cursor()
        
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                project_site TEXT NOT NULL,
                user_type TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (request_id) REFERENCES requests(id)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id)
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
        print("✅ Database tables created successfully!")

def migrate_from_sqlite():
    """
    Migrate data from SQLite to PostgreSQL
    """
    if DATABASE_TYPE != 'postgresql':
        print("Migration only needed for PostgreSQL")
        return
    
    # Check if SQLite database exists
    if not os.path.exists(SQLITE_DB_PATH):
        print("No SQLite database found to migrate")
        return
    
    print("🔄 Migrating data from SQLite to PostgreSQL...")
    
    # Connect to SQLite database
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_cursor = sqlite_conn.cursor()
    
    # Get all tables
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [table[0] for table in sqlite_cursor.fetchall()]
    
    # Migrate each table
    for table in tables:
        if table == 'sqlite_sequence':
            continue
            
        print(f"Migrating table: {table}")
        
        # Get data from SQLite
        sqlite_cursor.execute(f"SELECT * FROM {table}")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            continue
        
        # Get column names
        sqlite_cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in sqlite_cursor.fetchall()]
        
        # Insert data into PostgreSQL
        with get_conn() as pg_conn:
            pg_cursor = pg_conn.cursor()
            
            # Create insert query
            placeholders = ', '.join(['%s'] * len(columns))
            insert_query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            
            try:
                pg_cursor.executemany(insert_query, rows)
                pg_conn.commit()
                print(f"✅ Migrated {len(rows)} rows to {table}")
            except Exception as e:
                print(f"❌ Error migrating {table}: {e}")
                pg_conn.rollback()
    
    sqlite_conn.close()
    print("✅ Migration completed!")

if __name__ == "__main__":
    # Create tables and migrate data
    create_tables()
    migrate_from_sqlite()
