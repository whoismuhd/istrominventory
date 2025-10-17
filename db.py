# db.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import streamlit as st

load_dotenv()  # loads .env locally if present

@st.cache_resource
def get_engine():
    """
    Returns a cached SQLAlchemy engine.
    - Render: DATABASE_URL (Internal) -> Postgres
    - Local:  DATABASE_URL (External) -> Postgres, else fallback -> SQLite
    """
    url = (os.getenv("DATABASE_URL") or "").strip()

    if not url:
        st.warning("⚠️ DATABASE_URL not set — using local SQLite (istrominventory.db)")
        return create_engine("sqlite:///istrominventory.db", future=True, pool_pre_ping=True)

    # Normalize legacy scheme if any
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)

    # External URLs from Render usually require SSL
    if "render.com" in url and "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    eng = create_engine(url, future=True, pool_pre_ping=True)

    # quick smoke test
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        st.error(f"❌ Postgres connect failed: {e}\n⚠️ Falling back to SQLite.")
        return create_engine("sqlite:///istrominventory.db", future=True, pool_pre_ping=True)

    return eng

def init_db():
    """Create tables needed by the app. Add more DDLs as the app requires."""
    eng = get_engine()
    dialect = eng.url.get_backend_name()

    # All the tables needed by the app
    tables = []
    
    if dialect == "sqlite":
        tables = [
            # access_codes table
            """
            CREATE TABLE IF NOT EXISTS access_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            );
            """,
            # project_site_access_codes table
            """
            CREATE TABLE IF NOT EXISTS project_site_access_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_site TEXT NOT NULL,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_site)
            );
            """,
            # project_sites table
            """
            CREATE TABLE IF NOT EXISTS project_sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
            """,
            # users table
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                user_type TEXT CHECK(user_type IN ('admin', 'user')) NOT NULL,
                project_site TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
            """,
            # items table
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # requests table
            """
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(item_id) REFERENCES items(id)
            );
            """,
            # notifications table
            """
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
            """,
            # access_logs table
            """
            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                access_code TEXT NOT NULL,
                user_name TEXT,
                access_time TEXT NOT NULL,
                success INTEGER DEFAULT 1,
                role TEXT
            );
            """,
            # deleted_requests table
            """
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
            """
        ]
    else:
        # PostgreSQL tables
        tables = [
            # access_codes table
            """
            CREATE TABLE IF NOT EXISTS access_codes (
                id SERIAL PRIMARY KEY,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            );
            """,
            # project_site_access_codes table
            """
            CREATE TABLE IF NOT EXISTS project_site_access_codes (
                id SERIAL PRIMARY KEY,
                project_site TEXT NOT NULL,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_site)
            );
            """,
            # project_sites table
            """
            CREATE TABLE IF NOT EXISTS project_sites (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
            """,
            # users table
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                user_type TEXT CHECK(user_type IN ('admin', 'user')) NOT NULL,
                project_site TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
            """,
            # items table
            """
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
            );
            """,
            # requests table
            """
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
            );
            """,
            # notifications table
            """
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
            );
            """,
            # access_logs table
            """
            CREATE TABLE IF NOT EXISTS access_logs (
                id SERIAL PRIMARY KEY,
                access_code TEXT NOT NULL,
                user_name TEXT,
                access_time TIMESTAMP NOT NULL,
                success INTEGER DEFAULT 1,
                role TEXT
            );
            """,
            # deleted_requests table
            """
            CREATE TABLE IF NOT EXISTS deleted_requests (
                id SERIAL PRIMARY KEY,
                req_id INTEGER,
                item_name TEXT,
                qty REAL,
                requested_by TEXT,
                status TEXT,
                deleted_at TIMESTAMP,
                deleted_by TEXT
            );
            """
        ]

    with eng.begin() as conn:
        for ddl in tables:
            conn.execute(text(ddl))
    
    # Initialize default access codes if they don't exist
    init_default_access_codes(eng)

def init_default_access_codes(eng):
    """Initialize default access codes if they don't exist"""
    try:
        with eng.connect() as conn:
            # Check if access codes exist
            result = conn.execute(text("SELECT COUNT(*) FROM access_codes"))
            count = result.fetchone()[0]
            
            if count == 0:
                # Insert default access codes
                from datetime import datetime
                import pytz
                
                wat_timezone = pytz.timezone('Africa/Lagos')
                current_time = datetime.now(wat_timezone)
                
                with eng.begin() as trans_conn:
                    trans_conn.execute(text("""
                        INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                        VALUES (:admin_code, :user_code, :updated_at, :updated_by)
                    """), {
                        "admin_code": "Istrom2026",  # Your admin code
                        "user_code": "user123",     # Default user code
                        "updated_at": current_time.isoformat(),
                        "updated_by": "System"
                    })
                print("✅ Default access codes initialized!")
            else:
                print("✅ Access codes already exist")
    except Exception as e:
        print(f"❌ Failed to initialize access codes: {e}")