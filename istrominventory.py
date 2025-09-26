import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from pathlib import Path

DB_PATH = Path("istrominventory.db")

# --------------- DB helpers ---------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
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

    conn.commit()
    conn.close()

def df_items(filters=None):
    q = "SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp FROM items WHERE 1=1"
    params = []
    if filters:
        for k, v in filters.items():
            if v:
                q += f" AND {k} = ?"
                params.append(v)
    # keep user’s preferred order (by budget/section/grp/name in some views, but we’ll default to id ASC here)
    q += " ORDER BY budget, section, grp, name"
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

def upsert_items(df, category_guess=None, budget=None, section=None, grp=None):
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
            # Upsert priority: code else name+category+context
            if code:
                cur.execute("SELECT id FROM items WHERE code = ?", (code,))
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE items SET name=?, category=?, unit=?, qty=?, unit_cost=?, budget=?, section=?, grp=? WHERE id=?",
                                (name, category, unit, qty, unit_cost, b, s, g, row[0]))
                else:
                    cur.execute("INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp) VALUES(?,?,?,?,?,?,?,?,?)",
                                (code, name, category, unit, qty, unit_cost, b, s, g))
            else:
                cur.execute(
                    "SELECT id FROM items WHERE name=? AND category=? AND IFNULL(budget,'')=IFNULL(?,'') AND IFNULL(section,'')=IFNULL(?,'') AND IFNULL(grp,'')=IFNULL(?,'')",
                    (name, category, b, s, g)
                )
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE items SET unit=?, qty=?, unit_cost=?, budget=?, section=?, grp=? WHERE id=?",
                                (unit, qty, unit_cost, b, s, g, row[0]))
                else:
                    cur.execute("INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp) VALUES(?,?,?,?,?,?,?,?,?)",
                                (None, name, category, unit, qty, unit_cost, b, s, g))
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

# --------------- Import helpers ---------------
KEYS_NAME = ["name", "item", "description", "material", "role"]
KEYS_QTY = ["qty", "quantity", "stock", "available", "available_slots", "balance"]
KEYS_UNIT = ["unit", "uom", "units"]
KEYS_CODE = ["code", "id", "item_id", "sku", "ref"]
KEYS_COST = ["unit_cost", "cost", "price", "rate"]

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
st.set_page_config(page_title="IstromInventory", page_icon="📦", layout="wide")
st.title("📦 IstromInventory — Materials & Labour Tracker")

init_db()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Import / Setup", "Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History"])

