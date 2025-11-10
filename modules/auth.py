"""
Authentication and Session Management Module
Handles user authentication, session persistence, and login/logout
"""
import streamlit as st
import base64
import json
from datetime import datetime, timedelta
import pytz
from sqlalchemy import text
from db import get_engine
from logger import log_info, log_warning, log_error, log_debug

# Import utility functions from main file (will be moved to utils module later)
# For now, we'll import them to avoid circular dependencies
def get_nigerian_time_iso():
    """Get current time in Nigerian timezone as ISO string"""
    wat_timezone = pytz.timezone('Africa/Lagos')
    return datetime.now(wat_timezone).isoformat()

# Note: log_access is defined in the main file and will be imported when needed
# This avoids circular import issues

def log_access(access_code, success=True, user_name="Unknown", role=None):
    """Log access attempts to database with proper user identification"""
    try:
        # Determine role if not provided
        if role is None:
            codes_data = get_all_access_codes()
            admin_code = codes_data.get('admin_code')
            
            if access_code == admin_code:
                role = "admin"
            else:
                # Check if it's a project site access code
                for site_code in codes_data.get('site_codes', []):
                    project_site, user_code, _ = site_code
                    if access_code == user_code:
                        role = "project_site"
                        break
                else:
                    role = "unknown"
        
        # Get current time in West African Time
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        
        # Insert access log using SQLAlchemy
        engine = get_engine()
        backend = engine.url.get_backend_name()
        
        with engine.begin() as conn:
            if backend == 'postgresql':
                # PostgreSQL supports RETURNING
                result = conn.execute(text("""
                    INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                    VALUES (:access_code, :user_name, :access_time, :success, :role)
                    RETURNING id
                """), {
                    "access_code": access_code,
                    "user_name": user_name,
                    "access_time": current_time.isoformat(),
                    "success": 1 if success else 0,
                    "role": role
                })
                log_id = result.fetchone()[0]
            else:
                # SQLite doesn't support RETURNING, use lastrowid
                conn.execute(text("""
                    INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                    VALUES (:access_code, :user_name, :access_time, :success, :role)
                """), {
                    "access_code": access_code,
                    "user_name": user_name,
                    "access_time": current_time.isoformat(),
                    "success": 1 if success else 0,
                    "role": role
                })
                # Get the last inserted ID for SQLite
                result = conn.execute(text("SELECT last_insert_rowid()"))
                log_id = result.fetchone()[0]
            
            return log_id
    except Exception as e:
        log_error(f"Failed to log access: {e}")
        return None


