import streamlit as st
import sqlite3
import pandas as pd
import re
from functools import lru_cache
from datetime import datetime
from pathlib import Path
import time
import threading
import pytz
import shutil
import json
import os

DB_PATH = Path("istrominventory.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

# --------------- DB helpers ---------------
def get_conn():
    """Get database connection with optimized performance"""
    try:
        # Quick WAL cleanup without aggressive retries
        import os
        wal_file = 'istrominventory.db-wal'
        shm_file = 'istrominventory.db-shm'
        
        # Remove WAL files if they exist
        for file_path in [wal_file, shm_file]:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        
        # Connect with optimized settings for speed
        conn = sqlite3.connect(
            DB_PATH, 
            timeout=5.0,  # Reduced timeout for faster failure
            check_same_thread=False
        )
        
        # Optimized settings for performance
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode=DELETE")  # Avoid WAL mode
        conn.execute("PRAGMA synchronous=NORMAL")  # Faster than FULL
        conn.execute("PRAGMA cache_size=20000")  # Larger cache
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA busy_timeout=5000")  # 5 second busy timeout
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory mapping
        
        # Enable row factory
        conn.row_factory = sqlite3.Row
        return conn
        
    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "database is locked" in error_msg:
            st.warning("🔒 Database is temporarily locked. Please wait a moment and refresh the page.")
            return None
        elif "disk I/O error" in error_msg:
            # Quick WAL cleanup and retry once
            try:
                for file_path in ['istrominventory.db-wal', 'istrominventory.db-shm']:
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except:
                            pass
                # Single retry
                conn = sqlite3.connect(DB_PATH, timeout=5.0)
                conn.execute("PRAGMA journal_mode=DELETE")
                conn.row_factory = sqlite3.Row
                return conn
            except:
                st.error("🔧 Database I/O error. Please refresh the page.")
                return None
        else:
            st.error(f"Database error: {e}")
            return None
            
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

def init_db():
    """Initialize database with proper connection handling"""
    conn = get_conn()
    if conn is None:
        st.error("🔧 Failed to connect to database. Please refresh the page.")
        return
    
    try:
        cur = conn.cursor()
        # Items now carry budget/section/group context
        cur.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT NOT NULL,
            category TEXT CHECK(category IN ('materials','labour')) NOT NULL,
            unit TEXT,
            qty REAL NOT NULL DEFAULT 0,
            unit_cost REAL,
            budget TEXT,   -- e.g., "Budget 1 - Flats"
            section TEXT,  -- e.g., "SUBSTRUCTURE (EXCAVATION TO DPC LEVEL)"
            grp TEXT,       -- e.g., "MATERIAL ONLY" / "WOODS" / "PLUMBINGS"
            project_site TEXT DEFAULT 'Default Project'  -- e.g., "Lifecamp Kafe"
        );
    ''')

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
            ''', ("Istrom2026", "USER2026", "System", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        if conn:
            try:
                conn.close()
            except:
                pass

# --------------- User Authentication and Management Functions ---------------
def authenticate_by_access_code(access_code):
    """Authenticate a user by access code and return user info if successful"""
    conn = get_conn()
    if conn is None:
        return None
    
    try:
        cur = conn.cursor()
        
        # First check if it's the global admin code
        cur.execute('''
            SELECT admin_code FROM access_codes 
            ORDER BY updated_at DESC LIMIT 1
        ''')
        admin_result = cur.fetchone()
        
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
        cur.execute('''
            SELECT project_site, user_code FROM project_site_access_codes 
            WHERE user_code = ?
        ''', (access_code,))
        site_result = cur.fetchone()
        
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
        cur.execute('''
            SELECT admin_code, user_code FROM access_codes 
            ORDER BY updated_at DESC LIMIT 1
        ''')
        codes = cur.fetchone()
        
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
    finally:
        conn.close()

# Legacy password-based authentication removed - using access code system only

def create_simple_user(full_name, user_type, project_site, access_code):
    """Create a new user with simplified approach"""
    conn = get_conn()
    if conn is None:
        return False
    
    try:
        cur = conn.cursor()
        
        # Check if access code already exists in users table
        cur.execute("SELECT COUNT(*) FROM users WHERE username = ?", (access_code,))
        if cur.fetchone()[0] > 0:
            return False  # Access code already exists
        
        # Insert user into users table
        cur.execute('''
            INSERT INTO users (username, full_name, user_type, project_site, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (access_code, full_name, user_type, project_site, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 1))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"User creation error: {e}")
        return False
    finally:
        conn.close()

def delete_user(user_id):
    """Delete a user from the system"""
    conn = get_conn()
    if conn is None:
        return False
    
    try:
        cur = conn.cursor()
        
        # Get user info before deletion
        cur.execute("SELECT username, project_site FROM users WHERE id = ?", (user_id,))
        user_info = cur.fetchone()
        if user_info:
            username, project_site = user_info
            
            # Delete user from users table
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
            
            # Delete associated access code
            cur.execute("DELETE FROM project_site_access_codes WHERE user_code = ? AND project_site = ?", (username, project_site))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"User deletion error: {e}")
        return False
    finally:
        conn.close()

def get_user_by_username(username):
    """Get user information by username"""
    conn = get_conn()
    if conn is None:
        return None
    
    try:
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
    finally:
        conn.close()

def get_all_users():
    """Get all users for admin management"""
    conn = get_conn()
    if conn is None:
        return []
    
    try:
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
    finally:
        conn.close()

def is_admin():
    """Check if current user is admin"""
    return st.session_state.get('user_type') == 'admin'

def get_user_project_site():
    """Get current user's project site"""
    return st.session_state.get('project_site', 'Lifecamp Kafe')

def create_notification(notification_type, title, message, user_id=None, request_id=None):
    """Create a notification for admins"""
    conn = get_conn()
    if conn is None:
        print("❌ Database connection failed for notification creation")
        return False
    
    try:
        cur = conn.cursor()
        
        # Debug: Log what we're trying to insert
        print(f"🔔 Creating notification: type={notification_type}, user_id='{user_id}', title='{title}'")
        
        cur.execute('''
            INSERT INTO notifications (notification_type, title, message, user_id, request_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (notification_type, title, message, user_id, request_id))
        
        conn.commit()
        
        # Debug: Verify what was actually inserted
        cur.execute('SELECT id, user_id FROM notifications WHERE id = ?', (cur.lastrowid,))
        result = cur.fetchone()
        print(f"✅ Notification created with ID: {result[0]}, user_id: '{result[1]}'")
        
        return True
    except Exception as e:
        print(f"❌ Notification creation error: {e}")
        st.error(f"Notification creation error: {e}")
        return False
    finally:
        conn.close()

def get_admin_notifications():
    """Get unread notifications for admins"""
    conn = get_conn()
    if conn is None:
        print("❌ Database connection failed for notifications")
        return []
    
    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at,
                   u.full_name as requester_name
            FROM notifications n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE n.is_read = 0
            ORDER BY n.created_at DESC
            LIMIT 10
        ''')
        
        notifications = []
        for row in cur.fetchall():
            notifications.append({
                'id': row[0],
                'type': row[1],
                'title': row[2],
                'message': row[3],
                'request_id': row[4],
                'created_at': row[5],
                'requester_name': row[6]
            })
        
        print(f"🔍 Found {len(notifications)} unread notifications")
        return notifications
    except Exception as e:
        print(f"❌ Notification retrieval error: {e}")
        st.error(f"Notification retrieval error: {e}")
        return []
    finally:
        conn.close()

def get_all_notifications():
    """Get all notifications (read and unread) for admin log"""
    conn = get_conn()
    if conn is None:
        return []
    
    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at, n.is_read,
                   u.full_name as requester_name
            FROM notifications n
            LEFT JOIN users u ON n.user_id = u.id
            ORDER BY n.created_at DESC
            LIMIT 20
        ''')
        
        notifications = []
        for row in cur.fetchall():
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
    finally:
        conn.close()

def get_user_notifications():
    """Get notifications for the current user"""
    conn = get_conn()
    if conn is None:
        return []
    
    try:
        cur = conn.cursor()
        current_user = st.session_state.get('user_name', 'Unknown')
        
        # Debug: Show what user we're looking for
        print(f"🔍 Looking for notifications for user: '{current_user}'")
        
        # Try exact match first
        cur.execute('''
            SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at, n.is_read, n.user_id
            FROM notifications n
            WHERE n.user_id = ?
            ORDER BY n.created_at DESC
            LIMIT 10
        ''', (current_user,))
        
        notifications = cur.fetchall()
        
        # If no exact match, try to find notifications by request ownership
        if not notifications:
            print(f"🔍 No exact match for user '{current_user}', trying request ownership...")
            cur.execute('''
                SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at, n.is_read, n.user_id
                FROM notifications n
                JOIN requests r ON n.request_id = r.id
                WHERE r.requested_by = ?
                ORDER BY n.created_at DESC
                LIMIT 10
            ''', (current_user,))
            notifications = cur.fetchall()
            print(f"🔍 Found {len(notifications)} notifications by request ownership")
        
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
        
        print(f"🔍 Found {len(notification_list)} notifications for user '{current_user}'")
        return notification_list
    except Exception as e:
        st.error(f"User notification retrieval error: {e}")
        return []
    finally:
        conn.close()

def mark_notification_read(notification_id):
    """Mark a notification as read"""
    conn = get_conn()
    if conn is None:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (notification_id,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Notification update error: {e}")
        return False
    finally:
        conn.close()

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
    try:
        data = json.loads(json_data)
        
        with get_conn() as conn:
            cur = conn.cursor()
            
            # Clear existing data
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
    df_items_cached.clear()
    get_summary_data.clear()
    get_budget_options.clear()
    get_section_options.clear()
    df_items.clear()

def clear_all_caches():
    """Clear all caches and force refresh"""
    st.cache_data.clear()
    if hasattr(st, 'cache_resource'):
        st.cache_resource.clear()


# Project sites database functions
def get_project_sites():
    """Get all active project sites from database"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM project_sites WHERE is_active = 1 ORDER BY created_at")
            return [row[0] for row in cur.fetchall()]
    except sqlite3.OperationalError as e:
        if "disk I/O error" in str(e):
            # Try to recover from disk I/O error
            try:
                import os
                if os.path.exists('istrominventory.db-wal'):
                    os.remove('istrominventory.db-wal')
                if os.path.exists('istrominventory.db-shm'):
                    os.remove('istrominventory.db-shm')
                # Retry the operation
                return get_project_sites()
            except:
                return ["Lifecamp Kafe"]  # Fallback to default
        else:
            st.error(f"Database error getting project sites: {str(e)}")
            return ["Lifecamp Kafe"]  # Fallback to default
    except Exception as e:
        st.error(f"Failed to get project sites: {str(e)}")
        return ["Lifecamp Kafe"]  # Fallback to default

def add_project_site(name, description=""):
    """Add a new project site to database"""
    try:
        # Use simple connection without complex error handling
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        cur = conn.cursor()
        
        # Check if project site already exists
        cur.execute("SELECT COUNT(*) FROM project_sites WHERE name = ?", (name,))
        if cur.fetchone()[0] > 0:
            conn.close()
            return False  # Name already exists
        
        # Insert new project site
        cur.execute("INSERT INTO project_sites (name, description) VALUES (?, ?)", (name, description))
        conn.commit()
        conn.close()
        return True
        
    except sqlite3.IntegrityError:
        return False  # Name already exists
    except Exception as e:
        # Log error but don't show to user
        return False

def delete_project_site(name):
    """Delete a project site from database"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE project_sites SET is_active = 0 WHERE name = ?", (name,))
        conn.commit()
        return cur.rowcount > 0

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

def initialize_default_project_site():
    """Initialize Lifecamp Kafe as default project site if it doesn't exist"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM project_sites WHERE name = 'Lifecamp Kafe'")
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
        with get_conn() as conn:
            cur = conn.cursor()
            
            # Check if access codes exist in database
            cur.execute("SELECT admin_code, user_code FROM access_codes ORDER BY id DESC LIMIT 1")
            result = cur.fetchone()
            
            if result:
                return result[0], result[1]  # admin_code, user_code
            else:
                # Insert default codes if none exist
                wat_timezone = pytz.timezone('Africa/Lagos')
                current_time = datetime.now(wat_timezone)
                cur.execute("""
                    INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                    VALUES (?, ?, ?, ?)
                """, (DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE, current_time.isoformat(), "System"))
                conn.commit()
                return DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE
    except Exception as e:
        # Ultimate fallback to default codes
        return DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE

def log_access(access_code, success=True, user_name="Unknown"):
    """Log access attempts to database"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            
            # Get current access codes to determine role
            admin_code, user_code = get_access_codes()
            role = "admin" if access_code == admin_code else "user" if access_code == user_code else "unknown"
            
            # Special handling for session restore
            if access_code == "SESSION_RESTORE":
                role = st.session_state.get('user_role', 'unknown')
            
            # Get current time in West African Time (WAT)
            wat_timezone = pytz.timezone('Africa/Lagos')  # West African Time
            current_time = datetime.now(wat_timezone)
            
            cur.execute("""
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (?, ?, ?, ?, ?)
            """, (access_code, user_name, current_time.isoformat(), 1 if success else 0, role))
            conn.commit()
            
            # Get the log ID for this session
            cur.execute("SELECT last_insert_rowid()")
            log_id = cur.fetchone()[0]
            return log_id
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
                return log_access(access_code, success, user_name)
            except:
                pass
        st.error(f"Database error: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Failed to log access: {str(e)}")
        return None

@st.cache_data(ttl=30)  # Cache for 30 seconds for better responsiveness
def df_items_cached(project_site=None):
    """Cached version of df_items for better performance - shows items from current project site only"""
    if project_site is None:
        # Use user's assigned project site, fallback to session state
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
    
    q = "SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type, project_site FROM items WHERE project_site = ?"
    q += " ORDER BY budget, section, grp, building_type, name"
    with get_conn() as conn:
        if conn is None:
            return pd.DataFrame()  # Return empty DataFrame if connection fails
        return pd.read_sql_query(q, conn, params=(project_site,))

@st.cache_data(ttl=30)  # Cache for 30 seconds for better responsiveness
def get_budget_options(project_site=None):
    """Generate budget options based on actual database content"""
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
            
            # Generate all possible budget options (no redundancy)
            for budget_num in range(1, 21):  # Budgets 1-20
                for bt in PROPERTY_TYPES:
                    if bt:
                        # Add all subgroups for this budget and building type
                        budget_options.extend([
                            f"Budget {budget_num} - {bt}",
                            f"Budget {budget_num} - {bt} (General Materials)",
                            f"Budget {budget_num} - {bt} (Woods)",
                            f"Budget {budget_num} - {bt} (Plumbings)",
                            f"Budget {budget_num} - {bt} (Iron)",
                            f"Budget {budget_num} - {bt} (Labour)"
                        ])
    except Exception as e:
        # Fallback to basic options if database query fails
        for budget_num in range(1, 21):
            for bt in PROPERTY_TYPES:
                if bt:
                    budget_options.extend([
                        f"Budget {budget_num} - {bt}",
                        f"Budget {budget_num} - {bt} (General Materials)",
                        f"Budget {budget_num} - {bt} (Wood)",
                        f"Budget {budget_num} - {bt} (Plumbings)",
                        f"Budget {budget_num} - {bt} (Iron)",
                        f"Budget {budget_num} - {bt} (Labour)"
                    ])
    
    return budget_options

@st.cache_data(ttl=30)  # Cache for 30 seconds for better responsiveness
def get_section_options(project_site=None):
    """Generate section options based on actual database content"""
    section_options = ["All"]  # Always include "All" option
    
    # Use current project site if not specified
    if project_site is None:
        project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    try:
        # Get actual sections from database for this project site
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT section 
                FROM items 
                WHERE project_site = ? AND section IS NOT NULL AND section != ''
                ORDER BY section
            """, (project_site,))
            
            db_sections = [row[0] for row in cur.fetchall()]
            section_options.extend(db_sections)
    except Exception as e:
        # Fallback to basic options if database query fails
        section_options.extend(["materials", "labour"])
    
    return section_options

@st.cache_data(ttl=30)  # Cache for 30 seconds for better responsiveness
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

@st.cache_data(ttl=30)  # Cache for 30 seconds for better responsiveness
def df_items(filters=None):
    """Get items with optional filtering - optimized with database queries"""
    if not filters or not any(v for v in filters.values() if v):
        return df_items_cached(st.session_state.get('current_project_site'))
    
    # Build SQL query with filters for better performance
    q = "SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type FROM items WHERE 1=1"
    params = []
    
    for k, v in filters.items():
        if v is not None and v != "":
            if k == "budget":
                if "(" in str(v) and ")" in str(v):
                    # Specific subgroup search
                    q += " AND budget LIKE ?"
                    params.append(f"%{v}%")
                else:
                    # General search - use base budget
                    base_budget = str(v).split("(")[0].strip()
                    q += " AND budget LIKE ?"
                    params.append(f"%{base_budget}%")
            elif k == "section":
                q += " AND section LIKE ?"
                params.append(f"%{v}%")
            elif k == "building_type":
                q += " AND building_type LIKE ?"
                params.append(f"%{v}%")
            elif k == "category":
                q += " AND category LIKE ?"
                params.append(f"%{v}%")
            elif k == "code":
                q += " AND code LIKE ?"
                params.append(f"%{v}%")
            elif k == "name":
                q += " AND name LIKE ?"
                params.append(f"%{v}%")
    
    q += " ORDER BY budget, section, grp, building_type, name"
    
    with get_conn() as conn:
        return pd.read_sql_query(q, conn, params=params)

def calc_subtotal(filters=None) -> float:
    q = "SELECT SUM(COALESCE(qty,0) * COALESCE(unit_cost,0)) FROM items WHERE 1=1"
    params = []
    if filters:
        for k, v in filters.items():
            if v:
                q += f" AND {k} = ?"
                params.append(v)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(q, params)
        total = cur.fetchone()[0]
    return float(total or 0.0)

def upsert_items(df, category_guess=None, budget=None, section=None, grp=None, building_type=None, project_site=None):
    with get_conn() as conn:
        cur = conn.cursor()
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
                cur.execute("SELECT id FROM items WHERE code = ?", (code,))
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE items SET name=?, category=?, unit=?, qty=?, unit_cost=?, budget=?, section=?, grp=?, building_type=?, project_site=? WHERE id=?",
                                (name, category, unit, qty, unit_cost, b, s, g, bt, ps, row[0]))
                else:
                    cur.execute("INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp,building_type,project_site) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                (code, name, category, unit, qty, unit_cost, b, s, g, bt, ps))
            else:
                cur.execute(
                    "SELECT id FROM items WHERE name=? AND category=? AND IFNULL(budget,'')=IFNULL(?,'') AND IFNULL(section,'')=IFNULL(?,'') AND IFNULL(grp,'')=IFNULL(?,'') AND IFNULL(building_type,'')=IFNULL(?,'') AND project_site=?",
                    (name, category, b, s, g, bt, ps)
                )
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE items SET unit=?, qty=?, unit_cost=?, budget=?, section=?, grp=?, building_type=?, project_site=? WHERE id=?",
                                (unit, qty, unit_cost, b, s, g, bt, ps, row[0]))
                else:
                    cur.execute("INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp,building_type,project_site) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                (None, name, category, unit, qty, unit_cost, b, s, g, bt, ps))
        conn.commit()
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
    with get_conn() as conn:
        cur = conn.cursor()
        # Use West African Time (WAT)
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        cur.execute("INSERT INTO requests(ts, section, item_id, qty, requested_by, note, status, current_price) VALUES (?,?,?,?,?,?, 'Pending', ?)",
                    (current_time.isoformat(timespec="seconds"), section, item_id, float(qty), requested_by, note, current_price))
        
        # Get the request ID for notification
        request_id = cur.lastrowid
        
        # Get item name for notification
        cur.execute("SELECT name FROM items WHERE id = ?", (item_id,))
        item_result = cur.fetchone()
        item_name = item_result[0] if item_result else "Unknown Item"
        
        # Get current user ID for notification
        current_user_id = st.session_state.get('user_id')
        
        conn.commit()
        
        # Create notification for all admins (regardless of project site)
        current_project_site = st.session_state.get('current_project_site', 'Unknown Project')
        notification_success = create_notification(
            notification_type="new_request",
            title="New Request Submitted",
            message=f"{requested_by} ({current_project_site}) has submitted a request for {qty} units of {item_name}",
            user_id=None,  # Send to all admins - no project site filtering
            request_id=request_id
        )
        
        # Debug: Log notification creation
        if notification_success:
            print(f"✅ Notification created successfully for request {request_id}")
        else:
            print(f"❌ Failed to create notification for request {request_id}")
        
        # Automatically backup data for persistence
        try:
            auto_backup_data()
        except:
            pass

def set_request_status(req_id, status, approved_by=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT item_id, qty, section, status, current_price FROM requests WHERE id=?", (req_id,))
        r = cur.fetchone()
        if not r:
            return "Request not found"
        item_id, qty, section, old_status, current_price = r
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
                
                # Use current price from request if available, otherwise use item's unit cost
                if current_price and current_price > 0:
                    actual_cost = current_price * qty
                else:
                    # Fallback to item's unit cost
                    cur.execute("SELECT unit_cost FROM items WHERE id=?", (item_id,))
                    unit_cost_result = cur.fetchone()
                    actual_cost = unit_cost_result[0] * qty if unit_cost_result[0] else 0
                
                # Create actual record
                cur.execute("""
                    INSERT INTO actuals (item_id, actual_qty, actual_cost, actual_date, recorded_by, notes, project_site)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (item_id, qty, actual_cost, actual_date, approved_by or 'System', 
                     f"Auto-generated from approved request #{req_id}", project_site))
                
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
                cur.execute("""
                    DELETE FROM actuals 
                    WHERE item_id = ? AND recorded_by = ? AND notes LIKE ?
                """, (item_id, approved_by or 'System', f"Auto-generated from approved request #{req_id}"))
                
                # Clear cache to ensure actuals tab updates
                st.cache_data.clear()
                
            except Exception as e:
                # Don't fail the rejection if actual deletion fails
                pass
                
        cur.execute("UPDATE requests SET status=?, approved_by=? WHERE id=?", (status, approved_by, req_id))
        conn.commit()
        
        # Create notification for the user when request is approved
        if status == "Approved":
            # Get user ID who made the request
            cur.execute("SELECT requested_by FROM requests WHERE id=?", (req_id,))
            requester = cur.fetchone()
            if requester:
                requester_name = requester[0]
                
                # Get item name for notification
                cur.execute("SELECT name FROM items WHERE id=?", (item_id,))
                item_result = cur.fetchone()
                item_name = item_result[0] if item_result else "Unknown Item"
                
                # Debug: Log notification creation attempt
                print(f"🔔 Creating approval notification for user: {requester_name}")
                
                # Create notification for the user
                notification_success = create_notification(
                    notification_type="request_approved",
                    title="Request Approved",
                    message=f"Your request for {qty} units of {item_name} has been approved by {approved_by or 'Administrator'}",
                    user_id=requester_name,  # Send to the user who made the request
                    request_id=req_id
                )
                
                # Debug: Log notification result
                if notification_success:
                    print(f"✅ Approval notification created successfully for user: {requester_name}")
                else:
                    print(f"❌ Failed to create approval notification for user: {requester_name}")
            else:
                print(f"❌ No requester found for request {req_id}")
        
        # Create notification for the user when request is rejected
        elif status == "Rejected":
            # Get user ID who made the request
            cur.execute("SELECT requested_by FROM requests WHERE id=?", (req_id,))
            requester = cur.fetchone()
            if requester:
                requester_name = requester[0]
                
                # Get item name for notification
                cur.execute("SELECT name FROM items WHERE id=?", (item_id,))
                item_result = cur.fetchone()
                item_name = item_result[0] if item_result else "Unknown Item"
                
                # Create notification for the user
                create_notification(
                    notification_type="request_rejected",
                    title="Request Rejected",
                    message=f"Your request for {qty} units of {item_name} has been rejected by {approved_by or 'Administrator'}",
                    user_id=requester_name,  # Send to the user who made the request
                    request_id=req_id
                )
    return None

