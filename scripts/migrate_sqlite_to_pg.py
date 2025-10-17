# scripts/migrate_sqlite_to_pg.py
import os, sqlite3, pandas as pd
from sqlalchemy import create_engine, text

SQLITE_PATH = os.getenv("SQLITE_PATH", "istrominventory.db")
PG_URL = os.getenv("DATABASE_URL")  # Put External URL in your local .env

if not os.path.exists(SQLITE_PATH):
    raise SystemExit(f"SQLite file not found: {SQLITE_PATH}")
if not PG_URL:
    raise SystemExit("Set DATABASE_URL to your Render External URL (with :5432 and ?sslmode=require).")

pg = create_engine(PG_URL, future=True)

# Create tables on Postgres (matching the app) if they don't exist
with pg.begin() as c:
    c.execute(text("""
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
    """))
    c.execute(text("""
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
    """))

# Copy data table by table
sq = sqlite3.connect(SQLITE_PATH)
for tbl in ["items", "actuals"]:
    df = pd.read_sql(f"SELECT * FROM {tbl}", sq)
    if df.empty:
        print(f"{tbl}: empty, skipped")
        continue
    df.to_sql(tbl, pg, if_exists="append", index=False)
    print(f"{tbl}: migrated {len(df)} rows")
sq.close()
print("Migration complete ✅")
