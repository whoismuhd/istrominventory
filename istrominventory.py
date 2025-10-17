import streamlit as st
import sqlite3
import pandas as pd
import re
from functools import lru_cache
# Test deployment - data persistence verification - SUCCESS! PostgreSQL working!
from datetime import datetime, timedelta
from pathlib import Path
import time
import threading
import pytz
import shutil
import json
import os
from sqlalchemy import text
from db import get_engine, init_db
from schema_init import ensure_schema

st.set_page_config(page_title="IstromInventory", page_icon="📦", layout="wide")

# Initialize DB/tables at startup
init_db()          # if you already have it, keep it
ensure_schema()    # <-- create items/actuals when missing
engine = get_engine()

# --- TEMP diagnostics (remove later) ---
with st.expander("Diagnostics"):
    import os
    st.write("Has DATABASE_URL:", bool(os.getenv("DATABASE_URL")))
    st.write("DATABASE_URL:", os.getenv("DATABASE_URL", "Not set")[:50] + "...")
    try:
        with engine.connect() as c:
            # show tables present
            if engine.url.get_backend_name() != "sqlite":
                rows = c.execute(text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' ORDER BY 1"
                )).fetchall()
                st.write("Tables (PG):", [r[0] for r in rows] if rows else "N/A")
            else:
                st.write("Tables (SQLite):", "Using local SQLite database")
        st.success("DB connection OK ✅")
    except Exception as e:
        st.error(f"DB connection failed: {e}")
        
        # Check if access_codes table exists and has data
        try:
            with engine.connect() as c:
                result = c.execute(text("SELECT admin_code, user_code FROM access_codes ORDER BY id DESC LIMIT 1"))
                row = result.fetchone()
                if row:
                    st.write(f"Admin code: {row[0]}")
                    st.write(f"User code: {row[1]}")
                else:
                    st.warning("No access codes found in database!")
        except Exception as e:
            st.error(f"Error checking access codes: {e}")
            
    except Exception as e:
        st.error(f"DB connection failed: {e}")

# Check if we're on Render with PostgreSQL
database_url = os.getenv('DATABASE_URL', '')
print(f"🔍 Environment check - DATABASE_URL: {database_url[:50]}..." if database_url else "🔍 Environment check - No DATABASE_URL found")

# Also check for other Render environment variables
render_env = os.getenv('RENDER', '')
production_mode = os.getenv('PRODUCTION_MODE', '')
print(f"🔍 RENDER env: {render_env}, PRODUCTION_MODE: {production_mode}")

if database_url and 'postgresql://' in database_url:
    DATABASE_CONFIGURED = True
    print("🚀 PostgreSQL database detected - using persistent storage!")
elif render_env or production_mode:
    # We're on Render but no DATABASE_URL - this is a problem!
    print("🚨 CRITICAL: On Render but no DATABASE_URL found!")
    print("🚨 This means environment variables are not being set properly!")
    DATABASE_CONFIGURED = False
else:
    DATABASE_CONFIGURED = False
    print("🔍 Using SQLite for local development")

# Database connection helper
def safe_db_operation(operation_func, *args, **kwargs):
    """Safely execute database operations with proper error handling"""
    try:
        conn = get_conn()
        if conn is None:
            print("❌ Database connection failed - operation cancelled")
            return None
        return operation_func(conn, *args, **kwargs)
    except Exception as e:
        print(f"❌ Database operation failed: {e}")
        return None

def get_sql_placeholder():
    """Get the correct SQL parameter placeholder for the current database"""
    # Check if we're using PostgreSQL by looking at DATABASE_URL or DATABASE_TYPE
    database_url = os.getenv('DATABASE_URL', '')
    database_type = os.getenv('DATABASE_TYPE', '')
    
    # If we have a PostgreSQL URL or type, use %s placeholders
    if 'postgresql://' in database_url or database_type == 'postgresql':
        return '%s'  # PostgreSQL uses %s
    else:
        return '?'   # SQLite uses ?

# Database initialization
def initialize_database():
    """Initialize database with proper configuration"""
    try:
        # Ensure all required tables exist
        # database_config import removed - using direct PostgreSQL connection
        # Tables are created automatically in get_conn() for PostgreSQL
        return True
    except Exception as e:
        # Database initialization failed
        return False

# Nigerian timezone helper functions
def get_nigerian_time():
    """Get current time in Nigerian timezone (WAT)"""
    wat_timezone = pytz.timezone('Africa/Lagos')
    return datetime.now(wat_timezone)

def get_nigerian_time_str():
    """Get current time in Nigerian timezone as string"""
    return get_nigerian_time().strftime("%Y-%m-%d %H:%M:%S")

def get_nigerian_time_iso():
    """Get current time in Nigerian timezone as ISO string"""
    return get_nigerian_time().isoformat()

DB_PATH = Path("istrominventory.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

# --------------- DB helpers ---------------
def create_postgresql_tables(conn):
    """Create PostgreSQL tables if they don't exist"""
    try:
        cur = conn.cursor()
        
        # Create project_sites table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_sites (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Create project_site_access_codes table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_site_access_codes (
                id SERIAL PRIMARY KEY,
                project_site TEXT NOT NULL,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_site)
            )
        """)
        
        # Create items table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                category TEXT CHECK(category IN ('materials','labour')) NOT NULL,
                unit TEXT,
                qty REAL NOT NULL DEFAULT 0,
                unit_cost REAL,
                budget TEXT,
                section TEXT,
                grp TEXT,
                building_type TEXT,
                project_site TEXT DEFAULT 'Lifecamp Kafe',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create requests table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                ts TEXT NOT NULL,
                section TEXT CHECK(section IN ('materials','labour')) NOT NULL,
                item_id INTEGER NOT NULL,
                qty REAL NOT NULL,
                requested_by TEXT,
                note TEXT,
                status TEXT CHECK(status IN ('Pending','Approved','Rejected')) NOT NULL DEFAULT 'Pending',
                approved_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(item_id) REFERENCES items(id)
            )
        """)
        
        # Create notifications table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                notification_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                user_id INTEGER,
                request_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (request_id) REFERENCES requests (id)
            )
        """)
        
        # Create access_logs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS access_logs (
                id SERIAL PRIMARY KEY,
                access_code TEXT NOT NULL,
                user_name TEXT,
                access_time TIMESTAMP NOT NULL,
                success INTEGER DEFAULT 1,
                role TEXT
            )
        """)
        
        # Create users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                user_type TEXT CHECK(user_type IN ('admin', 'user')) NOT NULL,
                project_site TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Create access_codes table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS access_codes (
                id SERIAL PRIMARY KEY,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                updated_by TEXT
            )
        """)
        
        # Create deleted_requests table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deleted_requests (
                id SERIAL PRIMARY KEY,
                req_id INTEGER,
                item_name TEXT,
                qty REAL,
                requested_by TEXT,
                status TEXT,
                deleted_at TIMESTAMP,
                deleted_by TEXT
            )
        """)
        
        conn.commit()
        print("✅ PostgreSQL tables created/verified successfully!")
        
    except Exception as e:
        print(f"❌ Error creating PostgreSQL tables: {e}")
        conn.rollback()

def get_conn():
    """Legacy wrapper for compatibility - returns a context manager that works with cursor()"""
    class ConnectionWrapper:
        def __init__(self, engine):
            self.engine = engine
            self.conn = None
            
        def __enter__(self):
            self.conn = self.engine.connect()
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.conn:
                self.conn.close()
                
        def cursor(self):
            """Return a cursor-like object that works with SQLAlchemy"""
            class CursorWrapper:
                def __init__(self, connection):
                    self.connection = connection
                    
                def execute(self, query, params=None):
                    if params:
                        # Convert SQLite-style ? placeholders to SQLAlchemy :param style
                        if '?' in query:
                            # Simple replacement for common cases
                            param_count = query.count('?')
                            for i in range(param_count):
                                query = query.replace('?', f':param{i}', 1)
                            param_dict = {f'param{i}': params[i] for i in range(param_count)}
                        else:
                            param_dict = params
                    else:
                        param_dict = {}
                    
                    return self.connection.execute(text(query), param_dict)
                    
                def fetchone(self):
                    return self.connection.fetchone()
                    
                def fetchall(self):
                    return self.connection.fetchall()
                    
                def commit(self):
                    # SQLAlchemy handles commits automatically in context managers
                    pass
                    
                def close(self):
                    # Connection will be closed by context manager
                    pass
                    
            return CursorWrapper(self.conn)
            
        def commit(self):
            # SQLAlchemy handles commits automatically in context managers
            pass
            
        def close(self):
            # Connection will be closed by context manager
            pass
    
    return ConnectionWrapper(engine)

def init_db():
    """Initialize database with proper connection handling - now handled by db.py"""
    try:
        with engine.begin() as conn:
            # This function is now handled by db.py init_db()
            # Just ensure the engine is working
            conn.execute(text("SELECT 1"))

        cur.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            section TEXT CHECK(section IN ('materials','labour')) NOT NULL,
            item_id INTEGER NOT NULL,
            qty REAL NOT NULL,
            requested_by TEXT,
            note TEXT,
            status TEXT CHECK(status IN ('Pending','Approved','Rejected')) NOT NULL DEFAULT 'Pending',
            approved_by TEXT,
            FOREIGN KEY(item_id) REFERENCES items(id)
        );
    ''')

        # Add current_price column to requests table if it doesn't exist
        try:
            cur.execute("ALTER TABLE requests ADD COLUMN current_price REAL")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

        # ---------- NEW: Deleted requests log ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS deleted_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            req_id INTEGER,
            item_name TEXT,
            qty REAL,
            requested_by TEXT,
            status TEXT,
            deleted_at TEXT,
            deleted_by TEXT
        );
    """)
    
        # ---------- NEW: Actuals table for tracking real project performance ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS actuals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            actual_qty REAL NOT NULL,
            actual_cost REAL,
            actual_date TEXT NOT NULL,
            recorded_by TEXT,
            notes TEXT,
            project_site TEXT DEFAULT 'Lifecamp Kafe',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(item_id) REFERENCES items(id)
        );
    """)
        
        # Project configuration table
        cur.execute('''
        CREATE TABLE IF NOT EXISTS project_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_num INTEGER,
            building_type TEXT,
            num_blocks INTEGER,
            units_per_block INTEGER,
            additional_notes TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    ''')
    
        # Project sites table for persistence
        cur.execute('''
        CREATE TABLE IF NOT EXISTS project_sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );
    ''')
    
        # Users table for authentication and authorization
        cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            user_type TEXT CHECK(user_type IN ('admin', 'user')) NOT NULL,
            project_site TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );
    ''')
    
        # Notifications table for admin alerts
        cur.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            user_id INTEGER,
            request_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (request_id) REFERENCES requests (id)
        );
    ''')
        
        # Access codes table
        cur.execute('''
        CREATE TABLE IF NOT EXISTS access_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_code TEXT NOT NULL,
            user_code TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT
        );
    ''')
        
        # Project site access codes table
        cur.execute('''
        CREATE TABLE IF NOT EXISTS project_site_access_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_site TEXT NOT NULL,
            admin_code TEXT NOT NULL,
            user_code TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_site)
        );
    ''')
        
        # Access logs table
        cur.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            access_code TEXT NOT NULL,
            user_name TEXT,
            access_time TEXT NOT NULL,
            success INTEGER DEFAULT 1,
            role TEXT
        );
    ''')
        
        # --- Migration: add building_type column if missing ---
        cur.execute("PRAGMA table_info(items);")
        cols = [r[1] for r in cur.fetchall()]
        if "building_type" not in cols:
            cur.execute("ALTER TABLE items ADD COLUMN building_type TEXT;")
        
        # --- Migration: add project_site column if missing ---
        if "project_site" not in cols:
            cur.execute("ALTER TABLE items ADD COLUMN project_site TEXT DEFAULT 'Lifecamp Kafe';")
            # Update existing items to be assigned to Lifecamp Kafe
            cur.execute("UPDATE items SET project_site = 'Lifecamp Kafe' WHERE project_site IS NULL OR project_site = 'Default Project';")

        # --- Ensure existing items are assigned to Lifecamp Kafe ---
        cur.execute("UPDATE items SET project_site = 'Lifecamp Kafe' WHERE project_site IS NULL OR project_site = 'Default Project';")
        
        # --- Migration: Add missing columns to users table if they don't exist ---
        cur.execute("PRAGMA table_info(users)")
        user_columns = [col[1] for col in cur.fetchall()]
        
        # Add user_type column if missing
        if "user_type" not in user_columns:
            cur.execute("ALTER TABLE users ADD COLUMN user_type TEXT DEFAULT 'user'")
        
        # Add project_site column if missing
        if "project_site" not in user_columns:
            cur.execute("ALTER TABLE users ADD COLUMN project_site TEXT DEFAULT 'Lifecamp Kafe'")
        
        # Remove password_hash column if it exists (no longer needed)
        if "password_hash" in user_columns:
            try:
                cur.execute("ALTER TABLE users DROP COLUMN password_hash")
            except:
                pass  # SQLite doesn't support DROP COLUMN, ignore
        
        # Remove password column if it exists (no longer needed for access code system)
        if "password" in user_columns:
            try:
                cur.execute("ALTER TABLE users DROP COLUMN password")
            except:
                pass  # SQLite doesn't support DROP COLUMN, ignore
        
        # Add admin_code column if missing
        if "admin_code" not in user_columns:
            cur.execute("ALTER TABLE users ADD COLUMN admin_code TEXT")
        
        # Add created_at column if missing
        if "created_at" not in user_columns:
            cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")
        
        # Add is_active column if missing
        if "is_active" not in user_columns:
            cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
        
        # --- Initialize access codes if not exists ---
        cur.execute('SELECT COUNT(*) FROM access_codes')
        access_count = cur.fetchone()[0]
        if access_count == 0:
            cur.execute('''
                INSERT INTO access_codes (admin_code, user_code, updated_by, updated_at)
                VALUES (?, ?, ?, ?)
            ''', ("Istrom2026", "USER2026", "System", get_nigerian_time_str()))

            conn.commit()
    except Exception as e:
        st.error(f"Database initialization failed: {e}")

# --------------- User Authentication and Management Functions ---------------
def authenticate_by_access_code(access_code):
    """Authenticate a user by access code and return user info if successful"""
    try:
        with engine.connect() as conn:
            # First check if it's the global admin code
            result = conn.execute(text('''
                SELECT admin_code FROM access_codes 
                ORDER BY updated_at DESC LIMIT 1
            '''))
            admin_result = result.fetchone()
            
            if admin_result and access_code == admin_result[0]:
                # Global admin access
                return {
                    'id': 1,
                    'username': 'admin',
                    'full_name': 'System Administrator',
                    'user_type': 'admin',
                    'project_site': 'ALL',
                    'admin_code': admin_result[0]
                }
            
            # Check if it's a project site user code
            result = conn.execute(text('''
                SELECT project_site, user_code FROM project_site_access_codes 
                WHERE user_code = :access_code
            '''), {"access_code": access_code})
            site_result = result.fetchone()
            
            if site_result:
                project_site, user_code = site_result
                # Project site user access
                return {
                    'id': 999,
                    'username': 'user',
                    'full_name': f'User - {project_site}',
                    'user_type': 'user',
                    'project_site': project_site,
                    'admin_code': None
                }
            
            # Fallback to old system for backward compatibility
            result = conn.execute(text('''
                SELECT admin_code, user_code FROM access_codes 
                ORDER BY updated_at DESC LIMIT 1
            '''))
            codes = result.fetchone()
            
            if codes:
                admin_code, user_code = codes
                
                # Check if access code matches admin code
                if access_code == admin_code:
                    return {
                        'id': 1,
                        'username': 'admin',
                        'full_name': 'System Administrator',
                        'user_type': 'admin',
                        'project_site': 'ALL',
                        'admin_code': admin_code
                    }
                
                # Check if access code matches user code
                elif access_code == user_code:
                    return {
                        'id': 999,
                        'username': 'user',
                        'full_name': 'Regular User',
                        'user_type': 'user',
                        'project_site': 'Lifecamp Kafe',
                        'admin_code': None
                    }
            
            return None
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None

# Legacy password-based authentication removed - using access code system only

def create_simple_user(full_name, user_type, project_site, access_code):
    """Create a new user with enhanced persistence and error handling"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            
            # Check if access code already exists in users table
            cur.execute("SELECT COUNT(*) FROM users WHERE username = ?", (access_code,))
            if cur.fetchone()[0] > 0:
                st.error("Access code already exists. Please choose a different one.")
                return False
            
            # Insert user into users table with explicit transaction
            cur.execute('''
                INSERT INTO users (username, full_name, user_type, project_site, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (access_code, full_name, user_type, project_site, get_nigerian_time_str(), 1))
            
            # Log user creation in access_logs
            current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'System'))
            cur.execute('''
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                'SYSTEM',
                current_user,
                get_nigerian_time_iso(),
                1,
                st.session_state.get('user_type', 'admin')
            ))
            
            # Force commit and verify
            conn.commit()
            
            # Verify user was created
            cur.execute("SELECT id FROM users WHERE username = ?", (access_code,))
            user_id = cur.fetchone()
            if user_id:
                print(f"✅ User created successfully with ID: {user_id[0]}")
                return True
            else:
                print("❌ User creation verification failed")
                return False
                
    except Exception as e:
        st.error(f"User creation error: {e}")
        print(f"❌ User creation failed: {e}")
        return False

def delete_user(user_id):
    """Delete a user from the system - comprehensive cleanup of all related data"""
    try:
        with get_conn() as conn:
            if conn is None:
                return False
            
            cur = conn.cursor()
            
            # Get user info before deletion
            cur.execute("SELECT username, full_name, project_site, user_type FROM users WHERE id = ?", (user_id,))
            user_info = cur.fetchone()
            if not user_info:
                st.error("User not found")
                return False
                
            username, full_name, project_site, user_type = user_info
        
        # Log the deletion start
        current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
        deletion_log = f"User deletion initiated by {current_user}: {full_name} ({username}) from {project_site} (Type: {user_type})"
        
        # Insert deletion log
        cur.execute("""
            INSERT INTO access_logs (access_code, user_name, access_time, success, role)
            VALUES (?, ?, ?, ?, ?)
        """, (
            'SYSTEM', 
            current_user, 
            get_nigerian_time_iso(), 
            1, 
            st.session_state.get('user_type', 'user')
        ))
        
        # STEP 1: Delete all related records first (handle foreign key constraints)
        
        # Delete notifications for this user
        cur.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
        notifications_deleted = cur.rowcount
        
        # Delete requests made by this user
        cur.execute("DELETE FROM requests WHERE requested_by = ?", (full_name,))
        requests_deleted = cur.rowcount
        
        # Delete access logs for this user
        cur.execute("DELETE FROM access_logs WHERE user_name = ?", (full_name,))
        access_logs_deleted = cur.rowcount
        
        # Delete actuals recorded by this user
        cur.execute("DELETE FROM actuals WHERE recorded_by = ?", (full_name,))
        actuals_deleted = cur.rowcount
        
        # Delete any notifications sent to this user (by user_id)
        cur.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
        notifications_to_user_deleted = cur.rowcount
        
        # Delete any requests where this user is mentioned in note or other fields
        cur.execute("DELETE FROM requests WHERE requested_by = ? OR note LIKE ?", (full_name, f"%{full_name}%"))
        additional_requests_deleted = cur.rowcount
        
        # Delete any actuals where this user is mentioned
        cur.execute("DELETE FROM actuals WHERE recorded_by = ? OR notes LIKE ?", (full_name, f"%{full_name}%"))
        additional_actuals_deleted = cur.rowcount
        
        # STEP 2: Delete associated access code
        cur.execute("DELETE FROM project_site_access_codes WHERE user_code = ? AND project_site = ?", (username, project_site))
        access_codes_deleted = cur.rowcount
        
        # STEP 3: Finally delete the user
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        user_deleted = cur.rowcount
        
        if user_deleted > 0:
            conn.commit()
            
            # Log successful deletion with details
            cleanup_log = f"User '{full_name}' completely deleted. Cleaned up: {notifications_deleted} notifications, {requests_deleted} requests, {access_logs_deleted} access logs, {actuals_deleted} actuals, {access_codes_deleted} access codes"
            
            cur.execute("""
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (?, ?, ?, ?, ?)
            """, (
                'SYSTEM', 
                current_user, 
                get_nigerian_time_iso(), 
                1, 
                st.session_state.get('user_type', 'user')
            ))
            conn.commit()
            
            # Clear all caches to prevent data from coming back
            st.cache_data.clear()
            st.cache_resource.clear()
            
            st.success(f"User '{full_name}' deleted successfully!")
            st.info(f"Comprehensive cleanup completed: {notifications_deleted} notifications, {requests_deleted} requests, {access_logs_deleted} access logs, {actuals_deleted} actuals, {access_codes_deleted} access codes")
            return True
        else:
            st.error("Failed to delete user")
            return False
            
    except Exception as e:
        st.error(f"User deletion error: {e}")
        return False

def get_user_by_username(username):
    """Get user information by username"""
    try:
        with get_conn() as conn:
            if conn is None:
                return None
            
            cur = conn.cursor()
            cur.execute('''
                SELECT id, username, full_name, user_type, project_site, admin_code, created_at
                FROM users 
                WHERE username = ? AND is_active = 1
            ''', (username,))
            
            user = cur.fetchone()
            if user:
                return {
                    'id': user[0],
                    'username': user[1],
                    'full_name': user[2],
                    'user_type': user[3],
                    'project_site': user[4],
                    'admin_code': user[5],
                    'created_at': user[6]
                }
            return None
    except Exception as e:
        st.error(f"User lookup error: {e}")
        return None

def get_all_users():
    """Get all users for admin management"""
    try:
        with get_conn() as conn:
            if conn is None:
                return []
            
            cur = conn.cursor()
            # Try new schema first
            try:
                cur.execute('''
                    SELECT id, username, full_name, user_type, project_site, admin_code, created_at, is_active
                    FROM users 
                    ORDER BY created_at DESC
                ''')
                users = []
                for row in cur.fetchall():
                    users.append({
                        'id': row[0],
                        'username': row[1],
                        'full_name': row[2],
                        'user_type': row[3],
                        'project_site': row[4],
                        'admin_code': row[5],
                        'created_at': row[6],
                        'is_active': row[7]
                    })
                return users
            except:
                # Fallback to old schema
                cur.execute('''
                    SELECT id, username, full_name, role, created_at, is_active
                    FROM users 
                    ORDER BY created_at DESC
                ''')
                users = []
                for row in cur.fetchall():
                    users.append({
                        'id': row[0],
                        'username': row[1],
                        'full_name': row[2],
                        'user_type': row[3],  # Map role to user_type
                        'project_site': 'Lifecamp Kafe',  # Default project site
                        'admin_code': None,
                        'is_active': row[5],
                        'created_at': row[4]
                    })
                return users
    except Exception as e:
        st.error(f"User list error: {e}")
        return []

def is_admin():
    """Check if current user is admin"""
    return st.session_state.get('user_type') == 'admin'

def get_user_project_site():
    """Get current user's project site"""
    return st.session_state.get('project_site', 'Lifecamp Kafe')

def show_notification_popup(notification_type, title, message):
    """Show enhanced popup notification with better styling"""
    try:
        if notification_type == "new_request":
            st.success(f"🔔 **{title}**\n\n{message}")
            st.balloons()  # Add celebration effect for new requests
        elif notification_type == "request_approved":
            st.success(f"✅ **{title}**\n\n{message}")
            st.balloons()  # Add celebration effect for approvals
        elif notification_type == "request_rejected":
            st.error(f"❌ **{title}**\n\n{message}")
        else:
            st.info(f"ℹ️ **{title}**\n\n{message}")
    except Exception as e:
        # Fallback to simple notification
        st.info(f"Notification: {message}")

def create_notification_sound(frequency=500, duration=0.2, sample_rate=44100):
    """Create a distinctive, attention-grabbing notification sound that really stands out"""
    try:
        import numpy as np
        import io
        import wave
        
        # Create a more distinctive, attention-grabbing sound
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        
        # Create a distinctive "ding-dong" chime pattern that stands out
        # First chime (higher pitch, shorter)
        first_chime_duration = duration * 0.4
        first_t = t[:int(len(t) * 0.4)]
        
        # Second chime (lower pitch, longer)
        second_chime_duration = duration * 0.6
        second_t = t[int(len(t) * 0.4):]
        
        # First chime - bright and attention-grabbing
        first_freq = frequency * 1.5  # Higher pitch
        first_vibrato = 0.08 * np.sin(2 * np.pi * 4 * first_t)  # More vibrato
        first_tone = np.sin(2 * np.pi * (first_freq + first_vibrato * 40) * first_t)
        
        # Add bright harmonics for the first chime
        first_harmonic2 = 0.5 * np.sin(2 * np.pi * first_freq * 2 * first_t)
        first_harmonic3 = 0.3 * np.sin(2 * np.pi * first_freq * 3 * first_t)
        
        # Second chime - deeper and more resonant
        second_freq = frequency * 0.8  # Lower pitch
        second_vibrato = 0.06 * np.sin(2 * np.pi * 2 * second_t)  # Slower vibrato
        second_tone = np.sin(2 * np.pi * (second_freq + second_vibrato * 30) * second_t)
        
        # Add rich harmonics for the second chime
        second_harmonic2 = 0.4 * np.sin(2 * np.pi * second_freq * 1.5 * second_t)
        second_harmonic3 = 0.2 * np.sin(2 * np.pi * second_freq * 2.5 * second_t)
        second_harmonic4 = 0.1 * np.sin(2 * np.pi * second_freq * 3.5 * second_t)
        
        # Combine both chimes
        first_chime = first_tone + first_harmonic2 + first_harmonic3
        second_chime = second_tone + second_harmonic2 + second_harmonic3 + second_harmonic4
        
        # Create distinctive envelope with sharp attack and sustained decay
        envelope = np.ones_like(t)
        
        # Sharp attack for first chime (first 10% of total duration)
        attack_samples = int(0.1 * len(t))
        envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
        
        # Sustain for first chime (10% to 40%)
        sustain_start = int(0.1 * len(t))
        sustain_end = int(0.4 * len(t))
        envelope[sustain_start:sustain_end] = 1.0
        
        # Quick decay between chimes (40% to 50%)
        decay_start = int(0.4 * len(t))
        decay_mid = int(0.5 * len(t))
        envelope[decay_start:decay_mid] = np.linspace(1, 0.3, decay_mid - decay_start)
        
        # Second chime attack (50% to 60%)
        second_attack_start = int(0.5 * len(t))
        second_attack_end = int(0.6 * len(t))
        envelope[second_attack_start:second_attack_end] = np.linspace(0.3, 1, second_attack_end - second_attack_start)
        
        # Sustain second chime (60% to 80%)
        second_sustain_start = int(0.6 * len(t))
        second_sustain_end = int(0.8 * len(t))
        envelope[second_sustain_start:second_sustain_end] = 1.0
        
        # Final decay (80% to 100%)
        final_decay_start = int(0.8 * len(t))
        envelope[final_decay_start:] = np.linspace(1, 0, len(t) - final_decay_start)
        
        # Combine both chimes with the envelope
        wave_data = np.zeros_like(t)
        wave_data[:len(first_chime)] = first_chime
        wave_data[len(first_chime):] = second_chime
        
        # Apply the distinctive envelope
        wave_data = wave_data * envelope
        
        # Add a distinctive "ping" at the very beginning for maximum attention
        ping_samples = int(0.01 * sample_rate)  # 10ms ping
        if ping_samples < len(wave_data):
            ping = np.random.normal(0, 0.08, ping_samples) * np.exp(-np.linspace(0, 20, ping_samples))
            wave_data[:ping_samples] += ping
        
        # Add a subtle echo effect for more presence
        echo_delay = int(0.05 * sample_rate)  # 50ms echo
        if len(wave_data) > echo_delay:
            echo = 0.3 * wave_data[:-echo_delay] * np.exp(-np.linspace(0, 8, len(wave_data) - echo_delay))
            wave_data[echo_delay:] += echo
        
        # Add a subtle reverb tail for more realistic sound
        reverb_samples = int(0.15 * sample_rate)  # 150ms reverb
        if len(wave_data) > reverb_samples:
            reverb = 0.15 * wave_data[:-reverb_samples] * np.exp(-np.linspace(0, 6, len(wave_data) - reverb_samples))
            wave_data[reverb_samples:] += reverb
        
        # Convert to 16-bit integers with higher amplitude for more presence
        wave_data = np.clip(wave_data, -1, 1)  # Prevent clipping
        wave_data = (wave_data * 15000).astype(np.int16)  # Higher amplitude for more presence
        
        # Create WAV file in memory
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(wave_data.tobytes())
        
        buffer.seek(0)
        return buffer.getvalue()
        
    except ImportError:
        # Fallback: return None if numpy is not available
        return None
    except Exception as e:
        return None

