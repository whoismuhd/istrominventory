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

    # Example table used by logs: project_site_access_codes
    if dialect == "sqlite":
        ddl = """
        CREATE TABLE IF NOT EXISTS project_site_access_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT,
            access_code TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    else:
        ddl = """
        CREATE TABLE IF NOT EXISTS project_site_access_codes (
            id SERIAL PRIMARY KEY,
            site TEXT,
            access_code TEXT UNIQUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """

    with eng.begin() as conn:
        conn.execute(text(ddl))