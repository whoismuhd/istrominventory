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

DB_PATH = Path("istrominventory.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

# --------------- DB helpers ---------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    # Optimize SQLite settings for better performance
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=20000")  # Increased cache size
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory mapping
    conn.execute("PRAGMA optimize")  # Optimize database
    # Enable row factory for better performance
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
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
            grp TEXT       -- e.g., "MATERIAL ONLY" / "WOODS" / "PLUMBINGS"
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

    # --- Migration: add building_type column if missing ---
    cur.execute("PRAGMA table_info(items);")
    cols = [r[1] for r in cur.fetchall()]
    if "building_type" not in cols:
        cur.execute("ALTER TABLE items ADD COLUMN building_type TEXT;")


        conn.commit()
        conn.close()

# --------------- Backup and Data Protection Functions ---------------
def create_backup():
    """Create a timestamped backup of the database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"istrominventory_backup_{timestamp}.db"
    
    try:
        shutil.copy2(DB_PATH, backup_path)
        return str(backup_path)
    except Exception as e:
        st.error(f"❌ Failed to create backup: {str(e)}")
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
        st.error(f"❌ Failed to restore backup: {str(e)}")
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
                "export_timestamp": datetime.now().isoformat()
            }
            
            return json.dumps(export_data, indent=2, default=str)
    except Exception as e:
        st.error(f"❌ Failed to export data: {str(e)}")
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
        st.error(f"❌ Failed to import data: {str(e)}")
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
    with get_conn() as conn:
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

def clear_cache():
    """Clear the cached data when items are updated"""
    df_items_cached.clear()
    get_summary_data.clear()

@st.cache_data(ttl=300)  # Cache for 5 minutes
def df_items_cached():
    """Cached version of df_items for better performance"""
    q = "SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type FROM items WHERE 1=1"
    q += " ORDER BY budget, section, grp, building_type, name"
    with get_conn() as conn:
        return pd.read_sql_query(q, conn)

@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_budget_options():
    """Generate budget options - hardcoded to 1000 budgets for maximum flexibility"""
    budget_options = []
    
    # Generate budgets 1-1000 for all building types
    for budget_num in range(1, 1001):
        for bt in PROPERTY_TYPES:
            if bt:
                budget_options.extend([
                    f"Budget {budget_num} - {bt}",
                    f"Budget {budget_num} - {bt} (General Materials)",
                    f"Budget {budget_num} - {bt}(Woods)",
                    f"Budget {budget_num} - {bt}(Plumbings)",
                    f"Budget {budget_num} - {bt}(Irons)",
                    f"Budget {budget_num} - {bt} (Labour)"
                ])
    return budget_options

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_summary_data():
    """Cache summary data generation - optimized"""
    all_items = df_items_cached()
    if all_items.empty:
        return pd.DataFrame(), []
    
    all_items["Amount"] = (all_items["qty"].fillna(0) * all_items["unit_cost"].fillna(0)).round(2)
    
    # Create summary by budget and building type (optimized)
    summary_data = []
    
    # Only process budgets that actually have data - limit to first 10 for performance
    existing_budgets = all_items["budget"].str.extract(r"Budget (\d+)", expand=False).dropna().astype(int).unique()
    
    for budget_num in existing_budgets[:10]:  # Limit to first 10 budgets with data
        budget_items = all_items[all_items["budget"].str.contains(f"Budget {budget_num}", case=False, na=False)]
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

@st.cache_data(ttl=300)
def df_items(filters=None):
    """Get items with optional filtering - optimized with database queries"""
    if not filters or not any(v for v in filters.values() if v):
        return df_items_cached()
    
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

def upsert_items(df, category_guess=None, budget=None, section=None, grp=None, building_type=None):
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
            
            # Upsert priority: code else name+category+context
            if code:
                cur.execute("SELECT id FROM items WHERE code = ?", (code,))
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE items SET name=?, category=?, unit=?, qty=?, unit_cost=?, budget=?, section=?, grp=?, building_type=? WHERE id=?",
                                (name, category, unit, qty, unit_cost, b, s, g, bt, row[0]))
                else:
                    cur.execute("INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp,building_type) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (code, name, category, unit, qty, unit_cost, b, s, g, bt))
            else:
                cur.execute(
                    "SELECT id FROM items WHERE name=? AND category=? AND IFNULL(budget,'')=IFNULL(?,'') AND IFNULL(section,'')=IFNULL(?,'') AND IFNULL(grp,'')=IFNULL(?,'') AND IFNULL(building_type,'')=IFNULL(?,'')",
                    (name, category, b, s, g, bt)
                )
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE items SET unit=?, qty=?, unit_cost=?, budget=?, section=?, grp=?, building_type=? WHERE id=?",
                                (unit, qty, unit_cost, b, s, g, bt, row[0]))
                else:
                    cur.execute("INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp,building_type) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (None, name, category, unit, qty, unit_cost, b, s, g, bt))
        conn.commit()
        # Clear cache when items are updated
        clear_cache()

def update_item_qty(item_id: int, new_qty: float):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE items SET qty=? WHERE id=?", (float(new_qty), int(item_id)))
        conn.commit()

def update_item_rate(item_id: int, new_rate: float):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE items SET unit_cost=? WHERE id=?", (float(new_rate), int(item_id)))
        conn.commit()

def add_request(section, item_id, qty, requested_by, note):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO requests(ts, section, item_id, qty, requested_by, note, status) VALUES (?,?,?,?,?,?, 'Pending')",
                    (datetime.now().isoformat(timespec="seconds"), section, item_id, float(qty), requested_by, note))
        conn.commit()

def set_request_status(req_id, status, approved_by=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT item_id, qty, section, status FROM requests WHERE id=?", (req_id,))
        r = cur.fetchone()
        if not r:
            return "Request not found"
        item_id, qty, section, old_status = r
        if old_status == status:
            return None
        if status == "Approved":
            cur.execute("SELECT qty FROM items WHERE id=?", (item_id,))
            current_qty = cur.fetchone()[0]
            new_qty = current_qty - qty
            if new_qty < 0:
                return f"Insufficient stock/slots. Current: {current_qty}, requested: {qty}"
            cur.execute("UPDATE items SET qty=? WHERE id=?", (new_qty, item_id))
        if old_status == "Approved" and status in ("Pending","Rejected"):
            cur.execute("SELECT qty FROM items WHERE id=?", (item_id,))
            current_qty = cur.fetchone()[0]
            cur.execute("UPDATE items SET qty=? WHERE id=?", (current_qty + qty, item_id))
        cur.execute("UPDATE requests SET status=?, approved_by=? WHERE id=?", (status, approved_by, req_id))
        conn.commit()
    return None

def df_requests(status=None):
    q = "SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.status, r.approved_by FROM requests r JOIN items i ON r.item_id=i.id"
    params = ()
    if status and status != "All":
        q += " WHERE r.status=?"
        params = (status,)
    q += " ORDER BY r.id DESC"
    with get_conn() as conn:
        return pd.read_sql_query(q, conn, params=params)

def all_items_by_section(section):
    with get_conn() as conn:
        return pd.read_sql_query("SELECT id, name, unit, qty FROM items WHERE category=? ORDER BY name", conn, params=(section,))

def delete_item(item_id: int):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM items WHERE id=?", (item_id,))
            conn.commit()
        return None
    except sqlite3.IntegrityError:
        return "Cannot delete item: it has linked requests."
    except Exception as e:
        return f"Delete failed: {e}"

# ---------- NEW: delete_request logs + restore stock if needed ----------
def delete_request(req_id: int, deleted_by: str = "Admin"):
    """Delete a request (Pending/Approved/Rejected). If Approved, restore stock; always log to deleted_requests."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT r.id, i.name, r.qty, r.requested_by, r.status, r.item_id
                           FROM requests r JOIN items i ON r.item_id=i.id
                           WHERE r.id=?""", (req_id,))
            row = cur.fetchone()
            if not row:
                return "Request not found"
            req_id, item_name, qty, requested_by, status, item_id = row

            # If it was Approved, restore stock
            if status == "Approved":
                cur.execute("SELECT qty FROM items WHERE id=?", (item_id,))
                current_qty = cur.fetchone()[0]
                cur.execute("UPDATE items SET qty=? WHERE id=?", (current_qty + qty, item_id))

            # Log deletion
            cur.execute("""INSERT INTO deleted_requests(req_id, item_name, qty, requested_by, status, deleted_at, deleted_by)
                           VALUES(?,?,?,?,?,?,?)""",
                        (req_id, item_name, qty, requested_by, status,
                         datetime.now().isoformat(timespec="seconds"), deleted_by))

            # Delete request
            cur.execute("DELETE FROM requests WHERE id=?", (req_id,))
            conn.commit()
        return None
    except Exception as e:
        return f"Delete failed: {e}"

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
st.set_page_config(page_title="IstromInventory", page_icon="🏗️", layout="wide")
st.markdown(
    """
    <style>
    .app-brand {
        padding: 3rem 2rem;
        text-align: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        margin-bottom: 2rem;
        box-shadow: 0 20px 40px rgba(102, 126, 234, 0.3);
        position: relative;
        overflow: hidden;
    }
    
    .app-brand::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="25" cy="25" r="1" fill="white" opacity="0.1"/><circle cx="75" cy="75" r="1" fill="white" opacity="0.1"/><circle cx="50" cy="10" r="0.5" fill="white" opacity="0.1"/><circle cx="10" cy="60" r="0.5" fill="white" opacity="0.1"/><circle cx="90" cy="40" r="0.5" fill="white" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>');
        opacity: 0.3;
    }
    
    .app-brand h1 {
        font-size: 4.5rem;
        line-height: 1;
        margin: 0;
        font-weight: 900;
        background: linear-gradient(45deg, #ffffff, #f0f9ff);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        text-shadow: 0 4px 8px rgba(0,0,0,0.2);
        letter-spacing: -2px;
        margin-bottom: 1rem;
        position: relative;
        z-index: 1;
    }
    
    .app-brand .subtitle {
        color: rgba(255,255,255,0.95);
        font-size: 1.4rem;
        margin-top: 0.5rem;
        font-weight: 300;
        text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        position: relative;
        z-index: 1;
    }
    .chip {display:inline-block;padding:2px 8px;border-radius:999px;background:#eef2ff;color:#1f2937;font-size:12px;margin-right:6px;border:1px solid #e5e7eb}
    .chip.blue {background:#eff6ff;border-color:#dbeafe;color:#1e3a8a}
    .chip.green {background:#ecfdf5;border-color:#d1fae5;color:#065f46}
    .chip.gray {background:#f3f4f6;border-color:#e5e7eb;color:#374151}
    </style>
    <div class="app-brand">
      <h1>🏗️ IstromInventory</h1>
      <div class="subtitle">Professional Construction Inventory & Budget Management System</div>
    </div>
    """,
    unsafe_allow_html=True,
)

init_db()
ensure_indexes()

# Create automatic backup on startup
if not st.session_state.get('backup_created', False):
    backup_path = create_backup()
    if backup_path:
        st.session_state.backup_created = True
        cleanup_old_backups()

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

def set_auth_cookie(auth_data):
    """Set authentication data in browser cookie"""
    try:
        import base64
        import json
        encoded_data = base64.b64encode(json.dumps(auth_data).encode('utf-8')).decode('utf-8')
        st.query_params['auth_data'] = encoded_data
    except:
        pass

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "current_user_name" not in st.session_state:
    st.session_state.current_user_name = None
if "access_log_id" not in st.session_state:
    st.session_state.access_log_id = None
if "auth_timestamp" not in st.session_state:
    st.session_state.auth_timestamp = None

# Try to restore authentication from cookie on page load
if not st.session_state.authenticated:
    cookie_data = get_auth_cookie()
    if cookie_data:
        try:
            auth_time = datetime.fromisoformat(cookie_data['auth_timestamp'])
            current_time = datetime.now()
            # Check if authentication is still valid (24 hours)
            if (current_time - auth_time).total_seconds() < 86400:
                st.session_state.authenticated = True
                st.session_state.user_role = cookie_data['user_role']
                st.session_state.current_user_name = cookie_data['current_user_name']
                st.session_state.access_log_id = cookie_data.get('access_log_id')
                st.session_state.auth_timestamp = cookie_data['auth_timestamp']
        except:
            # Clear invalid cookie data
            st.query_params.clear()

# Check if authentication is still valid (24 hours)
def is_auth_valid():
    """Check if authentication is still valid (24 hours)"""
    if not st.session_state.authenticated or not st.session_state.auth_timestamp:
        return False
    
    try:
        auth_time = datetime.fromisoformat(st.session_state.auth_timestamp)
        current_time = datetime.now()
        # Authentication valid for 24 hours
        return (current_time - auth_time).total_seconds() < 86400
    except:
        return False

# Auto-logout if authentication expired
if st.session_state.authenticated and not is_auth_valid():
    st.session_state.authenticated = False
    st.session_state.user_role = None
    st.session_state.current_user_name = None
    st.session_state.access_log_id = None
    st.session_state.auth_timestamp = None
    # Clear cookie
    st.query_params.clear()

def is_admin():
    """Check if current user is admin"""
    return st.session_state.get('user_role') == 'admin'

def require_admin():
    """Require admin privileges, show error if not admin"""
    if not is_admin():
        st.error("❌ Admin privileges required for this action.")
        st.info("💡 Only administrators can perform this operation.")
        return False
    return True


# Access codes (you can change these)
ADMIN_ACCESS_CODE = "admin2024"
USER_ACCESS_CODE = "user2024"

def log_access(access_code, success=True, user_name="Unknown"):
    """Log access attempts to database"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            # Create access_logs table if it doesn't exist
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
            
            # Determine role based on access code
            role = "admin" if access_code == ADMIN_ACCESS_CODE else "user" if access_code == USER_ACCESS_CODE else "unknown"
            
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
    except Exception as e:
        st.error(f"Failed to log access: {str(e)}")
        return None

def check_access():
    """Check access with role-based authentication"""
    if st.session_state.authenticated:
        return True
    
    st.markdown("### 🔐 System Access")
    st.caption("Enter your access code to use the inventory system")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        access_code = st.text_input("Access Code", type="password", placeholder="Enter access code", key="access_code")
    with col2:
        user_name = st.text_input("Your Name", placeholder="Enter your name", key="user_name")
    
    if st.button("🚀 Access System", type="primary"):
        if not access_code or not user_name:
            st.error("❌ Please enter both access code and your name.")
        else:
            # Check access code
            if access_code == ADMIN_ACCESS_CODE:
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
                
                st.success(f"✅ Admin access granted! Welcome, {user_name}!")
                st.rerun()
            elif access_code == USER_ACCESS_CODE:
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
                st.success(f"✅ User access granted! Welcome, {user_name}!")
                st.rerun()
            else:
                log_access(access_code, success=False, user_name=user_name)
                st.error("❌ Invalid access code. Please try again.")
    
    st.stop()

# Check authentication before showing the app
check_access()


# Enhanced sidebar with user info
with st.sidebar:
    st.markdown("### 🏗️ IstromInventory")
    st.caption("Professional Construction Inventory System")
    
    st.divider()
    
    
    # Get current user info from session
    current_user = st.session_state.get('current_user_name', 'Unknown')
    current_role = st.session_state.get('user_role', 'user')
    
    st.markdown(f"**👤 User:** {current_user}")
    st.markdown(f"**🔑 Role:** {current_role.title()}")
    st.markdown("**Status:** ✅ Authenticated")
    
    # Show authentication expiry time
    if st.session_state.auth_timestamp:
        try:
            auth_time = datetime.fromisoformat(st.session_state.auth_timestamp)
            expiry_time = auth_time.replace(hour=auth_time.hour + 24)
            time_remaining = expiry_time - datetime.now()
            hours_remaining = int(time_remaining.total_seconds() / 3600)
            if hours_remaining > 0:
                st.markdown(f"**⏰ Session expires in:** {hours_remaining} hours")
            else:
                st.markdown("**⏰ Session expires:** Soon")
        except:
            st.markdown("**⏰ Session:** Active")
    
    st.divider()
    
    if st.button("🚪 Logout", type="secondary"):
        st.session_state.authenticated = False
        st.session_state.user_role = None
        st.session_state.current_user_name = None
        st.session_state.access_log_id = None
        st.session_state.auth_timestamp = None
        # Clear cookie
        st.query_params.clear()
        st.rerun()
    
    st.caption("System is ready for use")

# Create tabs based on user role
if st.session_state.get('user_role') == 'admin':
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History", "Budget Summary", "Admin Settings"])
else:
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History", "Budget Summary"])

# -------------------------------- Tab 1: Manual Entry (Budget Builder) --------------------------------
with tab1:
    st.subheader("📝 Manual Entry — Budget Builder")
    st.caption("Add items with proper categorization and context")
    
    # Check permissions for manual entry
    if not is_admin():
        st.warning("🔒 **Read-Only Access**: You can view items but cannot add, edit, or delete them.")
        st.info("💡 Contact an administrator if you need to make changes to the inventory.")
    
    # Project Context (outside form for immediate updates)
    st.markdown("### 🏗️ Project Context")
    col1, col2, col3 = st.columns([2,2,2])
    with col1:
        building_type = st.selectbox("🏠 Building Type", PROPERTY_TYPES, index=1, help="Select building type first", key="building_type_select")
    with col2:
        # Construction sections
        common_sections = [
            "SUBSTRUCTURE (GROUND TO DPC LEVEL)",
            "SUBSTRUCTURE (EXCAVATION TO DPC LEVEL)",
            "TERRACES (6-UNITS) DPC(TERRACE SUBSTRUCTURE)"
        ]
        
        section = st.selectbox("📚 Section", common_sections, index=0, help="Select construction section", key="manual_section_selectbox")
    with col3:
        # Filter budget options based on selected building type
        with st.spinner("Loading budget options..."):
            all_budget_options = get_budget_options()
            # Filter budgets that match the selected building type
            if building_type:
                budget_options = [opt for opt in all_budget_options if building_type in opt]
                # If no matching budgets found, show a message
                if not budget_options:
                    st.warning(f"No budgets found for {building_type}. Showing all budgets.")
                    budget_options = all_budget_options
            else:
                budget_options = all_budget_options
        
        # Budget selection - all budgets 1-1000 available
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

        st.markdown("### 🏷️ Category")
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
                st.error("❌ Admin privileges required for this action.")
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
                
                upsert_items(df_new, category_guess=category, budget=budget, section=section, grp=final_grp, building_type=final_bt)
                st.success(f"✅ Added: {name} ({qty} {unit}) to {budget} / {section} / {final_grp} / {final_bt}")
                st.info("💡 This item will now appear in the Budget Summary tab for automatic calculations!")
                st.rerun()

    st.divider()
    
    # Budget View & Totals
    st.subheader("📊 Budget View & Totals")
    
    # Filters
    st.markdown("### 🔍 Filters")
    col1, col2 = st.columns([2,2])
    with col1:
        # Create all budget options for the dropdown (cached)
        budget_options = get_budget_options()
        
        budget_filter = st.selectbox("🏷️ Budget Filter", budget_options, index=0, help="Select budget to filter", key="budget_filter_selectbox")
    with col2:
        # Construction sections
        common_sections = [
            "",
            "SUBSTRUCTURE (GROUND TO DPC LEVEL)",
            "SUBSTRUCTURE (EXCAVATION TO DPC LEVEL)",
            "TERRACES (6-UNITS) DPC(TERRACE SUBSTRUCTURE)"
        ]
        
        section_filter = st.selectbox("📂 Section Filter", common_sections, index=0, help="Select or type custom section", key="section_filter_selectbox")

    # Build filters for database-level filtering (much faster)
    filters = {}
    if budget_filter:
        filters["budget"] = budget_filter
    if section_filter:
        filters["section"] = section_filter
    
    # Get filtered items directly from database (cached)
    with st.spinner("Loading items..."):
        filtered_items = df_items(filters=filters)
        
    if filtered_items.empty:
        st.info("No items found matching your filters.")
        # Debug information
        st.write("**Debug Info:**")
        st.write(f"Budget filter selected: {budget_filter}")
        st.write(f"Section filter selected: {section_filter}")
        
        # Get debug info from database (cached)
        debug_items = df_items_cached()
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
        
        # Display table
        st.dataframe(
            filtered_items[["budget","section","grp","building_type","name","qty","unit","unit_cost","Amount"]],
            use_container_width=True,
            column_config={
                "unit_cost": st.column_config.NumberColumn("Unit Cost", format="₦%,.2f"),
                "Amount": st.column_config.NumberColumn("Amount", format="₦%,.2f"),
            }
        )
        
        # Show total
        total_amount = float(filtered_items["Amount"].sum())
        st.metric("💰 Total Amount", f"₦{total_amount:,.2f}")
        
        # Export
        csv_data = filtered_items.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv_data, "budget_view.csv", "text/csv")

# -------------------------------- Tab 2: Inventory --------------------------------
with tab2:
    st.subheader("📦 Current Inventory")
    
    # Check permissions for inventory management
    if not is_admin():
        st.warning("🔒 **Read-Only Access**: You can view inventory but cannot modify items.")
        st.info("💡 Contact an administrator if you need to make changes to the inventory.")
    st.caption("View, edit, and manage all inventory items")
    
    # Load all items first
    with st.spinner("Loading inventory..."):
        items = df_items()
    
    if not items.empty:
        items["Amount"] = (items["qty"].fillna(0) * items["unit_cost"].fillna(0)).round(2)

    # Simple filters - only Budget and Section
    st.markdown("### 🔍 Filters")
    
    colf1, colf2 = st.columns([2,2])
    with colf1:
        # Get all available budgets for dropdown
        all_budgets = items["budget"].unique() if not items.empty else []
        budget_options = ["All"] + sorted([budget for budget in all_budgets if pd.notna(budget)])
        f_budget = st.selectbox("🏷️ Budget Filter", budget_options, index=0, help="Select budget to filter by", key="inventory_budget_filter")
    with colf2:
        # Get all available sections for dropdown
        all_sections = items["section"].unique() if not items.empty else []
        section_options = ["All"] + sorted([section for section in all_sections if pd.notna(section)])
        f_section = st.selectbox("📂 Section Filter", section_options, index=0, help="Select section to filter by", key="inventory_section_filter")

    if not items.empty:
        # Apply only Budget and Section filters
        filtered_items = items.copy()
        
        # Budget filter (exact match from dropdown)
        if f_budget and f_budget != "All":
            budget_matches = filtered_items["budget"] == f_budget
            filtered_items = filtered_items[budget_matches]
        
        # Section filter (exact match from dropdown)
        if f_section and f_section != "All":
            section_matches = filtered_items["section"] == f_section
            filtered_items = filtered_items[section_matches]
        
        # Update items with filtered results
        items = filtered_items

        st.markdown("### 📊 Inventory Items")
        # Remove code column from display
        display_items = items.drop(columns=['code'], errors='ignore')
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

        st.markdown("### ✏️ Item Management")
        require_confirm = st.checkbox("Require confirmation for deletes", value=True, key="inv_confirm")
        
        # Simple item selection for deletion
        st.markdown("#### 🗑️ Select Items to Delete")
        
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
            
            if st.button("🗑️ Delete Selected Items", type="secondary", key="delete_button"):
                if require_confirm and not st.session_state.get("confirm_delete"):
                    st.session_state["confirm_delete"] = True
                    st.warning("⚠️ Click the button again to confirm deletion.")
                else:
                    # Clear confirmation state
                    if "confirm_delete" in st.session_state:
                        del st.session_state["confirm_delete"]
                    
                    # Delete selected items
                    deleted_count = 0
                    errors = []
                    
                    for item in selected_items:
                        err = delete_item(item['id'])
                        if err:
                            errors.append(f"Item {item['name']}: {err}")
                        else:
                            deleted_count += 1
                    
                    if errors:
                        for error in errors:
                            st.error(error)
                    
                    if deleted_count > 0:
                        st.success(f"✅ Successfully deleted {deleted_count} item(s).")
                        st.rerun()
        elif selected_items and not is_admin():
            st.error("❌ Admin privileges required for deletion.")
        
        # Individual item editing
        st.markdown("#### 📝 Individual Item Editing")
        for _, r in items.iterrows():
            with st.expander(f"📦 {r['name']} - {r['qty']} {r['unit'] or ''} @ ₦{(r['unit_cost'] or 0):,.2f}", expanded=False):
                col1, col2 = st.columns([1,1])
                
                with col1:
                    st.markdown("**Quantity**")
                    new_qty = st.number_input("New qty", value=float(r["qty"] or 0.0), step=1.0, key=f"qty_{int(r['id'])}")
                    if st.button("Update qty", key=f"upd_{int(r['id'])}"):
                        update_item_qty(int(r["id"]), float(new_qty))
                        st.success(f"✅ Quantity updated for item {int(r['id'])}")
                        st.rerun()
                
                with col2:
                    st.markdown("**Unit Cost**")
                    new_rate = st.number_input("New rate", value=float(r["unit_cost"] or 0.0), step=100.0, key=f"rate_{int(r['id'])}")
                    if st.button("Update rate", key=f"upd_rate_{int(r['id'])}"):
                        update_item_rate(int(r["id"]), float(new_rate))
                        st.success(f"✅ Rate updated for item {int(r['id'])}")
                        st.rerun()
    st.divider()
    st.markdown("### ⚠️ Danger Zone")
    coldz1, coldz2 = st.columns([3,2])
    with coldz1:
        if is_admin():
            also_logs = st.checkbox("Also clear deleted request logs", value=False, key="clear_logs")
        else:
            st.info("🔒 Admin privileges required for bulk operations")
    with coldz2:
        if is_admin():
            if st.button("🗑️ Delete ALL inventory and requests", type="secondary", key="delete_all_button"):
                if not st.session_state.get("confirm_clear_all"):
                    st.session_state["confirm_clear_all"] = True
                    st.warning("⚠️ Click the button again to confirm full deletion.")
                else:
                    clear_inventory(include_logs=also_logs)
                    st.success("✅ All items and requests cleared.")
                    st.rerun()
        else:
            st.button("🗑️ Delete ALL inventory and requests", type="secondary", key="delete_all_button", disabled=True, help="Admin privileges required")
    st.caption("Tip: Use Manual Entry / Import to populate budgets; use Make Request to deduct stock later.")
    

# -------------------------------- Tab 5: Budget Summary --------------------------------
with tab5:
    st.subheader("📈 Budget Summary by Building Type")
    st.caption("Comprehensive overview of all budgets and building types")
    
    # Navigation helper
    st.info("💡 **Tip**: Add items in the Manual Entry tab, then configure project structure here for automatic budget calculations!")
    
    # Get all items for summary (cached)
    with st.spinner("Loading budget summary data..."):
        all_items_summary, summary_data = get_summary_data()
    
    if not all_items_summary.empty:
        
        # Quick overview metrics
        st.markdown("#### 📊 Quick Overview")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            total_items = len(all_items_summary)
            st.metric("Total Items", total_items)
        with col2:
            total_amount = float(all_items_summary["Amount"].sum())
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
            
            # Grand total
            grand_total = sum([float(row["Total"].replace("₦", "").replace(",", "")) for row in summary_data])
            st.metric("🏆 Grand Total (All Budgets)", f"₦{grand_total:,.2f}")
            
            # Export summary
            summary_csv = summary_df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download Summary CSV", summary_csv, "budget_summary.csv", "text/csv")
        else:
            st.info("No budget data found for summary.")
    else:
        st.info("No items found for budget summary.")
    
    st.divider()
    
    # Manual Budget Summary Section
    st.subheader("📝 Manual Budget Summary")
    st.caption("Add custom budget summary information for each budget number")
    
    # Initialize session state for budget count
    if "max_budget_num" not in st.session_state:
        st.session_state.max_budget_num = 10
    
    # Add new budget button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("#### 📊 Available Budgets")
    with col2:
        if st.button("➕ Add New Budget", type="primary", key="add_new_budget"):
            st.session_state.max_budget_num += 1
            st.success(f"✅ Added Budget {st.session_state.max_budget_num}")
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
                budget_items = all_items_summary[all_items_summary["budget"].str.contains(f"Budget {budget_num}", case=False, na=False)]
                if not budget_items.empty:
                    budget_total = float(budget_items["Amount"].sum())
                    st.metric(f"Total Amount for Budget {budget_num}", f"₦{budget_total:,.2f}")
                    
                    # Show breakdown by building type
                    st.markdown("#### 🏗️ Breakdown by Building Type")
                    for building_type in PROPERTY_TYPES:
                        if building_type:
                            bt_items = budget_items[budget_items["building_type"] == building_type]
                            if not bt_items.empty:
                                bt_total = float(bt_items["Amount"].sum())
                                st.metric(f"{building_type}", f"₦{bt_total:,.2f}")
                else:
                    st.info(f"No items found for Budget {budget_num}")
            
            # Manual summary form for each building type
            st.markdown("#### 📋 Project Configuration by Building Type")
            
            for building_type in PROPERTY_TYPES:
                if building_type:
                    with st.expander(f"🏠 {building_type} Configuration", expanded=False):
                        with st.form(f"manual_summary_budget_{budget_num}_{building_type.lower().replace('-', '_')}"):
                            col1, col2 = st.columns([1, 1])
                            with col1:
                                num_blocks = st.number_input(
                                    f"Number of Blocks for {building_type}", 
                                    min_value=1, 
                                    step=1, 
                                    value=4,
                                    key=f"num_blocks_budget_{budget_num}_{building_type.lower().replace('-', '_')}"
                                )
                            
                            with col2:
                                units_per_block = st.number_input(
                                    f"Units per Block for {building_type}", 
                                    min_value=1, 
                                    step=1, 
                                    value=6 if building_type == "Flats" else 4 if building_type == "Terraces" else 2 if building_type == "Semi-detached" else 1,
                                    key=f"units_per_block_budget_{budget_num}_{building_type.lower().replace('-', '_')}"
                                )
                            
                            total_units = num_blocks * units_per_block
                            
                            # Additional notes
                            additional_notes = st.text_area(
                                f"Additional Notes for {building_type}",
                                placeholder="Add any additional budget information or notes...",
                                key=f"notes_budget_{budget_num}_{building_type.lower().replace('-', '_')}"
                            )
                            
                            submitted = st.form_submit_button(f"💾 Save {building_type} Configuration", type="primary")
                            
                            if submitted:
                                st.success(f"✅ {building_type} configuration saved for Budget {budget_num}!")
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
                                st.markdown("#### 📊 Manual Budget Summary")
                                st.markdown(f"""
                                **{building_type.upper()} BUDGET SUMMARY - BUDGET {budget_num}**
                                
                                - **GRAND TOTAL FOR 1 BLOCK**: ₦{amount_per_block:,.2f}
                                - **GRAND TOTAL FOR {num_blocks} BLOCKS**: ₦{total_budgeted_amount:,.2f}
                                - **TOTAL FOR 1 UNIT**: ₦{amount_per_unit:,.2f}
                                - **GRAND TOTAL FOR ALL {building_type.upper()} ({total_units}NOS)**: ₦{total_budgeted_amount:,.2f}
                                
                                {f"**Additional Notes**: {additional_notes}" if additional_notes else ""}
                                """)
                                
                                # Show calculation breakdown
                                st.markdown("#### 🔍 Calculation Breakdown")
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Amount per Unit", f"₦{amount_per_unit:,.2f}")
                                with col2:
                                    st.metric("Amount per Block (from DB)", f"₦{amount_per_block:,.2f}")
                                with col3:
                                    st.metric("Total for All Blocks", f"₦{total_budgeted_amount:,.2f}")
                                
                                # Show calculation formula
                                st.info(f"💡 **Formula**: Amount per Block = ₦{amount_per_block:,.2f} (from database) × {num_blocks} blocks = ₦{total_budgeted_amount:,.2f}")
                                st.info(f"💡 **Per Unit Formula**: Amount per Unit = ₦{amount_per_block:,.2f} ÷ {units_per_block} units = ₦{amount_per_unit:,.2f}")
                            else:
                                st.warning(f"No items found for {building_type} in Budget {budget_num}")
                        else:
                            st.warning("No items found in database")

# -------------------------------- Tab 4: Make Request --------------------------------
with tab3:
    st.subheader("Make a Request")
    st.caption("Request items for specific building types and budgets")
    
    # Check permissions for making requests
    if not is_admin():
        st.warning("🔒 **Read-Only Access**: You can view requests but cannot create new ones.")
        st.info("💡 Contact an administrator if you need to make requests.")
    
    # Project context for the request
    st.markdown("### 🏗️ Project Context")
    col1, col2, col3 = st.columns([2,2,2])
    with col1:
        section = st.radio("Section", ["materials","labour"], horizontal=True, key="request_section_radio")
    with col2:
        building_type = st.selectbox("🏠 Building Type", PROPERTY_TYPES, index=1, help="Select building type for this request", key="request_building_type_select")
    with col3:
        # Create budget options for the selected building type (cached)
        all_budget_options = get_budget_options()
        budget_options = [opt for opt in all_budget_options if building_type in opt]
        
        budget = st.selectbox("🏷️ Budget", budget_options, index=0, help="Select budget for this request", key="request_budget_select")
    
    # Filter items based on section, building type, and budget
    # Get all items first, then filter in memory for better flexibility
    all_items = df_items()
    
    # Apply filters step by step
    items_df = all_items.copy()
    
    # Filter by section (materials/labour)
    if section:
        items_df = items_df[items_df["category"] == section]
    
    # Filter by building type
    if building_type:
        items_df = items_df[items_df["building_type"] == building_type]
    
    # Filter by budget (smart matching)
    if budget:
        # For specific subgroups like "Budget 1 - Flats(Woods)", match exactly
        if "(" in budget and ")" in budget:
            # Exact match for specific subgroups
            budget_matches = items_df["budget"] == budget
        else:
            # For general budgets like "Budget 1 - Terraces", show ALL items under that budget
            # This includes "Budget 1 - Terraces", "Budget 1 - Terraces(Woods)", "Budget 1 - Terraces(Plumbings)", etc.
            budget_matches = items_df["budget"].str.contains(budget, case=False, na=False)
        
        # If no match found, try exact match as fallback
        if not budget_matches.any():
            st.warning(f"⚠️ No items found for budget '{budget}'. Trying exact match...")
            budget_matches = items_df["budget"] == budget
        
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
        
        # Debug information to help troubleshoot
        st.markdown("#### 🔍 Debug Information")
        st.write(f"**Filters applied:**")
        st.write(f"- Section: {section}")
        st.write(f"- Building Type: {building_type}")
        st.write(f"- Budget: {budget}")
        
        # Show what's actually in the database
        if not all_items.empty:
            st.write("**Available items in database:**")
            debug_df = all_items[["name", "category", "building_type", "budget"]].head(10)
            st.dataframe(debug_df, use_container_width=True)
            
            st.write("**Available budgets in database:**")
            unique_budgets = all_items["budget"].unique()
            for budget_name in unique_budgets[:10]:
                st.write(f"- {budget_name}")
            if len(unique_budgets) > 10:
                st.write(f"... and {len(unique_budgets) - 10} more")
            
            # Show items for the selected building type and budget (including subgroups)
            st.write(f"**Items for {building_type} building type and budget '{budget}' (including all subgroups):**")
            bt_budget_items = all_items[
                (all_items["building_type"] == building_type) & 
                (all_items["budget"].str.contains(budget, case=False, na=False))
            ]
            if not bt_budget_items.empty:
                bt_budget_debug_df = bt_budget_items[["name", "category", "budget"]].head(10)
                st.dataframe(bt_budget_debug_df, use_container_width=True)
            else:
                st.write(f"No items found for {building_type} building type with budget '{budget}' (including subgroups).")
                
            # Show items for the selected building type (all budgets)
            st.write(f"**All items for {building_type} building type (any budget):**")
            bt_items = all_items[all_items["building_type"] == building_type]
            if not bt_items.empty:
                bt_debug_df = bt_items[["name", "category", "budget"]].head(10)
                st.dataframe(bt_debug_df, use_container_width=True)
            else:
                st.write(f"No items found for {building_type} building type.")
        else:
            st.write("No items found in database at all.")
    else:
        st.markdown("### 📦 Available Items")
        item_row = st.selectbox("Item", options=items_df.to_dict('records'), format_func=lambda r: f"{r['name']} (Available: {r['qty']} {r['unit'] or ''}) — ₦{r['unit_cost'] or 0:,.2f}", key="request_item_select")
        
        st.markdown("### 📝 Request Details")
        col1, col2 = st.columns([1,1])
        with col1:
            qty = st.number_input("Quantity to request", min_value=1.0, step=1.0, value=1.0, key="request_qty_input")
            requested_by = st.text_input("Requested by", key="request_by_input")
        with col2:
            note = st.text_area("Note (optional)", key="request_note_input")
        
        # Show request summary
        if item_row and qty:
            total_cost = qty * (item_row.get('unit_cost', 0) or 0)
            st.markdown("### 💰 Request Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Unit Cost", f"₦{item_row.get('unit_cost', 0) or 0:,.2f}")
            with col2:
                st.metric("Quantity", f"{qty}")
            with col3:
                st.metric("Total Cost", f"₦{total_cost:,.2f}")
        
        if st.button("Submit request", key="submit_request_button", type="primary"):
            if not is_admin():
                st.error("❌ Admin privileges required for this action.")
                st.info("💡 Only administrators can submit requests.")
            else:
                add_request(section, item_row['id'], qty, requested_by, note)
                st.success(f"✅ Request submitted for {building_type} - {budget}. Go to Review to Approve/Reject.")
                st.rerun()

# -------------------------------- Tab 5: Review & History --------------------------------
with tab4:
    st.subheader("Review Requests")
    
    # Check permissions for request management
    if not is_admin():
        st.warning("🔒 **Read-Only Access**: You can view requests but cannot approve, reject, or modify them.")
        st.info("💡 Contact an administrator if you need to manage requests.")
    
    status_filter = st.selectbox("Filter by status", ["All","Pending","Approved","Rejected"], index=1)
    reqs = df_requests(status=None if status_filter=="All" else status_filter)
    st.dataframe(reqs, use_container_width=True)

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
            st.error("❌ Admin privileges required for this action.")
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
    st.subheader("Delete Requests")
    for _, r in reqs.iterrows():
        c1, c2 = st.columns([8,1])
        c1.write(f"[{int(r['id'])}] {r['item']} — {r['qty']} ({r['status']}) by {r['requested_by']}")
        if is_admin():
            if c2.button("Delete", key=f"del_req_{int(r['id'])}"):
                err = delete_request(int(r["id"]))  # logs + restores if approved
                if err:
                    st.error(err)
                else:
                    st.success(f"Deleted request {int(r['id'])} (logged)")
                    st.rerun()
        else:
            c2.button("Delete", key=f"del_req_{int(r['id'])}", disabled=True, help="Admin privileges required")

    st.divider()
    st.subheader("History")
    hist_tab1, hist_tab2 = st.tabs(["Approved Requests","Deleted Requests"])
    with hist_tab1:
        approved_df = df_requests("Approved")
        st.dataframe(approved_df, use_container_width=True)
        # Allow deleting approved directly from history
        for _, r in approved_df.iterrows():
            c1, c2 = st.columns([8,1])
            c1.write(f"[{int(r['id'])}] {r['item']} — {r['qty']} by {r['requested_by']}")
            if c2.button("Delete Approved", key=f"del_app_{int(r['id'])}"):
                err = delete_request(int(r["id"]))
                if err:
                    st.error(err)
                else:
                    st.success(f"Deleted approved request {int(r['id'])} (logged)")
                    st.rerun()

    with hist_tab2:
        deleted_log = df_deleted_requests()
        st.dataframe(deleted_log, use_container_width=True)
        # ---------- NEW: clear deleted logs for testing ----------
        if st.button("Clear All Deleted Logs", key="clear_deleted_logs_button"):
            clear_deleted_requests()
            st.success("All deleted requests cleared (testing mode).")
            st.rerun()
        st.caption("Deleted requests are logged here with details (req_id, item, qty, who requested, status, when deleted, deleted by).")

# -------------------------------- Tab 6: Admin Settings (Admin Only) --------------------------------
if st.session_state.get('user_role') == 'admin':
    with tab6:
        st.subheader("⚙️ Admin Settings")
        st.caption("Manage access codes and view system logs")
        
        # Access Code Management
        st.markdown("### 🔑 Access Code Management")
        
        with st.expander("🔧 Change Access Codes", expanded=False):
            st.markdown("#### Current Access Codes")
            col1, col2 = st.columns([1, 1])
            with col1:
                st.info(f"**Admin Code:** `{ADMIN_ACCESS_CODE}`")
            with col2:
                st.info(f"**User Code:** `{USER_ACCESS_CODE}`")
            
            st.markdown("#### Change Access Codes")
            st.caption("⚠️ **Warning**: Changing access codes will affect all users. Make sure to inform your team of the new codes.")
            
            with st.form("change_access_codes"):
                col1, col2 = st.columns([1, 1])
                with col1:
                    new_admin_code = st.text_input("New Admin Code", value=ADMIN_ACCESS_CODE, type="password", help="Enter new admin access code")
                with col2:
                    new_user_code = st.text_input("New User Code", value=USER_ACCESS_CODE, type="password", help="Enter new user access code")
                
                if st.form_submit_button("🔑 Update Access Codes", type="primary"):
                    if new_admin_code and new_user_code:
                        if new_admin_code == new_user_code:
                            st.error("❌ Admin and User codes cannot be the same.")
                        elif len(new_admin_code) < 4 or len(new_user_code) < 4:
                            st.error("❌ Access codes must be at least 4 characters long.")
                        else:
                            # Update the access codes in the code (this would require a restart)
                            st.warning("⚠️ **Note**: To change access codes, you need to update the code in the application. Contact your system administrator.")
                            st.info("💡 **Current codes**: Admin and User access codes are defined in the application code and require a code update to change.")
                    else:
                        st.error("❌ Please enter both access codes.")
        
        st.divider()
        
        # Access Logs
        st.markdown("### 📊 Access Logs")
        st.caption("View all system access attempts and user activity")
        
        # Filter options
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            log_role = st.selectbox("Filter by Role", ["All", "admin", "user", "unknown"], key="log_role_filter")
        with col2:
            log_days = st.number_input("Last N Days", min_value=1, max_value=365, value=7, help="Show logs from last N days", key="log_days_filter")
        with col3:
            if st.button("🔄 Refresh Logs", key="refresh_logs"):
                st.rerun()
        
        # Display access logs
        try:
            with get_conn() as conn:
                # Build query with filters
                query = """
                    SELECT access_code, user_name, access_time, success, role
                    FROM access_logs 
                    WHERE access_time >= datetime('now', '-{} days')
                """.format(log_days)
                
                if log_role != "All":
                    query += f" AND role = '{log_role}'"
                
                query += " ORDER BY access_time DESC LIMIT 100"
                
                logs_df = pd.read_sql_query(query, conn)
                
                if not logs_df.empty:
                    # Convert to West African Time for display
                    wat_timezone = pytz.timezone('Africa/Lagos')
                    
                    try:
                        # Ensure access_time is datetime type
                        logs_df['access_time'] = pd.to_datetime(logs_df['access_time'])
                        
                        # Check if already timezone-aware
                        if logs_df['access_time'].dt.tz is None:
                            # Not timezone-aware, localize to UTC first
                            logs_df['access_time'] = logs_df['access_time'].dt.tz_localize('UTC').dt.tz_convert(wat_timezone)
                        else:
                            # Already timezone-aware, just convert
                            logs_df['access_time'] = logs_df['access_time'].dt.tz_convert(wat_timezone)
                        
                        # Format the dataframe
                        logs_df['Access Time'] = logs_df['access_time'].dt.strftime('%H:%M:%S')
                        logs_df['Access Date'] = logs_df['access_time'].dt.strftime('%Y-%m-%d')
                    except Exception as e:
                        # Fallback: use original timestamps if conversion fails
                        st.warning(f"⚠️ Timezone conversion failed: {str(e)}")
                        logs_df['Access Time'] = logs_df['access_time'].astype(str).str[-8:]  # Last 8 chars for time
                        logs_df['Access Date'] = logs_df['access_time'].astype(str).str[:10]  # First 10 chars for date
                    logs_df['Status'] = logs_df['success'].map({1: '✅ Success', 0: '❌ Failed'})
                    logs_df['User'] = logs_df['user_name']
                    logs_df['Role'] = logs_df['role'].str.title()
                    logs_df['Access Code'] = logs_df['access_code']
                    
                    display_logs = logs_df[['User', 'Role', 'Access Code', 'Access Date', 'Access Time', 'Status']].copy()
                    display_logs.columns = ['User', 'Role', 'Access Code', 'Date', 'Time', 'Status']
                    
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
                    st.markdown("#### 👥 Access by Role")
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
        except Exception as e:
            st.error(f"Error loading access logs: {str(e)}")
        
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