def delete_request(req_id):
    """Delete a request from the database"""
    conn = get_conn()
    if conn is None:
        return False
    
    try:
        cur = conn.cursor()
        
        # First, check if this is an approved request and remove the associated actual record
        cur.execute("SELECT status, item_id FROM requests WHERE id = ?", (req_id,))
        result = cur.fetchone()
        if result:
            status, item_id = result
            if status == "Approved":
                # Remove the auto-generated actual record
                cur.execute("""
                    DELETE FROM actuals 
                    WHERE item_id = ? AND notes LIKE ?
                """, (item_id, f"Auto-generated from approved request #{req_id}"))
        
        # Delete the request
        cur.execute("DELETE FROM requests WHERE id = ?", (req_id,))
        conn.commit()
        
        # Also delete any associated notifications
        cur.execute("DELETE FROM notifications WHERE request_id = ?", (req_id,))
        conn.commit()
        
        # Clear cache to ensure actuals tab updates
        st.cache_data.clear()
        
        return True
    except Exception as e:
        print(f"❌ Error deleting request {req_id}: {e}")
        return False
    finally:
        conn.close()

def df_requests(status=None):
    # Check if user is admin - admins see all requests from all project sites
    user_type = st.session_state.get('user_type', 'user')
    
    if user_type == 'admin':
        # Admin sees ALL requests from ALL project sites
        q = """SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.status, r.approved_by,
               i.budget, i.building_type, i.grp, i.project_site
               FROM requests r 
               JOIN items i ON r.item_id=i.id"""
        params = []
        if status and status != "All":
            q += " WHERE r.status=?"
            params = [status]
        q += " ORDER BY r.id DESC"
    else:
        # Regular users see only requests from their assigned project site
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
        q = """SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.status, r.approved_by,
               i.budget, i.building_type, i.grp, i.project_site
               FROM requests r 
               JOIN items i ON r.item_id=i.id
               WHERE i.project_site = ?"""
        params = [project_site]
        if status and status != "All":
            q += " AND r.status=?"
            params = [project_site, status]
        q += " ORDER BY r.id DESC"
    
    with get_conn() as conn:
        return pd.read_sql_query(q, conn, params=params)

