"""
Authentication and Session Management Module
Handles user authentication, session management, and access control
"""

import streamlit as st
import base64
import json
from datetime import datetime
import pytz
from db import get_engine
from sqlalchemy import text

def get_nigerian_time():
    """Get current time in Nigerian timezone"""
    nigerian_tz = pytz.timezone('Africa/Lagos')
    return datetime.now(nigerian_tz)

def get_nigerian_time_iso():
    """Get current time in Nigerian timezone as ISO string"""
    return get_nigerian_time().isoformat()

def initialize_session():
    """Initialize session state with defaults"""
    defaults = {
        'logged_in': False,
        'user_id': None,
        'username': None,
        'full_name': None,
        'user_type': None,
        'project_site': None,
        'admin_code': None,
        'current_project_site': 'Lifecamp Kafe',
        'auth_timestamp': None
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_access_codes():
    """Get all access codes with caching to reduce database queries"""
    try:
        from db import get_engine
        engine = get_engine()
        
        with engine.connect() as conn:
            # Get global admin code
            result = conn.execute(text('''
                SELECT admin_code FROM access_codes 
                ORDER BY updated_at DESC LIMIT 1
            '''))
            admin_result = result.fetchone()
            admin_code = admin_result[0] if admin_result else None
            
            # Get project site codes
            result = conn.execute(text('''
                SELECT project_site, user_code, admin_code 
                FROM project_site_access_codes
                ORDER BY project_site
            '''))
            site_codes = result.fetchall()
            
            return {
                'admin_code': admin_code,
                'site_codes': site_codes
            }
    except Exception as e:
        print(f"Error getting access codes: {e}")
        return {'admin_code': None, 'site_codes': []}

def authenticate_user(access_code):
    """Authenticate user by project site access code only - optimized version"""
    try:
        # Use cached access codes to avoid multiple database queries
        codes_data = get_access_codes()
        
        # Check project site access codes first
        for site_code in codes_data['site_codes']:
            project_site, user_code, admin_code = site_code
            if access_code == user_code:
                return {
                    'id': 999,
                    'username': f'user_{project_site.lower().replace(" ", "_")}',
                    'full_name': f'User - {project_site}',
                    'user_type': 'user',
                    'project_site': project_site
                }
        
        # Check global admin code
        if codes_data['admin_code'] and access_code == codes_data['admin_code']:
            return {
                'id': 1,
                'username': 'admin',
                'full_name': 'System Administrator',
                'user_type': 'admin',
                'project_site': 'ALL'
            }
        
        return None
    except Exception as e:
        print(f"Authentication error: {e}")
        return None

def check_session_validity():
    """Check if current session is valid - no timeout"""
    # Sessions are valid as long as user is logged in - no timeout
    return st.session_state.logged_in

def save_session_to_cookie():
    """Save current session to browser cookie for persistence"""
    try:
        session_data = {
            'user_id': st.session_state.get('user_id'),
            'username': st.session_state.get('username'),
            'full_name': st.session_state.get('full_name'),
            'user_type': st.session_state.get('user_type'),
            'project_site': st.session_state.get('project_site'),
            'current_project_site': st.session_state.get('current_project_site'),
            'auth_timestamp': st.session_state.get('auth_timestamp')
        }
        
        encoded_data = base64.b64encode(json.dumps(session_data).encode('utf-8')).decode('utf-8')
        st.query_params['auth_data'] = encoded_data
    except:
        pass

def restore_session_from_cookie():
    """Restore session from browser cookie if valid - no timeout"""
    try:
        # Check if we have authentication data in URL params (Streamlit's way of persistence)
        auth_data = st.query_params.get('auth_data')
        if auth_data:
            decoded_data = base64.b64decode(auth_data).decode('utf-8')
            session_data = json.loads(decoded_data)
            
            # Restore session without time validation - sessions never expire
            st.session_state.logged_in = True
            st.session_state.user_id = session_data.get('user_id')
            st.session_state.username = session_data.get('username')
            st.session_state.full_name = session_data.get('full_name')
            st.session_state.user_type = session_data.get('user_type')
            st.session_state.project_site = session_data.get('project_site')
            st.session_state.current_project_site = session_data.get('current_project_site', None)
            st.session_state.auth_timestamp = session_data.get('auth_timestamp')
            return True
    except:
        pass
    return False

def is_admin():
    """Check if current user is admin"""
    return st.session_state.get('user_type') == 'admin'

def require_admin():
    """Require admin privileges, show error if not admin"""
    if not is_admin():
        st.error("Admin privileges required for this action.")
        st.info("Only administrators can perform this operation.")
        return False
    return True

def log_access(access_code, success=True, user_name="Unknown", role="user"):
    """Log access attempts to database"""
    try:
        from db import get_engine
        engine = get_engine()
        
        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (:access_code, :user_name, :access_time, :success, :role)
            """), {
                "access_code": access_code,
                "user_name": user_name,
                "access_time": get_nigerian_time_iso(),
                "success": 1 if success else 0,
                "role": role
            })
            return result.lastrowid
    except Exception as e:
        print(f"Error logging access: {e}")
        return None

def invalidate_access_codes_cache():
    """Invalidate access codes cache when codes are updated"""
    get_access_codes.clear()

def show_login_interface():
    """Display clean login interface"""
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h1 style="color: #1f77b4; margin-bottom: 2rem;">Istrom Inventory Management</h1>
        <p style="font-size: 1.2rem; color: #666; margin-bottom: 3rem;">Enter your access code to continue</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("login_form", clear_on_submit=False):
        st.markdown("### Access Code")
        access_code = st.text_input(
            "Enter your access code", 
            placeholder="Enter your access code here...",
            type="password",
            label_visibility="collapsed"
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Initialize login processing state
        if 'login_processing' not in st.session_state:
            st.session_state.login_processing = False
            
        if st.form_submit_button("Access System", type="primary", use_container_width=True, disabled=st.session_state.login_processing):
            if not st.session_state.login_processing:
                st.session_state.login_processing = True
                
                if access_code:
                    # Show loading spinner
                    with st.spinner("Authenticating..."):
                        user_info = authenticate_user(access_code)
                    
                    if user_info:
                        # Set session state
                        st.session_state.logged_in = True
                        st.session_state.user_id = user_info['id']
                        st.session_state.username = user_info['username']
                        st.session_state.full_name = user_info['full_name']
                        st.session_state.user_type = user_info['user_type']
                        st.session_state.project_site = user_info['project_site']
                        st.session_state.current_project_site = user_info['project_site'] if user_info['project_site'] != 'ALL' else None
                        st.session_state.auth_timestamp = get_nigerian_time_iso()
                        
                        # Log the successful access with actual user information
                        log_id = log_access(access_code, success=True, user_name=user_info['full_name'], role=user_info['user_type'])
                        st.session_state.access_log_id = log_id
                        try:
                            # Ensure any cached readers refresh (e.g., admin overview metrics)
                            st.cache_data.clear()
                        except Exception:
                            pass
                        
                        # Save session to cookie for persistent login
                        save_session_to_cookie()
                        
                        st.success(f"Welcome, {user_info['full_name']}! (Session: Persistent)")
                        # Immediate transition into the app after successful login
                        st.rerun()
                    else:
                        # Log failed access attempt
                        log_access(access_code, success=False, user_name="Unknown", role="unknown")
                        st.error("Invalid access code. Please try again.")
                        st.session_state.login_processing = False
                else:
                    st.error("Please enter your access code.")
                    st.session_state.login_processing = False
            else:
                st.session_state.login_processing = False
