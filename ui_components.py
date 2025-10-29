"""
UI Components Module
Handles all user interface components, styling, and layout
"""

import streamlit as st
from datetime import datetime
import pytz

def get_nigerian_time():
    """Get current time in Nigerian timezone"""
    nigerian_tz = pytz.timezone('Africa/Lagos')
    return datetime.now(nigerian_tz)

def get_nigerian_time_iso():
    """Get current time in Nigerian timezone as ISO string"""
    return get_nigerian_time().isoformat()

def setup_page_config():
    """Setup page configuration"""
    st.set_page_config(
        page_title="Istrom Inventory Management System", 
        page_icon="📊", 
        layout="wide",
        initial_sidebar_state="collapsed"
    )

def setup_custom_css():
    """Setup custom CSS styling"""
    st.markdown("""
    <style>
    /* Professional styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1.1rem;
        opacity: 0.9;
    }
    
    .sidebar-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .sidebar-header h1 {
        margin: 0;
        font-size: 1.5rem;
        font-weight: 600;
    }
    
    .sidebar-header p {
        margin: 0.5rem 0 0 0;
        font-size: 0.9rem;
        opacity: 0.9;
    }
    
    .user-info-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    
    .user-info-card h3 {
        margin: 0 0 0.5rem 0;
        color: #1e293b;
        font-size: 1.1rem;
    }
    
    .user-info-card p {
        margin: 0.25rem 0;
        color: #64748b;
    }
    
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        margin-top: 0.5rem;
    }
    
    .status-admin {
        background: #dcfce7;
        color: #166534;
    }
    
    .status-user {
        background: #dbeafe;
        color: #1e40af;
    }
    
    .project-info {
        background: #f1f5f9;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 0.75rem;
        margin-bottom: 1rem;
        font-size: 0.9rem;
    }
    
    .project-info strong {
        color: #0369a1;
        font-weight: 600;
    }
    
    .metric-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1e293b;
        margin: 0;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #64748b;
        margin: 0.25rem 0 0 0;
    }
    
    .notification-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    
    .notification-title {
        font-weight: 600;
        color: #1e293b;
        margin: 0 0 0.5rem 0;
    }
    
    .notification-message {
        color: #64748b;
        margin: 0 0 0.5rem 0;
    }
    
    .notification-meta {
        font-size: 0.8rem;
        color: #94a3b8;
    }
    
    .success-message {
        background: #dcfce7;
        border: 1px solid #bbf7d0;
        color: #166534;
        padding: 0.75rem;
        border-radius: 6px;
        margin: 1rem 0;
    }
    
    .error-message {
        background: #fef2f2;
        border: 1px solid #fecaca;
        color: #dc2626;
        padding: 0.75rem;
        border-radius: 6px;
        margin: 1rem 0;
    }
    
    .warning-message {
        background: #fffbeb;
        border: 1px solid #fed7aa;
        color: #d97706;
        padding: 0.75rem;
        border-radius: 6px;
        margin: 1rem 0;
    }
    
    .info-message {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        color: #1d4ed8;
        padding: 0.75rem;
        border-radius: 6px;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)

def create_header(user_name, user_type, project_site, session_remaining):
    """Create main application header"""
    st.markdown(f"""
    <div class="main-header">
        <h1>Istrom Inventory Management System</h1>
        <p>Welcome, {user_name} | Project: {project_site} | Session: {session_remaining}</p>
    </div>
    """, unsafe_allow_html=True)

def create_sidebar():
    """Create sidebar with user information"""
    st.markdown("""
    <style>
    .sidebar-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .sidebar-header h1 {
        margin: 0;
        font-size: 1.5rem;
        font-weight: 600;
    }
    
    .sidebar-header p {
        margin: 0.5rem 0 0 0;
        font-size: 0.9rem;
        opacity: 0.9;
    }
    
    .user-info-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    
    .user-info-card h3 {
        margin: 0 0 0.5rem 0;
        color: #1e293b;
        font-size: 1.1rem;
    }
    
    .user-info-card p {
        margin: 0.25rem 0;
        color: #64748b;
    }
    
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        margin-top: 0.5rem;
    }
    
    .status-admin {
        background: #dcfce7;
        color: #166534;
    }
    
    .status-user {
        background: #dbeafe;
        color: #1e40af;
    }
    
    .project-info {
        background: #f1f5f9;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 0.75rem;
        margin-bottom: 1rem;
        font-size: 0.9rem;
    }
    
    .project-info strong {
        color: #0369a1;
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Professional header
    st.markdown("""
    <div class="sidebar-header">
        <h1>Istrom Inventory</h1>
        <p>Management System</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get current user info from session with safe defaults
    current_user = st.session_state.get('full_name', 'Unknown')
    current_role = st.session_state.get('user_type', 'user')
    current_project = st.session_state.get('current_project_site', 'Unknown Project')
    
    # Ensure current_role is never None
    if current_role is None:
        current_role = 'user'
    
    # User information card
    st.markdown(f"""
    <div class="user-info-card">
        <h3>User Information</h3>
        <p><strong>Name:</strong> {current_user}</p>
        <p><strong>Role:</strong> {current_role.title()}</p>
        <div class="status-badge status-{current_role}">
            {current_role.title()} Access
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Project information
    st.markdown(f"""
    <div class="project-info">
        <strong>Current Project:</strong><br>
        {current_project}
    </div>
    """, unsafe_allow_html=True)

def create_metric_card(title, value, delta=None):
    """Create a metric card"""
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">{value}</p>
        <p class="metric-label">{title}</p>
    </div>
    """, unsafe_allow_html=True)

def create_notification_card(notification):
    """Create a notification card"""
    st.markdown(f"""
    <div class="notification-card">
        <h4 class="notification-title">{notification['title']}</h4>
        <p class="notification-message">{notification['message']}</p>
        <p class="notification-meta">
            {notification['created_at']} | Type: {notification['notification_type']}
        </p>
    </div>
    """, unsafe_allow_html=True)

def show_success_message(message):
    """Show success message"""
    st.markdown(f"""
    <div class="success-message">
        {message}
    </div>
    """, unsafe_allow_html=True)

def show_error_message(message):
    """Show error message"""
    st.markdown(f"""
    <div class="error-message">
        {message}
    </div>
    """, unsafe_allow_html=True)

def show_warning_message(message):
    """Show warning message"""
    st.markdown(f"""
    <div class="warning-message">
        {message}
    </div>
    """, unsafe_allow_html=True)

def show_info_message(message):
    """Show info message"""
    st.markdown(f"""
    <div class="info-message">
        {message}
    </div>
    """, unsafe_allow_html=True)

def create_tabs():
    """Create main application tabs"""
    return st.tabs([
        "📊 Dashboard",
        "📦 Inventory",
        "📝 Make Request", 
        "📋 My Requests",
        "🔔 Notifications",
        "⚙️ Settings"
    ])

def create_logout_button():
    """Create logout button"""
    if st.button("🚪 Logout", type="secondary", use_container_width=True):
        # Clear all session state
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        # Let Streamlit handle page refresh naturally