def all_items_by_section(section):
    # Get current project site
    project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    with get_conn() as conn:
        return pd.read_sql_query("SELECT id, name, unit, qty FROM items WHERE category=? AND project_site=? ORDER BY name", conn, params=(section, project_site))

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
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM deleted_requests ORDER BY id DESC", conn)

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
    if project_site is None:
        project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    with get_conn() as conn:
        query = """
            SELECT a.id, a.item_id, a.actual_qty, a.actual_cost, a.actual_date, a.recorded_by, a.notes, a.created_at, a.project_site,
                   i.name, i.code, i.budget, i.building_type, i.unit, i.category, i.section, i.grp
            FROM actuals a
            JOIN items i ON a.item_id = i.id
            WHERE a.project_site = ?
            ORDER BY a.actual_date DESC, a.created_at DESC
        """
        return pd.read_sql_query(query, conn, params=(project_site,))

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
                cur.execute("DELETE FROM actuals WHERE id = ?", (actual_id,))
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

def maintain_database():
    """Aggressive database maintenance and WAL cleanup"""
    try:
        import os
        import time
        
        # Force remove all WAL files
        wal_files = ['istrominventory.db-wal', 'istrominventory.db-shm']
        for file_path in wal_files:
            if os.path.exists(file_path):
                try:
                    os.chmod(file_path, 0o777)
                    os.remove(file_path)
                except:
                    try:
                        os.remove(file_path)
                    except:
                        pass
        
        # Wait a moment for file system to catch up
        time.sleep(0.5)
        
        # Try to connect and optimize
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
            conn.execute("PRAGMA foreign_keys = ON;")
            
            # Switch to DELETE mode to avoid WAL issues
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            
            # Optimize database
            conn.execute("PRAGMA optimize")
            conn.execute("VACUUM")  # Rebuild database to remove fragmentation
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as db_error:
            if conn:
                try:
                    conn.close()
                except:
                    pass
            st.error(f"Database optimization failed: {db_error}")
            return False
            
    except Exception as e:
        st.error(f"Database maintenance failed: {e}")
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

def clear_inventory(include_logs: bool = False):
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
    """Seamless authentication by access code"""
    conn = get_conn()
    if conn is None:
        return None
    
    try:
        cur = conn.cursor()
        
        # Check global admin code first
        cur.execute('SELECT admin_code FROM access_codes ORDER BY updated_at DESC LIMIT 1')
        admin_result = cur.fetchone()
        
        if admin_result and access_code == admin_result[0]:
            return {
                'id': 1,
                'username': 'admin',
                'full_name': 'System Administrator',
                'user_type': 'admin',
                'project_site': 'ALL'
            }
        
        # Check users table for individual user access codes
        cur.execute('''
            SELECT id, username, full_name, user_type, project_site 
            FROM users 
            WHERE username = ? AND is_active = 1
        ''', (access_code,))
        
        user_result = cur.fetchone()
        if user_result:
            return {
                'id': user_result[0],
                'username': user_result[1],
                'full_name': user_result[2],
                'user_type': user_result[3],
                'project_site': user_result[4]
            }
        
        return None
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None
    finally:
        conn.close()

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
                        st.session_state.current_project_site = user_info['project_site'] if user_info['project_site'] != 'ALL' else 'Lifecamp Kafe'
                        st.session_state.auth_timestamp = datetime.now().isoformat()
                        
                        # Save session to cookie for 10-hour persistence
                        save_session_to_cookie()
                        
                        st.success(f"✅ Welcome, {user_info['full_name']}! (Session: 10 hours)")
                        st.rerun()
                    else:
                        st.error("❌ Invalid access code. Please try again.")
                else:
                    st.error("❌ Please enter your access code.")

def show_logout_button():
    """Display logout button"""
    if st.button("🚪 Logout", key="logout_btn", help="Logout from the system"):
        # Clear session
        for key in list(st.session_state.keys()):
            if key not in ['current_project_site']:  # Keep project site for continuity
                del st.session_state[key]
        
        st.session_state.logged_in = False
        # Clear session cookie
        st.query_params.clear()
        st.success("✅ Logged out successfully!")
        st.rerun()

# Initialize session
initialize_session()

# --------------- PERSISTENT SESSION MANAGEMENT (10 HOURS) ---------------
def check_session_validity():
    """Check if current session is still valid (10 hours)"""
    if not st.session_state.logged_in or not st.session_state.get('auth_timestamp'):
        return False
    
    try:
        auth_time = datetime.fromisoformat(st.session_state.get('auth_timestamp'))
        current_time = datetime.now()
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
            current_time = datetime.now()
            session_duration = 10 * 60 * 60  # 10 hours
            
            if (current_time - auth_time).total_seconds() < session_duration:
                # Restore session
                st.session_state.logged_in = True
                st.session_state.user_id = session_data.get('user_id')
                st.session_state.username = session_data.get('username')
                st.session_state.full_name = session_data.get('full_name')
                st.session_state.user_type = session_data.get('user_type')
                st.session_state.project_site = session_data.get('project_site')
                st.session_state.current_project_site = session_data.get('current_project_site', 'Lifecamp Kafe')
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
            'current_project_site': st.session_state.get('current_project_site', 'Lifecamp Kafe'),
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
        st.success("🔄 Session restored from previous login")
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
# Get user info
user_name = st.session_state.get('full_name', 'Unknown')
user_type = st.session_state.get('user_type', 'user')
project_site = st.session_state.get('project_site', 'Lifecamp Kafe')

# Calculate session time remaining
session_remaining = ""
auth_timestamp = st.session_state.get('auth_timestamp')
if auth_timestamp:
    try:
        auth_time = datetime.fromisoformat(auth_timestamp)
        current_time = datetime.now()
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

# Compact dashboard header
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("User", user_name)
with col2:
    st.metric("Access", "Admin" if user_type == 'admin' else "User")
with col3:
    st.metric("Project", project_site)
with col4:
    st.metric("Session", session_remaining)

