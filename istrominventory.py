import streamlit as st
import sqlite3
import pandas as pd
import re
from functools import lru_cache
from datetime import datetime
from pathlib import Path
import time
import threading

DB_PATH = Path("istrominventory.db")

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
    """Cache budget options generation - highly optimized"""
    # Pre-generate common budget options for better performance
    budget_options = []
    
    # Only generate first 10 budgets to reduce dropdown size
    for budget_num in range(1, 11):
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

# Initialize session state for performance
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False

# Simple authentication system
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_login():
    """Simple login check"""
    if st.session_state.authenticated:
        return True
    
    st.markdown("### 🔐 System Access")
    st.caption("Enter the access code to use the inventory system")
    
    access_code = st.text_input("Access Code", type="password", placeholder="Enter access code", key="access_code")
    
    if st.button("🚀 Access System", type="primary"):
        # Simple access code - you can change this
        if access_code == "istrom2024":
            st.session_state.authenticated = True
            st.success("✅ Access granted! Welcome to IstromInventory.")
            st.rerun()
        else:
            st.error("❌ Invalid access code. Please try again.")
    
    st.stop()

# Check authentication before showing the app
check_login()

# Simple sidebar
with st.sidebar:
    st.markdown("### 🏗️ IstromInventory")
    st.caption("Professional Construction Inventory System")
    
    st.divider()
    
    st.markdown("**Status:** ✅ Authenticated")
    st.caption("System is ready for use")
    
    if st.button("🚪 Logout", type="secondary"):
        st.session_state.authenticated = False
        st.rerun()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History", "Budget Summary"])