# -------------------------------- Tab 1: Import / Setup --------------------------------
with tab1:
    st.subheader("Import from Excel/CSV")
    uploaded = st.file_uploader("Upload file (.xlsx, .xls, .csv)", type=["xlsx","xls","csv"])
    df = None

    if uploaded is not None:
        if uploaded.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            try:
                xls = pd.ExcelFile(uploaded)
                sheet = st.selectbox("Choose sheet", xls.sheet_names)
                st.caption("If your sheet has title rows before the header, set the header row below.")
                header_row_1based = st.number_input("Header row (1-based)", min_value=1, value=1, step=1)
                skip_before = st.number_input("Rows to skip before data (usually 0)", min_value=0, value=0, step=1)
                df = pd.read_excel(xls, sheet_name=sheet, header=header_row_1based-1)
                if skip_before > 0:
                    df = df.iloc[skip_before:].reset_index(drop=True)
            except Exception as e:
                st.error(f"Couldn't read the Excel: {e}")
                df = None

    if df is not None and not df.empty:
        st.write("Detected columns:", list(df.columns))
        st.dataframe(df.head(20), use_container_width=True)

        auto_name = auto_pick(df.columns, KEYS_NAME)
        auto_qty = auto_pick(df.columns, KEYS_QTY)
        auto_unit = auto_pick(df.columns, KEYS_UNIT)
        auto_code = auto_pick(df.columns, KEYS_CODE)
        auto_cost = auto_pick(df.columns, KEYS_COST)

        st.info("Map columns (you can keep 'Auto' if the guess is correct)")
        name_col = st.selectbox("Name column", options=["Auto (best guess)"] + list(df.columns), index=0 if auto_name else 1)
        qty_col = st.selectbox("Quantity column", options=["Auto (best guess)"] + list(df.columns), index=0 if auto_qty else 1)
        unit_col = st.selectbox("Unit column", options=["(none)"] + list(df.columns), index=0 if not auto_unit else df.columns.get_loc(auto_unit)+1)
        code_col = st.selectbox("Code/ID column", options=["(none)"] + list(df.columns), index=0 if not auto_code else df.columns.get_loc(auto_code)+1)
        cost_col = st.selectbox("Unit cost column", options=["(none)"] + list(df.columns), index=0 if not auto_cost else df.columns.get_loc(auto_cost)+1)

        category_guess = st.selectbox("Treat rows as", options=["materials","labour"])
        budget_ctx = st.text_input("Budget label (e.g., 'Budget 1 - Flats')", "")
        section_ctx = st.text_input("Section (e.g., 'SUBSTRUCTURE (EXCAVATION TO DPC LEVEL)')", "")
        group_ctx = st.text_input("Group (e.g., 'MATERIAL ONLY' / 'WOODS' / 'PLUMBINGS')", "")

        if st.button("Import rows"):
            def pick(col, auto):
                if col == "Auto (best guess)":
                    return auto
                if col == "(none)":
                    return None
                return col

            col_name = pick(name_col, auto_name)
            col_qty = pick(qty_col, auto_qty)
            col_unit = pick(unit_col, auto_unit)
            col_code = pick(code_col, auto_code)
            col_cost = pick(cost_col, auto_cost)

            if not col_name:
                st.error("Please select a name column.")
            else:
                df2 = pd.DataFrame()
                df2["name"] = df[col_name].astype(str)
                df2["category"] = category_guess
                if col_qty:
                    df2["qty"] = df[col_qty].apply(to_number).fillna(0.0)
                else:
                    df2["qty"] = 0.0
                if col_unit:
                    df2["unit"] = df[col_unit].astype(str)
                if col_code:
                    df2["code"] = df[col_code].astype(str)
                if col_cost:
                    df2["unit_cost"] = df[col_cost].apply(to_number)

                if budget_ctx:
                    df2["budget"] = budget_ctx
                if section_ctx:
                    df2["section"] = section_ctx
                if group_ctx:
                    df2["grp"] = group_ctx

                upsert_items(df2, category_guess=category_guess, budget=budget_ctx or None, section=section_ctx or None, grp=group_ctx or None)
                st.success("Imported! Check the Inventory/Budgets tabs.")
                st.rerun()

