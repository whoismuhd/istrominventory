"""
Database Operations Module
Handles all database operations, queries, and data management
"""

import streamlit as st
from db import get_engine
from sqlalchemy import text
from datetime import datetime
import pytz

def get_nigerian_time():
    """Get current time in Nigerian timezone"""
    nigerian_tz = pytz.timezone('Africa/Lagos')
    return datetime.now(nigerian_tz)

def get_nigerian_time_iso():
    """Get current time in Nigerian timezone as ISO string"""
    return get_nigerian_time().isoformat()

def safe_db_operation(operation_func, *args, **kwargs):
    """Safely execute database operations with error handling"""
    try:
        return operation_func(*args, **kwargs)
    except Exception as e:
        st.error(f"Database operation failed: {e}")
        return None

def get_inventory_items(project_site=None, search_term=None, category=None):
    """Get inventory items with optional filtering"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = "SELECT * FROM items WHERE 1=1"
            params = {}
            
            if project_site:
                query += " AND project_site = :project_site"
                params['project_site'] = project_site
            
            if search_term:
                query += " AND (name LIKE :search_term OR code LIKE :search_term)"
                params['search_term'] = f"%{search_term}%"
            
            if category:
                query += " AND category = :category"
                params['category'] = category
            
            query += " ORDER BY name"
            
            result = conn.execute(text(query), params)
            return result.fetchall()
    except Exception as e:
        st.error(f"Error fetching inventory items: {e}")
        return []

def add_inventory_item(item_data):
    """Add new inventory item"""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO items (name, code, category, unit, qty, unit_cost, budget, section, grp, building_type, project_site, created_at)
                VALUES (:name, :code, :category, :unit, :qty, :unit_cost, :budget, :section, :grp, :building_type, :project_site, :created_at)
            """), {
                **item_data,
                'created_at': get_nigerian_time_iso()
            })
            return result.lastrowid
    except Exception as e:
        st.error(f"Error adding inventory item: {e}")
        return None

def update_inventory_item(item_id, item_data):
    """Update existing inventory item"""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE items SET name = :name, code = :code, category = :category, unit = :unit, 
                qty = :qty, unit_cost = :unit_cost, budget = :budget, section = :section, 
                grp = :grp, building_type = :building_type, project_site = :project_site
                WHERE id = :item_id
            """), {
                'item_id': item_id,
                **item_data
            })
            return result.rowcount > 0
    except Exception as e:
        st.error(f"Error updating inventory item: {e}")
        return False

def delete_inventory_item(item_id):
    """Delete inventory item"""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("DELETE FROM items WHERE id = :item_id"), {"item_id": item_id})
            return result.rowcount > 0
    except Exception as e:
        st.error(f"Error deleting inventory item: {e}")
        return False

def get_requests(project_site=None, status=None, user_name=None):
    """Get requests with optional filtering"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = "SELECT * FROM requests WHERE 1=1"
            params = {}
            
            if project_site:
                query += " AND project_site = :project_site"
                params['project_site'] = project_site
            
            if status:
                query += " AND status = :status"
                params['status'] = status
            
            if user_name:
                query += " AND requested_by = :user_name"
                params['user_name'] = user_name
            
            query += " ORDER BY created_at DESC"
            
            result = conn.execute(text(query), params)
            return result.fetchall()
    except Exception as e:
        st.error(f"Error fetching requests: {e}")
        return []

def add_request(request_data):
    """Add new request"""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO requests (item_name, qty, requested_by, project_site, status, created_at)
                VALUES (:item_name, :qty, :requested_by, :project_site, :status, :created_at)
            """), {
                **request_data,
                'created_at': get_nigerian_time_iso()
            })
            return result.lastrowid
    except Exception as e:
        st.error(f"Error adding request: {e}")
        return None

def update_request_status(request_id, status, approved_by=None):
    """Update request status"""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE requests SET status = :status, approved_by = :approved_by, updated_at = :updated_at
                WHERE id = :request_id
            """), {
                'request_id': request_id,
                'status': status,
                'approved_by': approved_by,
                'updated_at': get_nigerian_time_iso()
            })
            return result.rowcount > 0
    except Exception as e:
        st.error(f"Error updating request status: {e}")
        return False

def get_notifications(user_id=None, project_site=None, unread_only=False):
    """Get notifications with optional filtering"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = "SELECT * FROM notifications WHERE 1=1"
            params = {}
            
            if user_id:
                query += " AND user_id = :user_id"
                params['user_id'] = user_id
            
            if project_site:
                query += " AND project_site = :project_site"
                params['project_site'] = project_site
            
            if unread_only:
                query += " AND is_read = 0"
            
            query += " ORDER BY created_at DESC"
            
            result = conn.execute(text(query), params)
            return result.fetchall()
    except Exception as e:
        st.error(f"Error fetching notifications: {e}")
        return []

def add_notification(notification_data):
    """Add new notification"""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO notifications (user_id, title, message, notification_type, project_site, created_at)
                VALUES (:user_id, :title, :message, :notification_type, :project_site, :created_at)
            """), {
                **notification_data,
                'created_at': get_nigerian_time_iso()
            })
            return result.lastrowid
    except Exception as e:
        st.error(f"Error adding notification: {e}")
        return None

def mark_notification_read(notification_id):
    """Mark notification as read"""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE notifications SET is_read = 1, read_at = :read_at
                WHERE id = :notification_id
            """), {
                'notification_id': notification_id,
                'read_at': get_nigerian_time_iso()
            })
            return result.rowcount > 0
    except Exception as e:
        st.error(f"Error marking notification as read: {e}")
        return False

def get_project_sites():
    """Get all project sites"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM project_sites WHERE is_active = 1 ORDER BY name"))
            return result.fetchall()
    except Exception as e:
        st.error(f"Error fetching project sites: {e}")
        return []

def add_project_site(name, description):
    """Add new project site"""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO project_sites (name, description, created_at)
                VALUES (:name, :description, :created_at)
            """), {
                'name': name,
                'description': description,
                'created_at': get_nigerian_time_iso()
            })
            return result.lastrowid
    except Exception as e:
        st.error(f"Error adding project site: {e}")
        return None

def get_user_project_site():
    """Get current user's project site"""
    return st.session_state.get('project_site', 'Lifecamp Kafe')

def db_health():
    """Check database health"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return True, "Connected"
    except Exception as e:
        return False, str(e)