# -------------------------------- Tab 1: Manual Entry (Budget Builder) --------------------------------
with tab1:
    st.subheader("📝 Manual Entry — Budget Builder")
    st.caption("Add items with proper categorization and context")
    
    # Add Item Form
    with st.form("add_item_form"):
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
            # Create all budget options for all building types and budget numbers (cached)
            with st.spinner("Loading budget options..."):
                budget_options = get_budget_options()
            
            budget = st.selectbox("🏷️ Budget Label", budget_options, index=0, help="Select budget type", key="budget_selectbox")

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
    st.caption("View, edit, and manage all inventory items")
    
    # Filters
    st.markdown("### 🔍 Filters")
    colf1, colf2, colf3 = st.columns([2,2,2])
    with colf1:
        f_budget = st.text_input("🏷️ Budget Filter", "", help="Filter by budget name", key="inv_budget_filter")
    with colf2:
        f_section = st.text_input("📂 Section Filter", "", help="Filter by section", key="inv_section_filter")
    with colf3:
        f_bt = st.selectbox("🏠 Building Type Filter", PROPERTY_TYPES, index=0, help="Filter by building type", key="inv_bt_filter")

    # Smart filtering for budget
    budget_filter_value = None
    if f_budget:
        if "(" in f_budget and ")" in f_budget:
            # Specific subgroup search
            budget_filter_value = f_budget
        else:
            # General search - use base budget
            budget_filter_value = f_budget.split("(")[0].strip()
    
    filters = {
        "budget": budget_filter_value,
        "section": f_section or None,
        "building_type": f_bt or None,
    }

    # Use optimized filtering with database queries
    with st.spinner("Loading inventory..."):
        items = df_items(filters=filters)
    
    if not items.empty:
        items["Amount"] = (items["qty"].fillna(0) * items["unit_cost"].fillna(0)).round(2)

    # Search and sort (always show)
    st.markdown("### 🔍 Search & Sort")
    col_search, col_sort = st.columns([3,2])
    with col_search:
        inv_search = st.text_input("🔍 Search name/code", "", help="Search by item name or code", key="inv_search_input")
    with col_sort:
        sort_choice = st.selectbox(
            "📊 Sort by",
            [
                "Name (A→Z)",
                "Name (Z→A)",
                "Qty (High→Low)",
                "Qty (Low→High)",
                "Amount (High→Low)",
                "Amount (Low→High)",
                "Rate (High→Low)",
                "Rate (Low→High)",
            ],
            index=0,
            help="Choose sorting option",
            key="inv_sort_selectbox"
        )

    if not items.empty:
        if inv_search:
            mask = (
                items["name"].astype(str).str.contains(inv_search, case=False, na=False)
                | items["code"].astype(str).str.contains(inv_search, case=False, na=False)
            )
            items = items[mask]

        if sort_choice == "Name (A→Z)":
            items = items.sort_values(by=["name"], ascending=True)
        elif sort_choice == "Name (Z→A)":
            items = items.sort_values(by=["name"], ascending=False)
        elif sort_choice == "Qty (High→Low)":
            items = items.sort_values(by=["qty"], ascending=False)
        elif sort_choice == "Qty (Low→High)":
            items = items.sort_values(by=["qty"], ascending=True)
        elif sort_choice == "Amount (High→Low)":
            items = items.sort_values(by=["Amount"], ascending=False)
        elif sort_choice == "Amount (Low→High)":
            items = items.sort_values(by=["Amount"], ascending=True)
        elif sort_choice == "Rate (High→Low)":
            items = items.sort_values(by=["unit_cost"], ascending=False)
        elif sort_choice == "Rate (Low→High)":
            items = items.sort_values(by=["unit_cost"], ascending=True)

        st.markdown("### 📊 Inventory Items")
        st.dataframe(
            items,
            use_container_width=True,
            column_config={
                "unit_cost": st.column_config.NumberColumn("Unit Cost", format="₦%,.2f"),
                "Amount": st.column_config.NumberColumn("Amount", format="₦%,.2f"),
                "qty": st.column_config.NumberColumn("Quantity", format="%.2f"),
            },
        )
        
        # Export
        csv_inv = items.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Inventory CSV", csv_inv, "inventory_view.csv", "text/csv")

        st.markdown("### ✏️ Quick Edit & Delete")
        require_confirm = st.checkbox("Require confirmation for deletes", value=True, key="inv_confirm")
        
        for _, r in items.iterrows():
            with st.expander(f"📦 {r['name']} - {r['qty']} {r['unit'] or ''} @ ₦{(r['unit_cost'] or 0):,.2f}", expanded=False):
                col1, col2, col3 = st.columns([1,1,1])
                
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
                
                with col3:
                    st.markdown("**Delete**")
                    if st.button("🗑️ Delete", key=f"inv_del_{int(r['id'])}"):
                        if require_confirm and not st.session_state.get(f"confirm_inv_{int(r['id'])}"):
                            st.session_state[f"confirm_inv_{int(r['id'])}"] = True
                            st.warning("⚠️ Click Delete again to confirm.")
                        else:
                            err = delete_item(int(r["id"]))
                            if err:
                                st.error(err)
                            else:
                                st.success(f"✅ Deleted item {int(r['id'])}")
                                st.rerun()
    st.divider()
    st.markdown("### ⚠️ Danger Zone")
    coldz1, coldz2 = st.columns([3,2])
    with coldz1:
        also_logs = st.checkbox("Also clear deleted request logs", value=False, key="clear_logs")
    with coldz2:
        if st.button("🗑️ Delete ALL inventory and requests", type="secondary", key="delete_all_button"):
            if not st.session_state.get("confirm_clear_all"):
                st.session_state["confirm_clear_all"] = True
                st.warning("⚠️ Click the button again to confirm full deletion.")
            else:
                clear_inventory(include_logs=also_logs)
                st.success("✅ All items and requests cleared.")
                st.rerun()
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
        item_row = st.selectbox("Item", options=items_df.to_dict('records'), format_func=lambda r: f"{r['name']} — {r['qty']} {r['unit'] or ''} — ₦{r['unit_cost'] or 0:,.2f}", key="request_item_select")
        
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
            add_request(section, item_row['id'], qty, requested_by, note)
            st.success(f"✅ Request submitted for {building_type} - {budget}. Go to Review to Approve/Reject.")
            st.rerun()

# -------------------------------- Tab 5: Review & History --------------------------------
with tab4:
    st.subheader("Review Requests")
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
        if c2.button("Delete", key=f"del_req_{int(r['id'])}"):
            err = delete_request(int(r["id"]))  # logs + restores if approved
            if err:
                st.error(err)
            else:
                st.success(f"Deleted request {int(r['id'])} (logged)")
                st.rerun()

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