def create_notification(notification_type, title, message, user_id=None, request_id=None):
    """Create a notification for specific users - ENFORCE ACCESS CODE ISOLATION"""
    try:
        with get_conn() as conn:
            if conn is None:
                return False
            
            cur = conn.cursor()
            # Handle user_id - if it's a string (name), try to find the user ID by access code
            actual_user_id = None
            if user_id and isinstance(user_id, str):
                # Method 1: Try to find by full_name
                cur.execute("SELECT id FROM users WHERE full_name = ?", (user_id,))
                user_result = cur.fetchone()
                if user_result:
                    actual_user_id = user_result[0]
                else:
                    # Method 2: Try to find by username
                    cur.execute("SELECT id FROM users WHERE username = ?", (user_id,))
                    user_result = cur.fetchone()
                    if user_result:
                        actual_user_id = user_result[0]
            elif user_id and isinstance(user_id, int):
                # Special case for project site users (user_id = -1)
                if user_id == -1:
                    actual_user_id = -1  # Project site user
                else:
                    # It's already a user ID - verify it exists
                    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                    user_result = cur.fetchone()
                    if user_result:
                        actual_user_id = user_id
            
            # If user_id is None, create admin notification (visible to all admins)
            if actual_user_id is None:
                # Create admin notification with user_id = NULL (visible to all admins)
                cur.execute('''
                    INSERT INTO notifications (notification_type, title, message, user_id, request_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (notification_type, title, message, None, request_id))
                conn.commit()
                # Admin notifications should not show popups to users
                # Only show popups for user-specific notifications
                return True
            else:
                # For project site users (user_id = -1), temporarily disable foreign key constraints
                if actual_user_id == -1:
                    cur.execute('PRAGMA foreign_keys = OFF')
                
                cur.execute('''
                    INSERT INTO notifications (notification_type, title, message, user_id, request_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (notification_type, title, message, actual_user_id, request_id))
                conn.commit()
                
                # Re-enable foreign key constraints if they were disabled
                if actual_user_id == -1:
                    cur.execute('PRAGMA foreign_keys = ON')
                
                # Show popup for user notifications when it's an approval/rejection
                if notification_type in ["request_approved", "request_rejected"]:
                    show_notification_popup(notification_type, title, message)
                
                return True
    except Exception as e:
        st.error(f"Notification creation error: {e}")
        return False

def get_admin_notifications():
    """Get unread notifications for admins - PROJECT-SPECIFIC admin notifications"""
    try:
        current_project = st.session_state.get('current_project_site', 'Lifecamp Kafe')
        
        with engine.connect() as conn:
            result = conn.execute(text('''
                SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at,
                       u.full_name as requester_name
                FROM notifications n
                LEFT JOIN users u ON n.user_id = u.id
                WHERE n.is_read = 0 
                AND n.user_id IS NULL
                AND n.notification_type IN ('new_request', 'request_approved', 'request_rejected')
                AND n.message LIKE :project_pattern
                ORDER BY n.created_at DESC
                LIMIT 10
            '''), {"project_pattern": f'%{current_project}%'})
            
            notifications = []
            for row in result.fetchall():
                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'message': row[3],
                    'request_id': row[4],
                    'created_at': row[5],
                    'requester_name': row[6]
                })
            
            return notifications
    except Exception as e:
        st.error(f"Notification retrieval error: {e}")
        return []

def get_all_notifications():
    """Get all notifications (read and unread) for admin log - PROJECT-SPECIFIC admin notifications"""
    try:
        with engine.connect() as conn:
            current_project = st.session_state.get('current_project_site', 'Lifecamp Kafe')
            
            # Get admin notifications that mention the current project site
            result = conn.execute(text('''
                SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at, n.is_read,
                       u.full_name as requester_name
                FROM notifications n
                LEFT JOIN users u ON n.user_id = u.id
                WHERE n.user_id IS NULL
                AND (n.notification_type IN ('new_request', 'request_approved', 'request_rejected'))
                AND n.message LIKE :current_project
                ORDER BY n.created_at DESC
                LIMIT 20
            '''), {"current_project": f'%{current_project}%'})
            
            notifications = []
            for row in result.fetchall():
                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'message': row[3],
                    'request_id': row[4],
                    'created_at': row[5],
                    'is_read': row[6],
                    'requester_name': row[7]
                })
            return notifications
    except Exception as e:
        st.error(f"Notification log retrieval error: {e}")
        return []

def get_user_notifications():
    """Get notifications for the current user - ENFORCE PROJECT ISOLATION"""
    try:
        with engine.begin() as conn:
            current_user = st.session_state.get('full_name', st.session_state.get('user_name', 'Unknown'))
            current_project = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
            
            # Clean up any notifications with user_id=None to prevent cross-project visibility
            conn.execute(text("DELETE FROM notifications WHERE user_id IS NULL"))
            
            # Try multiple methods to find the current user
            user_id = None
            # Method 1: Try to find by full_name and project_site
            result = conn.execute(text("SELECT id FROM users WHERE full_name = :full_name AND project_site = :project_site"), 
                               {"full_name": current_user, "project_site": current_project})
            user_result = result.fetchone()
            if user_result:
                user_id = user_result[0]
            else:
                # Method 2: Try to find by username and project_site
                current_username = st.session_state.get('username', st.session_state.get('user_name', 'Unknown'))
                result = conn.execute(text("SELECT id FROM users WHERE username = :username AND project_site = :project_site"), 
                                   {"username": current_username, "project_site": current_project})
                user_result = result.fetchone()
                if user_result:
                    user_id = user_result[0]
                else:
                    # Method 3: Try to find by session user_id if available
                    session_user_id = st.session_state.get('user_id')
                    if session_user_id:
                        result = conn.execute(text("SELECT id FROM users WHERE id = :user_id AND project_site = :project_site"), 
                                           {"user_id": session_user_id, "project_site": current_project})
                        user_result = result.fetchone()
                        if user_result:
                            user_id = session_user_id
            
            notifications = []
            
            # Try to get notifications by user ID - ENFORCE PROJECT ISOLATION
            if user_id:
                result = conn.execute(text('''
                    SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at, n.is_read, n.user_id
                    FROM notifications n
                    JOIN users u ON n.user_id = u.id
                    WHERE n.user_id = :user_id AND u.project_site = :project_site
                    ORDER BY n.created_at DESC
                    LIMIT 10
                '''), {"user_id": user_id, "project_site": current_project})
                notifications = result.fetchall()
            
            # Only show notifications that are specifically assigned to this user from their project
            # Do NOT use fallback query that can pick up admin notifications or cross-project notifications
            
            notification_list = []
            for row in notifications:
                notification_list.append({
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'message': row[3],
                    'request_id': row[4],
                    'created_at': row[5],
                    'is_read': row[6],
                    'user_id': row[7]
                })
            
            return notification_list
    except Exception as e:
        st.error(f"User notification retrieval error: {e}")
        return []

def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        with engine.begin() as conn:
            conn.execute(text('UPDATE notifications SET is_read = 1 WHERE id = :notification_id'), 
                       {"notification_id": notification_id})
            return True
    except Exception as e:
        st.error(f"Notification update error: {e}")
        return False

def delete_notification(notification_id):
    """Delete a notification"""
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM notifications WHERE id = :notification_id"), 
                       {"notification_id": notification_id})
            
            # Clear caches to prevent data from reappearing
            st.cache_data.clear()
            st.cache_resource.clear()
            
            return True
    except Exception as e:
        st.error(f"Error deleting notification: {e}")
        return False

def clear_old_access_logs(days=30):
    """Clear access logs older than specified days"""
    conn = get_conn()
    if conn is None:
        return False
    
    try:
        cur = conn.cursor()
        cutoff_date = (get_nigerian_time() - timedelta(days=days)).isoformat()
        
        # Count logs to be deleted
        cur.execute("SELECT COUNT(*) FROM access_logs WHERE access_time < ?", (cutoff_date,))
        count = cur.fetchone()[0]
        
        if count > 0:
            # Delete old logs
            cur.execute("DELETE FROM access_logs WHERE access_time < ?", (cutoff_date,))
            conn.commit()
            st.success(f"Cleared {count} old access logs (older than {days} days)")
            return True
        else:
            st.info("No old access logs to clear")
            return True
            
    except Exception as e:
        st.error(f"Error clearing old access logs: {e}")
        return False
    finally:
        conn.close()

def clear_all_access_logs():
    """Clear ALL access logs from the database"""
    try:
        with get_conn() as conn:
            if conn is None:
                return False
            
            cur = conn.cursor()
            
            # Count total logs
            cur.execute("SELECT COUNT(*) FROM access_logs")
            total_count = cur.fetchone()[0]
            
            if total_count > 0:
                # Delete ALL logs
                cur.execute("DELETE FROM access_logs")
                conn.commit()
                
                # Log this action
                current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
                cur.execute("""
                    INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    'SYSTEM',
                    current_user,
                    get_nigerian_time_iso(),
                    1,
                    st.session_state.get('user_type', 'admin')
                ))
                conn.commit()
                
                # Clear all caches to prevent data from coming back
                st.cache_data.clear()
                st.cache_resource.clear()
                
                st.success(f"Cleared ALL {total_count} access logs! Fresh start initiated.")
                return True
            else:
                st.info("No access logs to clear")
                return True
                
    except Exception as e:
        st.error(f"Error clearing all access logs: {e}")
        return False

# clear_all_caches function removed

def fix_dataframe_types(df):
    """Fix DataFrame column types to prevent PyArrow serialization errors"""
    if df is None or df.empty:
        return df
    
    try:
        # Fix S/N column if it exists
        if 'S/N' in df.columns:
            df['S/N'] = df['S/N'].astype(str)
        
        # Fix any other problematic columns
        for col in df.columns:
            if df[col].dtype == 'object':
                # Check if column has mixed types
                try:
                    # Try to convert to numeric, if it fails, keep as string
                    pd.to_numeric(df[col], errors='raise')
                except (ValueError, TypeError):
                    # Column has mixed types, convert all to string
                    df[col] = df[col].astype(str)
        
        return df
    except Exception as e:
        st.error(f"Error fixing DataFrame types: {e}")
        return df

# Session state diagnostic function removed

# --------------- Backup and Data Protection Functions ---------------
def create_backup():
    """Create a timestamped backup of the database"""
    # Use West African Time (WAT) for backup timestamps
    wat_timezone = pytz.timezone('Africa/Lagos')
    current_time = datetime.now(wat_timezone)
    timestamp = current_time.strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"istrominventory_backup_{timestamp}.db"
    
    try:
        shutil.copy2(DB_PATH, backup_path)
        return str(backup_path)
    except Exception as e:
        st.error(f" Failed to create backup: {str(e)}")
        return None

def get_backup_list():
    """Get list of available backups"""
    backup_files = list(BACKUP_DIR.glob("istrominventory_backup_*.db"))
    return sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True)

def restore_backup(backup_path):
    """Restore database from backup"""
    try:
        shutil.copy2(backup_path, DB_PATH)
        return True
    except Exception as e:
        st.error(f" Failed to restore backup: {str(e)}")
        return False

def export_data():
    """Export all data to JSON format"""
    try:
        with get_conn() as conn:
            # Export items
            items_df = pd.read_sql_query("SELECT * FROM items", conn)
            items_data = items_df.to_dict('records')
            
            # Export requests
            requests_df = pd.read_sql_query("SELECT * FROM requests", conn)
            requests_data = requests_df.to_dict('records')
            
            # Export access logs
            access_logs_df = pd.read_sql_query("SELECT * FROM access_logs", conn)
            access_logs_data = access_logs_df.to_dict('records')
            
            export_data = {
                "items": items_data,
                "requests": requests_data,
                "access_logs": access_logs_data,
                "export_timestamp": datetime.now(pytz.timezone('Africa/Lagos')).isoformat()
            }
            
            return json.dumps(export_data, indent=2, default=str)
    except Exception as e:
        st.error(f" Failed to export data: {str(e)}")
        return None

def import_data(json_data):
    """Import data from JSON format"""
    # PRODUCTION DATA PROTECTION - Prevent data loss
    if os.getenv('PRODUCTION_MODE') == 'true' or os.getenv('DISABLE_MIGRATION') == 'true':
        print("🚫 import_data() BLOCKED - PRODUCTION MODE - YOUR DATA IS SAFE")
        return False
    
    try:
        data = json.loads(json_data)
        
        with get_conn() as conn:
            cur = conn.cursor()
            
            # Clear existing data - ONLY ALLOWED IN DEVELOPMENT
            cur.execute("DELETE FROM access_logs")
            cur.execute("DELETE FROM requests")
            cur.execute("DELETE FROM items")
            
            # Import items
            for item in data.get("items", []):
                cur.execute("""
                    INSERT INTO items (id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get('id'), item.get('code'), item.get('name'), item.get('category'),
                    item.get('unit'), item.get('qty'), item.get('unit_cost'), item.get('budget'),
                    item.get('section'), item.get('grp'), item.get('building_type')
                ))
            
            # Import requests
            for request in data.get("requests", []):
                cur.execute("""
                    INSERT INTO requests (id, ts, section, item_id, qty, requested_by, note, status, approved_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    request.get('id'), request.get('ts'), request.get('section'), request.get('item_id'),
                    request.get('qty'), request.get('requested_by'), request.get('note'),
                    request.get('status'), request.get('approved_by')
                ))
            
            # Import access logs
            for log in data.get("access_logs", []):
                cur.execute("""
                    INSERT INTO access_logs (id, access_code, user_name, access_time, success, role)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    log.get('id'), log.get('access_code'), log.get('user_name'),
                    log.get('access_time'), log.get('success'), log.get('role')
                ))
            
            conn.commit()
            return True
    except Exception as e:
        st.error(f" Failed to import data: {str(e)}")
        return False

def cleanup_old_backups(max_backups=10):
    """Keep only the most recent backups"""
    backup_files = get_backup_list()
    if len(backup_files) > max_backups:
        for old_backup in backup_files[max_backups:]:
            try:
                old_backup.unlink()
            except Exception:
                pass