# -------------------------------- Tab 2: Manual Entry (Budget Builder) --------------------------------
with tab2:
    st.subheader("Manual Entry — Budget Builder")
    st.caption("Add items line by line with Budget / Section / Group context before you start deducting with requests.")
    with st.form("manual_add"):
        budget = st.text_input("Budget label *", "Budget 1 - Flats")
        section = st.text_input("Section *", "SUBSTRUCTURE (EXCAVATION TO DPC LEVEL)")
        grp = st.text_input("Group *", "MATERIAL ONLY")

        col1, col2, col3, col4, col5 = st.columns([2,1,1,1,1])
        with col1:
            name = st.text_input("Item name *", placeholder="e.g., STONE DUST")
        with col2:
            qty = st.number_input("QTY *", min_value=0.0, step=1.0, value=0.0)
        with col3:
            unit = st.text_input("Unit", placeholder="e.g., trips / pcs / bags")
        with col4:
            rate = st.number_input("Rate (unit cost)", min_value=0.0, step=100.0, value=0.0)
        with col5:
            category = st.selectbox("Category", ["materials","labour"], index=0)

        submitted = st.form_submit_button("Add line")
        if submitted:
            df_new = pd.DataFrame([{
                "name": name,
                "qty": qty,
                "unit": unit or None,
                "unit_cost": rate or None,
                "category": category,
                "budget": budget,
                "section": section,
                "grp": grp
            }])
            upsert_items(df_new, category_guess=category, budget=budget, section=section, grp=grp)
            st.success(f"Added: {name} ({qty} {unit}) to {budget} / {section} / {grp}")
            st.rerun()

    st.divider()
    st.subheader("Budget View & Totals")
    b = st.text_input("Filter: Budget", "Budget 1 - Flats")
    s = st.text_input("Filter: Section (optional)")
    g = st.text_input("Filter: Group (optional)")
    dfb = df_items(filters={"budget": b, "section": s or None, "grp": g or None})
    if dfb.empty:
        st.info("No items yet for this filter.")
    else:
        dfb["Amount"] = (dfb["qty"].fillna(0) * dfb["unit_cost"].fillna(0)).round(2)
        st.dataframe(dfb[["budget","section","grp","name","qty","unit","unit_cost","Amount"]], use_container_width=True)
        total = float(dfb["Amount"].sum())  # show subtotal of filtered view
        st.metric("Subtotal", f"₦{total:,.2f}")

        # Delete items (as in your original style)
        st.markdown("### Delete items")
        for _, r in dfb.iterrows():
            c1, c2 = st.columns([8,1])
            c1.write(f"[{r['id']}] {r['name']} — {r['qty']} {r['unit'] or ''}")
            if c2.button("Delete", key=f"del_item_{int(r['id'])}"):
                err = delete_item(int(r["id"]))
                if err:
                    st.error(err)
                else:
                    st.success(f"Deleted item {r['id']}")
                    st.rerun()

# -------------------------------- Tab 3: Inventory --------------------------------
with tab3:
    st.subheader("Current Inventory")
    items = df_items()
    if not items.empty:
        items["Amount"] = (items["qty"].fillna(0) * items["unit_cost"].fillna(0)).round(2)
        st.dataframe(items, use_container_width=True)
    st.caption("Tip: Use Manual Entry / Import to populate budgets; use Make Request to deduct stock later.")

# -------------------------------- Tab 4: Make Request --------------------------------
with tab4:
    st.subheader("Make a Request")
    section = st.radio("Section", ["materials","labour"], horizontal=True)
    items_df = all_items_by_section(section)
    if items_df.empty:
        st.warning(f"No items found for {section}. Import or add items in the first tab.")
    else:
        item_row = st.selectbox("Item", options=items_df.to_dict('records'), format_func=lambda r: f"{r['name']} — {r['qty']} {r['unit'] or ''}")
        qty = st.number_input("Quantity to request", min_value=1.0, step=1.0, value=1.0)
        requested_by = st.text_input("Requested by")
        note = st.text_area("Note (optional)")
        if st.button("Submit request"):
            add_request(section, item_row['id'], qty, requested_by, note)
            st.success("Request submitted as Pending. Go to Review to Approve/Reject.")
            st.rerun()

# -------------------------------- Tab 5: Review & History --------------------------------
with tab5:
    st.subheader("Review Requests")
    status_filter = st.selectbox("Filter by status", ["All","Pending","Approved","Rejected"], index=1)
    reqs = df_requests(status=None if status_filter=="All" else status_filter)
    st.dataframe(reqs, use_container_width=True)

    st.write("Approve/Reject a request by ID:")
    colA, colB, colC = st.columns(3)
    with colA:
        req_id = st.number_input("Request ID", min_value=1, step=1)
    with colB:
        action = st.selectbox("Action", ["Approve","Reject","Set Pending"])
    with colC:
        approved_by = st.text_input("Approved by / Actor")

    if st.button("Apply"):
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
        if st.button("Clear All Deleted Logs"):
            clear_deleted_requests()
            st.success("All deleted requests cleared (testing mode).")
            st.rerun()
        st.caption("Deleted requests are logged here with details (req_id, item, qty, who requested, status, when deleted, deleted by).")