# Status indicator
if user_type == 'admin':
    if notification_count > 0:
        st.warning(f"🔔 {notification_count} pending notifications")
    else:
        st.success("✅ All clear")
else:
    st.info("👤 User access")

# Logout button in sidebar
with st.sidebar:
    st.markdown("### User Actions")
    show_logout_button()

st.divider()

init_db()
ensure_indexes()

# Initialize persistent data file if it doesn't exist
def init_persistent_data():
    """Initialize persistent data file if it doesn't exist"""
    if not os.path.exists("persistent_data.json"):
        # Create empty persistent data file
        empty_data = {
            "items": [],
            "requests": [],
            "access_codes": {
                "admin_code": DEFAULT_ADMIN_ACCESS_CODE,
                "user_code": DEFAULT_USER_ACCESS_CODE
            },
            "backup_timestamp": datetime.now().isoformat()
        }
        try:
            with open("persistent_data.json", 'w') as f:
                json.dump(empty_data, f, indent=2)
        except:
            pass

init_persistent_data()

def auto_restore_from_file():
    """Automatically restore data from persistent sources - works seamlessly for companies"""
    try:
        # Primary: Try to restore from persistent file (most reliable)
        persistent_file = "persistent_data.json"
        try:
            if os.path.exists(persistent_file):
                with open(persistent_file, 'r') as f:
                    data = json.load(f)
                
                # Check if database is empty (fresh deployment)
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM items")
                    item_count = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM access_codes")
                    access_count = cur.fetchone()[0]
                    
                    # Only restore if database is empty (fresh deployment)
                    if item_count == 0 and access_count == 0:
                        # Restore items
                        if 'items' in data and data['items']:
                            items_df = pd.DataFrame(data['items'])
                            items_df.to_sql('items', conn, if_exists='append', index=False)
                        
                        # Restore requests
                        if 'requests' in data and data['requests']:
                            requests_df = pd.DataFrame(data['requests'])
                            requests_df.to_sql('requests', conn, if_exists='append', index=False)
                        
                        # Restore access codes
                        if 'access_codes' in data and data['access_codes']:
                            access_codes = data['access_codes']
                            cur.execute("""
                                INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                                VALUES (?, ?, ?, ?)
                            """, (access_codes['admin_code'], access_codes['user_code'], 
                                  data.get('backup_timestamp', datetime.now().isoformat()), 'AUTO_RESTORE'))
                            conn.commit()
                        
                        return True
        except:
            pass  # Fall back to other sources
        
        # Fallback: Try Streamlit Cloud secrets
        try:
            if hasattr(st, 'secrets') and 'PERSISTENT_DATA' in st.secrets:
                data = st.secrets['PERSISTENT_DATA']
                
                # Check if database is empty (fresh deployment)
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM items")
                    item_count = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM access_codes")
                    access_count = cur.fetchone()[0]
                    
                    # Only restore if database is empty (fresh deployment)
                    if item_count == 0 and access_count == 0:
                        # Restore items
                        if 'items' in data and data['items']:
                            items_df = pd.DataFrame(data['items'])
                            items_df.to_sql('items', conn, if_exists='append', index=False)
                        
                        # Restore requests
                        if 'requests' in data and data['requests']:
                            requests_df = pd.DataFrame(data['requests'])
                            requests_df.to_sql('requests', conn, if_exists='append', index=False)
                        
                        # Restore access codes
                        if 'access_codes' in data and data['access_codes']:
                            access_codes = data['access_codes']
                            cur.execute("""
                                INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                                VALUES (?, ?, ?, ?)
                            """, (access_codes['admin_code'], access_codes['user_code'], 
                                  data.get('backup_timestamp', datetime.now().isoformat()), 'AUTO_RESTORE'))
                            conn.commit()
                        
                        return True
        except:
            pass  # Fall back to local files
        
        # Final fallback: Check other backup files
        backup_locations = [
            'backup_data.json',
            '.app_backup.json',
            'app_data_backup.json',
            '/tmp/app_data_backup.json',
            'persistent_data.json'
        ]
        
        for location in backup_locations:
            if os.path.exists(location):
                try:
                    with open(location, 'r') as f:
                        data = json.load(f)
                    
                    # Check if database is empty (fresh deployment)
                    with get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) FROM items")
                        item_count = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM access_codes")
                        access_count = cur.fetchone()[0]
                        
                        # Only restore if database is empty (fresh deployment)
                        if item_count == 0 and access_count == 0:
                            # Restore items
                            if 'items' in data and data['items']:
                                items_df = pd.DataFrame(data['items'])
                                items_df.to_sql('items', conn, if_exists='append', index=False)
                            
                            # Restore requests
                            if 'requests' in data and data['requests']:
                                requests_df = pd.DataFrame(data['requests'])
                                requests_df.to_sql('requests', conn, if_exists='append', index=False)
                            
                            # Restore access codes
                            if 'access_codes' in data and data['access_codes']:
                                access_codes = data['access_codes']
                                cur.execute("""
                                    INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                                    VALUES (?, ?, ?, ?)
                                """, (access_codes['admin_code'], access_codes['user_code'], 
                                      data.get('backup_timestamp', datetime.now().isoformat()), 'AUTO_RESTORE'))
                                conn.commit()
                            
                            return True
                            
                except:
                    continue  # Try next location
        
        return False
    except Exception as e:
        # Silently fail - don't show errors to users
        return False

auto_restore_from_file()

# Create automatic backup on startup
if not st.session_state.get('backup_created', False):
    backup_path = create_backup()
    if backup_path:
        st.session_state.backup_created = True
        cleanup_old_backups()

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
                    st.info("🔄 **Auto-restoring data from previous deployment...**")
                    
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
                backup_timestamp = datetime.now().isoformat()
            
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


# Auto-restore on startup
auto_restore_data()

# Initialize session state for performance
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False


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
        log_access("SESSION_ACTIVITY", success=True, user_name=user_name)
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
                st.session_state.auth_timestamp = datetime.now().isoformat()
                log_id = log_access(access_code, success=True, user_name=user_name)
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
                st.session_state.auth_timestamp = datetime.now().isoformat()
                log_id = log_access(access_code, success=True, user_name=user_name)
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

# Compact sidebar
with st.sidebar:
    st.markdown("### Istrom Inventory")
    
    # Get current user info from session
    current_user = st.session_state.get('current_user_name', 'Unknown')
    current_role = st.session_state.get('user_role', 'user')
    
    st.markdown(f"**{current_user}** ({current_role.title()})")
    
    # Show session time remaining
    if st.session_state.get('auth_timestamp'):
        try:
            auth_time = datetime.fromisoformat(st.session_state.get('auth_timestamp'))
            expiry_time = auth_time.replace(hour=auth_time.hour + 24)
            time_remaining = expiry_time - datetime.now()
            hours_remaining = int(time_remaining.total_seconds() / 3600)
            if hours_remaining > 0:
                st.caption(f"Session: {hours_remaining}h remaining")
            else:
                st.caption("Session: Expiring soon")
        except:
            st.caption("Session: Active")
    
    st.divider()
    
    if st.button("Logout", type="secondary", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_role = None
        st.session_state.current_user_name = None
        st.session_state.access_log_id = None
        st.session_state.auth_timestamp = None
        st.query_params.clear()
        st.rerun()

# Project Site Selection
initialize_default_project_site()
project_sites = get_project_sites()

# Ensure current project site is set
if 'current_project_site' not in st.session_state:
    st.session_state.current_project_site = "Lifecamp Kafe"

# Project site selection based on user permissions
user_type = st.session_state.get('user_type', 'user')
user_project_site = st.session_state.get('project_site', 'Lifecamp Kafe')

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
        else:
            st.session_state.current_project_site = selected_site
    else:
        st.warning("No project sites available. Contact an administrator to add project sites.")
else:
    # Regular users are restricted to their assigned project site
    st.session_state.current_project_site = user_project_site
    st.info(f"🏗️ **Project Site:** {user_project_site}")

# Display current project site info
if 'current_project_site' in st.session_state:
    if user_type == 'admin':
        st.caption(f"📊 Working with: {st.session_state.current_project_site} | Budgets: 1-20")
    else:
        st.caption(f"📊 Available Budgets: 1-20")
else:
    st.warning("Please select a project site to continue.")

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
    # Regular users see same tabs as admin but without Admin Settings
    tab_names = ["Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History", "Budget Summary", "Actuals"]
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(tab_names)
    # Create dummy tab for compatibility
    tab7 = None

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
        st.warning("🔒 **Read-Only Access**: You can view items but cannot add, edit, or delete them.")
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
            "TERRACES (6-UNITS) DPC(TERRACE SUBSTRUCTURE)"
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
        category = st.selectbox("📂 Category", ["materials", "labour"], index=0, help="Select category", key="manual_category_select")
        
        # Set default group based on category
        if category == "materials":
            grp = "Materials"
        else:
            grp = "Labour"
        
        # Show line amount preview
        line_amount = float((qty or 0) * (rate or 0))
        st.metric("💰 Line Amount", f"₦{line_amount:,.2f}")
        
        submitted = st.form_submit_button("➕ Add Item", type="primary")
        
        if submitted:
            if not is_admin():
                st.error(" Admin privileges required for this action.")
                st.info("💡 Only administrators can add items to the inventory.")
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
                st.rerun()

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
        
        # Apply filters with hierarchical logic
        if filters.get('budget') and filters['budget'] != "All":
            budget_selected = filters['budget']
            # Hierarchical filtering - show all items that start with this budget
            # e.g., "Budget 1 - Flats" shows "Budget 1 - Flats", "Budget 1 - Flats(Woods)", etc.
            if "(" in budget_selected and ")" in budget_selected:
                # Specific subgroup - exact match
                filtered_items = filtered_items[filtered_items['budget'] == budget_selected]
            else:
                # Hierarchical - show all items that start with this budget
                filtered_items = filtered_items[filtered_items['budget'].str.startswith(budget_selected)]
        if filters.get('section') and filters['section'] != "All":
            filtered_items = filtered_items[filtered_items['section'] == filters['section']]
        
    if filtered_items.empty:
        st.info("No items found matching your filters.")
        # Debug information
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
        st.metric("💰 Total Amount", f"₦{total_amount:,.2f}")
        
        # Export
        csv_data = filtered_items.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv_data, "budget_view.csv", "text/csv")

