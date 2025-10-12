# db.py
import os
from sqlalchemy import create_engine
import streamlit as st

@st.cache_resource
def get_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        # Fallback to SQLite for local development
        return create_engine("sqlite:///istrominventory.db", pool_pre_ping=True)
    
    # Handle both SQLite and PostgreSQL URLs
    if url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)
    elif url.startswith("postgresql"):
        # Ensure psycopg2 is used for PostgreSQL
        if not url.startswith("postgresql+psycopg2"):
            url = url.replace("postgresql://", "postgresql+psycopg2://")
        return create_engine(url, pool_pre_ping=True)
    else:
        raise RuntimeError(f"Unsupported database URL: {url}")

@st.cache_resource
def get_conn():
    """Get database connection using SQLAlchemy engine"""
    return get_engine().connect()

from contextlib import contextmanager

@contextmanager
def sql_conn():
    """Context manager for database connections"""
    conn = get_engine().connect()
    try:
        yield conn
    finally:
        conn.close()
