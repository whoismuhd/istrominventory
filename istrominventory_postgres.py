"""
Istrom Inventory Management System - PostgreSQL Version

This is the main application file refactored to use PostgreSQL with SQLAlchemy.
It replaces all SQLite dependencies with PostgreSQL-compatible code.
"""

import streamlit as st
import pandas as pd
import logging
from datetime import datetime, timedelta
import os
from database_postgres import (
    get_engine, get_conn, execute_query, execute_update, execute_insert,
    initialize_database, check_database_health, get_connection_string
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Istrom Inventory Management System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database on startup
if not initialize_database():
    st.error("Failed to initialize database. Please check your connection.")
    st.stop()

# Session state initialization
def initialize_session():
    """Initialize session state variables."""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'user_type' not in st.session_state:
        st.session_state.user_type = None
    if 'full_name' not in st.session_state:
        st.session_state.full_name = None
    if 'project_site' not in st.session_state:
        st.session_state.project_site = None
    if 'current_project_site' not in st.session_state:
        st.session_state.current_project_site = None

initialize_session()

# Database health check
def show_database_status():
    """Show database connection status in sidebar."""
    try:
        health = check_database_health()
        if health["status"] == "healthy":
            st.sidebar.success(f"✅ {health['database_type']} Connected")
            st.sidebar.caption(f"Database: {health.get('database_name', 'unknown')}")
        else:
            st.sidebar.error(f"❌ Database Error: {health.get('error', 'Unknown error')}")
    except Exception as e:
        st.sidebar.error(f"❌ Database Check Failed: {e}")

show_database_status()

# Authentication functions
def authenticate_user(access_code: str) -> bool:
    """
    Authenticate user with access code.
    Returns True if authentication successful, False otherwise.
    """
    try:
        # Check if it's the hardcoded admin code
        if access_code == "Istrom2026":
            st.session_state.logged_in = True
            st.session_state.user_type = "admin"
            st.session_state.full_name = "System Administrator"
            st.session_state.project_site = "ALL"
            st.session_state.current_project_site = "ALL"
            return True
        
        # Check database for user codes
        result = execute_query("""
            SELECT username, full_name, user_type, project_site 
            FROM users 
            WHERE username = :access_code AND is_active = 1
        """, {"access_code": access_code})
        
        if not result.empty:
            user = result.iloc[0]
            st.session_state.logged_in = True
            st.session_state.user_type = user['user_type']
            st.session_state.full_name = user['full_name']
            st.session_state.project_site = user['project_site']
            st.session_state.current_project_site = user['project_site']
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return False

def get_user_by_username(username: str) -> dict:
    """Get user information by username."""
    try:
        result = execute_query("""
            SELECT id, username, full_name, user_type, project_site, is_active
            FROM users 
            WHERE username = :username
        """, {"username": username})
        
        if not result.empty:
            return result.iloc[0].to_dict()
        return {}
        
    except Exception as e:
        logger.error(f"Failed to get user: {e}")
        return {}

def create_user(username: str, full_name: str, user_type: str, project_site: str) -> bool:
    """Create a new user."""
    try:
        user_data = {
            'username': username,
            'full_name': full_name,
            'user_type': user_type,
            'project_site': project_site,
            'is_active': 1
        }
        
        execute_update("""
            INSERT INTO users (username, full_name, user_type, project_site, is_active)
            VALUES (:username, :full_name, :user_type, :project_site, :is_active)
        """, user_data)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        return False

# Data retrieval functions
def get_items(project_site: str = None) -> pd.DataFrame:
    """Get items for a specific project site."""
    try:
        if project_site is None:
            project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
        
        result = execute_query("""
            SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type, project_site
            FROM items 
            WHERE project_site = :project_site
            ORDER BY budget, section, grp, building_type, name
        """, {"project_site": project_site})
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get items: {e}")
        return pd.DataFrame()

def get_requests(project_site: str = None, status: str = None) -> pd.DataFrame:
    """Get requests for a specific project site."""
    try:
        if project_site is None:
            project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
        
        query = """
            SELECT r.id, r.item_id, r.item_name, r.requested_by, r.requested_qty, 
                   r.current_price, r.status, r.note, r.created_at, r.approved_by, 
                   r.approved_at, r.rejected_by, r.rejected_at
            FROM requests r
            WHERE r.requested_by IN (
                SELECT full_name FROM users WHERE project_site = :project_site
            )
        """
        params = {"project_site": project_site}
        
        if status:
            query += " AND r.status = :status"
            params["status"] = status
        
        query += " ORDER BY r.created_at DESC"
        
        result = execute_query(query, params)
        return result
        
    except Exception as e:
        logger.error(f"Failed to get requests: {e}")
        return pd.DataFrame()

def get_notifications(user_id: int = None) -> pd.DataFrame:
    """Get notifications for a user."""
    try:
        if user_id is None:
            # Get all notifications for admins
            result = execute_query("""
                SELECT n.id, n.sender_id, n.receiver_id, n.message, n.type, 
                       n.is_read, n.created_at, n.event_key,
                       s.full_name as sender_name
                FROM notifications n
                LEFT JOIN users s ON n.sender_id = s.id
                ORDER BY n.created_at DESC
                LIMIT 50
            """)
        else:
            # Get notifications for specific user
            result = execute_query("""
                SELECT n.id, n.sender_id, n.receiver_id, n.message, n.type, 
                       n.is_read, n.created_at, n.event_key,
                       s.full_name as sender_name
                FROM notifications n
                LEFT JOIN users s ON n.sender_id = s.id
                WHERE n.receiver_id = :user_id
                ORDER BY n.created_at DESC
                LIMIT 50
            """, {"user_id": user_id})
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        return pd.DataFrame()

def create_notification(sender_id: int, receiver_id: int, message: str, notification_type: str = 'info', event_key: str = None) -> bool:
    """Create a notification."""
    try:
        notification_data = {
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'message': message,
            'type': notification_type,
            'event_key': event_key
        }
        
        execute_update("""
            INSERT INTO notifications (sender_id, receiver_id, message, type, event_key)
            VALUES (:sender_id, :receiver_id, :message, :type, :event_key)
        """, notification_data)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
        return False

# Main application interface
def main():
    """Main application interface."""
    
    # Check if user is logged in
    if not st.session_state.get('logged_in', False):
        show_login_page()
        return
    
    # Show main application
    show_main_application()

def show_login_page():
    """Show login page."""
    st.title("🔐 Istrom Inventory Management System")
    st.markdown("---")
    
    with st.form("login_form"):
        st.subheader("Login")
        access_code = st.text_input("Access Code", type="password", placeholder="Enter your access code")
        submit_button = st.form_submit_button("Login", type="primary")
        
        if submit_button:
            if access_code:
                if authenticate_user(access_code):
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid access code. Please try again.")
            else:
                st.warning("Please enter an access code.")

def show_main_application():
    """Show main application interface."""
    
    # Header
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.title("📦 Istrom Inventory Management System")
    
    with col2:
        st.metric("User", st.session_state.get('full_name', 'Unknown'))
        st.metric("Access Level", st.session_state.get('user_type', 'Unknown').title())
    
    with col3:
        st.metric("Project Site", st.session_state.get('project_site', 'Unknown'))
        if st.button("Logout", type="secondary"):
            st.session_state.logged_in = False
            st.rerun()
    
    st.markdown("---")
    
    # Main tabs
    if st.session_state.get('user_type') == 'admin':
        show_admin_interface()
    else:
        show_user_interface()

def show_admin_interface():
    """Show admin interface."""
    
    tabs = st.tabs(["📊 Dashboard", "📦 Inventory", "📝 Requests", "👥 Users", "⚙️ Settings"])
    
    with tabs[0]:
        show_admin_dashboard()
    
    with tabs[1]:
        show_inventory_management()
    
    with tabs[2]:
        show_request_management()
    
    with tabs[3]:
        show_user_management()
    
    with tabs[4]:
        show_admin_settings()

def show_user_interface():
    """Show user interface."""
    
    tabs = st.tabs(["📊 Dashboard", "📦 Inventory", "📝 Make Request", "📋 My Requests", "🔔 Notifications"])
    
    with tabs[0]:
        show_user_dashboard()
    
    with tabs[1]:
        show_inventory_view()
    
    with tabs[2]:
        show_request_form()
    
    with tabs[3]:
        show_user_requests()
    
    with tabs[4]:
        show_user_notifications()

def show_admin_dashboard():
    """Show admin dashboard."""
    st.subheader("📊 Admin Dashboard")
    
    # Get statistics
    try:
        # Total items
        items_count = execute_query("SELECT COUNT(*) FROM items").iloc[0, 0]
        
        # Total requests
        requests_count = execute_query("SELECT COUNT(*) FROM requests").iloc[0, 0]
        
        # Pending requests
        pending_requests = execute_query("SELECT COUNT(*) FROM requests WHERE status = 'pending'").iloc[0, 0]
        
        # Total users
        users_count = execute_query("SELECT COUNT(*) FROM users").iloc[0, 0]
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Items", items_count)
        
        with col2:
            st.metric("Total Requests", requests_count)
        
        with col3:
            st.metric("Pending Requests", pending_requests)
        
        with col4:
            st.metric("Total Users", users_count)
        
        # Recent activity
        st.subheader("Recent Activity")
        recent_requests = execute_query("""
            SELECT item_name, requested_by, status, created_at
            FROM requests
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        if not recent_requests.empty:
            st.dataframe(recent_requests, use_container_width=True)
        else:
            st.info("No recent activity")
            
    except Exception as e:
        st.error(f"Failed to load dashboard data: {e}")

def show_user_dashboard():
    """Show user dashboard."""
    st.subheader("📊 User Dashboard")
    
    # Get user-specific statistics
    try:
        user_name = st.session_state.get('full_name')
        project_site = st.session_state.get('project_site')
        
        # User's items
        items_count = execute_query("""
            SELECT COUNT(*) FROM items WHERE project_site = :project_site
        """, {"project_site": project_site}).iloc[0, 0]
        
        # User's requests
        requests_count = execute_query("""
            SELECT COUNT(*) FROM requests WHERE requested_by = :user_name
        """, {"user_name": user_name}).iloc[0, 0]
        
        # Pending requests
        pending_requests = execute_query("""
            SELECT COUNT(*) FROM requests 
            WHERE requested_by = :user_name AND status = 'pending'
        """, {"user_name": user_name}).iloc[0, 0]
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Available Items", items_count)
        
        with col2:
            st.metric("My Requests", requests_count)
        
        with col3:
            st.metric("Pending Requests", pending_requests)
        
        # Recent requests
        st.subheader("My Recent Requests")
        user_requests = execute_query("""
            SELECT item_name, requested_qty, status, created_at
            FROM requests
            WHERE requested_by = :user_name
            ORDER BY created_at DESC
            LIMIT 10
        """, {"user_name": user_name})
        
        if not user_requests.empty:
            st.dataframe(user_requests, use_container_width=True)
        else:
            st.info("No requests yet")
            
    except Exception as e:
        st.error(f"Failed to load dashboard data: {e}")

def show_inventory_management():
    """Show inventory management interface."""
    st.subheader("📦 Inventory Management")
    
    # Get items
    items_df = get_items()
    
    if not items_df.empty:
        st.dataframe(items_df, use_container_width=True)
    else:
        st.info("No items found")

def show_inventory_view():
    """Show inventory view for users."""
    st.subheader("📦 Available Items")
    
    # Get items for user's project
    project_site = st.session_state.get('project_site')
    items_df = get_items(project_site)
    
    if not items_df.empty:
        st.dataframe(items_df, use_container_width=True)
    else:
        st.info("No items available for your project")

def show_request_management():
    """Show request management interface."""
    st.subheader("📝 Request Management")
    
    # Get all requests
    requests_df = get_requests()
    
    if not requests_df.empty:
        st.dataframe(requests_df, use_container_width=True)
    else:
        st.info("No requests found")

def show_request_form():
    """Show request form for users."""
    st.subheader("📝 Make a Request")
    
    with st.form("request_form"):
        # Get items for selection
        items_df = get_items()
        
        if not items_df.empty:
            item_options = items_df.apply(lambda x: f"{x['name']} ({x['unit']}) - ₦{x['unit_cost']:,.2f}", axis=1).tolist()
            selected_item = st.selectbox("Select Item", item_options)
            
            if selected_item:
                # Get selected item details
                item_index = item_options.index(selected_item)
                selected_item_data = items_df.iloc[item_index]
                
                quantity = st.number_input("Quantity", min_value=0.1, step=0.1, value=1.0)
                note = st.text_area("Note (optional)")
                
                if st.form_submit_button("Submit Request", type="primary"):
                    # Create request
                    request_data = {
                        'item_id': selected_item_data['id'],
                        'item_name': selected_item_data['name'],
                        'requested_by': st.session_state.get('full_name'),
                        'requested_qty': quantity,
                        'current_price': selected_item_data['unit_cost'],
                        'status': 'pending',
                        'note': note
                    }
                    
                    try:
                        execute_update("""
                            INSERT INTO requests (item_id, item_name, requested_by, requested_qty, current_price, status, note)
                            VALUES (:item_id, :item_name, :requested_by, :requested_qty, :current_price, :status, :note)
                        """, request_data)
                        
                        st.success("Request submitted successfully!")
                        
                        # Create notification for admins
                        create_notification(
                            sender_id=None,
                            receiver_id=None,  # All admins
                            message=f"{st.session_state.get('full_name')} submitted a request for {quantity} units of {selected_item_data['name']}",
                            notification_type='new_request',
                            event_key=f'request:{selected_item_data["id"]}:submitted'
                        )
                        
                    except Exception as e:
                        st.error(f"Failed to submit request: {e}")
        else:
            st.info("No items available for your project")

def show_user_requests():
    """Show user's requests."""
    st.subheader("📋 My Requests")
    
    user_name = st.session_state.get('full_name')
    requests_df = execute_query("""
        SELECT item_name, requested_qty, current_price, status, note, created_at
        FROM requests
        WHERE requested_by = :user_name
        ORDER BY created_at DESC
    """, {"user_name": user_name})
    
    if not requests_df.empty:
        st.dataframe(requests_df, use_container_width=True)
    else:
        st.info("No requests found")

def show_user_notifications():
    """Show user notifications."""
    st.subheader("🔔 Notifications")
    
    # Get user ID
    user_name = st.session_state.get('full_name')
    user_data = execute_query("SELECT id FROM users WHERE full_name = :user_name", {"user_name": user_name})
    
    if not user_data.empty:
        user_id = user_data.iloc[0]['id']
        notifications_df = get_notifications(user_id)
        
        if not notifications_df.empty:
            st.dataframe(notifications_df, use_container_width=True)
        else:
            st.info("No notifications")
    else:
        st.info("No notifications")

def show_user_management():
    """Show user management interface."""
    st.subheader("👥 User Management")
    
    # Get all users
    users_df = execute_query("""
        SELECT username, full_name, user_type, project_site, created_at, is_active
        FROM users
        ORDER BY created_at DESC
    """)
    
    if not users_df.empty:
        st.dataframe(users_df, use_container_width=True)
    else:
        st.info("No users found")

def show_admin_settings():
    """Show admin settings."""
    st.subheader("⚙️ Admin Settings")
    
    # Database status
    st.markdown("#### Database Status")
    health = check_database_health()
    
    if health["status"] == "healthy":
        st.success(f"✅ {health['database_type']} - {health.get('database_name', 'unknown')}")
    else:
        st.error(f"❌ Database Error: {health.get('error', 'Unknown error')}")
    
    # Connection info
    st.markdown("#### Connection Information")
    st.code(get_connection_string())

# Run the application
if __name__ == "__main__":
    main()