# -------------------------------- Tab 2: Inventory --------------------------------
with tab2:
    st.subheader("📦 Current Inventory")
    st.caption("View, edit, and manage all inventory items")
    
    # Check permissions for inventory management
    if not is_admin():
        st.warning("🔒 **Read-Only Access**: You can view inventory but cannot modify items.")
        st.info("Contact an administrator if you need to make changes to the inventory.")
    
    # Load all items first with progress indicator (optimized)
    with st.spinner("🔄 Loading inventory..."):
        items = df_items_cached(st.session_state.get('current_project_site'))
    
    # Show loading status
    if items.empty:
        st.info("📦 No items found. Add some items in the Manual Entry tab to get started.")
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
    st.markdown("### 🔍 Filters")
    
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
    
    # Budget filter with hierarchical logic
    if f_budget and f_budget != "All":
        if "(" in f_budget and ")" in f_budget:
            # Specific subgroup - exact match
            budget_matches = filtered_items["budget"] == f_budget
        else:
            # Hierarchical - show all items that start with this budget
            # e.g., "Budget 1 - Flats" shows "Budget 1 - Flats", "Budget 1 - Flats(Woods)", etc.
            budget_matches = filtered_items["budget"].str.startswith(f_budget)
        filtered_items = filtered_items[budget_matches]
    
    # Section filter
    if f_section and f_section != "All":
        section_matches = filtered_items["section"] == f_section
        filtered_items = filtered_items[section_matches]
    
    # Building type filter
    if f_building_type and f_building_type != "All":
        building_type_matches = filtered_items["building_type"] == f_building_type
        filtered_items = filtered_items[building_type_matches]
    
    # Update items with filtered results
    items = filtered_items
    
    # Debug: Show filter results
    st.caption(f"🔍 Filter Results: Showing {len(items)} items (filtered from {len(df_items_cached(st.session_state.get('current_project_site')))} total)")
    
    # Cache refresh button for budget calculations
    if st.button("🔄 Refresh Budget Calculations", help="Click if budget totals don't update after editing quantities"):
        clear_cache()
        st.success("✅ Cache cleared! Budget calculations will refresh on next page load.")
        st.rerun()

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
        st.warning(f"⚠️ You have selected {len(selected_items)} item(s) for deletion.")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button(" Delete Selected Items", type="secondary", key="delete_button"):
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
                    st.success(f" Successfully deleted {deleted_count} item(s).")
                
                if errors:
                    st.error(f" {len(errors)} item(s) could not be deleted:")
                    for error in errors:
                        st.error(error)
                
                if deleted_count > 0 or errors:
                    # Don't use st.rerun() - let the page refresh naturally
                    pass
                    
        with col2:
            if st.button("🔄 Clear Selection", key="clear_selection"):
                st.session_state["delete_selection"] = []
                # Don't use st.rerun() - let the page refresh naturally
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
                            
                            st.success(f"✅ Successfully updated item: {selected_item['name']}")
                            # Clear cache to refresh budget calculations
                            clear_cache()
                            # Don't use st.rerun() - let the page refresh naturally
                        except Exception as e:
                            st.error(f"❌ Error updating item: {e}")
            else:
                st.info("No items available for editing.")
    else:
        st.info("🔒 Admin privileges required to edit items.")
    
    st.divider()
    st.markdown("### Danger Zone")
    coldz1, coldz2 = st.columns([3,2])
    with coldz1:
        if is_admin():
            also_logs = st.checkbox("Also clear deleted request logs", value=False, key="clear_logs")
        else:
            st.info("🔒 Admin privileges required for bulk operations")
    with coldz2:
        if is_admin():
            if st.button(" Delete ALL inventory and requests", type="secondary", key="delete_all_button"):
                if not st.session_state.get("confirm_clear_all"):
                    st.session_state["confirm_clear_all"] = True
                    st.warning("⚠️ Click the button again to confirm full deletion.")
                else:
                    clear_inventory(include_logs=also_logs)
                    st.success(" All items and requests cleared.")
                    st.rerun()
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
        # Debug: Show current project site and user info
        current_project = st.session_state.get('current_project_site', 'Not set')
        user_project = st.session_state.get('project_site', 'Not set')
        user_type = st.session_state.get('user_type', 'Not set')
        st.caption(f"🔍 Debug: User type='{user_type}', Current project='{current_project}', Assigned project='{user_project}'")
        
        all_items_summary, summary_data = get_summary_data()
    
    # Debug: Show current project site and item count
    current_project = st.session_state.get('current_project_site', 'Not set')
    st.caption(f"🔍 Debug: Budget Summary for project '{current_project}' - Found {len(all_items_summary)} items")
    
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
        st.markdown("#### 🔄 Recent Items Added")
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
            st.metric("🏆 Grand Total (All Budgets)", f"₦{grand_total:,.2f}")
            
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
        st.session_state.max_budget_num = 10
    
    # Add new budget button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("#### Available Budgets")
    with col2:
        if st.button("➕ Add New Budget", type="primary", key="add_new_budget"):
            st.session_state.max_budget_num += 1
            st.success(f" Added Budget {st.session_state.max_budget_num}")
            st.rerun()
    
    # Create tabs for each budget number (optimized - only show budgets with data)
    # Get budgets that actually have data
    existing_budgets = []
    if not all_items_summary.empty:
        budget_numbers = all_items_summary["budget"].str.extract(r"Budget (\d+)", expand=False).dropna().astype(int).unique()
        existing_budgets = sorted(budget_numbers)
    
    # Only create tabs for first 5 budgets with data + 3 empty ones
    tabs_to_create = existing_budgets[:5] + list(range(max(existing_budgets) + 1 if existing_budgets else 1, min(max(existing_budgets) + 4 if existing_budgets else 4, st.session_state.max_budget_num + 1)))
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
                    # Load existing configuration from database
                    existing_config = get_project_config(budget_num, building_type)
                    
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
                                    st.rerun()
                        
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
                                st.markdown("#### 🔍 Calculation Breakdown")
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
        
        # Load user notifications
        user_notifications = get_user_notifications()
        
        if user_notifications:
            unread_count = sum(1 for n in user_notifications if not n['is_read'])
            if unread_count > 0:
                st.success(f"📬 You have {unread_count} new notification(s)!")
                
                for notification in user_notifications:
                    with st.container():
                        # Show notification status
                        status_icon = "🔴" if not notification['is_read'] else "✅"
                        st.write(f"{status_icon} **{notification['title']}** - {notification['created_at']}")
                        st.write(f"*{notification['message']}*")
                        
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            if not notification['is_read']:
                                if st.button("✅ Mark as Read", key=f"user_mark_read_{notification['id']}"):
                                    if mark_notification_read(notification['id']):
                                        st.success("Notification marked as read!")
                                        st.rerun()
                        with col2:
                            if notification['request_id']:
                                if st.button("View Request", key=f"user_view_request_{notification['id']}"):
                                    st.info("Navigate to Review & History tab to view the request")
                        st.divider()
            else:
                st.info("📭 No notifications yet. You'll receive notifications when your requests are approved or rejected.")
    
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
    all_items = df_items_cached(st.session_state.get('current_project_site'))
    
    
    # Apply filters step by step
    items_df = all_items.copy()
    
    # Filter by section (materials/labour)
    if section:
        items_df = items_df[items_df["category"] == section]
    
    # Filter by building type
    if building_type:
        items_df = items_df[items_df["building_type"] == building_type]
    
    # Filter by budget (hierarchical matching)
    if budget:
        # Hierarchical filtering - show all items that start with this budget
        # e.g., "Budget 1 - Flats" shows "Budget 1 - Flats", "Budget 1 - Flats(Woods)", etc.
        if "(" in budget and ")" in budget:
            # Specific subgroup - exact match
            budget_matches = items_df["budget"] == budget
        else:
            # Hierarchical - show all items that start with this budget
            budget_matches = items_df["budget"].str.startswith(budget)
        items_df = items_df[budget_matches]
    
    # If still no items found, try showing all items for the building type (fallback)
    if items_df.empty and building_type:
        st.info(f"⚠️ No items found for the specific budget '{budget}'. Showing all {section} items for {building_type} instead.")
        items_df = all_items[
            (all_items["category"] == section) & 
            (all_items["building_type"] == building_type)
        ]
    
    if items_df.empty:
            st.warning(f"No items found for {section} in {building_type} - {budget}. Add items in the Manual Entry tab first.")
            
    else:
        st.markdown("### 📦 Available Items")
        item_row = st.selectbox("Item", options=items_df.to_dict('records'), format_func=lambda r: f"{r['name']} (Available: {r['qty']} {r['unit'] or ''}) — ₦{r['unit_cost'] or 0:,.2f}", key="request_item_select")
        
        # Initialize session state for price input if not exists
        if 'request_price_input' not in st.session_state and item_row and 'unit_cost' in item_row:
            st.session_state.request_price_input = float(item_row.get('unit_cost', 0) or 0)
        
        st.markdown("### 📝 Request Details")
        
        # Show selected item info
        if item_row:
            st.info(f"**Selected Item:** {item_row['name']} | **Planned Rate:** ₦{item_row.get('unit_cost', 0) or 0:,.2f}")
        
        col1, col2 = st.columns([1,1])
        with col1:
            qty = st.number_input("Quantity to request", min_value=1.0, step=1.0, value=1.0, key="request_qty_input")
            requested_by = st.text_input("Requested by", key="request_by_input")
        with col2:
            # Get default price from selected item
            default_price = 0.0
            if item_row and 'unit_cost' in item_row:
                default_price = float(item_row.get('unit_cost', 0) or 0)
            
            # Price input for current/updated price
            current_price = st.number_input(
                "💰 Current Price per Unit", 
                min_value=0.0, 
                step=0.01, 
                value=default_price,
                help="Enter the current market price for this item. This will be used as the actual rate in actuals.",
                key="request_price_input"
            )
            
            # Add reset button for price
            if item_row and 'unit_cost' in item_row:
                planned_rate = float(item_row.get('unit_cost', 0) or 0)
                if st.button("🔄 Reset to Planned Rate", help="Reset current price to the planned rate", key="reset_price_button"):
                    # Clear session state to force reset
                    if 'request_price_input' in st.session_state:
                        del st.session_state.request_price_input
                    # Don't use st.rerun() - let the page refresh naturally
            
            note = st.text_area("Note (optional)", key="request_note_input")
        
        # Show request summary (outside columns for full width)
        if item_row and qty:
            # Use current price for total cost calculation
            total_cost = qty * current_price
            st.markdown("### Request Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Planned Rate", f"₦{item_row.get('unit_cost', 0) or 0:,.2f}")
            with col2:
                st.metric("Current Rate", f"₦{current_price:,.2f}")
            with col3:
                st.metric("Quantity", f"{qty}")
            
            st.metric("Total Cost (Current Rate)", f"₦{total_cost:,.2f}")
            
            # Show price difference if applicable
            planned_rate = item_row.get('unit_cost', 0) or 0
            if current_price != planned_rate:
                price_diff = current_price - planned_rate
                price_diff_pct = (price_diff / planned_rate * 100) if planned_rate > 0 else 0
                if price_diff > 0:
                    st.info(f"📈 Price increased by ₦{price_diff:,.2f} ({price_diff_pct:+.1f}%)")
                else:
                    st.info(f"📉 Price decreased by ₦{abs(price_diff):,.2f} ({price_diff_pct:+.1f}%)")
            
            if st.button("Submit request", key="submit_request_button", type="primary"):
                
                # Validate form inputs with proper null checks
                if not requested_by or not requested_by.strip():
                    st.error("❌ Please enter your name in the 'Requested by' field.")
                elif not item_row or item_row is None or not item_row.get('id'):
                    st.error("❌ Please select an item from the list.")
                elif qty is None or qty <= 0:
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
                        # Validate item ID exists in database
                        import sqlite3
                        conn = sqlite3.connect('istrominventory.db')
                        cur = conn.cursor()
                        cur.execute("SELECT id FROM items WHERE id = ?", (item_row['id'],))
                        if not cur.fetchone():
                            st.error(f"❌ Selected item (ID: {item_row['id']}) not found in database. Please refresh the page and try again.")
                        else:
                            add_request(section, item_row['id'], qty, requested_by, note, current_price)
                            # Log request submission activity
                            log_current_session()
                            st.success(f"✅ Request submitted successfully for {building_type} - {budget}!")
                            st.info("💡 Your request will be reviewed by an administrator. Check the Review & History tab for updates.")
                            # Clear cache to refresh data without rerun
                            st.cache_data.clear()
                        conn.close()
                    except Exception as e:
                        st.error(f"❌ Failed to submit request: {str(e)}")
                        st.info("💡 Please try again or contact an administrator if the issue persists.")

