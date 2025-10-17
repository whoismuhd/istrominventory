import os
from sqlalchemy import create_engine, text

url = (os.getenv("DATABASE_URL") or "").strip()
if not url:
    raise SystemExit("Set DATABASE_URL before running this test.")
engine = create_engine(url, future=True, pool_pre_ping=True)
with engine.connect() as c:
    print(c.execute(text("SELECT version()")).scalar())
print("OK ✅")