def initialize_session():
    """Initialize session state with defaults and improved error handling"""
    defaults = {
        'logged_in': False,
        'user_id': None,
        'username': None,
        'full_name': None,
        'user_type': None,
        'project_site': None,
        'admin_code': None,
        'current_project_site': 'Lifecamp Kafe',
        'auth_timestamp': None,
        'login_processing': False,
        'session_restore_attempted': False
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


@st.cache_data(ttl=600)  # Cache for 10 minutes for better performance
def get_all_access_codes():
    """Get all access codes with caching to reduce database queries"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Get project site access codes
            site_result = conn.execute(text('''
                SELECT project_site, user_code, admin_code FROM project_site_access_codes 
                ORDER BY project_site
            '''))
            site_codes = site_result.fetchall()
            
            # Get global admin code
            admin_result = conn.execute(text('''
                SELECT admin_code FROM access_codes 
                ORDER BY updated_at DESC LIMIT 1
            '''))
            admin_code = admin_result.fetchone()
            
            return {
                'site_codes': site_codes,
                'admin_code': admin_code[0] if admin_code else None
            }
    except Exception as e:
        log_error(f"Error fetching access codes: {e}")
        return {'site_codes': [], 'admin_code': None}


def invalidate_access_codes_cache():
    """Invalidate the access codes cache when codes are updated"""
    get_all_access_codes.clear()


def authenticate_user(access_code):
    """Authenticate user by project site access code only - optimized version"""
    try:
        # Use cached access codes to avoid multiple database queries
        codes_data = get_all_access_codes()
        
        # Check project site access codes first
        for site_code in codes_data['site_codes']:
            project_site, user_code, admin_code = site_code
            if access_code == user_code:
                return {
                    'id': 999,
                    'username': f'project_site_{project_site.lower().replace(" ", "_")}',
                    'full_name': f'Project Site - {project_site}',
                    'user_type': 'project_site',
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
        log_error(f"Authentication error: {e}")
        return None


def show_login_interface():
    """Display clean login interface"""
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h1>Istrom Inventory Management</h1>
        <p style="color: #666;">Professional Construction Project Management</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Access Code Login")
        
        access_code = st.text_input(
            "Enter Access Code", 
            placeholder="Enter your access code",
            type="password",
            help="Enter your admin or project site access code"
        )
        
        # Prevent double-click by checking if already processing
        if 'login_processing' not in st.session_state:
            st.session_state.login_processing = False
        
        if st.button("Access System", type="primary", use_container_width=True, key="access_system_btn", disabled=st.session_state.login_processing):
            if not st.session_state.login_processing:
                st.session_state.login_processing = True
                
                if access_code:
                    # Show loading spinner
                    with st.spinner("Authenticating..."):
                        user_info = authenticate_user(access_code)
                    
                    if user_info:
                        # Set session state (optimized)
                        st.session_state.logged_in = True
                        st.session_state.user_id = user_info['id']
                        st.session_state.username = user_info['username']
                        st.session_state.full_name = user_info['full_name']
                        st.session_state.user_type = user_info['user_type']
                        st.session_state.project_site = user_info['project_site']
                        st.session_state.current_project_site = user_info['project_site'] if user_info['project_site'] != 'ALL' else None
                        st.session_state.auth_timestamp = get_nigerian_time_iso()
                        
                        # Log successful access
                        try:
                            log_access(
                                access_code=access_code,
                                success=True,
                                user_name=user_info['full_name'],
                                role=user_info['user_type']
                            )
                        except Exception as e:
                            log_error(f"Failed to log successful access: {e}")
                        
                        # Minimal essential persistence before rerun
                        try:
                            save_session_to_cookie()
                        except:
                            pass
                        
                        # Clear processing flag
                        st.session_state.login_processing = False
                        
                        # Force immediate rerun to transition to app
                        st.rerun()
                    else:
                        # Log failed access attempt
                        try:
                            # Import log_access from main module (avoid circular import)
                            import sys
                            if 'istrominventory' in sys.modules:
                                sys.modules['istrominventory'].log_access(access_code, success=False, user_name="Unknown", role="unknown")
                        except:
                            pass
                        st.error("Invalid access code. Please try again.")
                        st.session_state.login_processing = False
                else:
                    st.error("Please enter your access code.")
                    st.session_state.login_processing = False


def check_session_validity():
    """Check if current session is still valid - persistent login"""
    # Only check if user is logged in - no timeout, no complex validation
    return st.session_state.get('logged_in', False)


def restore_session_from_cookie():
    """Restore session from browser cookie if valid - 24 hour timeout"""
    try:
        # Try to get session data from query params first
        session_data_encoded = st.query_params.get('session_data')
        
        # If not in query params, try to restore from localStorage via JavaScript
        if not session_data_encoded:
            # Check if we've already tried to restore from localStorage (to avoid infinite loops)
            # Use URL parameter instead of session_state since session_state clears on reload
            restore_attempted = st.query_params.get('ls_restore_attempted', 'false')
            if restore_attempted != 'true':
                # Inject JavaScript to read from localStorage and restore to query params
                st.markdown("""
                <script>
                (function() {
                    try {
                        const sessionData = localStorage.getItem('istrom_session_data');
                        if (sessionData) {
                            const url = new URL(window.location);
                            if (!url.searchParams.get('session_data')) {
                                url.searchParams.set('session_data', sessionData);
                                url.searchParams.set('ls_restore_attempted', 'true');
                                window.history.replaceState({}, '', url);
                                // Trigger a rerun to pick up the new query param
                                setTimeout(function() {
                                    window.location.reload();
                                }, 100);
                            }
                        } else {
                            // No session data in localStorage, remove the attempt flag
                            const url = new URL(window.location);
                            url.searchParams.delete('ls_restore_attempted');
                            window.history.replaceState({}, '', url);
                        }
                    } catch (e) {
                        console.log('Could not restore session from localStorage:', e);
                    }
                })();
                </script>
                """, unsafe_allow_html=True)
            return False
        
        # Decode session data
        session_data = json.loads(base64.b64decode(session_data_encoded).decode('utf-8'))
        
        # Check if session is valid (24 hour timeout)
        auth_timestamp = session_data.get('auth_timestamp')
        if auth_timestamp:
            try:
                auth_time = datetime.fromisoformat(auth_timestamp.replace('Z', '+00:00'))
                current_time = datetime.now(pytz.UTC)
                
                # Check if 24 hours have passed
                if current_time - auth_time > timedelta(hours=24):
                    log_warning(f"Session expired: {current_time - auth_time} elapsed")
                    return False
            except Exception as e:
                log_error(f"Error checking session timeout: {e}")
                return False
        
        # Restore session state
        st.session_state.logged_in = session_data.get('logged_in', False)
        st.session_state.user_id = session_data.get('user_id')
        st.session_state.username = session_data.get('username')
        st.session_state.full_name = session_data.get('full_name')
        st.session_state.user_type = session_data.get('user_type')
        st.session_state.project_site = session_data.get('project_site')
        st.session_state.current_project_site = session_data.get('current_project_site')
        st.session_state.auth_timestamp = session_data.get('auth_timestamp')
        
        # Clean up the restore attempt flag from URL if it exists
        if 'ls_restore_attempted' in st.query_params:
            del st.query_params['ls_restore_attempted']
        
        log_info(f"Session restored successfully for {session_data.get('username')}")
        return True
        
    except Exception as e:
        log_error(f"Error restoring session from cookie: {e}")
        return False


def save_session_to_cookie():
    """Save current session to browser cookie for persistence - only if data changed"""
    try:
        # Create session data (without timestamp for comparison)
        current_session_data = {
            'logged_in': st.session_state.get('logged_in', False),
            'user_id': st.session_state.get('user_id'),
            'username': st.session_state.get('username'),
            'full_name': st.session_state.get('full_name'),
            'user_type': st.session_state.get('user_type'),
            'project_site': st.session_state.get('project_site'),
            'current_project_site': st.session_state.get('current_project_site'),
        }
        
        # Check if session data has changed by comparing with existing query param
        existing_encoded = st.query_params.get('session_data')
        if existing_encoded:
            try:
                existing_data = json.loads(base64.b64decode(existing_encoded).decode('utf-8'))
                # Compare session data (ignore timestamp)
                existing_compare = {k: v for k, v in existing_data.items() if k != 'auth_timestamp'}
                if existing_compare == current_session_data:
                    # No change, don't update query params to avoid rerun
                    return
            except:
                pass  # If decode fails, proceed with save
        
        # Session data changed or doesn't exist - update it
        session_data = {
            **current_session_data,
            'auth_timestamp': datetime.now(pytz.UTC).isoformat()
        }
        
        # Encode and save to query params (Streamlit's way of persistence)
        # Only update if query param doesn't exist or is different to avoid reruns
        encoded_data = base64.b64encode(json.dumps(session_data).encode('utf-8')).decode('utf-8')
        current_param = st.query_params.get('session_data', '')
        if current_param != encoded_data:
            # Use st.query_params.update() with clear_on_submit=False to minimize reruns
            st.query_params['session_data'] = encoded_data
        
        # Also save to localStorage as a backup (via JavaScript)
        st.markdown(f"""
        <script>
        (function() {{
            try {{
                localStorage.setItem('istrom_session_data', '{encoded_data}');
            }} catch (e) {{
                console.log('Could not save session to localStorage:', e);
            }}
        }})();
        </script>
        """, unsafe_allow_html=True)
        
        log_info(f"Session saved to cookie for {session_data.get('username')}")
    except Exception as e:
        log_error(f"Error saving session to cookie: {e}")


def is_admin():
    """Check if current user is admin"""
    return st.session_state.get('user_type') == 'admin'