# -------------------------------- Tab 4: Review & History --------------------------------
with tab4:
    st.subheader("Review Requests")
    
    # Check permissions for request management
    if not is_admin():
        st.info("👤 **User Access**: You can view your requests and their status.")
        st.caption("💡 **Note**: Only administrators can approve or reject requests.")
    
    status_filter = st.selectbox("Filter by status", ["All","Pending","Approved","Rejected"], index=1)
    reqs = df_requests(status=None if status_filter=="All" else status_filter)
    
    # Get user type for display logic
    user_type = st.session_state.get('user_type', 'user')
    
    # Debug: Show current project site and request count
    current_project = st.session_state.get('current_project_site', 'Not set')
    if user_type == 'admin':
        st.caption(f"🔍 Debug: Admin Review & History - Found {len(reqs)} requests from ALL project sites")
    else:
        st.caption(f"🔍 Debug: Review & History for project '{current_project}' - Found {len(reqs)} requests")
    
    if not reqs.empty:
        # Create a more informative display with building type and budget context
        display_reqs = reqs.copy()
        
        # Create a context column that shows building type and budget
        display_reqs['Context'] = display_reqs.apply(lambda row: 
                f"{row['building_type']} - {row['budget']} ({row['grp']})" 
                if pd.notna(row['building_type']) and pd.notna(row['budget']) 
            else f"{row['budget']} ({row['grp']})" if pd.notna(row['budget'])
            else "No context", axis=1)
        
        # For admins, show project site information
        if user_type == 'admin':
            # Reorder columns for better display (include project site for admins)
            display_columns = ['id', 'ts', 'item', 'qty', 'requested_by', 'project_site', 'Context', 'status', 'approved_by', 'note']
            display_reqs = display_reqs[display_columns]
            # Rename columns for better readability
            display_reqs.columns = ['ID', 'Time', 'Item', 'Quantity', 'Requested By', 'Project Site', 'Building Type & Budget', 'Status', 'Approved By', 'Note']
        else:
            # Regular users don't need project site column
            display_columns = ['id', 'ts', 'item', 'qty', 'requested_by', 'Context', 'status', 'approved_by', 'note']
            display_reqs = display_reqs[display_columns]
            # Rename columns for better readability
            display_reqs.columns = ['ID', 'Time', 'Item', 'Quantity', 'Requested By', 'Building Type & Budget', 'Status', 'Approved By', 'Note']
        
        # Display the table
        st.dataframe(display_reqs, use_container_width=True)
        
        # Add delete buttons as a separate section with table-like layout
        if not display_reqs.empty:
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
                            current_user = st.session_state.get('user_name', 'Unknown')
                            can_delete = (user_type == 'admin') or (row['Requested By'] == current_user)
                            
                            if can_delete:
                                if st.button("🗑️ Delete", key=f"delete_{row['ID']}", help=f"Delete request {row['ID']}"):
                                    if delete_request(row['ID']):
                                        st.success(f"Request {row['ID']} deleted!")
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to delete request {row['ID']}")
                            else:
                                st.write("🔒 Not yours")
                    
                    st.divider()
            else:
                st.info("No approved or rejected requests found for deletion")
        else:
            st.info("No requests found matching the selected criteria.")

    st.write("Approve/Reject a request by ID:")
    colA, colB, colC = st.columns(3)
    with colA:
        req_id = st.number_input("Request ID", min_value=1, step=1, key="req_id_input")
    with colB:
        action = st.selectbox("Action", ["Approve","Reject","Set Pending"], key="action_select")
    with colC:
        approved_by = st.text_input("Approved by / Actor", key="approved_by_input")

    if st.button("Apply", key="apply_status_button"):
        if not is_admin():
            st.error(" Admin privileges required for this action.")
            st.info("💡 Only administrators can approve or reject requests.")
        else:
            target_status = "Approved" if action=="Approve" else ("Rejected" if action=="Reject" else "Pending")
            err = set_request_status(int(req_id), target_status, approved_by=approved_by or None)
            if err:
                st.error(err)
            else:
                st.success(f"Request {req_id} set to {target_status}.")
                st.rerun()

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
            display_columns = ['id', 'ts', 'item', 'qty', 'requested_by', 'Context', 'approved_by', 'note']
            display_approved = display_approved[display_columns]
            display_approved.columns = ['ID', 'Time', 'Item', 'Quantity', 'Requested By', 'Building Type & Budget', 'Approved By', 'Note']
            st.dataframe(display_approved, use_container_width=True)
            
            # Delete buttons for approved requests
            if not display_approved.empty:
                st.markdown("#### Delete Approved Requests")
                delete_cols = st.columns(min(len(display_approved), 4))
                for i, (_, row) in enumerate(display_approved.iterrows()):
                    with delete_cols[i % 4]:
                        if st.button(f"🗑️ Delete ID {row['ID']}", key=f"del_app_{row['ID']}", type="secondary"):
                            if delete_request(row['ID']):
                                st.success(f"Request {row['ID']} deleted!")
                                st.rerun()
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
            display_columns = ['id', 'ts', 'item', 'qty', 'requested_by', 'Context', 'approved_by', 'note']
            display_rejected = display_rejected[display_columns]
            display_rejected.columns = ['ID', 'Time', 'Item', 'Quantity', 'Requested By', 'Building Type & Budget', 'Approved By', 'Note']
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
                                st.rerun()
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
                        st.rerun()
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
        
        # Simple budget options
        budget_options = [
                "Budget 1 - Flats",
                "Budget 1 - Terraces", 
                "Budget 1 - Semi-detached",
                "Budget 1 - Fully-Detached"
            ]
        
        selected_budget = st.selectbox(
            "Choose a budget to view:",
            options=budget_options,
            key="budget_selector"
        )
        
        if selected_budget:
            # Parse the selected budget
            budget_part, building_part = selected_budget.split(" - ", 1)
            
            # Get all items for this budget (all categories)
            search_pattern = f"{budget_part} - {building_part}"
            
            budget_items = items_df[
                items_df['budget'].str.contains(search_pattern, case=False, na=False)
            ]
            
            if not budget_items.empty:
                st.markdown(f"##### {selected_budget}")
                st.markdown("**📊 BUDGET vs ACTUAL COMPARISON**")
                
                # Get actuals data for this budget
                actuals_df = get_actuals(project_site)
                
                # Filter actuals for this specific budget and building type
                filtered_actuals = actuals_df[
                    (actuals_df['budget'].str.contains(search_pattern, case=False, na=False))
                ]
                
                # Create comparison data
                comparison_data = []
                idx = 1
                
                # Group planned items by category
                planned_categories = {}
                for _, item in budget_items.iterrows():
                    category = item.get('category', 'General Materials')
                    if category not in planned_categories:
                        planned_categories[category] = []
                    planned_categories[category].append(item)
                
                # Group actuals by category
                actual_categories = {}
                for _, actual in filtered_actuals.iterrows():
                    category = actual.get('category', 'General Materials')
                    if category not in actual_categories:
                        actual_categories[category] = []
                    actual_categories[category].append(actual)
                
                # Create table data with proper category separation
                # First, collect all items and their categories
                all_items_dict = {}
                
                # Add planned items
                for _, item in budget_items.iterrows():
                    item_id = item['id']
                    category = item.get('grp', 'General Materials')  # Use grp field instead of category
                    all_items_dict[item_id] = {
                        'name': item['name'],
                        'unit': item['unit'],
                        'category': category,
                        'planned_qty': item['qty'] if pd.notna(item['qty']) else 0,
                        'planned_rate': item['unit_cost'] if pd.notna(item['unit_cost']) else 0,
                        'planned_amount': (item['qty'] if pd.notna(item['qty']) else 0) * (item['unit_cost'] if pd.notna(item['unit_cost']) else 0),
                        'actual_qty': 0,
                        'actual_rate': 0,
                        'actual_amount': 0
                    }
                
                # Add actual items
                for _, actual in filtered_actuals.iterrows():
                    item_id = actual['item_id']
                    if item_id in all_items_dict:
                        # Update existing item with actual data
                        all_items_dict[item_id]['actual_qty'] += actual['actual_qty']
                        all_items_dict[item_id]['actual_rate'] = actual['actual_cost'] / actual['actual_qty'] if actual['actual_qty'] > 0 else 0
                        all_items_dict[item_id]['actual_amount'] += actual['actual_cost']
                    else:
                        # Add new item from actuals
                        category = actual.get('grp', 'General Materials')  # Use grp field instead of category
                        all_items_dict[item_id] = {
                            'name': actual['name'],
                            'unit': actual['unit'],
                            'category': category,
                            'planned_qty': 0,
                            'planned_rate': 0,
                            'planned_amount': 0,
                            'actual_qty': actual['actual_qty'],
                            'actual_rate': actual['actual_cost'] / actual['actual_qty'] if actual['actual_qty'] > 0 else 0,
                            'actual_amount': actual['actual_cost']
                        }
                
                # Group items by category
                categories_dict = {}
                for item_id, item_data in all_items_dict.items():
                    category = item_data['category']
                    if category not in categories_dict:
                        categories_dict[category] = []
                    categories_dict[category].append(item_data)
                
                # Define the order of categories to display (based on grp field values)
                category_order = ['GENERAL MATERIALS', 'WOODS', 'PLUMBINGS', 'IRONS', 'LABOUR']
                
                # Process each category in the defined order
                for display_category in category_order:
                    # Find matching category in the data
                    matching_category = None
                    for cat_name in categories_dict.keys():
                        if (cat_name.lower() == display_category.lower() or 
                            cat_name.lower() in display_category.lower() or 
                            display_category.lower() in cat_name.lower()):
                            matching_category = cat_name
                            break
                    
                    if matching_category and categories_dict[matching_category]:
                        # Add category header with centered text
                        comparison_data.append({
                            'S/N': '',
                            'MATERIALS': f"**{display_category.upper()}**",
                            'PLANNED QTY': '',
                            'PLANNED UNIT': '',
                            'PLANNED RATE': '',
                            'PLANNED AMOUNT': '',
                            '│': '',
                            'ACTUAL QTY': '',
                            'ACTUAL UNIT': '',
                            'ACTUAL RATE': '',
                            'ACTUAL AMOUNT': ''
                        })
                        
                        # Add items in this category
                        category_planned_total = 0
                        category_actual_total = 0
                        
                        for item_data in categories_dict[matching_category]:
                            comparison_data.append({
                                'S/N': idx,
                                'MATERIALS': item_data['name'],
                                'PLANNED QTY': item_data['planned_qty'],
                                'PLANNED UNIT': item_data['unit'],
                                'PLANNED RATE': item_data['planned_rate'],
                                'PLANNED AMOUNT': item_data['planned_amount'],
                                '│': '│',  # Professional separator
                                'ACTUAL QTY': item_data['actual_qty'],
                                'ACTUAL UNIT': item_data['unit'],
                                'ACTUAL RATE': item_data['actual_rate'],
                                'ACTUAL AMOUNT': item_data['actual_amount']
                            })
                            idx += 1
                            
                            # Calculate category totals
                            category_planned_total += item_data['planned_amount']
                            category_actual_total += item_data['actual_amount']
                        
                        # Add category total row
                        comparison_data.append({
                            'S/N': '',
                            'MATERIALS': f"**{display_category} TOTAL**",
                            'PLANNED QTY': '',
                            'PLANNED UNIT': '',
                            'PLANNED RATE': '',
                            'PLANNED AMOUNT': category_planned_total,
                            '│': '│',  # Professional separator
                            'ACTUAL QTY': '',
                            'ACTUAL UNIT': '',
                            'ACTUAL RATE': '',
                            'ACTUAL AMOUNT': category_actual_total
                        })
                        
                        # Add blank row after category total for visual separation
                        comparison_data.append({
                            'S/N': '',
                            'MATERIALS': '',
                            'PLANNED QTY': '',
                            'PLANNED UNIT': '',
                            'PLANNED RATE': '',
                            'PLANNED AMOUNT': '',
                            '│': '',
                            'ACTUAL QTY': '',
                            'ACTUAL UNIT': '',
                            'ACTUAL RATE': '',
                            'ACTUAL AMOUNT': ''
                        })
                
                if comparison_data:
                    # Split data into planned and actual sections
                    planned_data = []
                    actual_data = []
                    
                    for row in comparison_data:
                        # Create planned section
                        planned_row = {
                            'S/N': row['S/N'] if row['S/N'] != '' else '',
                            'MATERIALS': row['MATERIALS'] if row['MATERIALS'] != '' else '',
                            'PLANNED QTY': row['PLANNED QTY'] if row['PLANNED QTY'] != '' else '',
                            'PLANNED UNIT': row['PLANNED UNIT'] if row['PLANNED UNIT'] != '' else '',
                            'PLANNED RATE': row['PLANNED RATE'] if row['PLANNED RATE'] != '' else '',
                            'PLANNED AMOUNT': row['PLANNED AMOUNT'] if row['PLANNED AMOUNT'] != '' else ''
                        }
                        planned_data.append(planned_row)
                        
                        # Create actual section
                        actual_row = {
                            'S/N': row['S/N'] if row['S/N'] != '' else '',
                            'MATERIALS': row['MATERIALS'] if row['MATERIALS'] != '' else '',
                            'ACTUAL QTY': row['ACTUAL QTY'] if row['ACTUAL QTY'] != '' else '',
                            'ACTUAL UNIT': row['ACTUAL UNIT'] if row['ACTUAL UNIT'] != '' else '',
                            'ACTUAL RATE': row['ACTUAL RATE'] if row['ACTUAL RATE'] != '' else '',
                            'ACTUAL AMOUNT': row['ACTUAL AMOUNT'] if row['ACTUAL AMOUNT'] != '' else ''
                        }
                        actual_data.append(actual_row)
                    
                    # Create separate dataframes
                    planned_df = pd.DataFrame(planned_data)
                    actual_df = pd.DataFrame(actual_data)
                    
                    # Format currency columns for planned table
                    planned_currency_cols = ['PLANNED RATE', 'PLANNED AMOUNT']
                    for col in planned_currency_cols:
                        if col in planned_df.columns:
                            planned_df[col] = planned_df[col].apply(
                                lambda x: f"₦{float(x):,.2f}" if pd.notna(x) and x != '' and x != 0 and str(x).strip() != '' else ""
                            )
                    
                    # Format currency columns for actual table
                    actual_currency_cols = ['ACTUAL RATE', 'ACTUAL AMOUNT']
                    for col in actual_currency_cols:
                        if col in actual_df.columns:
                            actual_df[col] = actual_df[col].apply(
                                lambda x: f"₦{float(x):,.2f}" if pd.notna(x) and x != '' and x != 0 and str(x).strip() != '' else ""
                            )
                    
                    # Display tables side by side using Streamlit dataframes
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("#### PLANNED BUDGET")
                        st.dataframe(planned_df, use_container_width=True, hide_index=True)
                    
                    with col2:
                        st.markdown("#### ACTUALS")
                        st.dataframe(actual_df, use_container_width=True, hide_index=True)
                    
                    # Calculate totals with proper NaN handling
                    total_planned = 0
                    total_actual = 0
                    
                    for item_data in all_items_dict.values():
                        planned_amount = item_data.get('planned_amount', 0)
                        actual_amount = item_data.get('actual_amount', 0)
                        
                        if pd.notna(planned_amount) and planned_amount != '':
                            total_planned += float(planned_amount)
                        if pd.notna(actual_amount) and actual_amount != '':
                            total_actual += float(actual_amount)
                    
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Total Planned", f"₦{total_planned:,.2f}")
                    with col2:
                        st.metric("Total Actual", f"₦{total_actual:,.2f}")
                else:
                    st.info("No items found for this budget")
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
        st.subheader("Admin Settings")
        st.caption("Manage users, project sites, and view system logs")
        
        # Access Code Management
        st.markdown("### Global Access Code Management")
        
        # Display global admin code
        st.markdown("#### 👑 Global Admin Access")
        current_admin_code, _ = get_access_codes()
        st.info(f"**Global Admin Code:** `{current_admin_code}`")
        st.caption("💡 **Note**: This admin code works for ALL project sites. Only one admin needed for the entire system.")
        
        st.divider()
        
        # Global access code management
        with st.expander("🌐 Global Access Code Management", expanded=False):
            st.markdown("#### Global Access Codes")
            current_admin_code, current_user_code = get_access_codes()
            col1, col2 = st.columns([1, 1])
            with col1:
                st.info(f"**Global Admin Code:** `{current_admin_code}`")
            with col2:
                st.info(f"**Global User Code:** `{current_user_code}`")
            
            st.markdown("#### Change Global Access Codes")
            st.caption("⚠️ **Warning**: Changing global access codes will affect all users across all project sites.")
            
            with st.form("change_global_access_codes"):
                new_admin_code = st.text_input("New Global Admin Code", value=current_admin_code, type="password", help="Enter new global admin access code")
                new_user_code = st.text_input("New Global User Code", value=current_user_code, type="password", help="Enter new global user access code")
                
                if st.form_submit_button("🔑 Update Global Access Codes", type="primary"):
                    if new_admin_code and new_user_code:
                        if new_admin_code == new_user_code:
                            st.error("❌ Admin and User codes cannot be the same.")
                        elif len(new_admin_code) < 4 or len(new_user_code) < 4:
                            st.error("❌ Access codes must be at least 4 characters long.")
                        else:
                            # Update global access codes
                            current_user = st.session_state.get('full_name', 'Admin')
                            if update_access_codes(new_admin_code, new_user_code, current_user):
                                st.success("✅ Global access codes updated successfully!")
                                st.info("💡 **Note**: New global access codes are now active.")
                                # Don't use st.rerun() - let the page refresh naturally
                            else:
                                st.error("❌ Failed to update global access codes. Please try again.")
                    else:
                        st.error("❌ Please enter both access codes.")
        
        st.divider()
        
        # Access Code Summary
        st.markdown("#### Access Code Summary")
        
        # Get user data for summary
        try:
            users = get_all_users()
        except:
            users = []
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_users = len(users)
            st.metric("Total Users", total_users)
        
        with col2:
            admin_users = len([u for u in users if u.get('user_type') == 'admin'])
            st.metric("Admin Users", admin_users)
        
        with col3:
            regular_users = len([u for u in users if u.get('user_type') == 'user'])
            st.metric("Regular Users", regular_users)
        
        with col4:
            active_users = len([u for u in users if u.get('is_active', True)])
            st.metric("Active Users", active_users)
        
        st.divider()
        
        # Project Site Management
        st.markdown("### Project Site Management")
        
        # Display current project sites
        st.markdown("#### Current Project Sites")
        admin_project_sites = get_project_sites()
        if admin_project_sites:
            for i, site in enumerate(admin_project_sites):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.write(f"**{i+1}.** {site}")
                with col2:
                    if st.button("Edit", key=f"edit_site_{i}", help="Edit this project site name"):
                        st.session_state[f"editing_site_{i}"] = True
                        st.session_state[f"edit_site_name_{i}"] = site
                        # Don't use st.rerun() - let the page refresh naturally
                with col3:
                    if st.button("Delete", key=f"delete_site_{i}", help="Delete this project site"):
                        if len(admin_project_sites) > 1:  # Don't allow deleting the last site
                            if delete_project_site(site):
                                st.success(f"Deleted '{site}' project site!")
                                # Don't use st.rerun() - let the page refresh naturally
                            else:
                                st.error("Failed to delete project site!")
                        else:
                            st.error("Cannot delete the last project site!")
                with col4:
                    if st.button("View", key=f"view_site_{i}", help="View items for this project site"):
                        st.session_state.current_project_site = site
                        # Clear cache when switching project sites
                        clear_cache()
                        st.success(f"Switched to '{site}' project site!")
                        # Don't use st.rerun() - let the page refresh naturally
                
                # Edit form for this site
                if st.session_state.get(f"editing_site_{i}", False):
                    with st.form(f"edit_form_{i}"):
                        new_name = st.text_input(
                            "New Project Site Name:", 
                            value=st.session_state.get(f"edit_site_name_{i}", site),
                            key=f"edit_input_{i}",
                            help="Enter the new name for this project site"
                        )
                        col_save, col_cancel = st.columns([1, 1])
                        with col_save:
                            if st.form_submit_button("💾 Save", type="primary"):
                                if new_name and new_name != site:
                                    if update_project_site_name(site, new_name):
                                        # Update current project site if it was the one being edited
                                        if st.session_state.get('current_project_site') == site:
                                            st.session_state.current_project_site = new_name
                                        
                                        st.success(f"✅ Updated '{site}' to '{new_name}'!")
                                        # Clear editing state
                                        if f"editing_site_{i}" in st.session_state:
                                            del st.session_state[f"editing_site_{i}"]
                                        if f"edit_site_name_{i}" in st.session_state:
                                            del st.session_state[f"edit_site_name_{i}"]
                                        # Don't use st.rerun() - let the page refresh naturally
                                    else:
                                        st.error("❌ A project site with this name already exists!")
                                elif new_name == site:
                                    st.info("ℹ️ No changes made.")
                                    # Clear editing state
                                    if f"editing_site_{i}" in st.session_state:
                                        del st.session_state[f"editing_site_{i}"]
                                    if f"edit_site_name_{i}" in st.session_state:
                                        del st.session_state[f"edit_site_name_{i}"]
                                    # Don't use st.rerun() - let the page refresh naturally
                                else:
                                    st.error("❌ Please enter a valid project site name!")
                        with col_cancel:
                            if st.form_submit_button("❌ Cancel"):
                                # Clear editing state
                                if f"editing_site_{i}" in st.session_state:
                                    del st.session_state[f"editing_site_{i}"]
                                if f"edit_site_name_{i}" in st.session_state:
                                    del st.session_state[f"edit_site_name_{i}"]
                                # Don't use st.rerun() - let the page refresh naturally
        else:
            st.warning("No project sites available.")
        
        # Add new project site
        with st.expander("➕ Add New Project Site", expanded=False):
            with st.form("add_project_site"):
                new_site_name = st.text_input("Project Site Name:", placeholder="e.g., Downtown Plaza", help="Enter a unique name for the new project site")
                new_site_description = st.text_area("Description (Optional):", placeholder="Brief description of the project site", help="Optional description for the project site")
                
                if st.form_submit_button("🏗️ Add Project Site", type="primary"):
                    if new_site_name:
                        if add_project_site(new_site_name, new_site_description):
                            st.session_state.current_project_site = new_site_name
                            # Clear cache when switching to new project site
                            clear_cache()
                            st.success(f"✅ Added '{new_site_name}' as a new project site!")
                            st.info(f"📊 This project site will have budgets 1-20 available.")
                            # Don't use st.rerun() - let the page refresh naturally
                        else:
                            st.error("❌ This project site already exists!")
                    else:
                        st.error("❌ Please enter a project site name!")
        
        st.divider()
        
        # Access Logs
        st.markdown("### Access Logs")
        st.caption("View all system access attempts and user activity")
        
        # Filter options
        col1, col2 = st.columns([2, 2])
        with col1:
            log_role = st.selectbox("Filter by Role", ["All", "admin", "user", "unknown"], key="log_role_filter")
        with col2:
            log_days = st.number_input("Last N Days", min_value=1, max_value=365, value=7, help="Show logs from last N days", key="log_days_filter")
        
        # Display access logs
        try:
            # Use simple connection to avoid I/O errors
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
            
            with conn:
                # Build query with filters - use a more robust date filter
                from datetime import datetime, timedelta
                cutoff_date = (datetime.now() - timedelta(days=log_days)).isoformat()
                
                query = """
                    SELECT access_code, user_name, access_time, success, role
                    FROM access_logs 
                    WHERE access_time >= ?
                """
                
                if log_role != "All":
                    query += f" AND role = '{log_role}'"
                
                query += " ORDER BY access_time DESC LIMIT 100"
                
                logs_df = pd.read_sql_query(query, conn, params=[cutoff_date])
                
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
                    
                    st.dataframe(display_logs, use_container_width=True)
                    
                    # Summary statistics
                    st.markdown("#### 📈 Access Statistics")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    total_access = len(logs_df)
                    successful_access = len(logs_df[logs_df['success'] == 1])
                    failed_access = len(logs_df[logs_df['success'] == 0])
                    unique_users = logs_df['user_name'].nunique()
                    
                    with col1:
                        st.metric("Total Access", total_access)
                    with col2:
                        st.metric("Successful", successful_access)
                    with col3:
                        st.metric("Failed", failed_access)
                    with col4:
                        st.metric("Unique Users", unique_users)
                    
                    # Role breakdown
                    st.markdown("#### Access by Role")
                    role_counts = logs_df['role'].value_counts()
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Admin Access", role_counts.get('admin', 0))
                    with col2:
                        st.metric("User Access", role_counts.get('user', 0))
                    with col3:
                        st.metric("Failed Access", role_counts.get('unknown', 0))
                    
                    # Export logs
                    csv_logs = logs_df.to_csv(index=False).encode("utf-8")
                    st.download_button("📥 Download Access Logs", csv_logs, "access_logs.csv", "text/csv")
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
        
        st.divider()
        
        # Database Maintenance
        st.markdown("### 🔧 Database Maintenance")
        st.caption("Maintain database integrity and resolve I/O errors")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.info("💡 **Database Maintenance**: Clean up WAL files and optimize database to resolve disk I/O errors.")
        with col2:
            if st.button("🔧 Maintain Database", type="secondary"):
                with st.spinner("Maintaining database..."):
                    if maintain_database():
                        st.success("✅ Database maintenance completed successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Database maintenance failed. Please try again.")
        
        st.divider()
        
        # Notifications Management - Collapsible
        with st.expander("🔔 Notifications", expanded=False):
            # Test notification button for debugging
            if st.button("🧪 Create Test Notification"):
                test_success = create_notification(
                    notification_type="test",
                    title="Test Notification",
                    message="This is a test notification to verify the system is working",
                    user_id=None,
                    request_id=None
                )
                if test_success:
                    st.success("✅ Test notification created successfully!")
                else:
                    st.error("❌ Failed to create test notification")
                st.rerun()
            
            # Display unread notifications
            notifications = get_admin_notifications()
            if notifications:
                st.markdown("#### 📬 New Notifications")
                st.caption(f"Found {len(notifications)} unread notifications")
                for notification in notifications:
                    with st.container():
                        st.write(f"**{notification['title']}** - {notification['created_at']}")
                        st.write(f"*{notification['message']}*")
                        
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            if st.button("✅ Mark as Read", key=f"mark_read_{notification['id']}"):
                                if mark_notification_read(notification['id']):
                                    st.success("Notification marked as read!")
                                    st.rerun()
                        with col2:
                            if notification['request_id']:
                                if st.button("View Request", key=f"view_request_{notification['id']}"):
                                    st.info("Navigate to Review & History tab to view the request")
                        st.divider()
            else:
                st.info("No new notifications")
                st.caption("All notifications from any project site will appear here")
            
            # Notification Log - All notifications (read and unread)
            st.markdown("#### Notification Log")
            all_notifications = get_all_notifications()
            if all_notifications:
                for notification in all_notifications[:10]:  # Show last 10 notifications
                    status_icon = "🔔" if notification['is_read'] == 0 else "✅"
                    st.write(f"{status_icon} **{notification['title']}** - {notification['created_at']}")
                    st.caption(f"*{notification['message']}*")
            else:
                st.info("No notifications in log")
        
        st.divider()
        
        # User Management
        st.markdown("### User Management")
        
        # Create new user
        with st.expander("➕ Create New User", expanded=False):
            with st.form("create_user_form"):
                st.markdown("#### Create New User")
                st.caption("💡 **Note**: Users will be created with access codes for their assigned project site.")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_access_code = st.text_input("🔐 Access Code", placeholder="Enter unique access code", help="Access code for this user to log in")
                with col2:
                    new_user_type = st.selectbox("🔑 User Type", ["user", "admin"], help="Admin users have full access, regular users are limited to their project site")
                with col3:
                    new_project_site = st.selectbox("🏗️ Project Site", get_project_sites(), help="Project site this user will be assigned to")
                
                if st.form_submit_button("👤 Create User", type="primary"):
                    if new_access_code:
                        # Create user with simplified approach
                        if create_simple_user("User", new_user_type, new_project_site, new_access_code):
                            st.success(f"✅ User created successfully!")
                            st.info(f"🔐 **Access Code**: `{new_access_code}` - User can now log in with this code")
                            # Clear cache to refresh user list without rerun
                            st.cache_data.clear()
                        else:
                            st.error("❌ Failed to create user. Access code might already exist.")
                    else:
                        st.error("❌ Please enter an access code")
        
        # Display existing users
        st.markdown("#### Current Users")
        
        # Add refresh button
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🔄 Refresh User List", help="Refresh the user list"):
                st.cache_data.clear()
                st.rerun()
        
        # Use cache_data to ensure the list refreshes when cache is cleared
        @st.cache_data
        def get_users_cached():
            return get_all_users()
        
        users = get_users_cached()
        
        # Debug: Show user count
        st.caption(f"📊 Total users in system: {len(users)}")
        if users:
            for user in users:
                col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
                with col1:
                    user_icon = "👑" if user['user_type'] == 'admin' else "👤"
                    st.write(f"{user_icon} **Access Code:** `{user['username']}`")
                with col2:
                    st.write(f"**Project:** {user['project_site']}")
                with col3:
                    # Show if this is the current user
                    if user['username'] == st.session_state.get('username'):
                        status = "🟢 Currently Logged In"
                    else:
                        status = "🟢 Active" if user['is_active'] else "🔴 Inactive"
                    st.write(status)
                with col4:
                    st.write(f"**Type:** {user['user_type'].title()}")
                with col5:
                    if user['username'] != st.session_state.get('username'):  # Don't allow deleting own account
                        if st.button("Delete", key=f"delete_user_{user['id']}", help="Delete this user"):
                            if delete_user(user['id']):
                                st.success(f"✅ User with access code '{user['username']}' deleted successfully!")
                                # Don't use st.rerun() - let the page refresh naturally
                            else:
                                st.error("❌ Failed to delete user. Please try again.")
                    else:
                        st.caption("👤 You")
        else:
            st.info("No users found")
        
        st.divider()
        
        # System Information
        st.markdown("### ℹ️ System Information")
        col1, col2 = st.columns([1, 1])
        with col1:
            st.info(f"**Current User:** {st.session_state.get('current_user_name', 'Unknown')}")
            st.info(f"**User Role:** {st.session_state.get('user_role', 'user').title()}")
        with col2:
            st.info(f"**Database:** SQLite")
            st.info(f"**Authentication:** Access Code System")
        
        st.caption("💡 **Note**: All access attempts are logged for security purposes. Admin users can view and export access logs.")


