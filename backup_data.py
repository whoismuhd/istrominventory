#!/usr/bin/env python3
"""
Data backup and restore mechanism for Render deployment
Ensures data persistence across deployments
"""

import os
import json
import sqlite3
from database_config import get_conn, DATABASE_TYPE

def backup_to_json():
    """Backup current database to JSON file"""
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            
            # Get all data from all tables
            backup_data = {}
            
            # Get items
            cursor.execute("SELECT * FROM items")
            items = cursor.fetchall()
            backup_data['items'] = [list(item) for item in items]
            
            # Get users
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()
            backup_data['users'] = [list(user) for user in users]
            
            # Get requests
            cursor.execute("SELECT * FROM requests")
            requests = cursor.fetchall()
            backup_data['requests'] = [list(req) for req in requests]
            
            # Get notifications
            cursor.execute("SELECT * FROM notifications")
            notifications = cursor.fetchall()
            backup_data['notifications'] = [list(notif) for notif in notifications]
            
            # Get actuals
            cursor.execute("SELECT * FROM actuals")
            actuals = cursor.fetchall()
            backup_data['actuals'] = [list(actual) for actual in actuals]
            
            # Get access_codes
            cursor.execute("SELECT * FROM access_codes")
            access_codes = cursor.fetchall()
            backup_data['access_codes'] = [list(code) for code in access_codes]
            
            # Get access_logs
            cursor.execute("SELECT * FROM access_logs")
            access_logs = cursor.fetchall()
            backup_data['access_logs'] = [list(log) for log in access_logs]
            
            # Save to JSON file
            with open('backup_data.json', 'w') as f:
                json.dump(backup_data, f, indent=2)
            
            print(f"✅ Backup completed: {len(items)} items, {len(users)} users, {len(requests)} requests")
            return True
            
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False

def restore_from_json():
    """Restore data from JSON backup"""
    try:
        if not os.path.exists('backup_data.json'):
            print("📭 No backup file found")
            return True
        
        with open('backup_data.json', 'r') as f:
            backup_data = json.load(f)
        
        with get_conn() as conn:
            cursor = conn.cursor()
            
            # Clear existing data
            cursor.execute("DELETE FROM access_logs")
            cursor.execute("DELETE FROM access_codes")
            cursor.execute("DELETE FROM actuals")
            cursor.execute("DELETE FROM notifications")
            cursor.execute("DELETE FROM requests")
            cursor.execute("DELETE FROM users")
            cursor.execute("DELETE FROM items")
            
            # Restore items
            if 'items' in backup_data:
                for item in backup_data['items']:
                    cursor.execute("""
                        INSERT INTO items (id, name, code, unit_cost, budget, building_type, unit, category, section, grp, project_site, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, item)
            
            # Restore users
            if 'users' in backup_data:
                for user in backup_data['users']:
                    cursor.execute("""
                        INSERT INTO users (id, username, full_name, project_site, user_type, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, user)
            
            # Restore requests
            if 'requests' in backup_data:
                for req in backup_data['requests']:
                    cursor.execute("""
                        INSERT INTO requests (id, ts, section, item_id, qty, requested_by, note, status, approved_by, current_price, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, req)
            
            # Restore notifications
            if 'notifications' in backup_data:
                for notif in backup_data['notifications']:
                    cursor.execute("""
                        INSERT INTO notifications (id, notification_type, title, message, user_id, request_id, is_read, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, notif)
            
            # Restore actuals
            if 'actuals' in backup_data:
                for actual in backup_data['actuals']:
                    cursor.execute("""
                        INSERT INTO actuals (id, item_id, actual_qty, actual_cost, actual_date, recorded_by, notes, project_site, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, actual)
            
            # Restore access_codes
            if 'access_codes' in backup_data:
                for code in backup_data['access_codes']:
                    cursor.execute("""
                        INSERT INTO access_codes (id, admin_code, user_code, updated_at, updated_by)
                        VALUES (?, ?, ?, ?, ?)
                    """, code)
            
            # Restore access_logs
            if 'access_logs' in backup_data:
                for log in backup_data['access_logs']:
                    cursor.execute("""
                        INSERT INTO access_logs (id, username, action, timestamp, ip_address, user_agent)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, log)
            
            conn.commit()
            print(f"✅ Restore completed: {len(backup_data.get('items', []))} items, {len(backup_data.get('users', []))} users")
            return True
            
    except Exception as e:
        print(f"❌ Restore failed: {e}")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "backup":
        backup_to_json()
    elif len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore_from_json()
    else:
        print("Usage: python backup_data.py [backup|restore]")
