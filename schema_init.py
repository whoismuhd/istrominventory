# schema_init.py
from sqlalchemy import text
from db import get_engine

def ensure_schema() -> None:
    """
    Create the tables required by the app if they don't exist yet.
    Works on PostgreSQL and SQLite.
    """
    engine = get_engine()
    dialect = engine.url.get_backend_name()

    if dialect == "sqlite":
        items = """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT,
            budget REAL,
            building_type TEXT,
            unit TEXT,
            category TEXT,
            section TEXT,
            grp TEXT,
            qty REAL NOT NULL DEFAULT 0,
            unit_cost REAL,
            project_site TEXT DEFAULT 'Lifecamp Kafe',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
        actuals = """
        CREATE TABLE IF NOT EXISTS actuals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            actual_qty REAL,
            actual_cost REAL,
            actual_date TEXT,
            recorded_by TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            project_site TEXT,
            FOREIGN KEY (item_id) REFERENCES items(id)
        );
        """
    else:  # postgres (and others similar to PG)
        items = """
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            code TEXT,
            budget REAL,
            building_type TEXT,
            unit TEXT,
            category TEXT,
            section TEXT,
            grp TEXT,
            qty REAL NOT NULL DEFAULT 0,
            unit_cost REAL,
            project_site TEXT DEFAULT 'Lifecamp Kafe',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        actuals = """
        CREATE TABLE IF NOT EXISTS actuals (
            id SERIAL PRIMARY KEY,
            item_id INTEGER NOT NULL REFERENCES items(id),
            actual_qty REAL,
            actual_cost REAL,
            actual_date TEXT,
            recorded_by TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            project_site TEXT
        );
        """

    with engine.begin() as c:
        c.execute(text(items))
        c.execute(text(actuals))