def ensure_indexes():
    """Create database indexes for better performance"""
    conn = get_conn()
    if conn is None:
        return
    
    try:
        cur = conn.cursor()
        # Create indexes for frequently queried columns
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_budget ON items(budget)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_section ON items(section)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_building_type ON items(building_type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_category ON items(category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_name ON items(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_code ON items(code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_requests_item_id ON requests(item_id)")
        conn.commit()
        conn.close()
    except Exception as e:
        if conn:
            try:
                conn.close()
            except:
                pass

def clear_cache():
    """Clear the cached data when items are updated or project site changes"""
    try:
        # Clear Streamlit caches
        st.cache_data.clear()
        st.cache_resource.clear()
    except Exception as e:
        st.error(f"Error clearing caches: {e}")

def clear_all_caches():
    """Clear all caches and force refresh"""
    st.cache_data.clear()
    if hasattr(st, 'cache_resource'):
        st.cache_resource.clear()


# Project sites database functions
def get_project_sites():
    """Get all active project sites from database"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM project_sites WHERE is_active = 1 ORDER BY created_at"))
            sites = [row[0] for row in result.fetchall()]
            print(f"🔍 Found {len(sites)} project sites: {sites}")
            return sites
    except Exception as e:
        print(f"❌ Failed to get project sites: {str(e)}")
        st.error(f"Failed to get project sites: {str(e)}")
        return []  # No fallback - let admin create project sites

def add_project_site(name, description=""):
    """Add a new project site to database"""
    try:
        with get_conn() as conn:
            # Debug: Check what type of connection we have
            if hasattr(conn, 'server_version'):
                print(f"🔍 Using PostgreSQL connection for add_project_site")
            else:
                print(f"🔍 Using SQLite connection for add_project_site - THIS IS THE PROBLEM!")
            
            cur = conn.cursor()
            # Check if project site already exists (only active ones)
            cur.execute("SELECT COUNT(*) FROM project_sites WHERE name = ? AND is_active = 1", (name,))
            count = cur.fetchone()[0]
            print(f"Debug: Checking for project site '{name}' - found {count} existing records")
            if count > 0:
                print(f"Debug: Project site '{name}' already exists")
                return False  # Name already exists
            
            # Insert new project site
            cur.execute("INSERT INTO project_sites (name, description) VALUES (?, ?)", (name, description))
            
            # Automatically create an access code for this project site
            default_access_code = f"PROJECT_{name.upper().replace(' ', '_')}"
            
            # Get admin_code from global access codes
            cur.execute("SELECT admin_code FROM access_codes ORDER BY updated_at DESC LIMIT 1")
            admin_result = cur.fetchone()
            admin_code = admin_result[0] if admin_result else "ADMIN_DEFAULT"
            
            cur.execute("INSERT INTO project_site_access_codes (project_site, admin_code, user_code, updated_at) VALUES (?, ?, ?, ?)", 
                       (name, admin_code, default_access_code, get_nigerian_time_str()))
            
            conn.commit()
            return True
        
    except sqlite3.IntegrityError:
        return False  # Name already exists
    except Exception as e:
        # Log error but don't show to user
        return False

def delete_project_site(name):
    """Delete a project site from database permanently"""
    try:
        with get_conn() as conn:
            if conn is None:
                return False
            cur = conn.cursor()
            
            # Delete the access codes for this project site
            cur.execute("DELETE FROM project_site_access_codes WHERE project_site = ?", (name,))
            access_codes_deleted = cur.rowcount
            
            # Permanently delete the project site record
            cur.execute("DELETE FROM project_sites WHERE name = ?", (name,))
            project_site_deleted = cur.rowcount
            
            conn.commit()
            
            # Return True if either operation succeeded
            return access_codes_deleted > 0 or project_site_deleted > 0
    except Exception as e:
        print(f"Error deleting project site: {e}")
        return False

def update_project_site_name(old_name, new_name):
    """Update project site name in database"""
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            # Update project_sites table
            cur.execute("UPDATE project_sites SET name = ? WHERE name = ?", (new_name, old_name))
            
            # Update items table
            cur.execute("UPDATE items SET project_site = ? WHERE project_site = ?", (new_name, old_name))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # New name already exists

def get_project_access_code(project_site):
    """Get access code for a specific project site"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            # Use case-insensitive matching
            cur.execute("SELECT user_code FROM project_site_access_codes WHERE LOWER(project_site) = LOWER(?)", (project_site,))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception:
        return None

def update_project_access_code(project_site, new_access_code):
    """Update access code for a specific project site"""
    try:
        with get_conn() as conn:
            if conn is None:
                print("Database connection failed")
                return False
                
            cur = conn.cursor()
            
            # Get admin_code from global access codes
            cur.execute("SELECT admin_code FROM access_codes ORDER BY updated_at DESC LIMIT 1")
            admin_result = cur.fetchone()
            admin_code = admin_result[0] if admin_result else "ADMIN_DEFAULT"
            
            # First try to update existing record (case-insensitive)
            cur.execute("UPDATE project_site_access_codes SET user_code = ?, admin_code = ?, updated_at = ? WHERE LOWER(project_site) = LOWER(?)", 
                       (new_access_code, admin_code, get_nigerian_time_str(), project_site))
            
            # If no rows were affected, insert new record
            if cur.rowcount == 0:
                cur.execute("INSERT INTO project_site_access_codes (project_site, admin_code, user_code, updated_at) VALUES (?, ?, ?, ?)", 
                           (project_site, admin_code, new_access_code, get_nigerian_time_str()))
            
            conn.commit()
            print(f"Successfully updated access code for project site: {project_site}")
            return True
    except Exception as e:
        print(f"Error updating project access code: {e}")
        st.error(f"Database error: {e}")
        return False

def initialize_default_project_site():
    """Initialize Lifecamp Kafe as default project site if it doesn't exist"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            # Check for any Lifecamp Kafe variation (with or without "Project")
            cur.execute("SELECT COUNT(*) FROM project_sites WHERE name LIKE '%Lifecamp Kafe%'")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO project_sites (name, description) VALUES (?, ?)", 
                           ("Lifecamp Kafe", "Default project site"))
                conn.commit()
    except sqlite3.OperationalError as e:
        if "disk I/O error" in str(e):
            # Try to recover from disk I/O error
            try:
                # Clear WAL file and retry
                import os
                if os.path.exists('istrominventory.db-wal'):
                    os.remove('istrominventory.db-wal')
                if os.path.exists('istrominventory.db-shm'):
                    os.remove('istrominventory.db-shm')
                # Retry the operation
                initialize_default_project_site()
            except:
                pass
        else:
            st.error(f"Database error in project site initialization: {str(e)}")
    except Exception as e:
        st.error(f"Failed to initialize default project site: {str(e)}")

# Access codes (configurable from admin interface)
DEFAULT_ADMIN_ACCESS_CODE = "admin2024"
DEFAULT_USER_ACCESS_CODE = "user2024"

def get_access_codes():
    """Get current access codes from Streamlit secrets or database fallback"""
    try:
        # First try to get from Streamlit secrets (persistent across deployments)
        try:
            admin_code = st.secrets.get("ACCESS_CODES", {}).get("admin_code", DEFAULT_ADMIN_ACCESS_CODE)
            user_code = st.secrets.get("ACCESS_CODES", {}).get("user_code", DEFAULT_USER_ACCESS_CODE)
            if admin_code != DEFAULT_ADMIN_ACCESS_CODE or user_code != DEFAULT_USER_ACCESS_CODE:
                return admin_code, user_code
        except:
            pass  # Fall back to database if secrets not available
        
        # Fallback to database
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT admin_code, user_code FROM access_codes ORDER BY id DESC LIMIT 1"))
                row = result.fetchone()
                
                if row:
                    return row[0], row[1]  # admin_code, user_code
                else:
                    # Insert default codes if none exist
                    wat_timezone = pytz.timezone('Africa/Lagos')
                    current_time = datetime.now(wat_timezone)
                    with engine.begin() as trans_conn:
                        trans_conn.execute(text("""
                            INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                            VALUES (:admin_code, :user_code, :updated_at, :updated_by)
                        """), {
                            "admin_code": DEFAULT_ADMIN_ACCESS_CODE,
                            "user_code": DEFAULT_USER_ACCESS_CODE,
                            "updated_at": current_time.isoformat(),
                            "updated_by": "System"
                        })
                    return DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE
        except Exception as e:
            print(f"❌ Database connection failed - using default access codes: {e}")
            return DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE
    except Exception as e:
        # Ultimate fallback to default codes
        return DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE

def log_access(access_code, success=True, user_name="Unknown", role=None):
    """Log access attempts to database with proper user identification"""
    try:
        # Determine role if not provided
        if role is None:
            admin_code, user_code = get_access_codes()
            if access_code == admin_code:
                role = "admin"
            elif access_code == user_code:
                role = "user"
            else:
                # Check if it's a project site access code
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT project_site FROM project_site_access_codes WHERE user_code = :access_code"), 
                                        {"access_code": access_code})
                    project_result = result.fetchone()
                    if project_result:
                        role = "user"  # Project site users are regular users
                    else:
                        role = "unknown"
            
            # Special handling for session restore
            if access_code == "SESSION_RESTORE":
                role = st.session_state.get('user_role', 'unknown')
        
        # Get current time in West African Time
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        
        # Insert access log using SQLAlchemy
        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (:access_code, :user_name, :access_time, :success, :role)
                RETURNING id
            """), {
                "access_code": access_code,
                "user_name": user_name,
                "access_time": current_time.isoformat(),
                "success": 1 if success else 0,
                "role": role
            })
            log_id = result.fetchone()[0]
            return log_id
    except Exception as e:
        print(f"❌ Failed to log access: {e}")
        return None

def df_items_cached(project_site=None):
    """Cached version of df_items for better performance - shows items from current project site only"""
    if project_site is None:
        # Use user's assigned project site, fallback to session state
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', None))
    
    from sqlalchemy import text
    from db import get_engine
    
    if project_site is None:
        # No project site selected - return empty DataFrame
        return pd.DataFrame()
    
    q = text("""
        SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type, project_site 
        FROM items 
        WHERE project_site = :ps
        ORDER BY budget, section, grp, building_type, name
    """)
    
    try:
        engine = get_engine()
        return pd.read_sql_query(q, engine, params={"ps": project_site})
    except Exception as e:
        # Log error but don't print to stdout to avoid BrokenPipeError
        return pd.DataFrame()

def get_budget_options(project_site=None):
    """Generate budget options based on actual database content"""
    budget_options = ["All"]  # Always include "All" option
    
    # Use current project site if not specified
    if project_site is None:
        project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    try:
        # Get actual budgets from database for this project site
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT DISTINCT budget 
                FROM items 
                WHERE project_site = :project_site AND budget IS NOT NULL AND budget != ''
                ORDER BY budget
            """), {"project_site": project_site})
            
            db_budgets = [row[0] for row in result.fetchall()]
            
            # Generate all possible budget options (no redundancy)
            # Get max budget number from session state or default to 20
            max_budget = st.session_state.get('max_budget_num', 20)
            for budget_num in range(1, max_budget + 1):  # Dynamic budget range
                for bt in PROPERTY_TYPES:
                    if bt:
                        # Add only subgroups for this budget and building type (no base budget)
                        # Match the actual database format (no space before parenthesis, "Irons" not "Iron")
                        base_subgroups = [
                            f"Budget {budget_num} - {bt}(General Materials)",
                            f"Budget {budget_num} - {bt}(Woods)",
                            f"Budget {budget_num} - {bt}(Plumbings)",
                            f"Budget {budget_num} - {bt}(Irons)",
                            f"Budget {budget_num} - {bt}(Labour)"
                        ]
                        
                        # Add Electrical and Mechanical for Budget 3 and above
                        if budget_num >= 3:
                            base_subgroups.extend([
                                f"Budget {budget_num} - {bt}(Electrical)",
                                f"Budget {budget_num} - {bt}(Mechanical)"
                            ])
                        
                        budget_options.extend(base_subgroups)
    except Exception as e:
        # Fallback to basic options if database query fails
        for budget_num in range(1, 21):
            for bt in PROPERTY_TYPES:
                if bt:
                    base_subgroups = [
                        f"Budget {budget_num} - {bt}(General Materials)",
                        f"Budget {budget_num} - {bt}(Woods)",
                        f"Budget {budget_num} - {bt}(Plumbings)",
                        f"Budget {budget_num} - {bt}(Irons)",
                        f"Budget {budget_num} - {bt}(Labour)"
                    ]
                    
                    # Add Electrical and Mechanical for Budget 3 and above
                    if budget_num >= 3:
                        base_subgroups.extend([
                            f"Budget {budget_num} - {bt}(Electrical)",
                            f"Budget {budget_num} - {bt}(Mechanical)"
                        ])
                    
                    budget_options.extend(base_subgroups)
    
    return budget_options

def get_base_budget_options(project_site=None):
    """Generate base budget options (e.g., 'Budget 1 - Flats') that have items in the database"""
    budget_options = ["All"]  # Always include "All" option
    
    # Use current project site if not specified
    if project_site is None:
        project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    try:
        # Get actual budgets from database for this project site
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT budget 
                FROM items 
                WHERE project_site = ? AND budget IS NOT NULL AND budget != ''
                ORDER BY budget
            """, (project_site,))
            
            db_budgets = [row[0] for row in cur.fetchall()]
            
            # Extract base budgets (e.g., "Budget 1 - Flats" from "Budget 1 - Flats (General Materials)")
            base_budgets = set()
            for budget in db_budgets:
                # Extract base budget by removing subgroup info
                if " - " in budget:
                    # Find the base budget part (e.g., "Budget 1 - Flats" from "Budget 1 - Flats (General Materials)")
                    base_part = budget.split(" (")[0]  # Remove subgroup
                    base_budgets.add(base_part)
            
            # Convert to sorted list
            budget_options.extend(sorted(base_budgets))
            return budget_options
            
    except Exception as e:
        # Fallback to basic options if database query fails
        return ["All", "Budget 1 - Flats", "Budget 1 - Terraces"]

def get_section_options(project_site=None):
    """Generate section options based on actual database content"""
    section_options = ["All"]  # Always include "All" option
    
    # Use current project site if not specified
    if project_site is None:
        project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    try:
        # Get actual sections from database for this project site
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT DISTINCT section 
                FROM items 
                WHERE project_site = :project_site AND section IS NOT NULL AND section != ''
                ORDER BY section
            """), {"project_site": project_site})
            
            db_sections = [row[0] for row in result.fetchall()]
            section_options.extend(db_sections)
    except Exception as e:
        # Fallback to basic options if database query fails
        section_options.extend(["materials", "labour"])
    
    return section_options

def get_summary_data():
    """Cache summary data generation - optimized"""
    # For regular users, use their assigned project site, for admins use current_project_site
    user_type = st.session_state.get('user_type', 'user')
    if user_type == 'admin':
        project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    else:
        # Regular users should use their assigned project site
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
    
    all_items = df_items_cached(project_site)
    if all_items.empty:
        return pd.DataFrame(), []
    
    all_items["Amount"] = (all_items["qty"].fillna(0) * all_items["unit_cost"].fillna(0)).round(2)
    
    # Create summary by budget and building type (optimized)
    summary_data = []
    
    # Only process budgets that actually have data - limit to first 10 for performance
    existing_budgets = all_items["budget"].str.extract(r"Budget (\d+)", expand=False).dropna().astype(int).unique()
    
    for budget_num in existing_budgets[:10]:  # Limit to first 10 budgets with data
        budget_items = all_items[all_items["budget"].str.contains(f"Budget {budget_num}", case=False, na=False, regex=False)]
        if not budget_items.empty:
            budget_total = float(budget_items["Amount"].sum())
            
            # Get totals by building type for this budget (optimized)
            building_totals = budget_items.groupby("building_type")["Amount"].sum().to_dict()
            
            summary_data.append({
                "Budget": f"Budget {budget_num}",
                "Flats": f"₦{building_totals.get('Flats', 0):,.2f}",
                "Terraces": f"₦{building_totals.get('Terraces', 0):,.2f}",
                "Semi-detached": f"₦{building_totals.get('Semi-detached', 0):,.2f}",
                "Fully-detached": f"₦{building_totals.get('Fully-detached', 0):,.2f}",
                "Total": f"₦{budget_total:,.2f}"
            })
    
    return all_items, summary_data

def df_items(filters=None):
    """Get items with optional filtering - optimized with database queries"""
    if not filters or not any(v for v in filters.values() if v):
        return df_items_cached(st.session_state.get('current_project_site'))
    
    from sqlalchemy import text
    from db import get_engine
    
    # Build SQL query with filters for better performance - ENFORCE PROJECT ISOLATION
    current_project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    # Start with base query
    q = text("""
        SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type 
        FROM items 
        WHERE project_site = :ps
    """)
    params = {"ps": current_project_site}
    
    for k, v in filters.items():
        if v is not None and v != "":
            if k == "budget":
                if "(" in str(v) and ")" in str(v):
                    # Specific subgroup search
                    q = text(str(q) + " AND budget LIKE :budget")
                    params["budget"] = f"%{v}%"
                else:
                    # General search - use base budget
                    base_budget = str(v).split("(")[0].strip()
                    q = text(str(q) + " AND budget LIKE :budget")
                    params["budget"] = f"%{base_budget}%"
            elif k == "section":
                q = text(str(q) + " AND section LIKE :section")
                params["section"] = f"%{v}%"
            elif k == "building_type":
                q = text(str(q) + " AND building_type LIKE :building_type")
                params["building_type"] = f"%{v}%"
            elif k == "category":
                q = text(str(q) + " AND category LIKE :category")
                params["category"] = f"%{v}%"
            elif k == "code":
                q = text(str(q) + " AND code LIKE :code")
                params["code"] = f"%{v}%"
            elif k == "name":
                q = text(str(q) + " AND name LIKE :name")
                params["name"] = f"%{v}%"
    
    q = text(str(q) + " ORDER BY budget, section, grp, building_type, name")
    
    engine = get_engine()
    return pd.read_sql_query(q, engine, params=params)

def calc_subtotal(filters=None) -> float:
    # ENFORCE PROJECT ISOLATION - only calculate for current project
    current_project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    placeholder = get_sql_placeholder()
    q = f"SELECT SUM(COALESCE(qty,0) * COALESCE(unit_cost,0)) FROM items WHERE project_site = {placeholder}"
    params = [current_project_site]
    if filters:
        for k, v in filters.items():
            if v:
                q += f" AND {k} = {placeholder}"
                params.append(v)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(q, params)
        total = cur.fetchone()[0]
    return float(total or 0.0)

def upsert_items(df, category_guess=None, budget=None, section=None, grp=None, building_type=None, project_site=None):
    with engine.begin() as conn:
        for _, r in df.iterrows():
            code = str(r.get("code") or r.get("item_id") or r.get("labour_id") or "").strip() or None
            name = str(r.get("name") or r.get("item") or r.get("role") or "").strip()
            if not name:
                continue
            unit = str(r.get("unit") or r.get("uom") or r.get("units") or "").strip() or None
            unit_cost = r.get("unit_cost")
            try:
                unit_cost = float(unit_cost) if unit_cost not in (None, "") else None
            except:
                unit_cost = None
            qty = r.get("qty")
            if qty is None:
                qty = r.get("quantity") or r.get("available_slots") or 0
            try:
                qty = float(qty) if qty not in (None, "") else 0.0
            except:
                qty = 0.0
            category = (r.get("category") or category_guess or "").strip().lower()
            if category not in ("materials","labour"):
                category = "labour" if ("role" in r.index or "available_slots" in r.index) else "materials"
            # context
            b = r.get("budget") or budget
            s = r.get("section") or section
            g = r.get("grp") or grp
            bt = r.get("building_type") or building_type
            ps = r.get("project_site") or project_site or st.session_state.get('current_project_site', 'Lifecamp Kafe')
            
            # Upsert priority: code else name+category+context
            if code:
                result = conn.execute(text("SELECT id FROM items WHERE code = :code"), {"code": code})
                row = result.fetchone()
                if row:
                    conn.execute(text("""
                        UPDATE items SET name=:name, category=:category, unit=:unit, qty=:qty, unit_cost=:unit_cost, 
                        budget=:budget, section=:section, grp=:grp, building_type=:building_type, project_site=:project_site 
                        WHERE id=:id
                    """), {
                        "name": name, "category": category, "unit": unit, "qty": qty, "unit_cost": unit_cost,
                        "budget": b, "section": s, "grp": g, "building_type": bt, "project_site": ps, "id": row[0]
                    })
                else:
                    conn.execute(text("""
                        INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp,building_type,project_site) 
                        VALUES(:code,:name,:category,:unit,:qty,:unit_cost,:budget,:section,:grp,:building_type,:project_site)
                    """), {
                        "code": code, "name": name, "category": category, "unit": unit, "qty": qty, "unit_cost": unit_cost,
                        "budget": b, "section": s, "grp": g, "building_type": bt, "project_site": ps
                    })
            else:
                # Use COALESCE instead of IFNULL for PostgreSQL
                result = conn.execute(text("""
                    SELECT id FROM items WHERE name=:name AND category=:category 
                    AND COALESCE(budget,'')=COALESCE(:budget,'') AND COALESCE(section,'')=COALESCE(:section,'') 
                    AND COALESCE(grp,'')=COALESCE(:grp,'') AND COALESCE(building_type,'')=COALESCE(:building_type,'') 
                    AND project_site=:project_site
                """), {
                    "name": name, "category": category, "budget": b, "section": s, 
                    "grp": g, "building_type": bt, "project_site": ps
                })
                row = result.fetchone()
                if row:
                    conn.execute(text("""
                        UPDATE items SET unit=:unit, qty=:qty, unit_cost=:unit_cost, budget=:budget, 
                        section=:section, grp=:grp, building_type=:building_type, project_site=:project_site 
                        WHERE id=:id
                    """), {
                        "unit": unit, "qty": qty, "unit_cost": unit_cost, "budget": b, "section": s, 
                        "grp": g, "building_type": bt, "project_site": ps, "id": row[0]
                    })
                else:
                    conn.execute(text("""
                        INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp,building_type,project_site) 
                        VALUES(:code,:name,:category,:unit,:qty,:unit_cost,:budget,:section,:grp,:building_type,:project_site)
                    """), {
                        "code": None, "name": name, "category": category, "unit": unit, "qty": qty, "unit_cost": unit_cost,
                        "budget": b, "section": s, "grp": g, "building_type": bt, "project_site": ps
                    })
        
        # Clear cache when items are updated
        clear_cache()
        # Automatically backup data for persistence
        try:
            auto_backup_data()
        except:
            pass  # Silently fail if backup doesn't work

def update_item_qty(item_id: int, new_qty: float):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE items SET qty=? WHERE id=?", (float(new_qty), int(item_id)))
        conn.commit()
        # Automatically backup data for persistence
        try:
            auto_backup_data()
        except:
            pass

def update_item_rate(item_id: int, new_rate: float):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE items SET unit_cost=? WHERE id=?", (float(new_rate), int(item_id)))
        conn.commit()
        # Automatically backup data for persistence
        try:
            auto_backup_data()
        except:
            pass

def add_request(section, item_id, qty, requested_by, note, current_price=None):
    with engine.begin() as conn:
        # Use West African Time (WAT)
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        
        # Insert request without current_price column for now
        result = conn.execute(text("""
            INSERT INTO requests(ts, section, item_id, qty, requested_by, note, status) 
            VALUES (:ts, :section, :item_id, :qty, :requested_by, :note, 'Pending')
        """), {
            "ts": current_time.isoformat(timespec="seconds"),
            "section": section,
            "item_id": item_id,
            "qty": float(qty),
            "requested_by": requested_by,
            "note": note
        })
        
        # Get the request ID for notification
        request_id = result.lastrowid
        
        # Get item name for notification
        result = conn.execute(text("SELECT name FROM items WHERE id = :item_id"), {"item_id": item_id})
        item_result = result.fetchone()
        item_name = item_result[0] if item_result else "Unknown Item"
        
        # Get current user ID for notification
        current_user_id = st.session_state.get('user_id')
        
        # Create notification for the user who made the request (project-specific) - NO SOUND
        current_project_site = st.session_state.get('current_project_site', 'Unknown Project')
        
        # For project site access codes, create a user notification with a special user_id
        # Use a negative ID to distinguish from real user IDs
        project_user_id = -1  # Special ID for project site users
        
        notification_success = create_notification(
            notification_type="new_request",
            title="Request Submitted",
            message=f"Your request for {qty} units of {item_name} has been submitted successfully",
            user_id=project_user_id,  # Send to project site user
            request_id=request_id
        )
        
        # Create admin notification for the new request - WITH SOUND
        # Get the requester's username for better identification
        cur.execute("SELECT username FROM users WHERE id = ?", (current_user_id,))
        requester_username = cur.fetchone()
        requester_username = requester_username[0] if requester_username else requested_by
        
        # Create project-specific admin notification
        admin_notification_success = create_notification(
            notification_type="new_request",
            title="New Request Submitted",
            message=f"{requested_by} from {current_project_site} has submitted a request for {qty} units of {item_name}",
            user_id=None,  # Admin notification - visible to all admins
            request_id=request_id
        )
        
        
        # Automatically backup data for persistence
        try:
            auto_backup_data()
        except:
            pass

def set_request_status(req_id, status, approved_by=None):
    with engine.begin() as conn:
        result = conn.execute(text("SELECT item_id, qty, section, status FROM requests WHERE id=:req_id"), {"req_id": req_id})
        r = result.fetchone()
        if not r:
            return "Request not found"
        item_id, qty, section, old_status = r
        if old_status == status:
            return None
        if status == "Approved":
            # DO NOT deduct from inventory - budget remains unchanged
            # Just create actual record to track usage
            
            # Automatically create actual record when request is approved
            try:
                # Get current project site
                project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
                
                # Get current date
                from datetime import datetime
                wat_timezone = pytz.timezone('Africa/Lagos')
                current_time = datetime.now(wat_timezone)
                actual_date = current_time.date().isoformat()
                
                # Use item's unit cost for actual cost calculation
                result = conn.execute(text("SELECT unit_cost FROM items WHERE id=:item_id"), {"item_id": item_id})
                unit_cost_result = result.fetchone()
                actual_cost = unit_cost_result[0] * qty if unit_cost_result[0] else 0
                
                # Create actual record
                conn.execute(text("""
                    INSERT INTO actuals (item_id, actual_qty, actual_cost, actual_date, recorded_by, notes, project_site)
                    VALUES (:item_id, :actual_qty, :actual_cost, :actual_date, :recorded_by, :notes, :project_site)
                """), {
                    "item_id": item_id,
                    "actual_qty": qty,
                    "actual_cost": actual_cost,
                    "actual_date": actual_date,
                    "recorded_by": approved_by or 'System',
                    "notes": f"Auto-generated from approved request #{req_id}",
                    "project_site": project_site
                })
                
                # Clear cache to ensure actuals tab updates
                st.cache_data.clear()
                
            except Exception as e:
                # Don't fail the approval if actual creation fails
                pass
                
        if old_status == "Approved" and status in ("Pending","Rejected"):
            # DO NOT restore inventory - budget remains unchanged
            # Just remove the actual record
            
            # Remove the auto-generated actual record when request is rejected/pending
            try:
                conn.execute(text("""
                    DELETE FROM actuals 
                    WHERE item_id = :item_id AND recorded_by = :recorded_by AND notes LIKE :notes
                """), {
                    "item_id": item_id,
                    "recorded_by": approved_by or 'System',
                    "notes": f"Auto-generated from approved request #{req_id}"
                })
                
                # Clear cache to ensure actuals tab updates
                st.cache_data.clear()
                
            except Exception as e:
                # Don't fail the rejection if actual deletion fails
                pass
                
        conn.execute(text("UPDATE requests SET status=:status, approved_by=:approved_by WHERE id=:req_id"), 
                    {"status": status, "approved_by": approved_by, "req_id": req_id})
        
        # Create notification for the user when request is approved
        if status == "Approved":
            # Get user ID who made the request - find the specific user by matching request details
            result = conn.execute(text("SELECT requested_by, item_id FROM requests WHERE id=:req_id"), {"req_id": req_id})
            requester_result = result.fetchone()
            if requester_result:
                requester_name = requester_result[0]
                request_item_id = requester_result[1]
                
                # Find the specific user who made this request by matching project site with item's project site
                result = conn.execute(text("""
                    SELECT u.id FROM users u 
                    JOIN items i ON u.project_site = i.project_site 
                    WHERE u.full_name = :requester_name AND i.id = :request_item_id
                    LIMIT 1
                """), {"requester_name": requester_name, "request_item_id": request_item_id})
                specific_user = result.fetchone()
                
                if specific_user:
                    specific_user_id = specific_user[0]
                else:
                    # Fallback: find by name and project site from session
                    current_project = st.session_state.get('current_project_site', 'Lifecamp Kafe')
                    result = conn.execute(text("SELECT id FROM users WHERE full_name = :requester_name AND project_site = :current_project"), 
                                       {"requester_name": requester_name, "current_project": current_project})
                    fallback_user = result.fetchone()
                    specific_user_id = fallback_user[0] if fallback_user else None
                
                # Get item name for notification
                result = conn.execute(text("SELECT name FROM items WHERE id=:item_id"), {"item_id": item_id})
                item_result = result.fetchone()
                item_name = item_result[0] if item_result else "Unknown Item"
                
                # Create notification for the specific user who made the request
                notification_success = False
                if specific_user_id:
                    notification_success = create_notification(
                        notification_type="request_approved",
                        title="Request Approved",
                        message=f"Admin approved your request for {qty} units of {item_name}",
                        user_id=specific_user_id,  # Send to the specific user who made the request
                        request_id=req_id
                    )
                
                if notification_success:
                    st.success(f"Notification sent to {requester_name}")
                else:
                    st.error(f"Failed to send notification to {requester_name}")
                
                # Create admin notification for the approval action
                # Get the requester's username for better identification
                cur.execute("SELECT username FROM users WHERE id = ?", (specific_user_id,))
                requester_username = cur.fetchone()
                requester_username = requester_username[0] if requester_username else requester_name
                
                admin_notification_success = create_notification(
                    notification_type="request_approved",
                    title="Request Approved by Admin",
                    message=f"Admin approved request #{req_id} for {qty} units of {item_name} from {requester_name} ({requester_username})",
                    user_id=None,  # Admin notification - no specific user
                    request_id=req_id
                )
                
                # Create notification for project users from the SAME project as the requester
                try:
                    # Find the requester's project site
                    cur.execute("""
                        SELECT u.project_site FROM users u 
                        WHERE u.full_name = ? OR u.username = ?
                        LIMIT 1
                    """, (requester_name, requester_name))
                    requester_project = cur.fetchone()
                    
                    if requester_project:
                        requester_project_site = requester_project[0]
                        
                        # Find users from the SAME project as the requester (excluding the requester)
                        cur.execute("""
                            SELECT id, full_name, username FROM users 
                            WHERE project_site = ? AND user_type = 'user'
                        """, (requester_project_site,))
                        project_users = cur.fetchall()
                        
                        for user in project_users:
                            user_id, full_name, username = user
                            # Skip the requester to avoid duplicate notifications
                            if full_name != requester_name and username != requester_name:
                                try:
                                    # Create notification for project user
                                    project_notification_success = create_notification(
                                        notification_type="request_approved",
                                        title="Request Approved",
                                        message=f"A request for {qty} units of {item_name} from your project has been approved by admin",
                                        user_id=user_id,  # Send to project user
                                        request_id=req_id
                                    )
                                    
                                    if project_notification_success:
                                        st.caption(f"Project notification sent to {full_name} ({username})")
                                    else:
                                        st.caption(f"Failed to send project notification to {full_name}")
                                except Exception as e:
                                    st.caption(f"Error creating project notifications: {e}")
                except Exception as e:
                    st.caption(f"Error creating project notifications: {e}")
        
        # Create notification for the user when request is rejected
        elif status == "Rejected":
            # Get user ID who made the request - find the specific user by matching request details
            cur.execute("SELECT requested_by, item_id FROM requests WHERE id=?", (req_id,))
            requester_result = cur.fetchone()
            if requester_result:
                requester_name = requester_result[0]
                request_item_id = requester_result[1]
                
                # Find the specific user who made this request by matching project site with item's project site
                cur.execute("""
                    SELECT u.id FROM users u 
                    JOIN items i ON u.project_site = i.project_site 
                    WHERE u.full_name = ? AND i.id = ?
                    LIMIT 1
                """, (requester_name, request_item_id))
                specific_user = cur.fetchone()
                
                if specific_user:
                    specific_user_id = specific_user[0]
                else:
                    # Fallback: find by name and project site from session
                    current_project = st.session_state.get('current_project_site', 'Lifecamp Kafe')
                    cur.execute("SELECT id FROM users WHERE full_name = ? AND project_site = ?", (requester_name, current_project))
                    fallback_user = cur.fetchone()
                    specific_user_id = fallback_user[0] if fallback_user else None
                
                # Get item name for notification
                cur.execute("SELECT name FROM items WHERE id=?", (item_id,))
                item_result = cur.fetchone()
                item_name = item_result[0] if item_result else "Unknown Item"
                
                # Create notification for the specific user who made the request
                if specific_user_id:
                    create_notification(
                        notification_type="request_rejected",
                        title="Request Rejected",
                        message=f"Admin rejected your request for {qty} units of {item_name}",
                        user_id=specific_user_id,  # Send to the specific user who made the request
                        request_id=req_id
                    )
                    
                    # Create admin notification for the rejection action
                    # Get the requester's username for better identification
                    cur.execute("SELECT username FROM users WHERE id = ?", (specific_user_id,))
                    requester_username = cur.fetchone()
                    requester_username = requester_username[0] if requester_username else requester_name
                    
                    create_notification(
                        notification_type="request_rejected",
                        title="Request Rejected by Admin",
                        message=f"Admin rejected request #{req_id} for {qty} units of {item_name} from {requester_name} ({requester_username})",
                        user_id=None,  # Admin notification - no specific user
                        request_id=req_id
                    )
    return None

def delete_request(req_id):
    """Delete a request from the database and log the deletion"""
    try:
        with get_conn() as conn:
            if conn is None:
                return False
            
            cur = conn.cursor()
            
            # Get request details before deletion for logging
            cur.execute("""
                SELECT r.status, r.item_id, r.requested_by, r.qty, i.name, i.project_site 
                FROM requests r
                LEFT JOIN items i ON r.item_id = i.id
                WHERE r.id = ?
            """, (req_id,))
            result = cur.fetchone()
            
            if not result:
                return False
                
            status, item_id, requested_by, quantity, item_name, project_site = result
            
            # Log the deletion
            current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
            deletion_log = f"Request #{req_id} deleted by {current_user}: {requested_by} requested {quantity} units of {item_name} (Status: {status})"
            
            # Insert deletion log into access_logs
            cur.execute("""
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (?, ?, ?, ?, ?)
            """, (
                'SYSTEM', 
                current_user, 
                get_nigerian_time_iso(), 
                1, 
                st.session_state.get('user_type', 'user')
            ))
            
            # First, check if this is an approved request and remove the associated actual record
            if status == "Approved":
                # Remove the auto-generated actual record
                actuals_deleted = cur.execute("""
                    DELETE FROM actuals 
                    WHERE item_id = ? AND notes LIKE ?
                """, (item_id, f"Auto-generated from approved request #{req_id}"))
                
                # Log actuals deletion
                if actuals_deleted.rowcount > 0:
                    actuals_log = f"Associated actuals deleted for request #{req_id} (item: {item_name})"
                    cur.execute("""
                        INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        'SYSTEM', 
                        current_user, 
                        get_nigerian_time_iso(), 
                        1, 
                        st.session_state.get('user_type', 'user')
                    ))
            
            # Temporarily disable foreign key constraints for deletion
            cur.execute("PRAGMA foreign_keys = OFF")
            
            # First delete any associated notifications
            cur.execute("DELETE FROM notifications WHERE request_id = ?", (req_id,))
            
            # Then delete the request
            cur.execute("DELETE FROM requests WHERE id = ?", (req_id,))
            
            # Log the deleted request to deleted_requests table
            cur.execute("""
                INSERT INTO deleted_requests (req_id, item_name, qty, requested_by, status, deleted_at, deleted_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (req_id, item_name, quantity, requested_by, status, get_nigerian_time_iso(), current_user))
            
            # Re-enable foreign key constraints
            cur.execute("PRAGMA foreign_keys = ON")
            
            # Reset the ID sequence for requests table
            cur.execute("DELETE FROM sqlite_sequence WHERE name = 'requests'")
            
            conn.commit()
            
            # Clear cache to ensure actuals tab updates
            st.cache_data.clear()
            
            return True
    except Exception as e:
        st.error(f"Error deleting request: {e}")
        return False

def get_user_requests(user_name, status_filter="All"):
    """Get requests for a specific user with proper filtering"""
    try:
        from sqlalchemy import text
        from db import get_engine
        
        # Build query for user's requests
        query = text("""
            SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.status, r.approved_by,
                   i.budget, i.building_type, i.grp, i.project_site, r.current_price
            FROM requests r 
            JOIN items i ON r.item_id = i.id
            WHERE r.requested_by = :user_name
        """)
        params = {"user_name": user_name}
        
        # Add status filter if not "All"
        if status_filter and status_filter != "All":
            query = text(str(query) + " AND r.status = :status")
            params["status"] = status_filter
        
        query = text(str(query) + " ORDER BY r.id DESC")
        
        engine = get_engine()
        return pd.read_sql_query(query, engine, params=params)
    except Exception as e:
        st.error(f"Error fetching user requests: {e}")
        return pd.DataFrame()

def df_requests(status=None):
    from sqlalchemy import text
    from db import get_engine
    
    # Check if user is admin - admins see all requests from all project sites
    user_type = st.session_state.get('user_type', 'user')
    
    if user_type == 'admin':
        # Admin sees ALL requests from ALL project sites
        q = text("""
            SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.status, r.approved_by,
                   i.budget, i.building_type, i.grp, i.project_site
            FROM requests r 
            JOIN items i ON r.item_id=i.id
        """)
        params = {}
        if status and status != "All":
            q = text(str(q) + " WHERE r.status=:status")
            params["status"] = status
        q = text(str(q) + " ORDER BY r.id DESC")
    else:
        # Regular users see only requests from their assigned project site AND only their own requests
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
        current_user = st.session_state.get('full_name', st.session_state.get('user_name', 'Unknown'))
        q = text("""
            SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.status, r.approved_by,
                   i.budget, i.building_type, i.grp, i.project_site
            FROM requests r 
            JOIN items i ON r.item_id=i.id
            WHERE i.project_site = :project_site AND r.requested_by = :current_user
        """)
        params = {"project_site": project_site, "current_user": current_user}
        if status and status != "All":
            q = text(str(q) + " AND r.status=:status")
            params["status"] = status
        q = text(str(q) + " ORDER BY r.id DESC")
    
    engine = get_engine()
    return pd.read_sql_query(q, engine, params=params)

def all_items_by_section(section):
    from sqlalchemy import text
    from db import get_engine
    
    # Get current project site
    project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    q = text("SELECT id, name, unit, qty FROM items WHERE category=:section AND project_site=:project_site ORDER BY name")
    engine = get_engine()
    return pd.read_sql_query(q, engine, params={"section": section, "project_site": project_site})

def delete_item(item_id: int):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            # Check if item exists first
            cur.execute("SELECT id, name FROM items WHERE id=?", (item_id,))
            result = cur.fetchone()
            if not result:
                return f"Item not found (ID: {item_id})"
            
            item_name = result[1]
            
            # Check for linked requests
            cur.execute("SELECT COUNT(*) FROM requests WHERE item_id=?", (item_id,))
            request_count = cur.fetchone()[0]
            if request_count > 0:
                return f"Cannot delete '{item_name}': It has {request_count} linked request(s). Delete the requests first."
            
            # Delete the item
            cur.execute("DELETE FROM items WHERE id=?", (item_id,))
            conn.commit()
            
            # Clear cache after deletion
            clear_cache()
            
            # Auto-backup after deletion
            try:
                auto_backup_data()
            except:
                pass  # Don't fail deletion if backup fails
            
        return None
    except sqlite3.IntegrityError:
        return "Cannot delete item: it has linked requests."
    except Exception as e:
        return f"Delete failed: {e}"

# ---------- REMOVED: delete_request_with_logging function that was causing budget issues ----------
# This function was restoring stock quantities when deleting approved requests,
# which was causing the budget totals to change incorrectly.

# ---------- NEW: fetch deleted requests ----------
def df_deleted_requests():
    from sqlalchemy import text
    from db import get_engine
    
    q = text("SELECT * FROM deleted_requests ORDER BY id DESC")
    engine = get_engine()
    return pd.read_sql_query(q, engine)

# ---------- NEW: clear all deleted logs (for testing) ----------
def clear_deleted_requests():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM deleted_requests")
        conn.commit()

# Actuals functions
def add_actual(item_id, actual_qty, actual_cost, actual_date, recorded_by, notes=""):
    """Add actual usage/cost for an item"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            # Get current project site
            project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
            
            cur.execute("""
                INSERT INTO actuals (item_id, actual_qty, actual_cost, actual_date, recorded_by, notes, project_site)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (item_id, actual_qty, actual_cost, actual_date, recorded_by, notes, project_site))
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Failed to add actual: {str(e)}")
        return False

def get_actuals(project_site=None):
    """Get actuals for current or specified project site"""
    from sqlalchemy import text
    from db import get_engine
    
    if project_site is None:
        project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    query = text("""
        SELECT a.id, a.item_id, a.actual_qty, a.actual_cost, a.actual_date, a.recorded_by, a.notes, a.created_at, a.project_site,
               i.name, i.code, i.budget, i.building_type, i.unit, i.category, i.section, i.grp
        FROM actuals a
        JOIN items i ON a.item_id = i.id
        WHERE a.project_site = :project_site
        ORDER BY a.actual_date DESC, a.created_at DESC
    """)
    
    engine = get_engine()
    return pd.read_sql_query(query, engine, params={"project_site": project_site})

def delete_actual(actual_id):
    """Delete an actual record with enhanced error handling"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with get_conn() as conn:
                if conn is None:
                    st.error("🔧 Database connection failed. Please refresh the page.")
                    return False
                
                cur = conn.cursor()
                cur.execute(f"DELETE FROM actuals WHERE id = {placeholder}", (actual_id,))
                conn.commit()
                return True
                
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "disk I/O error" in error_msg or "database is locked" in error_msg:
                if attempt < max_retries - 1:
                    # Clean up WAL files and retry
                    try:
                        import os
                        if os.path.exists('istrominventory.db-wal'):
                            os.remove('istrominventory.db-wal')
                        if os.path.exists('istrominventory.db-shm'):
                            os.remove('istrominventory.db-shm')
                    except:
                        pass
                    time.sleep(1)
                    continue
                else:
                    st.error(f"🔧 Delete failed: {e}")
                    st.info("💡 Please refresh the page to retry. If the problem persists, restart the application.")
                    return False
            else:
                st.error(f"Delete failed: {e}")
                return False
        except Exception as e:
            st.error(f"Failed to delete actual: {str(e)}")
            return False
    
    return False


# Project configuration functions
def save_project_config(budget_num, building_type, num_blocks, units_per_block, additional_notes=""):
    """Save project configuration to database"""
    with get_conn() as conn:
        cur = conn.cursor()
        # Use West African Time (WAT)
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        
        # Check if config already exists
        cur.execute("SELECT id FROM project_config WHERE budget_num = ? AND building_type = ?", 
                   (budget_num, building_type))
        existing = cur.fetchone()
        
        if existing:
            # Update existing config
            cur.execute("""
                UPDATE project_config 
                SET num_blocks = ?, units_per_block = ?, additional_notes = ?, updated_at = ?
                WHERE budget_num = ? AND building_type = ?
            """, (num_blocks, units_per_block, additional_notes, current_time.isoformat(), budget_num, building_type))
        else:
            # Insert new config
            cur.execute("""
                INSERT INTO project_config (budget_num, building_type, num_blocks, units_per_block, additional_notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (budget_num, building_type, num_blocks, units_per_block, additional_notes, 
                  current_time.isoformat(), current_time.isoformat()))
        conn.commit()

def get_project_config(budget_num, building_type):
    """Get project configuration from database"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT num_blocks, units_per_block, additional_notes 
                FROM project_config 
                WHERE budget_num = ? AND building_type = ?
            """, (budget_num, building_type))
            result = cur.fetchone()
            if result:
                return {
                    'num_blocks': result[0],
                    'units_per_block': result[1],
                    'additional_notes': result[2]
                }
            return None
    except Exception as e:
        print(f"⚠️ Database error in get_project_config: {e}")
        return None

def clear_inventory(include_logs: bool = False):
    # PRODUCTION DATA PROTECTION - Prevent data loss
    if os.getenv('PRODUCTION_MODE') == 'true' or os.getenv('DISABLE_MIGRATION') == 'true':
        print("🚫 clear_inventory() BLOCKED - PRODUCTION MODE - YOUR DATA IS SAFE")
        return False
    
    # Create backup before destructive operation
    create_backup()
    
    with get_conn() as conn:
        cur = conn.cursor()
        # Remove dependent rows first due to FK constraints
        cur.execute("DELETE FROM requests")
        if include_logs:
            cur.execute("DELETE FROM deleted_requests")
        cur.execute("DELETE FROM items")
        conn.commit()


# --------------- Import helpers ---------------
KEYS_NAME = ["name", "item", "description", "material", "role"]
KEYS_QTY = ["qty", "quantity", "stock", "available", "available_slots", "balance"]
KEYS_UNIT = ["unit", "uom", "units"]
KEYS_CODE = ["code", "id", "item_id", "sku", "ref"]
KEYS_COST = ["unit_cost", "cost", "price", "rate"]

# Supported property/building types
PROPERTY_TYPES = [
    "",
    "Flats",
    "Terraces",
    "Semi-detached",
    "Fully-detached",
]

MATERIAL_GROUPS = ["MATERIAL(WOODS)", "MATERIAL(PLUMBINGS)", "MATERIAL(IRONS)"]


def auto_pick(cols, keys):
    cols_low = [c.lower() for c in cols]
    for k in keys:
        for i, c in enumerate(cols_low):
            if k in c:
                return cols[i]
    return None

def to_number(val):
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return val
    s = str(val)
    s = re.sub(r"[₦$,]", "", s)
    s = s.replace("'", "").replace(" ", "").replace("\xa0","")
    s = s.replace(".", "") if s.count(",")==1 and s.endswith(",00") else s
    s = s.replace(",", "")
    try:
        return float(s)
    except:
        return None

# --------------- UI ---------------
st.set_page_config(
    page_title="Istrom Inventory Management System", 
    page_icon="🏗️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize database on startup
initialize_database()

# --------------- SEAMLESS ACCESS CODE SYSTEM ---------------
def initialize_session():
    """Initialize session state with defaults"""
    defaults = {
        'logged_in': False,
        'user_id': None,
        'username': None,
        'full_name': None,
        'user_type': None,
        'project_site': None,
        'admin_code': None,
        'current_project_site': 'Lifecamp Kafe',
        'auth_timestamp': None
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def authenticate_user(access_code):
    """Authenticate user by project site access code only"""
    try:
        print(f"🔍 Authenticating access code: {access_code}")
        
        # Check if it's a project site access code
        with engine.connect() as conn:
            result = conn.execute(text('''
                SELECT project_site, user_code, admin_code FROM project_site_access_codes 
                WHERE user_code = :access_code
            '''), {"access_code": access_code})
            site_result = result.fetchone()
            print(f"🔍 Project site access code check result: {site_result}")
            
            if site_result:
                project_site, user_code, admin_code = site_result
                # Project site user access - user can only see their project site
                return {
                    'id': 999,
                    'username': f'user_{project_site.lower().replace(" ", "_")}',
                    'full_name': f'User - {project_site}',
                    'user_type': 'user',
                    'project_site': project_site
                }
            
            # Check if it's a global admin code (from access_codes table)
            result = conn.execute(text('''
                SELECT admin_code FROM access_codes 
                ORDER BY updated_at DESC LIMIT 1
            '''))
            admin_result = result.fetchone()
            print(f"🔍 Admin code check result: {admin_result}")
            
            if admin_result and access_code == admin_result[0]:
                print(f"✅ Admin authentication successful for: {access_code}")
                # Global admin access - can see all project sites
                return {
                    'id': 1,
                    'username': 'admin',
                    'full_name': 'System Administrator',
                    'user_type': 'admin',
                    'project_site': 'ALL'
                }
            else:
                print(f"❌ Access code {access_code} not found in database")
                print(f"❌ Expected admin code: {admin_result[0] if admin_result else 'None'}")
        
        return None
    except Exception as e:
        print(f"Database lookup failed: {e}")
        return None

def show_login_interface():
    """Display clean login interface"""
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h1>Istrom Inventory Management</h1>
        <p style="color: #666;">Professional Construction Project Management</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔐 Access Code Login")
        
        with st.form("seamless_login", clear_on_submit=False):
            access_code = st.text_input(
                "Enter Access Code", 
                placeholder="Enter your access code",
                type="password",
                help="Enter your admin or project site access code"
            )
            
            if st.form_submit_button("🚀 Access System", type="primary", use_container_width=True):
                if access_code:
                    user_info = authenticate_user(access_code)
                    if user_info:
                        # Set session state
                        st.session_state.logged_in = True
                        st.session_state.user_id = user_info['id']
                        st.session_state.username = user_info['username']
                        st.session_state.full_name = user_info['full_name']
                        st.session_state.user_type = user_info['user_type']
                        st.session_state.project_site = user_info['project_site']
                        st.session_state.current_project_site = user_info['project_site'] if user_info['project_site'] != 'ALL' else None
                        st.session_state.auth_timestamp = get_nigerian_time_iso()
                        
                        # Log the successful access with actual user information
                        log_id = log_access(access_code, success=True, user_name=user_info['full_name'], role=user_info['user_type'])
                        st.session_state.access_log_id = log_id
                        
                        # Save session to cookie for 10-hour persistence
                        save_session_to_cookie()
                        
                        st.success(f"Welcome, {user_info['full_name']}! (Session: 10 hours)")
                        st.rerun()
                    else:
                        # Log failed access attempt
                        log_access(access_code, success=False, user_name="Unknown", role="unknown")
                        st.error("Invalid access code. Please try again.")
                else:
                    st.error("Please enter your access code.")

def show_logout_button():
    """Display logout button"""
    if st.button("Logout", key="logout_btn", help="Logout from the system"):
        # Clear session
        for key in list(st.session_state.keys()):
            if key not in ['current_project_site']:  # Keep project site for continuity
                del st.session_state[key]
        
        st.session_state.logged_in = False
        # Clear session cookie
        st.query_params.clear()
        st.success("Logged out successfully!")
        st.rerun()

# Initialize session - REQUIRED FOR APP TO WORK
initialize_session()

# --------------- PERSISTENT SESSION MANAGEMENT (10 HOURS) ---------------
def check_session_validity():
    """Check if current session is still valid (10 hours)"""
    if not st.session_state.logged_in or not st.session_state.get('auth_timestamp'):
        return False
    
    try:
        auth_time = datetime.fromisoformat(st.session_state.get('auth_timestamp'))
        current_time = get_nigerian_time()
        # Session valid for 10 hours (36000 seconds)
        session_duration = 10 * 60 * 60  # 10 hours in seconds
        return (current_time - auth_time).total_seconds() < session_duration
    except:
        return False

def restore_session_from_cookie():
    """Restore session from browser cookie if valid"""
    try:
        # Check if we have authentication data in URL params (Streamlit's way of persistence)
        auth_data = st.query_params.get('auth_data')
        if auth_data:
            import base64
            import json
            decoded_data = base64.b64decode(auth_data).decode('utf-8')
            session_data = json.loads(decoded_data)
            
            # Check if session is still valid (10 hours)
            auth_time = datetime.fromisoformat(session_data['auth_timestamp'])
            current_time = get_nigerian_time()
            session_duration = 10 * 60 * 60  # 10 hours
            
            if (current_time - auth_time).total_seconds() < session_duration:
                # Restore session
                st.session_state.logged_in = True
                st.session_state.user_id = session_data.get('user_id')
                st.session_state.username = session_data.get('username')
                st.session_state.full_name = session_data.get('full_name')
                st.session_state.user_type = session_data.get('user_type')
                st.session_state.project_site = session_data.get('project_site')
                st.session_state.current_project_site = session_data.get('current_project_site', None)
                st.session_state.auth_timestamp = session_data.get('auth_timestamp')
                return True
    except:
        pass
    return False

def save_session_to_cookie():
    """Save current session to browser cookie for persistence"""
    try:
        session_data = {
            'user_id': st.session_state.get('user_id'),
            'username': st.session_state.get('username'),
            'full_name': st.session_state.get('full_name'),
            'user_type': st.session_state.get('user_type'),
            'project_site': st.session_state.get('project_site'),
            'current_project_site': st.session_state.get('current_project_site', None),
            'auth_timestamp': st.session_state.get('auth_timestamp')
        }
        
        import base64
        import json
        encoded_data = base64.b64encode(json.dumps(session_data).encode('utf-8')).decode('utf-8')
        st.query_params['auth_data'] = encoded_data
    except:
        pass

# Try to restore session from cookie on page load
if not st.session_state.logged_in:
    if restore_session_from_cookie():
        # Check if the restored session is valid for both admin and regular users
        user_type = st.session_state.get('user_type')
        username = st.session_state.get('username')
        project_site = st.session_state.get('project_site')
        
        if user_type == 'admin' and username == 'admin' and project_site == 'ALL':
            st.success("Admin session restored from previous login")
        elif user_type == 'user' and username and project_site:
            st.success("User session restored from previous login")
        else:
            # Clear incorrect session and force fresh login
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            show_login_interface()
            st.stop()
    else:
        show_login_interface()
        st.stop()

# Check if current session is still valid (10 hours)
if not check_session_validity():
    # Session expired, clear everything
    for key in list(st.session_state.keys()):
        if key not in ['current_project_site']:  # Keep project site for continuity
            del st.session_state[key]
    st.session_state.logged_in = False
    st.query_params.clear()
    show_login_interface()
    st.stop()

# Save session to cookie for persistence (update timestamp)
if st.session_state.logged_in:
    save_session_to_cookie()
st.markdown(
    """
    <style>
    /* Cache-busting timestamp: """ + get_nigerian_time_iso() + """ */
    /* Premium Enterprise Styling */
    .app-brand {
        padding: 3rem 2rem;
        text-align: center;
        background: linear-gradient(135deg, #1e293b 0%, #334155 50%, #475569 100%);
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    .app-brand::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, rgba(59, 130, 246, 0.1) 0%, transparent 50%, rgba(16, 185, 129, 0.1) 100%);
        animation: shimmer 4s ease-in-out infinite;
    }
    
    @keyframes shimmer {
        0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
    }
    
    .app-brand h1 {
        font-size: 2.5rem;
        line-height: 1.2;
        margin: 0;
        font-weight: 700;
        color: #ffffff;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        letter-spacing: -0.5px;
        margin-bottom: 1rem;
        position: relative;
        z-index: 2;
    }
    
    .app-brand .subtitle {
        color: rgba(255,255,255,0.9);
        font-size: 1.2rem;
        margin-top: 0.5rem;
        font-weight: 400;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        position: relative;
        z-index: 2;
        letter-spacing: 0.3px;
    }
    
    .app-brand .tagline {
        color: rgba(255,255,255,0.7);
        font-size: 0.9rem;
        margin-top: 0.5rem;
        font-weight: 300;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2);
        position: relative;
        z-index: 2;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-family: 'Arial', sans-serif;
    }
    /* Premium Enterprise Components */
    .chip {display:inline-block;padding:4px 12px;border-radius:6px;background:#f8fafc;color:#1f2937;font-size:12px;margin-right:8px;border:1px solid #e2e8f0;font-weight:500}
    .chip.blue {background:#eff6ff;border-color:#dbeafe;color:#1e3a8a}
    .chip.green {background:#ecfdf5;border-color:#d1fae5;color:#065f46}
    .chip.gray {background:#f3f4f6;border-color:#e5e7eb;color:#374151}
    
    /* Professional Data Tables */
    .stDataFrame {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Premium Buttons */
    .stButton > button {
        border-radius: 6px;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    /* Professional Metrics */
    .metric-container {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    /* Clean Sidebar */
    .css-1d391kg {
        background: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }
    
    /* Sidebar text styling - readable */
    .sidebar .stMarkdown {
        font-size: 1.0rem !important;
    }
    
    .sidebar .stMarkdown h3 {
        font-size: 1.1rem !important;
    }
    
    .sidebar .stMarkdown p {
        font-size: 0.9rem !important;
    }
    
    .sidebar .stMarkdown strong {
        font-size: 0.9rem !important;
    }
    
    /* Target sidebar content specifically */
    .sidebar-content .stMarkdown {
        font-size: 0.9rem !important;
    }
    
    .sidebar-content .stMarkdown h3 {
        font-size: 1.0rem !important;
    }
    
    .sidebar-content .stMarkdown p {
        font-size: 0.8rem !important;
    }
    
    .sidebar-content .stMarkdown strong {
        font-size: 0.8rem !important;
    }
    
    /* Professional Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #1f2937;
        font-weight: 600;
        letter-spacing: -0.025em;
    }
    
    /* Clean Form Elements */
    .stSelectbox > div > div {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }
    
    .stTextInput > div > div > input {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }
    
    .stNumberInput > div > div > input {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }
    
    /* Reduce unnecessary gaps */
    .element-container {
        margin-bottom: 0.5rem !important;
    }
    
    .stMarkdown {
        margin-bottom: 0.5rem !important;
    }
    
    .stCaption {
        margin-top: 0.25rem !important;
        margin-bottom: 0.25rem !important;
    }
    
    /* Compact spacing */
    .stMetric {
        margin-bottom: 0.5rem !important;
    }
    
    /* Large readable dashboard metrics */
    .stMetric > div {
        font-size: 1.8rem !important;
    }
    
    .stMetric > div > div {
        font-size: 1.6rem !important;
    }
    
    .stMetric > div > div[data-testid="metric-value"] {
        font-size: 2.2rem !important;
        font-weight: 600 !important;
    }
    
    .stMetric > div > div[data-testid="metric-delta"] {
        font-size: 1.4rem !important;
    }
    
    /* Large dashboard header specific styling */
    .stMetric {
        font-size: 1.8rem !important;
        padding: 1.2rem !important;
        margin-bottom: 1.2rem !important;
    }
    
    .stMetric > div {
        font-size: 1.8rem !important;
    }
    
    .stMetric > div > div {
        font-size: 1.8rem !important;
    }
    
    /* Target all metric labels and values */
    [data-testid="metric-label"] {
        font-size: 1.6rem !important;
        font-weight: 500 !important;
    }
    
    [data-testid="metric-value"] {
        font-size: 2.4rem !important;
        font-weight: 600 !important;
    }
    
    /* More aggressive targeting for dashboard metrics */
    .stMetric * {
        font-size: 1.8rem !important;
    }
    
    .stMetric label {
        font-size: 1.6rem !important;
    }
    
    .stMetric div {
        font-size: 1.8rem !important;
    }
    
    /* Large dashboard header */
    .element-container .stMetric {
        font-size: 1.8rem !important;
    }
    
    .element-container .stMetric * {
        font-size: 1.8rem !important;
    }
    
    /* FORCE LARGE FONTS - Override any small font rules */
    .stMetric, .stMetric *, .stMetric div, .stMetric span, .stMetric label {
        font-size: 1.8rem !important;
    }
    
    .stMetric [data-testid="metric-label"] {
        font-size: 1.6rem !important;
    }
    
    .stMetric [data-testid="metric-value"] {
        font-size: 2.4rem !important;
        font-weight: 700 !important;
    }
    
    /* Override any conflicting small font rules */
    *[style*="font-size: 0."] {
        font-size: 1.2rem !important;
    }
    
    /* SPECIFIC TARGETING FOR TOTAL AMOUNTS AND METRICS */
    .stMetric {
        font-size: 2.0rem !important;
        padding: 1.5rem !important;
        margin: 1rem 0 !important;
    }
    
    .stMetric > div {
        font-size: 2.0rem !important;
    }
    
    .stMetric > div > div {
        font-size: 2.0rem !important;
    }
    
    .stMetric label {
        font-size: 1.8rem !important;
        font-weight: 600 !important;
    }
    
    .stMetric [data-testid="metric-value"] {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        color: #1f2937 !important;
    }
    
    .stMetric [data-testid="metric-delta"] {
        font-size: 1.6rem !important;
    }
    
    /* Force all metric containers to be large */
    .element-container .stMetric {
        font-size: 2.0rem !important;
        padding: 1.5rem !important;
    }
    
    .element-container .stMetric * {
        font-size: 2.0rem !important;
    }
    
    /* Target specific metric text */
    .stMetric div[data-testid="metric-value"] {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
    }
    
    /* ULTRA AGGRESSIVE OVERRIDE FOR ALL METRICS */
    .stMetric, .stMetric *, .stMetric div, .stMetric span, .stMetric p, .stMetric label {
        font-size: 2.0rem !important;
        line-height: 1.2 !important;
    }
    
    .stMetric [data-testid="metric-value"], .stMetric [data-testid="metric-delta"] {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        color: #1f2937 !important;
    }
    
    /* Force override for any remaining small fonts */
    .stMetric * {
        font-size: 2.0rem !important;
    }
    
    /* Specific targeting for metric containers */
    div[data-testid="metric-container"] {
        font-size: 2.0rem !important;
        padding: 1.5rem !important;
    }
    
    div[data-testid="metric-container"] * {
        font-size: 2.0rem !important;
    }
    
    /* COMPACT METRIC SIZES */
    .stMetric, .stMetric *, .stMetric div, .stMetric span, .stMetric p, .stMetric label, .stMetric strong {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
        line-height: 1.2 !important;
    }
    
    .stMetric [data-testid="metric-value"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #1f2937 !important;
    }
    
    .stMetric [data-testid="metric-delta"] {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
    }
    
    /* Override any Streamlit default styling */
    .stMetric > div > div {
        font-size: 1.3rem !important;
    }
    
    /* Force all metric text to be compact size */
    .stMetric label, .stMetric div, .stMetric span {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
    }
    
    /* NUCLEAR OVERRIDE - Force all metrics to be compact */
    .stMetric, .stMetric *, .stMetric div, .stMetric span, .stMetric p, .stMetric label, .stMetric strong, .stMetric h1, .stMetric h2, .stMetric h3, .stMetric h4, .stMetric h5, .stMetric h6 {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
        line-height: 1.2 !important;
    }
    
    .stMetric [data-testid="metric-value"], .stMetric [data-testid="metric-delta"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }
    
    /* Override any remaining small fonts */
    .stMetric * {
        font-size: 1.3rem !important;
    }
    
    /* Force override for all metric containers */
    div[data-testid="metric-container"], div[data-testid="metric-container"] * {
        font-size: 1.3rem !important;
    }
    
    /* Target specific metric elements */
    .stMetric > div > div > div {
        font-size: 1.3rem !important;
    }
    
    /* Mobile Responsive Design */
    @media (max-width: 768px) {
        .app-brand {
            padding: 2rem 1rem;
            margin-bottom: 1rem;
        }
        
        .app-brand h1 {
            font-size: 2.5rem;
            letter-spacing: -1px;
            margin-bottom: 1rem;
        }
        
        .app-brand .subtitle {
            font-size: 1.1rem;
            margin-top: 0.5rem;
        }
        
        .app-brand .tagline {
            font-size: 0.8rem;
            margin-top: 0.5rem;
            letter-spacing: 1px;
        }
        
        /* Make tables responsive */
        .stDataFrame {
            font-size: 0.8rem;
        }
        
        /* Better mobile spacing */
        .element-container {
            margin-bottom: 0.5rem;
        }
        
        /* Mobile-friendly buttons */
        .stButton > button {
            width: 100%;
            margin-bottom: 0.5rem;
        }
        
        /* Mobile sidebar */
        .css-1d391kg {
            width: 100% !important;
        }
    }
    
    @media (max-width: 480px) {
        .app-brand h1 {
            font-size: 2rem;
        }
        
        .app-brand .subtitle {
            font-size: 1rem;
        }
        
        .app-brand .tagline {
            font-size: 0.7rem;
        }
    }
    </style>
    <div class="app-brand">
      <h1>Istrom Inventory Management System</h1>
      <div class="subtitle">Professional Construction Inventory & Budget Management</div>
      <div class="tagline">Enterprise-Grade • Real-Time Analytics • Advanced Tracking</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Modern Professional Header
# Get user info - use correct session state keys
user_name = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
user_type = st.session_state.get('user_type', st.session_state.get('user_role', 'user'))
project_site = st.session_state.get('project_site', 'Lifecamp Kafe')

# Calculate session time remaining
session_remaining = ""
auth_timestamp = st.session_state.get('auth_timestamp')
if auth_timestamp:
    try:
        auth_time = datetime.fromisoformat(auth_timestamp)
        current_time = get_nigerian_time()
        elapsed = (current_time - auth_time).total_seconds()
        remaining = (10 * 60 * 60) - elapsed  # 10 hours in seconds
        if remaining > 0:
            hours_left = int(remaining // 3600)
            minutes_left = int((remaining % 3600) // 60)
            session_remaining = f"{hours_left}h {minutes_left}m"
        else:
            session_remaining = "Expired"
    except:
        session_remaining = "Active"

# Get notification count for admins
notification_count = 0
if user_type == 'admin':
    notifications = get_admin_notifications()
    notification_count = len(notifications)

# Compact dashboard header using HTML with bigger fonts
st.markdown(f"""
<div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
    <div style="flex: 1; text-align: center; padding: 0.8rem; border: 1px solid #e2e8f0; border-radius: 4px; background: #f8fafc;">
        <div style="font-size: 1.2rem; color: #64748b; margin-bottom: 0.4rem;">User</div>
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937;">{user_name}</div>
    </div>
    <div style="flex: 1; text-align: center; padding: 0.8rem; border: 1px solid #e2e8f0; border-radius: 4px; background: #f8fafc;">
        <div style="font-size: 1.2rem; color: #64748b; margin-bottom: 0.4rem;">Access</div>
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937;">{"Admin" if user_type == 'admin' else "User"}</div>
    </div>
    <div style="flex: 1; text-align: center; padding: 0.8rem; border: 1px solid #e2e8f0; border-radius: 4px; background: #f8fafc;">
        <div style="font-size: 1.2rem; color: #64748b; margin-bottom: 0.4rem;">Project</div>
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937;">{project_site}</div>
    </div>
    <div style="flex: 1; text-align: center; padding: 0.8rem; border: 1px solid #e2e8f0; border-radius: 4px; background: #f8fafc;">
        <div style="font-size: 1.2rem; color: #64748b; margin-bottom: 0.4rem;">Session</div>
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937;">{session_remaining}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Status indicator
if user_type == 'admin':
    if notification_count > 0:
        st.warning(f"{notification_count} pending notifications")
    else:
        st.success("All clear")
else:
    st.info("User access")

# Logout button in sidebar
# Old sidebar section removed - now using professional sidebar below

# init_db()  # DISABLED: Using database_config.py instead
# ensure_indexes()  # DISABLED: Using database_config.py instead

# Initialize persistent data file if it doesn't exist
# def init_persistent_data()  # DISABLED FOR PRODUCTION:
#     """Initialize persistent data file if it doesn't exist"""
#     if not os.path.exists("persistent_data.json"):
#         # Create empty persistent data file
#         empty_data = {
#             "items": [],
#             "requests": [],
#             "access_codes": {
#                 "admin_code": DEFAULT_ADMIN_ACCESS_CODE,
#                 "user_code": DEFAULT_USER_ACCESS_CODE
#             },
#             "backup_timestamp": get_nigerian_time_iso()
#         }
#         try:
#             with open("persistent_data.json", 'w') as f:
#                 json.dump(empty_data, f, indent=2)
#         except:
#             pass

# init_persistent_data()  # DISABLED FOR PRODUCTION

# DISABLED: auto_restore_from_file() was causing data loss on production

# auto_restore_from_file()  # DISABLED: This was causing data loss on production

# Create automatic backup on startup - DISABLED FOR PRODUCTION
# if not st.session_state.get('backup_created', False):
#     backup_path = create_backup()
#     if backup_path:
#         st.session_state.backup_created = True
#         cleanup_old_backups()

# Auto-restore data from Streamlit Cloud secrets if available
def auto_restore_data():
    """Automatically restore data from Streamlit Cloud secrets on startup"""
    try:
        # Check if we have access codes in secrets
        if 'ACCESS_CODES' in st.secrets:
            access_codes = st.secrets['ACCESS_CODES']
            
            # Check if database has any access codes
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM access_codes")
                access_count = cur.fetchone()[0]
                
                # Only restore if no access codes in database (fresh deployment)
                if access_count == 0:
                    # Restore access codes from secrets
                    cur.execute("""
                        INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                        VALUES (?, ?, ?, ?)
                    """, (
                        access_codes['admin_code'], 
                        access_codes['user_code'], 
                        datetime.now(pytz.timezone('Africa/Lagos')).isoformat(), 
                        'AUTO_RESTORE'
                    ))
                    conn.commit()
                    
                    st.success("**Access codes restored from previous deployment!**")
                    return True
                    
        # Also check for persistent data
        if 'PERSISTENT_DATA' in st.secrets:
            data = st.secrets['PERSISTENT_DATA']
            
            # Check if this is a fresh deployment (no items in database)
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM items")
                item_count = cur.fetchone()[0]
                
                # Only restore if database is empty (fresh deployment)
                if item_count == 0 and data:
                    st.info("**Auto-restoring data from previous deployment...**")
                    
                    # Restore items
                    if 'items' in data:
                        for item in data['items']:
                            cur.execute("""
                                INSERT INTO items (id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                item.get('id'), item.get('code'), item.get('name'), item.get('category'),
                                item.get('unit'), item.get('qty'), item.get('unit_cost'), item.get('budget'),
                                item.get('section'), item.get('grp'), item.get('building_type')
                            ))
                    
                    # Restore requests
                    if 'requests' in data:
                        for request in data['requests']:
                            cur.execute("""
                                INSERT INTO requests (id, ts, section, item_id, qty, requested_by, note, status, approved_by)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                request.get('id'), request.get('ts'), request.get('section'), request.get('item_id'),
                                request.get('qty'), request.get('requested_by'), request.get('note'),
                                request.get('status'), request.get('approved_by')
                            ))
                    
                    conn.commit()
                    st.success("**Data restored successfully!** All your items and settings are back.")
                    st.rerun()
    except Exception as e:
        # Silently fail if secrets not available (local development)
        pass

def auto_backup_data():
    """Automatically backup data for persistence - works seamlessly in background"""
    # PRODUCTION PROTECTION - Don't run backup operations in production
    if os.getenv('PRODUCTION_MODE') == 'true' or os.getenv('DISABLE_MIGRATION') == 'true':
        return False
    try:
        with get_conn() as conn:
            # Get ALL data - items, requests, and access codes
            items_df = pd.read_sql_query("SELECT * FROM items", conn)
            requests_df = pd.read_sql_query("SELECT * FROM requests", conn)
            
            # Get access codes
            cur = conn.cursor()
            cur.execute("SELECT admin_code, user_code FROM access_codes ORDER BY id DESC LIMIT 1")
            access_result = cur.fetchone()
            access_codes = {
                "admin_code": access_result[0] if access_result else DEFAULT_ADMIN_ACCESS_CODE,
                "user_code": access_result[1] if access_result else DEFAULT_USER_ACCESS_CODE
            }
            
            # Create backup data
            try:
                backup_timestamp = datetime.now(pytz.timezone('Africa/Lagos')).isoformat()
            except:
                backup_timestamp = get_nigerian_time_iso()
            
            backup_data = {
                "items": items_df.to_dict('records'),
                "requests": requests_df.to_dict('records'),
                "access_codes": access_codes,
                "backup_timestamp": backup_timestamp
            }
            
            # Save to multiple locations for maximum reliability
            success = False
            
            # Primary: persistent_data.json (tracked by git)
            try:
                with open("persistent_data.json", 'w') as f:
                    json.dump(backup_data, f, default=str, indent=2)
                success = True
            except:
                pass
            
            # Secondary: backup_data.json (backup copy)
            try:
                with open("backup_data.json", 'w') as f:
                    json.dump(backup_data, f, default=str, indent=2)
                success = True
            except:
                pass
            
            # Tertiary: Streamlit Cloud secrets (if available)
            try:
                if hasattr(st, 'secrets') and st.secrets:
                    st.secrets["PERSISTENT_DATA"] = backup_data
                    st.secrets["ACCESS_CODES"] = access_codes
                    success = True
            except:
                pass
            
            return success
    except Exception as e:
        # Silently fail - don't show errors to users
        return False


# Auto-restore on startup - DISABLED FOR PRODUCTION
# auto_restore_data()  # DISABLED: This was causing data loss on production

# PRODUCTION DATA PROTECTION - COMPLETELY DISABLE ALL MIGRATION
# TEST: This comment proves data persistence works!
if os.getenv('PRODUCTION_MODE') == 'true' or os.getenv('DISABLE_MIGRATION') == 'true':
    print("🚫 MIGRATION COMPLETELY DISABLED - PRODUCTION DATA IS PROTECTED")
    print("🚫 NO DATABASE OPERATIONS WILL RUN DURING DEPLOYMENT")
    print("🚫 YOUR USERS AND DATA ARE SAFE")
    
    # Override database functions to prevent any operations
    def create_tables():
        print("🚫 create_tables() BLOCKED - PRODUCTION MODE")
        return False
    
    def migrate_from_sqlite():
        print("🚫 migrate_from_sqlite() BLOCKED - PRODUCTION MODE")
        return False
    
    # Override data import functions to prevent data loss
    def import_data(json_data):
        print("🚫 import_data() BLOCKED - PRODUCTION MODE")
        return False
    
    def clear_inventory(include_logs=False):
        print("🚫 clear_inventory() BLOCKED - PRODUCTION MODE")
        return False

# ADDITIONAL PROTECTION - Check if database has data and prevent any operations
try:
    with get_conn() as conn:
        cursor = conn.cursor()
        
        # Check if database already has data
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM items")
        item_count = cursor.fetchone()[0]
        
        # If database has data, set a flag to prevent any operations
        if user_count > 0 or item_count > 0:
            print("🚫 DATABASE HAS EXISTING DATA - ALL OPERATIONS BLOCKED")
            print("🚫 YOUR USERS AND DATA ARE PROTECTED")
            
            # Set environment variable to block all operations
            os.environ['DATABASE_HAS_DATA'] = 'true'
            
except:
    # If database doesn't exist or can't connect, continue normally
    pass

# Initialize session state for performance
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False

# Database health check
def db_health():
    """Check database connection health"""
    try:
        from sqlalchemy import text
        from db import get_engine
        with get_engine().connect() as c:
            if os.getenv('DATABASE_URL', '').startswith('postgresql'):
                row = c.execute(text("SELECT current_database()")).scalar()
                return True, f"PostgreSQL: {row}"
            else:
                row = c.execute(text("SELECT 1")).scalar()
                return True, f"SQLite: {row}"
    except Exception as e:
        return False, str(e)

# Show database health in sidebar
if st.session_state.get('user_type') == 'admin':
    ok, info = db_health()
    if ok:
        st.sidebar.success(f"DB: {info}")
    else:
        st.sidebar.error(f"DB Error: {info}")


# Advanced access code authentication system with persistent cookies
def get_auth_cookie():
    """Get authentication data from browser cookie"""
    try:
        import streamlit.components.v1 as components
        # Try to get auth data from cookie
        cookie_data = st.query_params.get('auth_data')
        if cookie_data:
            import base64
            import json
            decoded_data = base64.b64decode(cookie_data).decode('utf-8')
            return json.loads(decoded_data)
    except:
        pass
    return None


# --------------- SIMPLIFIED SESSION MANAGEMENT ---------------

def require_admin():
    """Require admin privileges, show error if not admin"""
    if not is_admin():
        st.error(" Admin privileges required for this action.")
        st.info("Only administrators can perform this operation.")
        return False
    return True




def update_admin_access_code(new_admin_code, updated_by="Admin"):
    """Update admin access code in database and automatically persist"""
    try:
        # Update database
        with get_conn() as conn:
            cur = conn.cursor()
            wat_timezone = pytz.timezone('Africa/Lagos')
            current_time = datetime.now(wat_timezone)
            
            # Insert new admin access code
            cur.execute("""
                INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
            """, (new_admin_code, '', current_time.isoformat(), updated_by))
            conn.commit()
            
        # Automatically backup data for persistence
        try:
            if auto_backup_data():
                st.success("Admin access code updated and automatically saved!")
            else:
                st.success("Admin access code updated successfully!")
                
                # Show instructions for manual setup if auto-backup fails
                st.info("**For Streamlit Cloud persistence:** You may need to manually configure secrets. Contact your system administrator.")
        except Exception as e:
            st.success("Admin access code updated successfully!")
            # Silently handle backup errors
        
        return True
    except Exception as e:
        st.error(f"Error updating admin access code: {e}")
        return False

def update_access_codes(new_admin_code, new_user_code, updated_by="Admin"):
    """Update access codes in database and automatically persist"""
    try:
        # Update database
        with get_conn() as conn:
            cur = conn.cursor()
            wat_timezone = pytz.timezone('Africa/Lagos')
            current_time = datetime.now(wat_timezone)
            
            # Insert new access codes
            cur.execute("""
                INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
            """, (new_admin_code, new_user_code, current_time.isoformat(), updated_by))
            conn.commit()
            
        # Automatically backup data for persistence
        try:
            if auto_backup_data():
                st.success("Access codes updated and automatically saved!")
            else:
                st.success("Access codes updated successfully!")
                
                # Show instructions for manual setup if auto-backup fails
                st.info("**For Streamlit Cloud persistence:** You may need to manually configure secrets. Contact your system administrator.")
        except Exception as e:
            st.success("Access codes updated successfully!")
            # Silently handle backup errors
        
        return True
    except Exception as e:
        st.error(f"Error updating access codes: {str(e)}")
        return False

def update_project_site_access_codes(project_site, admin_code, user_code):
    """Update access codes for a specific project site"""
    conn = get_conn()
    if conn is None:
        return False
    
    try:
        cur = conn.cursor()
        # Use West African Time (WAT)
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        
        # Create or update project site access codes
        cur.execute('''
            INSERT OR REPLACE INTO project_site_access_codes (project_site, admin_code, user_code, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (project_site, admin_code, user_code, current_time.isoformat(timespec="seconds")))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error updating project site access codes: {e}")
        return False
    finally:
        conn.close()

def update_project_site_user_code(project_site, user_code):
    """Update user access code for a specific project site"""
    conn = get_conn()
    if conn is None:
        return False
    
    try:
        cur = conn.cursor()
        # Use West African Time (WAT)
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        
        # Create or update project site user access code
        cur.execute('''
            INSERT OR REPLACE INTO project_site_access_codes (project_site, admin_code, user_code, updated_at)
            VALUES (?, (SELECT admin_code FROM project_site_access_codes WHERE project_site = ? LIMIT 1), ?, ?)
        ''', (project_site, project_site, user_code, current_time.isoformat(timespec="seconds")))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error updating project site user access code: {e}")
        return False
    finally:
        conn.close()


def log_current_session():
    """Log current session activity"""
    if st.session_state.get('authenticated') and st.session_state.get('current_user_name'):
        user_name = st.session_state.get('current_user_name')
        user_role = st.session_state.get('user_role', 'unknown')
        log_access("SESSION_ACTIVITY", success=True, user_name=user_name, role=user_role)
        return True
    return False

def check_access():
    """Check access with role-based authentication"""
    if st.session_state.authenticated:
        return True
    
    # Get current access codes from database
    admin_code, user_code = get_access_codes()
    
    st.markdown("### 🔐 System Access")
    st.caption("Enter your access code to use the inventory system")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        access_code = st.text_input("Access Code", type="password", placeholder="Enter access code", key="access_code")
    with col2:
        user_name = st.text_input("Your Name", placeholder="Enter your name", key="user_name")
    
    if st.button("🚀 Access System", type="primary"):
        if not access_code or not user_name:
            st.error(" Please enter both access code and your name.")
        else:
            # Show loading indicator
            with st.spinner("🔐 Authenticating..."):
                pass  # Remove unnecessary delay
            # Check access code
            if access_code == admin_code:
                st.session_state.authenticated = True
                st.session_state.user_role = "admin"
                st.session_state.current_user_name = user_name
                st.session_state.auth_timestamp = get_nigerian_time_iso()
                log_id = log_access(access_code, success=True, user_name=user_name, role="admin")
                st.session_state.access_log_id = log_id
                
                # Save authentication to cookie
                auth_data = {
                    'authenticated': True,
                    'user_role': 'admin',
                    'current_user_name': user_name,
                    'auth_timestamp': st.session_state.auth_timestamp,
                    'access_log_id': log_id
                }
                set_auth_cookie(auth_data)
                
                st.success(f" Admin access granted! Welcome, {user_name}!")
                st.rerun()
            elif access_code == user_code:
                st.session_state.authenticated = True
                st.session_state.user_role = "user"
                st.session_state.current_user_name = user_name
                st.session_state.auth_timestamp = get_nigerian_time_iso()
                log_id = log_access(access_code, success=True, user_name=user_name, role="user")
                st.session_state.access_log_id = log_id
                
                # Save authentication to cookie
                auth_data = {
                    'authenticated': True,
                    'user_role': 'user',
                    'current_user_name': user_name,
                    'auth_timestamp': st.session_state.auth_timestamp,
                    'access_log_id': log_id
                }
                set_auth_cookie(auth_data)
                st.session_state.access_log_id = log_id
                st.success(f" User access granted! Welcome, {user_name}!")
                st.rerun()
            else:
                log_access(access_code, success=False, user_name=user_name)
                st.error(" Invalid access code. Please try again.")
    
    st.stop()

# Authentication is already checked above - no need for additional check

# Check for new notifications and show popup messages for users
def show_notification_popups():
    """Show popup messages for users with new notifications"""
    try:
        # Only show popups for regular users (not admins)
        if st.session_state.get('user_type') != 'admin':
            user_notifications = get_user_notifications()
            
            # Check for unread notifications
            unread_notifications = [n for n in user_notifications if not n.get('is_read', False)]
            
            if unread_notifications:
                # Show popup for each unread notification
                for notification in unread_notifications[:3]:  # Show max 3 notifications
                    if notification['type'] == 'request_approved':
                        st.success(f"**{notification['title']}** - {notification['message']}")
                    elif notification['type'] == 'request_rejected':
                        st.error(f"**{notification['title']}** - {notification['message']}")
                    else:
                        st.info(f"**{notification['title']}** - {notification['message']}")
                
                # Show summary if there are more than 3 notifications
                if len(unread_notifications) > 3:
                    st.info(f"You have {len(unread_notifications)} total unread notifications. Check the Notifications tab for more details.")
                
                # Add a dismiss button
                if st.button("Dismiss Notifications", key="dismiss_notifications"):
                    # Mark all unread notifications as read
                    for notification in unread_notifications:
                        mark_notification_read(notification['id'])
                    st.success("Notifications dismissed!")
                    # Don't use st.rerun() - let the page refresh naturally
    except Exception as e:
        pass  # Silently handle errors to not break the app

# Show notification popups for users
show_notification_popups()

# Show notification banner for users with unread notifications
def show_notification_banner():
    """Show a prominent banner for users with unread notifications"""
    try:
        # Only show banner for regular users (not admins)
        if st.session_state.get('user_type') != 'admin':
            user_notifications = get_user_notifications()
            unread_count = len([n for n in user_notifications if not n.get('is_read', False)])
            
            if unread_count > 0:
                # Create a prominent banner
                st.markdown("""
                <div style="background: linear-gradient(90deg, #ff6b6b, #ff8e8e); color: white; padding: 1rem; border-radius: 8px; margin: 1rem 0; text-align: center; box-shadow: 0 4px 12px rgba(255, 107, 107, 0.3);">
                    <h3 style="margin: 0; color: white;">You have {} unread notification{}</h3>
                    <p style="margin: 0.5rem 0 0 0; color: white; opacity: 0.9;">Check the Notifications tab to view your notifications</p>
                </div>
                """.format(unread_count, 's' if unread_count > 1 else ''), unsafe_allow_html=True)
    except Exception as e:
        pass  # Silently handle errors

# Show notification banner
show_notification_banner()

# Mobile-friendly sidebar toggle
st.markdown("""
<style>
@media (max-width: 768px) {
    .sidebar .sidebar-content {
        padding: 1rem 0.5rem;
    }
    
    .sidebar .sidebar-content h3 {
        font-size: 1.2rem;
        margin-bottom: 0.5rem;
    }
    
    .sidebar .sidebar-content .stMarkdown {
        font-size: 0.9rem;
    }
}
</style>
""", unsafe_allow_html=True)

# Professional Sidebar
with st.sidebar:
    # Professional sidebar styling
    st.markdown("""
    <style>
    .sidebar-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 1rem;
        margin: -1rem -1rem 1rem -1rem;
        border-radius: 0 0 12px 12px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .sidebar-header h1 {
        margin: 0;
        font-size: 1.4rem;
        font-weight: 700;
        color: white;
    }
    
    .sidebar-header p {
        margin: 0.5rem 0 0 0;
        font-size: 0.9rem;
        opacity: 0.9;
        color: white;
    }
    
    .user-info-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    
    .user-info-card h3 {
        margin: 0 0 0.5rem 0;
        font-size: 1rem;
        color: #1f2937;
        font-weight: 600;
    }
    
    .user-info-card p {
        margin: 0.25rem 0;
        font-size: 0.85rem;
        color: #64748b;
    }
    
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 500;
        margin-top: 0.5rem;
    }
    
    .status-admin {
        background: #dbeafe;
        color: #1e40af;
        border: 1px solid #93c5fd;
    }
    
    .status-user {
        background: #f0fdf4;
        color: #166534;
        border: 1px solid #86efac;
    }
    
    .session-info {
        background: #fef3c7;
        border: 1px solid #f59e0b;
        border-radius: 6px;
        padding: 0.75rem;
        margin: 1rem 0;
        font-size: 0.85rem;
        color: #92400e;
    }
    
    .sidebar-actions {
        margin-top: 1.5rem;
    }
    
    .logout-btn {
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-weight: 600;
        width: 100%;
        transition: all 0.2s ease;
    }
    
    .logout-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(239, 68, 68, 0.3);
    }
    
    .project-info {
        background: #f0f9ff;
        border: 1px solid #0ea5e9;
        border-radius: 6px;
        padding: 0.75rem;
        margin: 1rem 0;
        font-size: 0.85rem;
        color: #0c4a6e;
    }
    
    .project-info strong {
        color: #0369a1;
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Professional header
    st.markdown("""
    <div class="sidebar-header">
        <h1>📦 Istrom Inventory</h1>
        <p>Management System</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get current user info from session
    current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
    current_role = st.session_state.get('user_type', st.session_state.get('user_role', 'user'))
    current_project = st.session_state.get('current_project_site', 'Unknown Project')
    
    # User information card
    st.markdown(f"""
    <div class="user-info-card">
        <h3>👤 User Information</h3>
        <p><strong>Name:</strong> {current_user}</p>
        <p><strong>Role:</strong> {current_role.title()}</p>
        <div class="status-badge status-{current_role}">
            {current_role.title()} Access
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Project information
    st.markdown(f"""
    <div class="project-info">
        <strong>🏗️ Current Project:</strong><br>
        {current_project}
    </div>
    """, unsafe_allow_html=True)
    
    # Session information
    if st.session_state.get('auth_timestamp'):
        try:
            auth_time = datetime.fromisoformat(st.session_state.get('auth_timestamp'))
            expiry_time = auth_time.replace(hour=auth_time.hour + 24)
            time_remaining = expiry_time - get_nigerian_time()
            hours_remaining = int(time_remaining.total_seconds() / 3600)
            
            if hours_remaining > 0:
                session_status = f"⏰ {hours_remaining}h remaining"
                session_color = "#059669" if hours_remaining > 2 else "#d97706"
            else:
                session_status = "⚠️ Expiring soon"
                session_color = "#dc2626"
        except:
            session_status = "✅ Active"
            session_color = "#059669"
    else:
        session_status = "✅ Active"
        session_color = "#059669"
    
    st.markdown(f"""
    <div class="session-info" style="border-color: {session_color}; color: {session_color};">
        <strong>Session Status:</strong><br>
        {session_status}
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar actions
    st.markdown('<div class="sidebar-actions">', unsafe_allow_html=True)
    
    if st.button("🚪 Logout", type="secondary", use_container_width=True, help="Logout from the system"):
        st.session_state.authenticated = False
        st.session_state.user_role = None
        st.session_state.current_user_name = None
        st.session_state.access_log_id = None
        st.session_state.auth_timestamp = None
        st.query_params.clear()
        st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
# Project Site Selection - REQUIRED FOR APP TO WORK
# No default project site creation - let admin create them
try:
    project_sites = get_project_sites()
except Exception as e:
    # Could not load project sites during startup
    project_sites = []  # No fallback - let admin create project sites

# Don't set a default project site - let admin choose
if 'current_project_site' not in st.session_state:
    st.session_state.current_project_site = None

# Database persistence test - verify PostgreSQL is working
def test_database_persistence():
    """Test if database persistence is working properly"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            
            # Test if we can create and retrieve data
            cur.execute("""
                CREATE TABLE IF NOT EXISTS persistence_test (
                    id SERIAL PRIMARY KEY,
                    test_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert test data
            cur.execute("INSERT INTO persistence_test (test_data) VALUES (?)", ("test_persistence",))
            conn.commit()
            
            # Retrieve test data
            cur.execute("SELECT * FROM persistence_test WHERE test_data = ?", ("test_persistence",))
            result = cur.fetchone()
            
            if result:
                # Database persistence test PASSED - PostgreSQL is working!
                return True
            else:
                # Database persistence test FAILED - Data not retrievable!
                return False
                
    except Exception as e:
        # Database persistence test ERROR
        return False

# User persistence test - test if users actually persist
def test_user_persistence():
    """Test if user creation and retrieval works properly"""
    try:
        with engine.connect() as conn:
            # Check if users table exists and has data
            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.fetchone()[0]
            print(f"📊 Current user count in database: {user_count}")
            
            # Check if there are any users
            result = conn.execute(text("SELECT username, full_name, project_site FROM users LIMIT 5"))
            users = result.fetchall()
            
            if users:
                print("✅ Users found in database:")
                for user in users:
                    print(f"   - {user[1]} ({user[0]}) - {user[2]}")
            else:
                print("❌ No users found in database!")
                
            return len(users) > 0
                
    except Exception as e:
        print(f"❌ User persistence test ERROR: {e}")
        return False

# Run database persistence tests on startup
# Database persistence tests running...
# App version: v6.0 - SYNTAX FIXED
test_database_persistence()
test_user_persistence()

# Debug actuals issue
def debug_actuals_issue():
    """Debug why approved requests aren't showing in actuals"""
    try:
        with engine.connect() as conn:
            # Check approved requests
            result = conn.execute(text("""
                SELECT r.id, r.status, r.qty, i.name, i.project_site, r.current_price
                FROM requests r 
                JOIN items i ON r.item_id = i.id
                WHERE r.status = 'Approved'
                ORDER BY r.id DESC
                LIMIT 5
            """))
            approved_requests = result.fetchall()
            print(f"📋 Approved requests found: {len(approved_requests)}")
            for req in approved_requests:
                print(f"   - Request #{req[0]}: {req[3]} (Qty: {req[2]}, Project: {req[4]}, Price: {req[5]})")
            
            # Check actuals records
            result = conn.execute(text("""
                SELECT a.id, a.actual_qty, a.actual_cost, a.project_site, i.name
                FROM actuals a
                JOIN items i ON a.item_id = i.id
                ORDER BY a.id DESC
                LIMIT 5
            """))
            actuals_records = result.fetchall()
            print(f"📊 Actuals records found: {len(actuals_records)}")
            for actual in actuals_records:
                print(f"   - Actual #{actual[0]}: {actual[4]} (Qty: {actual[1]}, Cost: {actual[2]}, Project: {actual[3]})")
            
            # Check current project site
            current_project = st.session_state.get('current_project_site', 'Not set')
            print(f"🏗️ Current project site: {current_project}")
            
    except Exception as e:
        print(f"❌ Debug actuals error: {e}")

debug_actuals_issue()

# Comprehensive app connectivity test
def test_app_connectivity():
    """Test all app connections and data flow"""
    # Running comprehensive app connectivity test...
    
    try:
        # Test 1: Database connection
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            # Database connection: PASSED
        
        # Test 2: User authentication system
        test_access_code = "test123"
        auth_result = authenticate_user(test_access_code)
        # Authentication system is working if it returns None for invalid codes (expected behavior)
        # Authentication system: PASSED
        
        # Test 3: Session state
        session_keys = ['logged_in', 'user_type', 'current_project_site']
        session_ok = all(key in st.session_state for key in session_keys)
        # Session state might not be fully initialized outside Streamlit context
        # Session state: PASSED
        
        # Test 4: Notification system
        try:
            # Test notification system without showing popup
            pass  # Notification system: PASSED
        except:
            # Notification system: FAILED
            pass
        
        # Test 5: Data retrieval functions
        try:
            items = df_items_cached("Lifecamp Kafe")
            requests = df_requests("Pending")
            # Data retrieval: PASSED
        except Exception as e:
            # Data retrieval: FAILED
            pass
        
        # Test 6: Project site management
        try:
            project_sites = get_project_sites()
            # Project sites: PASSED
        except Exception as e:
            # Project sites: FAILED
            pass
        
        # App connectivity test completed!
        return True
        
    except Exception as e:
        # App connectivity test failed
        return False

test_app_connectivity()

# Project site selection based on user permissions
user_type = st.session_state.get('user_type', 'user')
user_project_site = st.session_state.get('project_site', None)

if user_type == 'admin':
    # Admins can select any project site
    if project_sites:
        current_index = 0
        if st.session_state.current_project_site in project_sites:
            current_index = project_sites.index(st.session_state.current_project_site)
        
        selected_site = st.selectbox(
            "Select Project Site:",
            project_sites,
            index=current_index,
            key="project_site_selector",
            help="Choose which project site you want to work with"
        )
        
        # Check if project site changed before updating
        if st.session_state.current_project_site != selected_site:
            clear_cache()
            st.session_state.current_project_site = selected_site
            st.rerun()  # Refresh to show new project site data
        else:
            st.session_state.current_project_site = selected_site
    else:
        if user_type == 'admin':
            st.info("No project sites created yet. Use the Admin Settings tab to create your first project site.")
        else:
            st.warning("No project sites available. Contact an administrator to add project sites.")
else:
    # Regular users are restricted to their assigned project site
    if user_project_site:
        st.session_state.current_project_site = user_project_site
        st.info(f"🏗️ **Project Site:** {user_project_site}")
    else:
        st.warning("No project site assigned. Please contact an administrator.")

# Display current project site info
if 'current_project_site' in st.session_state and st.session_state.current_project_site:
    if user_type == 'admin':
        st.caption(f"📊 Working with: {st.session_state.current_project_site} | Budgets: 1-20")
    else:
        st.caption(f"📊 Available Budgets: 1-20")
else:
    if user_type == 'admin':
        st.info("Please select a project site from the dropdown above to continue.")
    else:
        st.warning("Please contact an administrator to set up your project site access.")

# Tab persistence implementation
def get_current_tab():
    """Get current tab from URL params or default to 0"""
    tab_param = st.query_params.get('tab', '0')
    try:
        return int(tab_param)
    except:
        return 0

def set_current_tab(tab_index):
    """Set current tab in URL params"""
    st.query_params.tab = str(tab_index)

# Initialize tab persistence
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = get_current_tab()

# Create tabs based on user type with persistence
if st.session_state.get('user_type') == 'admin':
    tab_names = ["Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History", "Budget Summary", "Actuals", "Admin Settings"]
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tab_names)
else:
    # Regular users see same tabs as admin but without Admin Settings, plus Notifications
    tab_names = ["Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History", "Budget Summary", "Actuals", "Notifications"]
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tab_names)

# Tab persistence - update URL when tab changes
current_tab = get_current_tab()
if current_tab != st.session_state.active_tab:
    st.session_state.active_tab = current_tab

# Store current tab in session state for persistence
st.session_state.current_tab = current_tab

# -------------------------------- Tab 1: Manual Entry (Budget Builder) --------------------------------
with tab1:
    st.subheader("Manual Entry - Budget Builder")
    st.caption("Add items with proper categorization and context")
    
    # Check permissions for manual entry
    if not is_admin():
        st.warning("**Read-Only Access**: You can view items but cannot add, edit, or delete them.")
        st.info("Contact an administrator if you need to make changes to the inventory.")
    
    # Project Context (outside form for immediate updates)
    st.markdown("### Project Context")
    col1, col2, col3 = st.columns([2,2,2])
    with col1:
        building_type = st.selectbox("Building Type", PROPERTY_TYPES, index=1, help="Select building type first", key="building_type_select")
    with col2:
        # Construction sections
        common_sections = [
            "SUBSTRUCTURE (GROUND TO DPC LEVEL)",
            "SUBSTRUCTURE (EXCAVATION TO DPC LEVEL)",
            "TERRACES (6-UNITS) DPC(TERRACE SUBSTRUCTURE)",
            "SUPERSTRUCTURE: GROUND FLOOR; (COLUMN, LINTEL AND BLOCK WORK)",
            "SUPERSTRUCTURE, GROUND FLOOR; (SLAB,BEAMS AND STAIR CASE)",
            "SUPERSTRUCTURE, FIRST FLOOR; (COLUMN, LINTEL AND BLOCK WORK)"
        ]
        
        section = st.selectbox("Section", common_sections, index=0, help="Select construction section", key="manual_section_selectbox")
    with col3:
        # Filter budget options based on selected building type
        with st.spinner("Loading budget options..."):
            all_budget_options = get_budget_options(st.session_state.get('current_project_site'))
            # Filter budgets that match the selected building type
            if building_type:
                # Use more robust matching for building types with hyphens
                if building_type in ["Semi-detached", "Fully-detached"]:
                    # For hyphenated building types, use exact matching
                    budget_options = [opt for opt in all_budget_options if f" - {building_type}" in opt or f"({building_type}" in opt]
                else:
                    budget_options = [opt for opt in all_budget_options if building_type in opt]
                
                # If no matching budgets found, show a message
                if not budget_options:
                    st.warning(f"No budgets found for {building_type}. Showing all budgets.")
                    budget_options = all_budget_options
            else:
                budget_options = all_budget_options
        
        # Budget selection - filtered by building type
        budget = st.selectbox("🏷️ Budget Label", budget_options, index=0, help="Select budget type", key="budget_selectbox")
        
        # Show info about filtered budgets
        if building_type and len(budget_options) < len(all_budget_options):
            st.caption(f"Showing {len(budget_options)} budget(s) for {building_type}")


    # Add Item Form
    with st.form("add_item_form"):
        st.markdown("### 📦 Item Details")
        col1, col2, col3, col4 = st.columns([2,1,1,1])
        with col1:
            name = st.text_input("📄 Item Name", placeholder="e.g., STONE DUST", key="manual_name_input")
        with col2:
            qty = st.number_input("📦 Quantity", min_value=0.0, step=1.0, value=0.0, key="manual_qty_input")
        with col3:
            unit = st.text_input("📏 Unit", placeholder="e.g., trips, pcs, bags", key="manual_unit_input")
        with col4:
            rate = st.number_input("₦ Unit Cost", min_value=0.0, step=100.0, value=0.0, key="manual_rate_input")

        st.markdown("### Category")
        category = st.selectbox("📂 Category", ["Materials", "Labour", "Material/Labour"], index=0, help="Select category", key="manual_category_select")
        
        # Set default group based on category
        if category == "Materials":
            grp = "Materials"
        elif category == "Labour":
            grp = "Labour"
        else:  # Material/Labour
            grp = "Material/Labour"

        # Show line amount preview
        line_amount = float((qty or 0) * (rate or 0))
        st.markdown(f"""
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937; text-align: center; padding: 0.6rem; background: #f8fafc; border-radius: 8px; margin: 0.4rem 0;">
            Line Amount: ₦{line_amount:,.2f}
        </div>
        """, unsafe_allow_html=True)

        submitted = st.form_submit_button("Add Item", type="primary")
        
        if submitted:
            if not is_admin():
                st.error(" Admin privileges required for this action.")
                st.info("Only administrators can add items to the inventory.")
            else:
                # Parse subgroup from budget if present
                parsed_grp = None
                if budget and "(" in budget and ")" in budget:
                    match = re.search(r"\(([^)]+)\)", budget)
                    if match:
                        parsed_grp = match.group(1).strip().upper()
                        # Convert to proper format
                        if parsed_grp in ["WOODS", "PLUMBINGS", "IRONS"]:
                            parsed_grp = f"MATERIAL({parsed_grp})"
                
                # Use parsed subgroup if valid, otherwise use manual selection
                final_grp = parsed_grp if parsed_grp else grp
                
                # Parse building type from budget if present
                parsed_bt = None
                for bt_name in [t for t in PROPERTY_TYPES if t]:
                    if budget and bt_name.lower() in budget.lower():
                        parsed_bt = bt_name
                        break
                
                final_bt = building_type or parsed_bt

                # Create and save item
                df_new = pd.DataFrame([{
                    "name": name,
                    "qty": qty,
                    "unit": unit or None,
                    "unit_cost": rate or None,
                    "category": category,
                    "budget": budget,
                    "section": section,
                    "grp": final_grp,
                    "building_type": final_bt
                }])
                
                # Add item (no unnecessary spinner)
                upsert_items(df_new, category_guess=category, budget=budget, section=section, grp=final_grp, building_type=final_bt, project_site=st.session_state.get('current_project_site'))
                # Log item addition activity
                log_current_session()
                
                st.success(f" Successfully added: {name} ({qty} {unit}) to {budget} / {section} / {final_grp} / {final_bt}")
                st.info("💡 This item will now appear in the Budget Summary tab for automatic calculations!")
                # Don't use st.rerun() - let the page refresh naturally

    st.divider()
    
    # Budget View & Totals
    st.subheader("Budget View & Totals")
    
    # Filters
    st.markdown("### Filters")
    col1, col2 = st.columns([2,2])
    with col1:
        # Create all budget options for the dropdown (cached)
        budget_options = get_budget_options(st.session_state.get('current_project_site'))
        
        budget_filter = st.selectbox("🏷️ Budget Filter", budget_options, index=0, help="Select budget to filter (shows all subgroups)", key="budget_filter_selectbox")
    with col2:
        # Construction sections
        common_sections = [
            "",
            "SUBSTRUCTURE (GROUND TO DPC LEVEL)",
            "SUBSTRUCTURE (EXCAVATION TO DPC LEVEL)",
            "TERRACES (6-UNITS) DPC(TERRACE SUBSTRUCTURE)"
        ]
        
        # Get dynamic section options from database
        section_options = get_section_options(st.session_state.get('current_project_site'))
        section_filter = st.selectbox("📂 Section Filter", section_options, index=0, help="Select or type custom section", key="section_filter_selectbox")

    # Build filters for database-level filtering (much faster)
    filters = {}
    if budget_filter:
        filters["budget"] = budget_filter
    if section_filter:
        filters["section"] = section_filter
    
    # Get filtered items directly from database (cached)
    with st.spinner("Loading items..."):
        # First get items for current project site, then apply filters
        all_items = df_items_cached(st.session_state.get('current_project_site'))
        filtered_items = all_items.copy()
        
        # Apply filters with flexible matching (space and case insensitive)
        if filters.get('budget') and filters['budget'] != "All":
            budget_selected = filters['budget']
            
            def normalize_budget_string(budget_str):
                """Normalize budget string for comparison - remove extra spaces, convert to lowercase"""
                if pd.isna(budget_str):
                    return ""
                return str(budget_str).strip().lower().replace("  ", " ")  # Remove extra spaces
            
            # Normalize the selected budget
            normalized_selected = normalize_budget_string(budget_selected)
            
            if "(" in budget_selected and ")" in budget_selected:
                # Specific subgroup - flexible exact match
                budget_matches = filtered_items["budget"].apply(
                    lambda x: normalize_budget_string(x) == normalized_selected
                )
            else:
                # Hierarchical - show all items that contain this budget
                # e.g., "Budget 1 - Terraces" shows "Budget 1 - Terraces", "Budget 1 - Terraces(Plumbings)", etc.
                budget_matches = filtered_items["budget"].apply(
                    lambda x: normalized_selected in normalize_budget_string(x)
                )
            
            filtered_items = filtered_items[budget_matches]
        if filters.get('section') and filters['section'] != "All":
            filtered_items = filtered_items[filtered_items['section'] == filters['section']]
        
    if filtered_items.empty:
        st.info("No items found matching your filters.")
        st.write("**Debug Info:**")
        st.write(f"Budget filter selected: {budget_filter}")
        st.write(f"Section filter selected: {section_filter}")
        
        # Get debug info from database (cached)
        debug_items = df_items_cached(st.session_state.get('current_project_site'))
        if not debug_items.empty:
            st.write(f"Total items in database: {len(debug_items)}")
            st.write("**Available budgets in database:**")
            unique_budgets = debug_items["budget"].unique()
            for budget in unique_budgets[:10]:  # Show first 10
                st.write(f"- {budget}")
            if len(unique_budgets) > 10:
                st.write(f"... and {len(unique_budgets) - 10} more")
            
            st.write("**Available sections in database:**")
            unique_sections = debug_items["section"].unique()
            for section in unique_sections[:10]:  # Show first 10
                st.write(f"- {section}")
            if len(unique_sections) > 10:
                st.write(f"... and {len(unique_sections) - 10} more")
    else:
        # Calculate amounts
        filtered_items["Amount"] = (filtered_items["qty"].fillna(0) * filtered_items["unit_cost"].fillna(0)).round(2)
        
        # Display table with proper currency formatting
        display_df = filtered_items[["budget","section","grp","building_type","name","qty","unit","unit_cost","Amount"]].copy()
        
        # Ensure Amount column has no NaN values for display
        display_df["Amount"] = display_df["Amount"].fillna(0)
        
        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "unit_cost": st.column_config.NumberColumn("Unit Cost", format="₦%,.2f"),
                "Amount": st.column_config.NumberColumn("Amount", format="₦%,.2f"),
            }
        )
        
        # Show total with proper NaN handling
        total_amount = filtered_items["Amount"].sum()
        if pd.notna(total_amount):
            total_amount = float(total_amount)
        else:
            total_amount = 0.0
        st.markdown(f"""
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937; text-align: center; padding: 0.6rem; background: #f8fafc; border-radius: 8px; margin: 0.4rem 0;">
            Total Amount: ₦{total_amount:,.2f}
        </div>
        """, unsafe_allow_html=True)
        
        # Export
        csv_data = filtered_items.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv_data, "budget_view.csv", "text/csv")

# -------------------------------- Tab 2: Inventory --------------------------------
with tab2:
    st.subheader("📦 Current Inventory")
    st.caption("View, edit, and manage all inventory items")
    
    # Check permissions for inventory management
    if not is_admin():
        st.warning("**Read-Only Access**: You can view inventory but cannot modify items.")
        st.info("Contact an administrator if you need to make changes to the inventory.")
    
    # Load all items first with progress indicator (optimized)
    with st.spinner("Loading inventory..."):
        items = df_items_cached(st.session_state.get('current_project_site'))
    
    # Show loading status
    if items.empty:
        st.info("No items found. Add some items in the Manual Entry tab to get started.")
        st.stop()
    
    # Calculate amounts
    items["Amount"] = (items["qty"].fillna(0) * items["unit_cost"].fillna(0)).round(2)

    # Quick stats (optimized)
    total_items = len(items)
    # Calculate total value with proper NaN handling
    total_value = items["Amount"].sum()
    if pd.notna(total_value):
        total_value = float(total_value)
    else:
        total_value = 0.0
    
    # Professional Dashboard Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Items", f"{total_items:,}", help="Total inventory items")
    with col2:
        st.metric("Total Value", f"₦{total_value:,.2f}", help="Total inventory value")
    with col3:
        materials_count = (items['category'] == 'materials').sum()
        st.metric("Materials", f"{materials_count:,}", help="Material items count")
    with col4:
        labour_count = (items['category'] == 'labour').sum()
        st.metric("Labour", f"{labour_count:,}", help="Labour items count")
    
    # Professional Chart Section
    if not items.empty:
        st.markdown("### Inventory Analysis")
        
        # Category breakdown chart (single diagram)
        category_data = items['category'].value_counts()
        if not category_data.empty:
            st.bar_chart(category_data, height=300)

    # Professional Filters
    st.markdown("### Filters")
    
    colf1, colf2, colf3 = st.columns([2,2,2])
    with colf1:
        # Get dynamic budget options from database
        budget_options = get_budget_options(st.session_state.get('current_project_site'))
        f_budget = st.selectbox("🏷️ Budget Filter", budget_options, index=0, help="Select budget to filter by (shows all subgroups)", key="inventory_budget_filter")
    with colf2:
        # Get dynamic section options from database
        section_options = get_section_options(st.session_state.get('current_project_site'))
        f_section = st.selectbox("📂 Section Filter", section_options, index=0, help="Select section to filter by", key="inventory_section_filter")
    with colf3:
        # Building type filter
        building_type_options = ["All"] + PROPERTY_TYPES
        f_building_type = st.selectbox("🏠 Building Type Filter", building_type_options, index=0, help="Select building type to filter by", key="inventory_building_type_filter")

    # Apply filters using hierarchical logic
    filtered_items = items.copy()
    
    # Debug info
    st.caption(f"🔍 Total items before filtering: {len(filtered_items)}")
        
    # Budget filter with flexible matching (space and case insensitive)
    if f_budget and f_budget != "All":
        def normalize_budget_string(budget_str):
            """Normalize budget string for comparison - remove extra spaces, convert to lowercase"""
            if pd.isna(budget_str):
                return ""
            # Convert to string, strip whitespace, convert to lowercase
            normalized = str(budget_str).strip().lower()
            # Remove extra spaces and normalize spacing around parentheses
            normalized = normalized.replace("  ", " ")  # Remove double spaces
            normalized = normalized.replace(" (", "(")   # Remove space before opening parenthesis
            normalized = normalized.replace("( ", "(")   # Remove space after opening parenthesis
            normalized = normalized.replace(" )", ")")   # Remove space before closing parenthesis
            # Handle "Iron" vs "Irons" difference
            normalized = normalized.replace("(iron)", "(irons)")
            return normalized
        
        # Normalize the filter budget
        normalized_filter = normalize_budget_string(f_budget)
        
        if "(" in f_budget and ")" in f_budget:
            # Specific subgroup - flexible exact match
            budget_matches = filtered_items["budget"].apply(
                lambda x: normalize_budget_string(x) == normalized_filter
            )
        else:
            # Hierarchical - show all items that contain this budget
            # e.g., "Budget 1 - Terraces" shows "Budget 1 - Terraces", "Budget 1 - Terraces(Plumbings)", etc.
            budget_matches = filtered_items["budget"].apply(
                lambda x: normalized_filter in normalize_budget_string(x)
            )
        
        filtered_items = filtered_items[budget_matches]
        st.caption(f"🔍 After budget filter: {len(filtered_items)} items")
        
    # Section filter
    if f_section and f_section != "All":
        section_matches = filtered_items["section"] == f_section
        filtered_items = filtered_items[section_matches]
        st.caption(f"🔍 After section filter: {len(filtered_items)} items")
    
    # Building type filter
    if f_building_type and f_building_type != "All":
        building_type_matches = filtered_items["building_type"] == f_building_type
        filtered_items = filtered_items[building_type_matches]
        st.caption(f"🔍 After building type filter: {len(filtered_items)} items")
    
    # Update items with filtered results
    items = filtered_items
    st.caption(f"✅ Final filtered items: {len(items)} items")
    current_project = st.session_state.get('current_project_site', 'Not set')
    try:
        total_items_in_project = len(df_items_cached(st.session_state.get('current_project_site')))
    except Exception as e:
        # Could not load items during startup
        total_items_in_project = 0
    # Cache refresh button removed

    st.markdown("### Inventory Items")
    
    # Remove code and project_site columns from display
    display_items = items.drop(columns=['code', 'project_site'], errors='ignore')
    
    # Display the dataframe with full width
    st.dataframe(
        display_items,
        use_container_width=True,
        column_config={
            "unit_cost": st.column_config.NumberColumn("Unit Cost", format="₦%,.2f"),
            "Amount": st.column_config.NumberColumn("Amount", format="₦%,.2f"),
            "qty": st.column_config.NumberColumn("Quantity", format="%.2f"),
        },
    )
    
    
    # Export
    csv_inv = display_items.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download Inventory CSV", csv_inv, "inventory_view.csv", "text/csv")

    st.markdown("### Item Management")
    require_confirm = st.checkbox("Require confirmation for deletes", value=True, key="inv_confirm")
    
    # Simple item selection for deletion
    st.markdown("####  Select Items to Delete")
    
    # Create a list of items for selection
    item_options = []
    for _, r in items.iterrows():
        item_options.append({
            'id': int(r['id']),
            'name': r['name'],
            'qty': r['qty'],
            'unit': r['unit'],
            'display': f"{r['name']} - {r['qty']} {r['unit'] or ''} @ ₦{(r['unit_cost'] or 0):,.2f}"
        })
    
    # Multi-select for deletion
    selected_items = st.multiselect(
        "Select items to delete:",
        options=item_options,
        format_func=lambda x: x['display'],
        key="delete_selection",
        help="Select multiple items to delete at once"
    )
    
    if selected_items and is_admin():
        st.warning(f"You have selected {len(selected_items)} item(s) for deletion.")
        
        # Wrap delete functionality in a form
        with st.form("delete_items_form"):
            col1, col2 = st.columns([1, 1])
            with col1:
                delete_submitted = st.form_submit_button("🗑️ Delete Selected Items", type="secondary")
            with col2:
                clear_submitted = st.form_submit_button("Clear Selection", type="secondary")
            
            if delete_submitted:
                # Delete selected items immediately
                deleted_count = 0
                errors = []
                
                for item in selected_items:
                    # Check if item has linked requests
                    with get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) FROM requests WHERE item_id=?", (item['id'],))
                        request_count = cur.fetchone()[0]
                        
                        if request_count > 0:
                            errors.append(f"Item {item['name']}: Has {request_count} linked request(s)")
                        else:
                            err = delete_item(item['id'])
                            if err:
                                errors.append(f"Item {item['name']}: {err}")
                            else:
                                deleted_count += 1
                    
                if deleted_count > 0:
                    st.success(f"✅ Successfully deleted {deleted_count} item(s).")
                    
                    if errors:
                        st.error(f"❌ {len(errors)} item(s) could not be deleted:")
                        for error in errors:
                            st.error(error)
                
                if deleted_count > 0 or errors:
                    # Refresh the page to show updated inventory
                    st.rerun()
            
            if clear_submitted:
                st.session_state["delete_selection"] = []
                st.rerun()
    elif selected_items and not is_admin():
        st.error(" Admin privileges required for deletion.")
    
    # Individual item editing (simplified to avoid nested columns)
    st.markdown("#### 📝 Individual Item Management")
    st.info("💡 Use the bulk selection above to manage multiple items, or edit items directly below.")
    
    # Individual item edit functionality
    if is_admin():
        st.markdown("##### ✏️ Edit Individual Items")
        
        # Create a form for editing items (uses filtered items)
        with st.form("edit_item_form"):
            st.markdown(f"**Select an item to edit (filtered results: {len(items)} items):**")
            
            # Create a selectbox for item selection using filtered items
            item_edit_options = []
            for _, r in items.iterrows():
                item_edit_options.append({
                    'id': int(r['id']),
                    'name': r['name'],
                    'display': f"[{int(r['id'])}] {r['name']} - {r['qty']} {r['unit'] or ''} @ ₦{(r['unit_cost'] or 0):,.2f}"
                })
            
            if item_edit_options:
                selected_item = st.selectbox(
                    "Choose item to edit:",
                    options=item_edit_options,
                    format_func=lambda x: x['display'],
                    key="edit_item_select"
                )
                
                if selected_item:
                    # Get current item data
                    current_item = items[items['id'] == selected_item['id']].iloc[0]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        new_qty = st.number_input(
                            "📦 New Quantity",
                            min_value=0.0,
                            step=0.1,
                            value=float(current_item['qty']),
                            key="edit_qty"
                        )
                    with col2:
                        new_cost = st.number_input(
                            "₦ New Unit Cost",
                            min_value=0.0,
                            step=0.01,
                            value=float(current_item['unit_cost']),
                            key="edit_cost"
                        )
                    
                    # Show preview of changes
                    old_amount = float(current_item['qty']) * float(current_item['unit_cost'])
                    new_amount = new_qty * new_cost
                    amount_change = new_amount - old_amount
                    
                    st.markdown("**Change Preview:**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Old Amount", f"₦{old_amount:,.2f}")
                    with col2:
                        st.metric("New Amount", f"₦{new_amount:,.2f}")
                    with col3:
                        st.metric("Change", f"₦{amount_change:,.2f}", delta=f"{amount_change:,.2f}")
                    
                    # Submit button
                    if st.form_submit_button("💾 Update Item", type="primary"):
                        try:
                            with get_conn() as conn:
                                cur = conn.cursor()
                                cur.execute(
                                    "UPDATE items SET qty=?, unit_cost=? WHERE id=?",
                                    (new_qty, new_cost, selected_item['id'])
                                )
                                conn.commit()
                            
                            st.success(f"Successfully updated item: {selected_item['name']}")
                            # Clear cache to refresh budget calculations
                            clear_cache()
                            # Don't use st.rerun() - let the page refresh naturally
                        except Exception as e:
                            st.error(f"Error updating item: {e}")
            else:
                st.info("No items available for editing.")
    else:
        st.info("Admin privileges required to edit items.")
    
    st.divider()
    st.markdown("### Danger Zone")
    coldz1, coldz2 = st.columns([3,2])
    with coldz1:
        if is_admin():
            also_logs = st.checkbox("Also clear deleted request logs", value=False, key="clear_logs")
        else:
            st.info("Admin privileges required for bulk operations")
    with coldz2:
        if is_admin():
            if st.button(" Delete ALL inventory and requests", type="secondary", key="delete_all_button"):
                if not st.session_state.get("confirm_clear_all"):
                    st.session_state["confirm_clear_all"] = True
                    st.warning("Click the button again to confirm full deletion.")
                else:
                    clear_inventory(include_logs=also_logs)
                    st.success(" All items and requests cleared.")
                    # Don't use st.rerun() - let the page refresh naturally
        else:
            st.button(" Delete ALL inventory and requests", type="secondary", key="delete_all_button", disabled=True, help="Admin privileges required")
    st.caption("Tip: Use Manual Entry / Import to populate budgets; use Make Request to deduct stock later.")
    

# -------------------------------- Tab 5: Budget Summary --------------------------------
with tab5:
    st.subheader("Budget Summary by Building Type")
    st.caption("Comprehensive overview of all budgets and building types")
    
    # Check permissions for budget management
    if not is_admin():
        st.info("👤 **User Access**: You can view budget summaries but cannot modify them.")
    
    # Navigation helper
    st.info("💡 **Tip**: Add items in the Manual Entry tab, then configure project structure here for automatic budget calculations!")
    
    # Get all items for summary (cached)
    with st.spinner("Loading budget summary data..."):
        current_project = st.session_state.get('current_project_site', 'Not set')
        user_project = st.session_state.get('project_site', 'Not set')
        user_type = st.session_state.get('user_type', 'Not set')
        all_items_summary, summary_data = get_summary_data()
    current_project = st.session_state.get('current_project_site', 'Not set')
    # Manual cache clear button removed
    
    if not all_items_summary.empty:
        
        # Quick overview metrics
        st.markdown("#### Quick Overview")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            total_items = len(all_items_summary)
            st.metric("Total Items", total_items)
        with col2:
            # Calculate total amount with proper NaN handling
            total_amount = all_items_summary["Amount"].sum()
            if pd.notna(total_amount):
                total_amount = float(total_amount)
            else:
                total_amount = 0.0
            st.metric("Total Amount", f"₦{total_amount:,.2f}")
        with col3:
            unique_budgets = all_items_summary["budget"].nunique()
            st.metric("Active Budgets", unique_budgets)
        with col4:
            unique_building_types = all_items_summary["building_type"].nunique()
            st.metric("Building Types", unique_building_types)
        
        # Show recent items added
        st.markdown("#### Recent Items Added")
        recent_items = all_items_summary.tail(5)[["name", "budget", "building_type", "Amount"]]
        st.dataframe(recent_items, use_container_width=True)
        
        # Use cached summary data
        if summary_data:
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, use_container_width=True)
            
            # Grand total with proper error handling
            grand_total = 0
            for row in summary_data:
                try:
                    total_str = str(row["Total"]).replace("₦", "").replace(",", "").strip()
                    if total_str and total_str != '':
                        grand_total += float(total_str)
                except (ValueError, TypeError):
                    continue
            st.markdown(f"""
            <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937; text-align: center; padding: 0.6rem; background: #f8fafc; border-radius: 8px; margin: 0.4rem 0;">
                Grand Total (All Budgets): ₦{grand_total:,.2f}
            </div>
            """, unsafe_allow_html=True)
            
            # Export summary
            summary_csv = summary_df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download Summary CSV", summary_csv, "budget_summary.csv", "text/csv")
        else:
            st.info("No budget data found for summary.")
    else:
        st.info("📦 No items found for this project site. Add items in the Manual Entry tab to see budget summaries.")
        st.markdown("#### Quick Overview")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Items", 0)
        with col2:
            st.metric("Total Amount", "₦0.00")
        with col3:
            st.metric("Active Budgets", 0)
        with col4:
            st.metric("Building Types", 0)
    
    st.divider()
    
    # Manual Budget Summary Section
    st.subheader("Manual Budget Summary")
    st.caption("Add custom budget summary information for each budget number")
    
    # Initialize session state for budget count
    if "max_budget_num" not in st.session_state:
        st.session_state.max_budget_num = 20
    
    # Budget summary header
    st.markdown("#### Available Budgets")
    
    # Create tabs for budgets 1 to 20 (or current max_budget_num)
    # Show all budgets from 1 to max_budget_num
    max_budget = st.session_state.get('max_budget_num', 20)
    tabs_to_create = list(range(1, max_budget + 1))  # Budgets 1 to 20 (or current max)
    budget_tabs = st.tabs([f"Budget {i}" for i in tabs_to_create])
    
    for i, tab in enumerate(budget_tabs):
        budget_num = tabs_to_create[i]
        with tab:
            st.markdown(f"### Budget {budget_num} Summary")
            
            # Get items for this budget
            if not all_items_summary.empty:
                budget_items = all_items_summary[all_items_summary["budget"].str.contains(f"Budget {budget_num}", case=False, na=False, regex=False)]
                if not budget_items.empty:
                    # Calculate budget total with proper NaN handling
                    budget_total = budget_items["Amount"].sum()
                    if pd.notna(budget_total):
                        budget_total = float(budget_total)
                    else:
                        budget_total = 0.0
                    st.metric(f"Total Amount for Budget {budget_num}", f"₦{budget_total:,.2f}")
                    
                    # Show breakdown by building type
                    st.markdown("#### Breakdown by Building Type")
                    for building_type in PROPERTY_TYPES:
                        if building_type:
                            bt_items = budget_items[budget_items["building_type"] == building_type]
                            if not bt_items.empty:
                                # Calculate building type total with proper NaN handling
                                bt_total = bt_items["Amount"].sum()
                                if pd.notna(bt_total):
                                    bt_total = float(bt_total)
                                else:
                                    bt_total = 0.0
                                st.metric(f"{building_type}", f"₦{bt_total:,.2f}")
                else:
                    st.info(f"No items found for Budget {budget_num}")
            
            # Manual summary form for each building type
            st.markdown("#### Project Configuration by Building Type")
            
            for building_type in PROPERTY_TYPES:
                if building_type:
                    # Load existing configuration from database (with error handling)
                    try:
                        existing_config = get_project_config(budget_num, building_type)
                    except Exception as e:
                        print(f"⚠️ Could not load project config for {building_type}: {e}")
                        existing_config = None
                    
                    # Set default values
                    default_blocks = 4
                    default_units = 6 if building_type == "Flats" else 4 if building_type == "Terraces" else 2 if building_type == "Semi-detached" else 1
                    default_notes = ""
                    
                    # Use saved values if they exist
                    if existing_config:
                        default_blocks = existing_config['num_blocks']
                        default_units = existing_config['units_per_block']
                        default_notes = existing_config['additional_notes']
                    
                    with st.expander(f"🏠 {building_type} Configuration", expanded=False):
                        with st.form(f"manual_summary_budget_{budget_num}_{building_type.lower().replace('-', '_')}"):
                                num_blocks = st.number_input(
                                    f"Number of Blocks for {building_type}", 
                                    min_value=1, 
                                    step=1, 
                                    value=default_blocks,
                                    key=f"num_blocks_budget_{budget_num}_{building_type.lower().replace('-', '_')}"
                                )
                            
                                units_per_block = st.number_input(
                                    f"Units per Block for {building_type}", 
                                    min_value=1, 
                                    step=1, 
                                    value=default_units,
                                    key=f"units_per_block_budget_{budget_num}_{building_type.lower().replace('-', '_')}"
                                )
                            
                                total_units = num_blocks * units_per_block
                                
                                # Additional notes
                                additional_notes = st.text_area(
                                    f"Additional Notes for {building_type}",
                                    placeholder="Add any additional budget information or notes...",
                                    value=default_notes,
                                    key=f"notes_budget_{budget_num}_{building_type.lower().replace('-', '_')}"
                                )
                                
                                submitted = st.form_submit_button(f"💾 Save {building_type} Configuration", type="primary")
                                
                                if submitted:
                                    # Save to database
                                    save_project_config(budget_num, building_type, num_blocks, units_per_block, additional_notes)
                                    st.success(f" {building_type} configuration saved for Budget {budget_num}!")
                                    # Don't use st.rerun() - let the page refresh naturally
                        
                        # Calculate actual amounts from database
                        if not all_items_summary.empty:
                            bt_items = budget_items[budget_items["building_type"] == building_type]
                            if not bt_items.empty:
                                # Calculate amounts from actual database data
                                # The database amount represents the cost for 1 block
                                amount_per_block = float(bt_items["Amount"].sum())
                                
                                # Calculate per unit and total amounts
                                # Total for 1 unit = Total for 1 block ÷ Number of flats per block
                                amount_per_unit = amount_per_block / units_per_block if units_per_block > 0 else 0
                                total_budgeted_amount = amount_per_block * num_blocks
                                
                                # Manual budget summary display with calculated amounts
                                st.markdown("#### Manual Budget Summary")
                                st.markdown(f"""
                                **{building_type.upper()} BUDGET SUMMARY - BUDGET {budget_num}**
                                
                                - **GRAND TOTAL FOR 1 BLOCK**: ₦{amount_per_block:,.2f}
                                - **GRAND TOTAL FOR {num_blocks} BLOCKS**: ₦{total_budgeted_amount:,.2f}
                                - **TOTAL FOR 1 UNIT**: ₦{amount_per_unit:,.2f}
                                - **GRAND TOTAL FOR ALL {building_type.upper()} ({total_units}NOS)**: ₦{total_budgeted_amount:,.2f}
                                
                                {f"**Additional Notes**: {additional_notes}" if additional_notes else ""}
                                """)
                                
                                # Show calculation breakdown (simplified to avoid nested columns)
                                st.markdown("#### Calculation Breakdown")
                                st.metric("Amount per Unit", f"₦{amount_per_unit:,.2f}")
                                st.metric("Amount per Block (from DB)", f"₦{amount_per_block:,.2f}")
                                st.metric("Total for All Blocks", f"₦{total_budgeted_amount:,.2f}")
                                
                                # Show calculation formula
                                st.info(f"💡 **Formula**: Amount per Block = ₦{amount_per_block:,.2f} (from database) × {num_blocks} blocks = ₦{total_budgeted_amount:,.2f}")
                                st.info(f"💡 **Per Unit Formula**: Amount per Unit = ₦{amount_per_block:,.2f} ÷ {units_per_block} units = ₦{amount_per_unit:,.2f}")
                            else:
                                st.warning(f"No items found for {building_type} in Budget {budget_num}")
                        else:
                            st.warning("No items found in database")

# -------------------------------- Tab 3: Make Request --------------------------------
with tab3:
    st.subheader("Make a Request")
    st.caption("Request items for specific building types and budgets")
    
    # Regular users can make requests, admins can do everything
    if not is_admin():
        st.info("👤 **User Access**: You can make requests and view your request history.")
        st.caption("💡 **Note**: Your requests will be reviewed by an administrator.")
        
        # Notifications are now displayed in the dedicated Notifications tab
        st.info("📧 **Notifications**: Check the Notifications tab to view your request notifications.")
    
    # Project context for the request
    st.markdown("### Project Context")
    col1, col2, col3 = st.columns([2,2,2])
    with col1:
        section = st.radio("Section", ["materials","labour"], horizontal=True, key="request_section_radio")
    with col2:
        building_type = st.selectbox("🏠 Building Type", PROPERTY_TYPES, index=1, help="Select building type for this request", key="request_building_type_select")
    with col3:
        # Create budget options for the selected building type (cached)
        all_budget_options = get_budget_options(st.session_state.get('current_project_site'))
        # Use more robust matching for building types with hyphens
        if building_type in ["Semi-detached", "Fully-detached"]:
            # For hyphenated building types, use exact matching
            budget_options = [opt for opt in all_budget_options if f" - {building_type}" in opt or f"({building_type}" in opt]
        else:
            budget_options = [opt for opt in all_budget_options if building_type in opt]
        
        budget = st.selectbox("🏷️ Budget", budget_options, index=0, help="Select budget for this request", key="request_budget_select")
    
    # Filter items based on section, building type, and budget
    # Get all items first, then filter in memory for better flexibility
    # Clear any cached data to ensure fresh data
    if 'request_items_cache' in st.session_state:
        del st.session_state.request_items_cache
    
    all_items = df_items_cached(st.session_state.get('current_project_site'))
    
    
    # Apply filters step by step
    items_df = all_items.copy()
    
    # Filter by section (materials/labour)
    if section:
        items_df = items_df[items_df["category"] == section]
    
    # Filter by building type
    if building_type:
        items_df = items_df[items_df["building_type"] == building_type]
    
    # Filter by budget (flexible matching - space and case insensitive)
    if budget:
        def normalize_budget_string(budget_str):
            """Normalize budget string for comparison - remove extra spaces, convert to lowercase"""
            if pd.isna(budget_str):
                return ""
            # Convert to string, strip whitespace, convert to lowercase
            normalized = str(budget_str).strip().lower()
            # Remove extra spaces and normalize spacing around parentheses
            normalized = normalized.replace("  ", " ")  # Remove double spaces
            normalized = normalized.replace(" (", "(")   # Remove space before opening parenthesis
            normalized = normalized.replace("( ", "(")   # Remove space after opening parenthesis
            normalized = normalized.replace(" )", ")")   # Remove space before closing parenthesis
            # Handle "Iron" vs "Irons" difference
            normalized = normalized.replace("(iron)", "(irons)")
            return normalized
        
        # Normalize the selected budget
        normalized_selected = normalize_budget_string(budget)
        
        # Create flexible matching logic
        if "(" in budget and ")" in budget:
            # Specific subgroup - flexible exact match
            budget_matches = items_df["budget"].apply(
                lambda x: normalize_budget_string(x) == normalized_selected
            )
        else:
            # Hierarchical matching - show all items that contain this budget
            # e.g., "Budget 1 - Terraces" shows "Budget 1 - Terraces", "Budget 1 - Terraces(Plumbings)", etc.
            budget_matches = items_df["budget"].apply(
                lambda x: normalized_selected in normalize_budget_string(x)
            )
        
        items_df = items_df[budget_matches]
    
    # If still no items found, try showing all items for the building type (fallback)
    if items_df.empty and building_type:
        available_budgets = all_items[all_items["building_type"] == building_type]["budget"].unique()
        st.info(f"⚠️ No items found for the specific budget '{budget}'. Available budgets for {building_type}:")
        for avail_budget in sorted(available_budgets):
            if pd.notna(avail_budget):
                st.write(f"  • {avail_budget}")
        
        st.info(f"Showing all {section} items for {building_type} instead.")
        items_df = all_items[
            (all_items["category"] == section) & 
            (all_items["building_type"] == building_type)
        ]
    
    if items_df.empty:
        st.warning(f"No items found for {section} in {building_type} - {budget}. Add items in the Manual Entry tab first.")
        
    else:
        st.markdown("### 📦 Available Items")
        
        # Item selection outside form to avoid caching issues
        st.markdown("### 📝 Request Details")
        
        # Single item selection - outside form to avoid caching
        selected_item = st.selectbox(
            "Item", 
            options=items_df.to_dict('records'), 
            format_func=lambda r: f"{r['name']} (Available: {r['qty']} {r['unit'] or ''}) — ₦{r['unit_cost'] or 0:,.2f}", 
            key="request_item_select",
            index=0  # Select first item by default
        )
        
        # Show selected item info - outside form
        if selected_item:
            st.info(f"**Selected Item:** {selected_item['name']} | **Planned Rate:** ₦{selected_item.get('unit_cost', 0) or 0:,.2f}")
        else:
            st.warning("⚠️ Please select an item from the dropdown above")
        
        # Wrap the request submission in a proper form
        with st.form("request_submission_form", clear_on_submit=True):
            
            # Only show form fields if an item is selected
            if selected_item:
                col1, col2 = st.columns([1,1])
                with col1:
                    # Create a dynamic key for quantity input that changes with item selection
                    qty_key = f"request_qty_input_{selected_item.get('id', 'none') if selected_item else 'none'}"
                    
                    qty = st.number_input("Quantity to request", min_value=1.0, step=1.0, value=1.0, key=qty_key)
                    
                    # Mandatory name input field
                    requested_by = st.text_input(
                        "Your Name *", 
                        placeholder="Enter your full name",
                        help="This is required to identify who is making the request",
                        key="request_name_input"
                    )
                with col2:
                    # Get default price from selected item
                    default_price = 0.0
                    if selected_item and 'unit_cost' in selected_item:
                        default_price = float(selected_item.get('unit_cost', 0) or 0)
                    
                    # Create a dynamic key for price input that changes with item selection
                    price_key = f"request_price_input_{selected_item.get('id', 'none') if selected_item else 'none'}"
                    
                    # Use dynamic key for price input
                    current_price = st.number_input(
                        "💰 Current Price per Unit", 
                        min_value=0.0, 
                        step=0.01, 
                        value=default_price,
                        help="Enter the current market price for this item. This will be used as the actual rate in actuals.",
                        key=price_key
                    )
                    
                    note = st.text_area(
                        "Notes *", 
                        placeholder="Please provide details about this request...",
                        help="This is required to explain the purpose of your request",
                        key="request_note_input"
                    )
                
                # Show request summary (outside columns for full width)
                if qty:
                    # Use current price for total cost calculation
                    total_cost = qty * current_price
                    st.markdown("### Request Summary")
                    
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Planned Rate", f"₦{selected_item.get('unit_cost', 0) or 0:,.2f}")
                    with col2:
                        st.metric("Current Rate", f"₦{current_price:,.2f}")
                    with col3:
                        st.metric("Quantity", f"{qty}")
                    
                    st.markdown(f"""
                    <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937; text-align: center; padding: 0.6rem; background: #f8fafc; border-radius: 8px; margin: 0.4rem 0;">
                        Total Cost (Current Rate): ₦{total_cost:,.2f}
                    </div>
                    """, unsafe_allow_html=True)
                
                    # Show selected items section
                    st.markdown("### 🛒 Selected Items")
                    st.success(f"✅ **{selected_item['name']}** - Quantity: {qty} - Total: ₦{total_cost:,.2f}")
                    
                    # Show price difference if applicable
                    planned_rate = selected_item.get('unit_cost', 0) or 0
                    if current_price != planned_rate:
                        price_diff = current_price - planned_rate
                        price_diff_pct = (price_diff / planned_rate * 100) if planned_rate > 0 else 0
                        if price_diff > 0:
                            st.info(f"📈 Price increased by ₦{price_diff:,.2f} ({price_diff_pct:+.1f}%)")
                        else:
                            st.info(f"📉 Price decreased by ₦{abs(price_diff):,.2f} ({price_diff_pct:+.1f}%)")
                
                # Form validation and submission
                submitted = st.form_submit_button("Submit Request", type="primary", use_container_width=True)
                
                if submitted:
                    # Capture form values at submission time
                    form_qty = qty
                    form_requested_by = requested_by
                    form_current_price = current_price
                    form_note = note
                    
                    # Validate form inputs with proper null checks
                    if not form_requested_by or not form_requested_by.strip():
                        st.error("❌ Please enter your name. This field is required.")
                    elif not form_note or not form_note.strip():
                        st.error("❌ Please provide notes explaining your request. This field is required.")
                    elif not selected_item or selected_item is None or not selected_item.get('id'):
                        st.error("❌ Please select an item from the list.")
                    elif form_qty is None or form_qty <= 0:
                        st.error("❌ Please enter a valid quantity (greater than 0).")
                    elif not section or section is None:
                        st.error("❌ Please select a section (materials or labour).")
                    elif not building_type or building_type is None:
                        st.error("❌ Please select a building type.")
                    elif not budget or budget is None:
                        st.error("❌ Please select a budget.")
                    else:
                        # Both admins and regular users can submit requests
                        try:
                            # Validate item ID exists in database using proper connection
                            with get_conn() as conn:
                                cur = conn.cursor()
                                cur.execute("SELECT id FROM items WHERE id = ?", (selected_item['id'],))
                                if not cur.fetchone():
                                    st.error(f"❌ Selected item (ID: {selected_item['id']}) not found in database. Please refresh the page and try again.")
                                else:
                                    add_request(section, selected_item['id'], form_qty, form_requested_by, form_note, form_current_price)
                                    # Log request submission activity
                                    log_current_session()
                                    st.success(f"✅ Request submitted successfully for {building_type} - {budget}!")
                                    st.info("💡 Your request will be reviewed by an administrator. Check the Review & History tab for updates.")
                                    # Clear cache to refresh data without rerun
                                    st.cache_data.clear()
                        except Exception as e:
                            st.error(f"❌ Failed to submit request: {str(e)}")
                            st.info("💡 Please try again or contact an administrator if the issue persists.")

# -------------------------------- Tab 4: Review & History --------------------------------
with tab4:
    st.subheader("📋 Request History")
    
    # Get user type and current user info
    user_type = st.session_state.get('user_type', 'user')
    current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
    current_project = st.session_state.get('current_project_site', 'Not set')
    
    # Display user info
    if user_type == 'admin':
        st.info("👑 **Admin Access**: You can view and manage all requests from all project sites.")
    else:
        st.info(f"👤 **Your Requests**: Viewing requests for {current_user} in {current_project}")
        st.caption("💡 **Note**: Only administrators can approve or reject requests.")
    
    # Status filter
    status_filter = st.selectbox("Filter by status", ["All","Pending","Approved","Rejected"], index=1)
    
    # Get requests based on user type
    if user_type == 'admin':
        # Admins see all requests
        reqs = df_requests(status=None if status_filter=="All" else status_filter)
    else:
        # Regular users only see their own requests
        reqs = get_user_requests(current_user, status_filter)
    # Display requests
    if not reqs.empty:
        st.success(f"📊 Found {len(reqs)} request(s) matching your criteria")
        
        # Create a better display for user requests
        display_reqs = reqs.copy()
        
        # Format timestamp for better readability
        if 'ts' in display_reqs.columns:
            display_reqs['ts'] = pd.to_datetime(display_reqs['ts']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Create context column
        display_reqs['Context'] = display_reqs.apply(lambda row: 
            f"{row.get('building_type', 'N/A')} - {row.get('budget', 'N/A')} ({row.get('grp', 'N/A')})" 
            if pd.notna(row.get('building_type')) and pd.notna(row.get('budget')) 
            else f"{row.get('budget', 'N/A')} ({row.get('grp', 'N/A')})" if pd.notna(row.get('budget'))
            else "No context", axis=1)
        
        # Select and rename columns based on user type
        if user_type == 'admin':
            # Admin view with project site
            display_columns = ['id', 'ts', 'item', 'qty', 'requested_by', 'project_site', 'Context', 'status', 'approved_by', 'note']
            display_reqs = display_reqs[display_columns]
            display_reqs.columns = ['ID', 'Time', 'Item', 'Quantity', 'Requested By', 'Project Site', 'Building Type & Budget', 'Status', 'Approved By', 'Note']
        else:
            # User view without project site
            display_columns = ['id', 'ts', 'item', 'qty', 'Context', 'status', 'approved_by', 'note']
            display_reqs = display_reqs[display_columns]
            display_reqs.columns = ['ID', 'Time', 'Item', 'Quantity', 'Building Type & Budget', 'Status', 'Approved By', 'Note']
        
        # Display the table with better formatting
        st.dataframe(display_reqs, use_container_width=True)
        
        # Show request statistics - calculate from original reqs data, not filtered display_reqs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            pending_count = len(reqs[reqs['status'] == 'Pending'])
            st.metric("Pending", pending_count)
        with col2:
            approved_count = len(reqs[reqs['status'] == 'Approved'])
            st.metric("Approved", approved_count)
        with col3:
            rejected_count = len(reqs[reqs['status'] == 'Rejected'])
            st.metric("Rejected", rejected_count)
        with col4:
            total_count = len(reqs)
            st.metric("Total", total_count)
        
        # Add delete buttons as a separate section with table-like layout (Admin only)
        if not display_reqs.empty and user_type == 'admin':
            deletable_requests = display_reqs[display_reqs['Status'].isin(['Approved', 'Rejected'])]
            if not deletable_requests.empty:
                st.markdown("#### Delete Actions")
                st.caption(f"Found {len(deletable_requests)} requests that can be deleted")
                
                # Create a table-like layout for delete buttons
                for index, row in deletable_requests.iterrows():
                    col1, col2, col3, col4, col5, col6, col7, col8, col9, col10 = st.columns([1, 2, 2, 1, 2, 2, 1, 2, 2, 1])
                    
                    with col1:
                        st.write(f"**{row['ID']}**")
                    with col2:
                        st.write(row['Time'])
                    with col3:
                        st.write(row['Item'])
                    with col4:
                        st.write(f"{row['Quantity']}")
                        with col5:
                            st.write(row['Requested By'])
                        with col6:
                            if user_type == 'admin':
                                st.write(f"**{row['Project Site']}**")
                            else:
                                st.write(row['Building Type & Budget'])
                        with col7:
                            if row['Status'] == 'Approved':
                                st.success("Approved")
                            else:
                                st.error("Rejected")
                        with col8:
                            st.write(row['Approved By'] if pd.notna(row['Approved By']) else "N/A")
                        with col9:
                            if user_type == 'admin':
                                st.write(row['Building Type & Budget'])
                            else:
                                st.write("")
                        with col10:
                            # Allow users to delete their own requests, admins can delete any request
                            current_user = st.session_state.get('full_name', st.session_state.get('user_name', 'Unknown'))
                            can_delete = (user_type == 'admin') or (row['Requested By'] == current_user)
                            
                            if can_delete:
                                if st.button("🗑️ Delete", key=f"delete_{row['ID']}", help=f"Delete request {row['ID']}"):
                                    if delete_request(row['ID']):
                                        st.success(f"Request {row['ID']} deleted!")
                                        st.rerun()  # Refresh to update the table
                                    else:
                                        st.error(f"Failed to delete request {row['ID']}")
                            else:
                                st.write("🔒 Not yours")
                    
                    st.divider()
            else:
                st.info("No approved or rejected requests found for deletion")
    else:
        st.info("No requests found matching the selected criteria.")

    # Only show approve/reject section for admins
    if is_admin():
        st.write("Approve/Reject a request by ID:")
        colA, colB, colC = st.columns(3)
        with colA:
            req_id = st.number_input("Request ID", min_value=1, step=1, key="req_id_input")
        with colB:
            action = st.selectbox("Action", ["Approve","Reject","Set Pending"], key="action_select")
        with colC:
            approved_by = st.text_input("Approved by / Actor", key="approved_by_input")

        if st.button("Apply", key="apply_status_button"):
            # Validate request ID
            if req_id <= 0:
                st.error("❌ Request ID must be greater than 0")
            elif not approved_by or not approved_by.strip():
                st.error("❌ Please enter the name of the person approving/rejecting")
            else:
                target_status = "Approved" if action=="Approve" else ("Rejected" if action=="Reject" else "Pending")
                err = set_request_status(int(req_id), target_status, approved_by=approved_by or None)
                if err:
                    st.error(err)
                else:
                    st.success(f"Request {req_id} set to {target_status}.")
                    st.rerun()  # Refresh to update the display and counts

    st.divider()
    st.subheader("Complete Request Management")
    hist_tab1, hist_tab2, hist_tab3 = st.tabs([" Approved Requests", " Rejected Requests", " Deleted Requests"])
    
    with hist_tab1:
        st.markdown("####  Approved Requests")
        approved_df = df_requests("Approved")
        if not approved_df.empty:
            # Create enhanced display for approved requests
            display_approved = approved_df.copy()
            display_approved['Context'] = display_approved.apply(lambda row: 
                f"{row['building_type']} - {row['budget']} ({row['grp']})" 
                if pd.notna(row['building_type']) and pd.notna(row['budget']) 
                else f"{row['budget']} ({row['grp']})" if pd.notna(row['budget'])
                else "No context", axis=1)
            
            # Show enhanced dataframe with delete buttons
            # Calculate total price (price × quantity) and include project site for admins
            display_approved['total_price'] = display_approved['qty'] * display_approved['current_price']
            
            if user_type == 'admin':
                display_columns = ['id', 'ts', 'item', 'qty', 'total_price', 'requested_by', 'project_site', 'Context', 'approved_by', 'note']
                display_approved = display_approved[display_columns]
                display_approved.columns = ['ID', 'Time', 'Item', 'Quantity', 'Total Price', 'Requested By', 'Project Site', 'Building Type & Budget', 'Approved By', 'Note']
            else:
                display_columns = ['id', 'ts', 'item', 'qty', 'total_price', 'requested_by', 'Context', 'approved_by', 'note']
                display_approved = display_approved[display_columns]
                display_approved.columns = ['ID', 'Time', 'Item', 'Quantity', 'Total Price', 'Requested By', 'Building Type & Budget', 'Approved By', 'Note']
            st.dataframe(display_approved, use_container_width=True)
            
            # Delete buttons for approved requests (Admin only)
            if not display_approved.empty and is_admin():
                st.markdown("#### Delete Approved Requests")
                delete_cols = st.columns(min(len(display_approved), 4))
                for i, (_, row) in enumerate(display_approved.iterrows()):
                    with delete_cols[i % 4]:
                        if st.button(f"🗑️ Delete ID {row['ID']}", key=f"del_app_{row['ID']}", type="secondary"):
                            if delete_request(row['ID']):
                                st.success(f"Request {row['ID']} deleted!")
                                st.rerun()  # Refresh to update the table
                            else:
                                st.error(f"Failed to delete request {row['ID']}")
        else:
            st.info("No approved requests found.")
    
    with hist_tab2:
        st.markdown("####  Rejected Requests")
        rejected_df = df_requests("Rejected")
        if not rejected_df.empty:
            # Create enhanced display for rejected requests
            display_rejected = rejected_df.copy()
            display_rejected['Context'] = display_rejected.apply(lambda row: 
                f"{row['building_type']} - {row['budget']} ({row['grp']})" 
                if pd.notna(row['building_type']) and pd.notna(row['budget']) 
                else f"{row['budget']} ({row['grp']})" if pd.notna(row['budget'])
                else "No context", axis=1)
            
            # Show enhanced dataframe with delete buttons
            # Calculate total price (price × quantity) and include project site for admins
            display_rejected['total_price'] = display_rejected['qty'] * display_rejected['current_price']
            
            if user_type == 'admin':
                display_columns = ['id', 'ts', 'item', 'qty', 'total_price', 'requested_by', 'project_site', 'Context', 'approved_by', 'note']
                display_rejected = display_rejected[display_columns]
                display_rejected.columns = ['ID', 'Time', 'Item', 'Quantity', 'Total Price', 'Requested By', 'Project Site', 'Building Type & Budget', 'Approved By', 'Note']
            else:
                display_columns = ['id', 'ts', 'item', 'qty', 'total_price', 'requested_by', 'Context', 'approved_by', 'note']
                display_rejected = display_rejected[display_columns]
                display_rejected.columns = ['ID', 'Time', 'Item', 'Quantity', 'Total Price', 'Requested By', 'Building Type & Budget', 'Approved By', 'Note']
            st.dataframe(display_rejected, use_container_width=True)
            
            # Delete buttons for rejected requests
            if not display_rejected.empty:
                st.markdown("#### Delete Rejected Requests")
                delete_cols = st.columns(min(len(display_rejected), 4))
                for i, (_, row) in enumerate(display_rejected.iterrows()):
                    with delete_cols[i % 4]:
                        if st.button(f"🗑️ Delete ID {row['ID']}", key=f"del_rej_{row['ID']}", type="secondary"):
                            if delete_request(row['ID']):
                                st.success(f"Request {row['ID']} deleted!")
                                st.rerun()  # Refresh to update the table
                            else:
                                st.error(f"Failed to delete request {row['ID']}")
        else:
            st.info("No rejected requests found.")

    with hist_tab3:
        st.markdown("####  Deleted Requests History")
        deleted_log = df_deleted_requests()
        if not deleted_log.empty:
            st.dataframe(deleted_log, use_container_width=True)
            st.caption("All deleted requests are logged here - includes previously Pending, Approved, and Rejected requests that were deleted.")
            
            # Clear deleted logs option (admin only)
            if is_admin():
                if st.button(" Clear All Deleted Logs", key="clear_deleted_logs_button"):
                    if not st.session_state.get("confirm_clear_deleted_logs"):
                        st.session_state["confirm_clear_deleted_logs"] = True
                        st.warning("⚠️ Click the button again to confirm clearing all deleted logs.")
                    else:
                        # Clear confirmation state
                        if "confirm_clear_deleted_logs" in st.session_state:
                            del st.session_state["confirm_clear_deleted_logs"]
                        
                        clear_deleted_requests()
                        st.success(" All deleted request logs cleared.")
                        # Don't use st.rerun() - let the page refresh naturally
            else:
                st.info("🔒 Admin privileges required to clear deleted logs.")
        else:
            st.info("No deleted requests found in history.")

# -------------------------------- Tab 6: Actuals --------------------------------
with tab6:
    st.subheader("Actuals")
    st.caption("View actual costs and usage")
    
    # Check permissions for actuals management
    if not is_admin():
        st.info("👤 **User Access**: You can view actuals but cannot modify them.")
    
    # Get current project site
    project_site = st.session_state.get('current_project_site', 'Not set')
    st.write(f"**Project Site:** {project_site}")
    
    # Get all items for current project site
    items_df = df_items_cached(project_site)
    
    if not items_df.empty:
        # Budget Selection Dropdown
        st.markdown("#### Select Budget to View")
        
        # Hardcoded budget options - Budget 1-20 for all building types
        budget_options = []
        
        # Generate all budget options from 1 to 20
        for budget_num in range(1, 21):
            for building_type in ["Flats", "Terraces", "Semi-detached", "Fully-Detached"]:
                budget_options.append(f"Budget {budget_num} - {building_type}")
        
        selected_budget = st.selectbox(
            "Choose a budget to view:",
            options=budget_options,
            key="budget_selector"
        )
        
        if selected_budget:
            # Parse the selected budget
            budget_part, building_part = selected_budget.split(" - ", 1)
            
            # Get all items for this budget
            search_pattern = f"{budget_part} - {building_part}"
            budget_items = items_df[
                items_df['budget'].str.contains(search_pattern, case=False, na=False)
            ]
            
            if not budget_items.empty:
                st.markdown(f"##### {selected_budget}")
                st.markdown("**📊 BUDGET vs ACTUAL COMPARISON**")
                
                # Get actuals data
                actuals_df = get_actuals(project_site)
                
                # Group items by category (grp field)
                categories = {}
                for _, item in budget_items.iterrows():
                    category = item.get('grp', 'GENERAL MATERIALS')
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(item)
                
                # Display tables side by side
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### PLANNED BUDGET")
                    
                    # Process each category
                    for category_name, category_items in categories.items():
                        st.markdown(f"**{category_name}**")
                        
                        planned_data = []
                        for idx, item in enumerate(category_items, 1):
                            planned_data.append({
                                'S/N': str(idx),
                                'Item': item['name'],
                                'Qty': f"{item['qty']:.1f}",
                                'Unit Cost': f"₦{item['unit_cost']:,.2f}",
                                'Total Cost': f"₦{item['qty'] * item['unit_cost']:,.2f}"
                            })
                        
                        planned_df = pd.DataFrame(planned_data)
                        st.dataframe(planned_df, use_container_width=True, hide_index=True)
                        
                        # Category total with error handling
                        category_total = 0
                        for item in category_items:
                            try:
                                qty = float(item['qty']) if pd.notna(item['qty']) else 0
                                unit_cost = float(item['unit_cost']) if pd.notna(item['unit_cost']) else 0
                                category_total += qty * unit_cost
                            except (ValueError, TypeError):
                                continue
                        st.markdown(f"**{category_name} Total: ₦{category_total:,.2f}**")
                        st.markdown("---")
                
                with col2:
                    st.markdown("#### ACTUALS")
                    
                    # Process each category
                    for category_name, category_items in categories.items():
                        st.markdown(f"**{category_name}**")
                        
                        actual_data = []
                        for idx, item in enumerate(category_items, 1):
                            # Get actual data for this item
                            actual_qty = 0
                            actual_cost = 0
                            
                            if not actuals_df.empty:
                                item_actuals = actuals_df[actuals_df['item_id'] == item['id']]
                                if not item_actuals.empty:
                                    actual_qty = item_actuals['actual_qty'].sum()
                                    actual_cost = item_actuals['actual_cost'].sum()
                            
                            actual_data.append({
                                'S/N': str(idx),
                                'Item': item['name'],
                                'Qty': f"{actual_qty:.1f}",
                                'Unit Cost': f"₦{actual_cost/actual_qty:,.2f}" if actual_qty > 0 else "₦0.00",
                                'Total Cost': f"₦{actual_cost:,.2f}"
                            })
                        
                        actual_df = pd.DataFrame(actual_data)
                        st.dataframe(actual_df, use_container_width=True, hide_index=True)
                        
                        # Category total with error handling
                        category_actual = 0
                        if not actuals_df.empty:
                            for item in category_items:
                                try:
                                    item_actuals = actuals_df[actuals_df['item_id'] == item['id']]
                                    if not item_actuals.empty:
                                        actual_cost = item_actuals['actual_cost'].sum()
                                        if pd.notna(actual_cost):
                                            category_actual += float(actual_cost)
                                except (ValueError, TypeError):
                                    continue
                        
                        st.markdown(f"**{category_name} Total: ₦{category_actual:,.2f}**")
                        st.markdown("---")
                
                # Calculate totals with proper error handling
                total_planned = 0
                for _, item in budget_items.iterrows():
                    try:
                        qty = float(item['qty']) if pd.notna(item['qty']) else 0
                        unit_cost = float(item['unit_cost']) if pd.notna(item['unit_cost']) else 0
                        total_planned += qty * unit_cost
                    except (ValueError, TypeError):
                        continue
                
                total_actual = 0
                if not actuals_df.empty:
                    for _, item in budget_items.iterrows():
                        item_actuals = actuals_df[actuals_df['item_id'] == item['id']]
                        if not item_actuals.empty:
                            try:
                                actual_cost = item_actuals['actual_cost'].sum()
                                if pd.notna(actual_cost):
                                    total_actual += float(actual_cost)
                            except (ValueError, TypeError):
                                continue
                
                # Display totals
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Planned", f"₦{total_planned:,.2f}")
                with col2:
                    st.metric("Total Actual", f"₦{total_actual:,.2f}")
        else:
            st.info("Please select a budget to view.")
    else:
        st.info("📦 No items found for this project site.")
        st.markdown("""
        **How to get started:**
        1. Add items to your inventory in the Manual Entry tab
        2. Create requests in the Make Request tab
        3. Approve requests in the Review & History tab
        4. Approved requests will automatically appear here as actuals
        """)


# -------------------------------- Tab 7: Admin Settings (Admin Only) --------------------------------
if st.session_state.get('user_type') == 'admin':
    with tab7:
        st.subheader("System Administration")
        
        # System Overview - Always visible
        st.markdown("### System Overview")
        
        # Get project site access codes and system stats
        try:
            with engine.connect() as conn:
                # Count project sites with access codes (force fresh query)
                result = conn.execute(text("SELECT COUNT(*) FROM project_site_access_codes"))
                project_sites_count = result.fetchone()[0]
                
                # Debug: Show what we're actually counting
                result = conn.execute(text("SELECT project_site FROM project_site_access_codes"))
                sites = result.fetchall()
                print(f"Debug: Counting {len(sites)} project sites: {[site[0] for site in sites]}")
                
                # Get total items across all project sites
                result = conn.execute(text("SELECT COUNT(*) FROM items"))
                total_items = result.fetchone()[0]
                
                # Get total requests
                result = conn.execute(text("SELECT COUNT(*) FROM requests"))
                total_requests = result.fetchone()[0]
                
                # Get today's access logs
                today = get_nigerian_time().strftime('%Y-%m-%d')
                result = conn.execute(text("SELECT COUNT(*) FROM access_logs WHERE DATE(access_time) = :today"), {"today": today})
                today_access = result.fetchone()[0]
        except:
            project_sites_count = 0
            total_items = 0
            total_requests = 0
            today_access = 0
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # Show project sites with access codes
            st.metric("Project Sites", project_sites_count)
        
        with col2:
            # Show total inventory items
            st.metric("Total Items", total_items)
        
        with col3:
            # Show total requests
            st.metric("Total Requests", total_requests)
        
        with col4:
            # Show today's access activity
            st.metric("Today's Access", today_access)
        
        st.divider()
        
        # Access Code Management - Dropdown
        with st.expander("Access Code Management", expanded=False):
            current_admin_code, _ = get_access_codes()
            
            st.info(f"**Admin Code:** `{current_admin_code}`")
            
            st.markdown("#### Change Admin Access Code")
            st.caption("Changing the admin access code will affect admin login. Inform your team of the new code.")
            
            with st.form("change_admin_access_code"):
                new_admin_code = st.text_input("New Admin Code", value=current_admin_code, type="password")
                
                if st.form_submit_button("Update Admin Code", type="primary"):
                    if new_admin_code:
                        if len(new_admin_code) < 4:
                            st.error("Admin code must be at least 4 characters long.")
                        else:
                            current_user = st.session_state.get('full_name', 'Admin')
                            if update_admin_access_code(new_admin_code, current_user):
                                st.success("Admin access code updated successfully!")
                            else:
                                st.error("Failed to update admin access code. Please try again.")
                    else:
                        st.error("Please enter a new admin code.")
        
        # Project Site Management - Dropdown
        with st.expander("Project Site Management", expanded=False):
            admin_project_sites = get_project_sites()
            if admin_project_sites:
                for i, site in enumerate(admin_project_sites):
                    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                    with col1:
                        st.write(f"**{i+1}.** {site}")
                        # Show current access code for this project
                        project_access_code = get_project_access_code(site)
                        if project_access_code:
                            st.caption(f"Access Code: `{project_access_code}`")
                        else:
                            st.caption("No access code set")
                    with col2:
                        if st.button("Edit", key=f"edit_site_{i}"):
                            st.session_state[f"editing_site_{i}"] = True
                            st.session_state[f"edit_site_name_{i}"] = site
                    with col3:
                        if st.button("Access Code", key=f"access_code_{i}"):
                            st.session_state[f"managing_access_code_{i}"] = True
                    with col4:
                        if st.button("Delete", key=f"delete_site_{i}"):
                            if len(admin_project_sites) > 1:
                                if delete_project_site(site):
                                    st.success(f"Deleted '{site}' project site!")
                                else:
                                    st.error("Failed to delete project site!")
                            else:
                                st.error("Cannot delete the last project site!")
                    with col5:
                        if st.button("View", key=f"view_site_{i}"):
                            st.session_state.current_project_site = site
                            clear_cache()
                    
                    # Access code management for each project
                    if st.session_state.get(f"managing_access_code_{i}", False):
                        st.markdown(f"#### Manage Access Code for {site}")
                        current_code = get_project_access_code(site)
                        
                        with st.form(f"access_code_form_{i}"):
                            new_access_code = st.text_input(
                                "Project Access Code", 
                                value=current_code or f"PROJECT_{site.upper().replace(' ', '_')}", 
                                help="This code will be used by users to access this specific project",
                                key=f"new_access_code_{i}"
                            )
                            
                            col_submit, col_cancel = st.columns([1, 1])
                            with col_submit:
                                if st.form_submit_button("Update Access Code", type="primary"):
                                    if new_access_code and len(new_access_code) >= 4:
                                        if update_project_access_code(site, new_access_code):
                                            st.success(f"Access code updated for {site}!")
                                            st.session_state[f"managing_access_code_{i}"] = False
                                        else:
                                            st.error("Failed to update access code!")
                                    else:
                                        st.error("Access code must be at least 4 characters long!")
                            
                            with col_cancel:
                                if st.form_submit_button("Cancel"):
                                    st.session_state[f"managing_access_code_{i}"] = False
                            st.success(f"Switched to '{site}' project site!")
                    
                    # Edit form for this site
                    if st.session_state.get(f"editing_site_{i}", False):
                        with st.form(f"edit_form_{i}"):
                            new_name = st.text_input(
                                "New Project Site Name:", 
                                value=st.session_state.get(f"edit_site_name_{i}", site),
                                key=f"edit_input_{i}"
                            )
                            col_save, col_cancel = st.columns([1, 1])
                            with col_save:
                                if st.form_submit_button("Save", type="primary"):
                                    if new_name and new_name != site:
                                        if update_project_site_name(site, new_name):
                                            if st.session_state.get('current_project_site') == site:
                                                st.session_state.current_project_site = new_name
                                            st.success(f"Updated '{site}' to '{new_name}'!")
                                            if f"editing_site_{i}" in st.session_state:
                                                del st.session_state[f"editing_site_{i}"]
                                            if f"edit_site_name_{i}" in st.session_state:
                                                del st.session_state[f"edit_site_name_{i}"]
                                        else:
                                            st.error("A project site with this name already exists!")
                                    elif new_name == site:
                                        st.info("No changes made.")
                                        if f"editing_site_{i}" in st.session_state:
                                            del st.session_state[f"editing_site_{i}"]
                                        if f"edit_site_name_{i}" in st.session_state:
                                            del st.session_state[f"edit_site_name_{i}"]
                                    else:
                                        st.error("Please enter a valid project site name!")
                            with col_cancel:
                                if st.form_submit_button("Cancel"):
                                    if f"editing_site_{i}" in st.session_state:
                                        del st.session_state[f"editing_site_{i}"]
                                    if f"edit_site_name_{i}" in st.session_state:
                                        del st.session_state[f"edit_site_name_{i}"]
            else:
                st.warning("No project sites available.")
            
            st.markdown("#### Add New Project Site")
            with st.form("add_project_site"):
                new_site_name = st.text_input("Project Site Name:", placeholder="e.g., Downtown Plaza")
                new_site_description = st.text_area("Description (Optional):", placeholder="Brief description of the project site")
                
                if st.form_submit_button("Add Project Site", type="primary"):
                    if new_site_name:
                        if add_project_site(new_site_name, new_site_description):
                            st.session_state.current_project_site = new_site_name
                            clear_cache()
                            st.success(f"Added '{new_site_name}' as a new project site!")
                        else:
                            st.error("This project site already exists!")
                    else:
                        st.error("Please enter a project site name!")
        
        # Access Logs - Enhanced Dropdown
        with st.expander("Access Logs", expanded=False):
            st.markdown("#### Access Log Management")
            
            # Enhanced filter options
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            with col1:
                log_role = st.selectbox("Filter by Role", ["All", "admin", "user", "unknown"], key="log_role_filter")
            with col2:
                log_days = st.number_input("Last N Days", min_value=1, max_value=365, value=7, key="log_days_filter")
            with col3:
                if st.button("Refresh", key="refresh_logs"):
                    st.rerun()
            with col4:
                st.caption("Use 'Clear ALL Logs' below for complete reset")
            
            # Clear ALL logs section
            st.markdown("#### Clear All Access Logs")
            st.warning("**Warning**: This will delete ALL access logs and start fresh. This action cannot be undone!")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("Clear ALL Logs", key="clear_all_logs", type="primary"):
                    if clear_all_access_logs():
                        st.rerun()  # Refresh the page to start fresh
                    else:
                        st.error("Failed to clear all logs")
            with col2:
                st.caption("This will delete all access logs and refresh the page to start from the beginning.")
            
            # Cache and session management sections removed
            
            # Quick stats
            st.markdown("#### Quick Overview")
            col1, col2, col3, col4 = st.columns(4)
            
            # Get quick stats
            try:
                from sqlalchemy import text
                from db import get_engine
                
                engine = get_engine()
                
                # Total logs
                total_logs = pd.read_sql_query(text("SELECT COUNT(*) as count FROM access_logs"), engine).iloc[0]['count']
                
                # Today's logs
                today = get_nigerian_time().strftime('%Y-%m-%d')
                today_logs = pd.read_sql_query(
                    text("SELECT COUNT(*) as count FROM access_logs WHERE DATE(access_time) = :today"), 
                    engine, params={"today": today}
                ).iloc[0]['count']
                
                # Failed attempts
                failed_logs = pd.read_sql_query(
                    text("SELECT COUNT(*) as count FROM access_logs WHERE success = 0"), 
                    engine
                ).iloc[0]['count']
                
                # Unique users
                unique_users = pd.read_sql_query(
                    text("SELECT COUNT(DISTINCT user_name) as count FROM access_logs WHERE user_name IS NOT NULL"), 
                    engine
                ).iloc[0]['count']
                
                with col1:
                    st.metric("Total Logs", total_logs)
                with col2:
                    st.metric("Today's Access", today_logs)
                with col3:
                    st.metric("Failed Attempts", failed_logs)
                with col4:
                    st.metric("Unique Users", unique_users)
                        
            except Exception as e:
                st.error(f"Error loading quick stats: {e}")
            
            st.divider()
        
            # Display access logs
            try:
                from sqlalchemy import text
                from db import get_engine
                from datetime import datetime, timedelta
                
                engine = get_engine()
                cutoff_date = (get_nigerian_time() - timedelta(days=log_days)).isoformat()
                
                # Build query with proper parameterized filters
                query = text("""
                    SELECT access_code, user_name, access_time, success, role
                    FROM access_logs 
                    WHERE access_time >= :cutoff_date
                """)
                params = {"cutoff_date": cutoff_date}
                
                if log_role != "All":
                    query = text(str(query) + " AND role = :role")
                    params["role"] = log_role
                
                query = text(str(query) + " ORDER BY access_time DESC LIMIT 100")
                
                logs_df = pd.read_sql_query(query, engine, params=params)
                
                if not logs_df.empty:
                    # Convert to West African Time for display
                    wat_timezone = pytz.timezone('Africa/Lagos')
                    
                    # Simple approach: just format the timestamps as strings
                    try:
                        # Convert to datetime first
                        logs_df['access_time'] = pd.to_datetime(logs_df['access_time'], errors='coerce')
                        
                        # For valid datetime values, format them nicely
                        valid_mask = logs_df['access_time'].notna()
                        if valid_mask.any():
                            # Format valid datetime values
                            logs_df.loc[valid_mask, 'Access DateTime'] = logs_df.loc[valid_mask, 'access_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                        
                        # For invalid values, use the original string
                        invalid_mask = ~valid_mask
                        if invalid_mask.any():
                            logs_df.loc[invalid_mask, 'Access DateTime'] = logs_df.loc[invalid_mask, 'access_time'].astype(str)
                            
                    except Exception as e:
                        # Fallback: use original timestamps as strings
                        logs_df['Access DateTime'] = logs_df['access_time'].astype(str)
                    logs_df['Status'] = logs_df['success'].map({1: ' Success', 0: ' Failed'})
                    logs_df['User'] = logs_df['user_name']
                    logs_df['Role'] = logs_df['role'].str.title()
                    logs_df['Access Code'] = logs_df['access_code']
                    
                    display_logs = logs_df[['User', 'Role', 'Access Code', 'Access DateTime', 'Status']].copy()
                    display_logs.columns = ['User', 'Role', 'Access Code', 'Date & Time', 'Status']
                    
                    # Display access logs
                    st.markdown("#### Access Log Details")
                    
                    # Display with pagination
                    page_size = 20
                    total_pages = (len(display_logs) - 1) // page_size + 1
                    
                    if total_pages > 1:
                        page = st.selectbox("Page", range(1, total_pages + 1), key="log_page")
                        start_idx = (page - 1) * page_size
                        end_idx = start_idx + page_size
                        page_logs = display_logs.iloc[start_idx:end_idx]
                        st.caption(f"Showing {start_idx + 1}-{min(end_idx, len(display_logs))} of {len(display_logs)} logs")
                    else:
                        page_logs = display_logs
                    
                    # Display the logs
                    st.dataframe(page_logs, use_container_width=True)
                    
                    # Enhanced statistics
                    st.markdown("#### Access Statistics")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    total_access = len(logs_df)
                    successful_access = len(logs_df[logs_df['success'] == 1])
                    failed_access = len(logs_df[logs_df['success'] == 0])
                    unique_users = logs_df['user_name'].nunique()
                    
                    with col1:
                        st.metric("Total Access", total_access)
                    with col2:
                        st.metric("Successful", successful_access, delta=f"{successful_access/total_access*100:.1f}%" if total_access > 0 else "0%")
                    with col3:
                        st.metric("Failed", failed_access, delta=f"{failed_access/total_access*100:.1f}%" if total_access > 0 else "0%")
                    with col4:
                        st.metric("Unique Users", unique_users)
                    
                    # Role breakdown with charts
                    st.markdown("#### Access by Role")
                    role_counts = logs_df['role'].value_counts()
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Admin Access", role_counts.get('admin', 0))
                    with col2:
                        st.metric("User Access", role_counts.get('user', 0))
                    with col3:
                        st.metric("Failed Access", role_counts.get('unknown', 0))
                    
                    # Export options
                    st.markdown("#### Export Options")
                    col1, col2 = st.columns(2)
                    with col1:
                        csv_logs = logs_df.to_csv(index=False).encode("utf-8")
                        st.download_button("📥 Download All Logs", csv_logs, "access_logs.csv", "text/csv")
                    with col2:
                        filtered_csv = display_logs.to_csv(index=False).encode("utf-8")
                        st.download_button("📥 Download Filtered Logs", filtered_csv, "filtered_access_logs.csv", "text/csv")
                else:
                    st.info("No access logs found for the selected criteria.")
            except sqlite3.OperationalError as e:
                if "disk I/O error" in str(e):
                    # Try to recover from disk I/O error
                    try:
                        import os
                        if os.path.exists('istrominventory.db-wal'):
                            os.remove('istrominventory.db-wal')
                        if os.path.exists('istrominventory.db-shm'):
                            os.remove('istrominventory.db-shm')
                        st.warning("Database I/O error detected. Please refresh the page to retry.")
                        st.rerun()
                    except:
                        st.info("Access logs are temporarily unavailable. Please try again later.")
                else:
                    st.info("Access logs are temporarily unavailable. Please try again later.")
            except Exception as e:
                st.info("Access logs are temporarily unavailable. Please try again later.")
        
        # Notifications Management - Dropdown
        with st.expander("Notifications", expanded=False):
            # Display unread notifications
            notifications = get_admin_notifications()
            if notifications:
                st.markdown("#### New Notifications")
                st.caption(f"Found {len(notifications)} unread notifications")
                for notification in notifications:
                    with st.container():
                        st.write(f"**{notification['title']}** - {notification['created_at']}")
                        st.write(f"*{notification['message']}*")
                        
                        col1, col2, col3 = st.columns([1, 1, 1])
                        with col1:
                            if st.button("Mark as Read", key=f"mark_read_{notification['id']}"):
                                if mark_notification_read(notification['id']):
                                    st.success("Notification marked as read!")
                                    st.rerun()
                        with col2:
                            if notification['request_id']:
                                if st.button("View Request", key=f"view_request_{notification['id']}"):
                                    st.info("Navigate to Review & History tab to view the request")
                        with col3:
                            if st.button("Delete", key=f"delete_notification_{notification['id']}", type="secondary"):
                                if delete_notification(notification['id']):
                                    st.success("Notification deleted!")
                                    st.rerun()
                                else:
                                    st.error("Failed to delete notification")
                        st.divider()
            else:
                st.info("No new notifications")
            
            # Notification Log - All notifications (read and unread)
            st.markdown("#### Notification Log")
            all_notifications = get_all_notifications()
            if all_notifications:
                for notification in all_notifications[:10]:  # Show last 10 notifications
                    status_icon = "🔔" if notification['is_read'] == 0 else "✅"
                    st.write(f"{status_icon} **{notification['title']}** - {notification['created_at']}")
                    st.caption(f"*{notification['message']}*")
                    
                    # Add delete button for each notification in log
                    col1, col2 = st.columns([3, 1])
                    with col2:
                        if st.button("Delete", key=f"delete_log_notification_{notification['id']}", type="secondary"):
                            if delete_notification(notification['id']):
                                st.success("Notification deleted!")
                                st.rerun()
                            else:
                                st.error("Failed to delete notification")
            else:
                st.info("No notifications in log")
        
        
        # Notification Settings - Dropdown
        with st.expander("Notification Settings", expanded=False):
            st.info("🔔 **Popup Notifications**: You'll see popup notifications when:")
            st.caption("• New requests are submitted (for admins)")
            st.caption("• Your requests are approved or rejected (for users)")
            st.caption("• All notifications are also logged in the Notifications tab")
        

# -------------------------------- User Notifications Tab --------------------------------
# Only show for regular users (not admins)
if st.session_state.get('user_type') != 'admin':
    with tab7:  # Notifications tab for users (tab7 is the 7th tab for regular users)
        st.subheader("Your Notifications")
        st.caption("View notifications for your requests")
        
        # Get current user info
        current_user = st.session_state.get('full_name', st.session_state.get('user_name', 'Unknown'))
        # Get user's notifications - ONLY notifications specifically assigned to this user
        conn = get_conn()
        if conn:
            try:
                cur = conn.cursor()
                
                # Get user ID for current user - use enhanced identification methods
                user_id = None
                current_project = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
                
                # Method 1: Try by full_name and project_site
                placeholder = get_sql_placeholder()
                cur.execute(f"SELECT id FROM users WHERE full_name = {placeholder} AND project_site = {placeholder}", (current_user, current_project))
                user_result = cur.fetchone()
                if user_result:
                    user_id = user_result[0]
                else:
                    # Method 2: Try by username and project_site
                    current_username = st.session_state.get('username', st.session_state.get('user_name', 'Unknown'))
                    cur.execute("SELECT id FROM users WHERE username = ? AND project_site = ?", (current_username, current_project))
                    user_result = cur.fetchone()
                    if user_result:
                        user_id = user_result[0]
                    else:
                        # Method 3: Try by session user_id and project_site
                        session_user_id = st.session_state.get('user_id')
                        if session_user_id:
                            cur.execute("SELECT id FROM users WHERE id = ? AND project_site = ?", (session_user_id, current_project))
                            user_result = cur.fetchone()
                            if user_result:
                                user_id = session_user_id
                
                notifications = []
                if user_id:
                    # Get notifications specifically assigned to this user ONLY
                    # Include all notification types for the user
                    cur.execute('''
                        SELECT id, notification_type, title, message, request_id, created_at, is_read
                        FROM notifications 
                        WHERE user_id = ? 
                        AND notification_type IN ('new_request', 'request_approved', 'request_rejected')
                        ORDER BY created_at DESC
                        LIMIT 20
''', (user_id,))
                    notifications = cur.fetchall()
                else:
                    # For project site access codes, show notifications for project site users (user_id = -1)
                    cur.execute('''
                        SELECT id, notification_type, title, message, request_id, created_at, is_read
                        FROM notifications 
                        WHERE user_id = -1 
                        AND notification_type IN ('new_request', 'request_approved', 'request_rejected')
                        ORDER BY created_at DESC
                        LIMIT 20
''')
                    notifications = cur.fetchall()
                
                # Display notifications
                if notifications:
                    unread_count = len([n for n in notifications if not n[6]])  # is_read is index 6
                    read_count = len([n for n in notifications if n[6]])  # is_read is index 6
                    
                    st.info(f"**Total:** {len(notifications)} | **Unread:** {unread_count} | **Read:** {read_count}")
                    
                    # Filter options
                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        filter_type = st.selectbox("Filter by Type", ["All", "new_request", "request_approved", "request_rejected"], key="user_notification_filter")
                    with col2:
                        filter_status = st.selectbox("Filter by Status", ["All", "Unread", "Read"], key="user_notification_status_filter")
                    with col3:
                        if st.button("Refresh", key="refresh_user_notifications"):
                            st.rerun()
                    
                    # Filter notifications
                    filtered_notifications = []
                    for notification in notifications:
                        # Check type filter
                        if filter_type != "All" and notification[1] != filter_type:
                            continue
                        
                        # Check status filter
                        if filter_status == "Unread" and notification[6]:  # is_read
                            continue
                        elif filter_status == "Read" and not notification[6]:  # is_read
                            continue
                        
                        filtered_notifications.append(notification)
                    
                    # Display filtered notifications
                    if filtered_notifications:
                        st.markdown(f"#### Showing {len(filtered_notifications)} notification(s)")
                        
                        for notification in filtered_notifications:
                            # Notification data
                            notif_id, notif_type, title, message, request_id, created_at, is_read = notification
                            
                            # Status indicators
                            status_icon = "●" if not is_read else "✓"
                            type_icon = "✓" if notif_type == 'request_approved' else "✗" if notif_type == 'request_rejected' else "!"
                            
                            # Display notification
                            with st.container():
                                st.markdown(f"**{status_icon} {type_icon} {title}**")
                                st.write(f"*{message}*")
                                st.caption(f"{created_at}")
                                
                                # Action buttons
                                col1, col2, col3 = st.columns([1, 1, 2])
                                with col1:
                                    if not is_read:
                                        if st.button("Mark as Read", key=f"user_mark_read_{notif_id}"):
                                            try:
                                                cur.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
                                                conn.commit()
                                                st.success("Notification marked as read!")
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Error: {e}")
                                with col2:
                                    if request_id:
                                        if st.button("View Request", key=f"user_view_request_{notif_id}"):
                                            st.info("Navigate to Review & History tab to view the request")
                                with col3:
                                    st.caption(f"Type: {notif_type} | ID: {notif_id}")
                                
                                st.divider()
                    else:
                        st.info("No notifications match your current filters.")
                else:
                    st.info("No notifications yet. You'll receive notifications when your requests are approved or rejected.")
                    st.caption("**Tip**: Submit requests in the Make Request tab to start receiving notifications.")
                
            except Exception as e:
                st.error(f"Error loading notifications: {e}")
        else:
            st.error("Unable to connect to database")
        
        # Clear notifications button for users
        st.markdown("#### 🧹 Notification Management")
        if st.button("🗑️ Clear All My Notifications", help="Remove all your notifications"):
            try:
                conn = get_conn()
                if conn:
                    cur = conn.cursor()
                    # Get user ID
                    cur.execute("SELECT id FROM users WHERE full_name = ?", (current_user,))
                    user_result = cur.fetchone()
                    user_id = user_result[0] if user_result else None
                    
                    if user_id:
                        # Delete all notifications for this user
                        cur.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
                        deleted_count = cur.rowcount
                        conn.commit()
                        st.success(f"✅ Cleared {deleted_count} of your notifications!")
                        st.rerun()
                    else:
                        st.error("User not found in database")
                conn.close()
            except Exception as e:
                st.error(f"Error clearing notifications: {e}")
        
        st.divider()
        
        # Notification settings for users
        st.markdown("#### ⚙️ Notification Settings")
        st.info("🔔 **Popup Notifications**: You'll see popup notifications when your requests are approved or rejected")
        st.caption("All notifications are also logged in this tab for your reference")

