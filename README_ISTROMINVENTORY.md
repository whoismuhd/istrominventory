
# IstromInventory — Materials & Labour Tracker

A simple Streamlit + SQLite app.
- Import from Excel/CSV (map columns)
- Track current quantities/slots
- Submit requests (Pending)
- Approve/Reject (Approving deducts; reverting restores)

## Quick Start
1) Install Python 3.9+
2) Put these files in a folder (e.g., `istrominventory/`):
   - istrominventory.py
   - requirements.txt
3) Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4) Run the app:
   ```bash
   streamlit run istrominventory.py
   ```
5) In your browser:
   - **Import / Setup**: upload your Excel/CSV, map columns, import
   - **Inventory**: view items
   - **Make Request**: create a Pending request
   - **Review & History**: Approve/Reject; approvals deduct from stock

## Data
- Database: `istrominventory.db` (auto-created in the same folder)
- Items: code, name, category (materials/labour), unit, qty, unit_cost
- Requests: who/what/when/status; quantites deducted on approval

## Notes
- Import materials and labour separately (choose "Treat rows as" accordingly).
- If your Excel has multiple sheets, export the sheet you need and import.
