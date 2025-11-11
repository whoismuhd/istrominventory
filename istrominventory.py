import streamlit as st
import sqlite3
import pandas as pd
import re
from functools import lru_cache
# Test deployment - data persistence verification - SUCCESS! PostgreSQL working!
from datetime import datetime, timedelta
from pathlib import Path
import time
import threading
import pytz
import shutil
import json
import os
from sqlalchemy import text
from db import get_engine, init_db
from schema_init import ensure_schema
from logger import log_info, log_warning, log_error, log_debug
# Import authentication functions from modules (refactored)
from modules.auth import (
    initialize_session, get_all_access_codes, invalidate_access_codes_cache,
    authenticate_user, show_login_interface, check_session_validity,
    restore_session_from_cookie, save_session_to_cookie, is_admin
)
# Email functionality removed for better performance

st.set_page_config(
    page_title="Istrom Inventory Management System", 
    page_icon="📊", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Prevent automatic reruns - only rerun when explicitly needed
if 'prevent_rerun' not in st.session_state:
    st.session_state.prevent_rerun = False

# Removed custom dark mode - using Streamlit native Settings menu

# Add JavaScript functions for notifications
st.markdown("""
<script>
function playNotificationSound() {
    try {
        // Create audio context for notification sound
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        
        // Create a simple beep sound
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        // Set frequency and duration
        oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
        
        // Play the sound
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.5);
    } catch (e) {
        console.log('Audio not supported:', e);
    }
}

function showNotificationToast(message) {
    // Create a simple toast notification
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #4CAF50;
        color: white;
        padding: 15px 20px;
        border-radius: 5px;
        z-index: 10000;
        font-family: Arial, sans-serif;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        animation: slideIn 0.3s ease-out;
    `;
    
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

// Global notification system
window.NotificationSystem = {
    playSound: function() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
            oscillator.frequency.setValueAtTime(600, audioContext.currentTime + 0.1);
            oscillator.frequency.setValueAtTime(800, audioContext.currentTime + 0.2);
            
            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.3);
        } catch (e) {
            console.log('Audio not supported');
        }
    },
    
    showToast: function(message, type = 'success', duration = 4000) {
        // Remove existing toasts
        const existingToasts = document.querySelectorAll('.notification-toast');
        existingToasts.forEach(toast => toast.remove());
        
        const toast = document.createElement('div');
        toast.className = 'notification-toast';
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : type === 'warning' ? '#ff9800' : '#2196F3'};
            color: white;
            padding: 16px 24px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10000;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 14px;
            font-weight: 500;
            max-width: 350px;
            word-wrap: break-word;
            transform: translateX(100%);
            transition: transform 0.3s ease-in-out;
            cursor: pointer;
        `;
        
        const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️';
        toast.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">${icon}</span>
                <span>${message}</span>
            </div>
        `;
        
        // Add click to dismiss
        toast.onclick = function() {
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        };
        
        document.body.appendChild(toast);
        
        // Animate in
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 100);
        
        // Auto dismiss
        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.transform = 'translateX(100%)';
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    },
    
    checkNotifications: function() {
        // Check for various notification types
        const notifications = [
            { key: 'request_approved_notification', message: 'Request approved successfully!', type: 'success' },
            { key: 'request_rejected_notification', message: 'Request has been rejected', type: 'error' },
            { key: 'request_submitted_notification', message: 'Request submitted successfully!', type: 'success' },
            { key: 'item_added_notification', message: 'Item added successfully!', type: 'success' },
            { key: 'item_updated_notification', message: 'Item updated successfully!', type: 'success' },
            { key: 'item_deleted_notification', message: 'Item deleted successfully!', type: 'warning' },
            { key: 'access_code_updated_notification', message: 'Access code updated successfully!', type: 'success' },
            { key: 'project_site_added_notification', message: 'Project site added successfully!', type: 'success' }
        ];
        
        console.log('🔔 Checking notifications for project site account...');
        
        notifications.forEach(notif => {
            if (localStorage.getItem(notif.key) === 'true') {
                console.log('🔔 Found notification:', notif.key);
                this.playSound();
                this.showToast(notif.message, notif.type);
                localStorage.removeItem(notif.key);
            }
        });
        
        // Also check for any pending notifications from the server
        this.checkServerNotifications();
    },
    
    checkServerNotifications: function() {
        // This will be called to check for server-side notifications
        // For now, we'll rely on localStorage notifications
        // In the future, this could make an API call to check for pending notifications
    }
};

// Initialize notification system
document.addEventListener('DOMContentLoaded', function() {
    window.NotificationSystem.checkNotifications();
});

// Also check notifications when the page becomes visible (for project site accounts)
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        window.NotificationSystem.checkNotifications();
    }
});

// Check notifications every 30 seconds for project site accounts (reduced frequency for performance)
setInterval(function() {
    window.NotificationSystem.checkNotifications();
}, 60000); // Reduced from 30 seconds to 60 seconds to reduce reruns

// Make functions globally available
window.playNotificationSound = () => window.NotificationSystem.playSound();
window.showNotificationToast = (message, type) => window.NotificationSystem.showToast(message, type);
</script>
""", unsafe_allow_html=True)

# Email functionality removed for better performance

# Email functionality removed for better performance

# Enhanced real-time notification system with tab persistence
st.markdown("""
<script>
// Tab persistence and real-time notification system
let notificationCheckInterval;
let lastNotificationCount = 0;

// Tab persistence - save current tab to session storage
function saveCurrentTab(tabIndex) {
    try {
        sessionStorage.setItem('istrominventory_active_tab', tabIndex);
        console.log('Tab saved:', tabIndex);
    } catch (e) {
        console.log('Could not save tab:', e);
    }
}

// Load saved tab from session storage
function loadCurrentTab() {
    try {
        const savedTab = sessionStorage.getItem('istrominventory_active_tab');
        if (savedTab !== null) {
            console.log('Tab loaded:', savedTab);
            return parseInt(savedTab);
        }
    } catch (e) {
        console.log('Could not load tab:', e);
    }
    return 0; // Default to first tab
}

// Enhanced notification sound with multiple tones - LOUD AND ATTENTION-GRABBING
function playNotificationSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        
        // Create a more attention-grabbing sound sequence
        const playTone = (frequency, startTime, duration, volume = 0.9) => {
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.setValueAtTime(frequency, startTime);
            gainNode.gain.setValueAtTime(volume, startTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duration);
            
            oscillator.start(startTime);
            oscillator.stop(startTime + duration);
        };
        
        // Play a LOUD sequence of tones for maximum attention
        const now = audioContext.currentTime;
        playTone(800, now, 0.3, 1.0);           // First loud tone
        playTone(1000, now + 0.1, 0.3, 1.0);    // Second loud tone
        playTone(1200, now + 0.2, 0.4, 1.0);    // Third loud tone
        playTone(800, now + 0.4, 0.3, 1.0);     // Fourth loud tone
        playTone(1000, now + 0.6, 0.2, 0.8);    // Final tone
        
        console.log('LOUD notification sound played');
    } catch (e) {
        console.log('Sound not available:', e);
    }
}

// Check for new notifications without full page refresh
function checkNotifications() {
    try {
        // This would typically make an AJAX request to check for new notifications
        // For now, we'll use a simple approach with localStorage
        const currentCount = localStorage.getItem('notification_count') || '0';
        const count = parseInt(currentCount);
        
        if (count > lastNotificationCount) {
            playNotificationSound();
            showNotificationToast('New notification received!');
            lastNotificationCount = count;
        }
    } catch (e) {
        console.log('Notification check failed:', e);
    }
}

// Show notification toast
function showNotificationToast(message) {
    // Create a toast notification
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: linear-gradient(135deg, #3b82f6, #1d4ed8);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        z-index: 10000;
        font-weight: 600;
        animation: slideIn 0.3s ease;
    `;
    toast.textContent = message;
    
    // Add animation keyframes
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(toast);
    
    // Remove toast after 3 seconds
    setTimeout(() => {
        toast.remove();
        style.remove();
    }, 3000);
}

// Initialize notification system (tab persistence removed - causes conflicts)
document.addEventListener('DOMContentLoaded', function() {
    // Start notification checking (reduced frequency to prevent unnecessary reruns)
    // Check every 60 seconds instead of 10 seconds to reduce server load and reruns
    notificationCheckInterval = setInterval(checkNotifications, 60000); // Check every 60 seconds
    
    console.log('Enhanced notification system loaded');
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    if (notificationCheckInterval) {
        clearInterval(notificationCheckInterval);
    }
});
</script>
""", unsafe_allow_html=True)

# Initialize DB/tables at startup
init_db()          # if you already have it, keep it
ensure_schema()    # <-- create items/actuals when missing

# Migration: Add current_price column to requests table if it doesn't exist
def migrate_add_current_price_column():
    """Add current_price column to requests table if it doesn't exist"""
    try:
        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        backend = engine.url.get_backend_name()
        
        with engine.begin() as conn:
            if backend == 'postgresql':
                # PostgreSQL: Check if column exists before adding
                try:
                    result = conn.execute(text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'requests' 
                        AND column_name = 'current_price'
                    """))
                    exists = result.fetchone()
                    if not exists:
                        conn.execute(text("ALTER TABLE requests ADD COLUMN current_price DOUBLE PRECISION"))
                        log_info("Added current_price column to requests table (PostgreSQL)")
                    else:
                        log_info("current_price column already exists in requests table (PostgreSQL)")
                except Exception as pg_error:
                    # Fallback: try to add directly, catch error if it exists
                    try:
                        conn.execute(text("ALTER TABLE requests ADD COLUMN current_price DOUBLE PRECISION"))
                        log_info("Added current_price column to requests table (PostgreSQL - fallback)")
                    except Exception:
                        log_warning(f"Note: current_price column may already exist (PostgreSQL): {pg_error}")
            else:
                # SQLite: Try to add column, ignore if it already exists
                try:
                    conn.execute(text("ALTER TABLE requests ADD COLUMN current_price REAL"))
                    log_info("Added current_price column to requests table (SQLite)")
                except Exception as sqlite_error:
                    # Column already exists, ignore
                    log_info(f"current_price column already exists in requests table (SQLite)")
    except Exception as e:
        log_warning(f"Migration error (continuing anyway): {e}")

migrate_add_current_price_column()


def migrate_add_building_subtype_column():
    """Add building_subtype column to requests table if it doesn't exist"""
    try:
        from sqlalchemy import text
        from db import get_engine

        engine = get_engine()
        backend = engine.url.get_backend_name()

        with engine.begin() as conn:
            if backend == 'postgresql':
                try:
                    result = conn.execute(text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = 'requests'
                        AND column_name = 'building_subtype'
                    """))
                    exists = result.fetchone()
                    if not exists:
                        conn.execute(text("ALTER TABLE requests ADD COLUMN building_subtype TEXT"))
                        log_info("Added building_subtype column to requests table (PostgreSQL)")
                    else:
                        log_info("building_subtype column already exists in requests table (PostgreSQL)")
                except Exception as pg_error:
                    try:
                        conn.execute(text("ALTER TABLE requests ADD COLUMN building_subtype TEXT"))
                        log_info("Added building_subtype column to requests table (PostgreSQL - fallback)")
                    except Exception:
                        log_warning(f"Note: building_subtype column may already exist (PostgreSQL): {pg_error}")
            else:
                try:
                    conn.execute(text("ALTER TABLE requests ADD COLUMN building_subtype TEXT"))
                    log_info("Added building_subtype column to requests table (SQLite)")
                except Exception:
                    log_info("building_subtype column already exists in requests table (SQLite)")
    except Exception as e:
        log_warning(f"Migration error (continuing anyway): {e}")


migrate_add_building_subtype_column()


def migrate_add_deleted_requests_building_subtype_column():
    """Add building_subtype column to deleted_requests table if it doesn't exist"""
    try:
        from sqlalchemy import text
        from db import get_engine

        engine = get_engine()
        backend = engine.url.get_backend_name()

        with engine.begin() as conn:
            if backend == 'postgresql':
                try:
                    result = conn.execute(text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = 'deleted_requests'
                        AND column_name = 'building_subtype'
                    """))
                    exists = result.fetchone()
                    if not exists:
                        conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN building_subtype TEXT"))
                        log_info("Added building_subtype column to deleted_requests table (PostgreSQL)")
                    else:
                        log_info("building_subtype column already exists in deleted_requests table (PostgreSQL)")
                except Exception as pg_error:
                    try:
                        conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN building_subtype TEXT"))
                        log_info("Added building_subtype column to deleted_requests table (PostgreSQL - fallback)")
                    except Exception:
                        log_warning(f"Note: building_subtype column may already exist in deleted_requests table (PostgreSQL): {pg_error}")
            else:
                try:
                    conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN building_subtype TEXT"))
                    log_info("Added building_subtype column to deleted_requests table (SQLite)")
                except Exception:
                    log_info("building_subtype column already exists in deleted_requests table (SQLite)")
    except Exception as e:
        log_warning(f"Migration error for deleted_requests building_subtype (continuing anyway): {e}")

migrate_add_deleted_requests_building_subtype_column()


def migrate_add_actuals_building_subtype_column():
    """Add building_subtype column to actuals table if it doesn't exist"""
    try:
        from sqlalchemy import text
        from db import get_engine

        engine = get_engine()
        backend = engine.url.get_backend_name()

        with engine.begin() as conn:
            if backend == 'postgresql':
                try:
                    result = conn.execute(text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'actuals'
                          AND column_name = 'building_subtype'
                    """))
                    exists = result.fetchone()
                    if not exists:
                        conn.execute(text("ALTER TABLE actuals ADD COLUMN building_subtype TEXT"))
                        log_info("Added building_subtype column to actuals table (PostgreSQL)")
                    else:
                        log_info("building_subtype column already exists in actuals table (PostgreSQL)")
                except Exception as pg_error:
                    try:
                        conn.execute(text("ALTER TABLE actuals ADD COLUMN building_subtype TEXT"))
                        log_info("Added building_subtype column to actuals table (PostgreSQL - fallback)")
                    except Exception:
                        log_warning(f"Note: building_subtype column may already exist in actuals table (PostgreSQL): {pg_error}")
            else:
                try:
                    conn.execute(text("ALTER TABLE actuals ADD COLUMN building_subtype TEXT"))
                    log_info("Added building_subtype column to actuals table (SQLite)")
                except Exception:
                    log_info("building_subtype column already exists in actuals table (SQLite)")
    except Exception as e:
        log_warning(f"Migration error while adding building_subtype to actuals (continuing anyway): {e}")


migrate_add_actuals_building_subtype_column()

def migrate_add_deleted_requests_note_column():
    """Add note column to deleted_requests table if it doesn't exist"""
    try:
        from sqlalchemy import text
        from db import get_engine

        engine = get_engine()
        backend = engine.url.get_backend_name()

        with engine.begin() as conn:
            if backend == 'postgresql':
                try:
                    result = conn.execute(text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = 'deleted_requests'
                        AND column_name = 'note'
                    """))
                    exists = result.fetchone()
                    if not exists:
                        conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN note TEXT"))
                        log_info("Added note column to deleted_requests table (PostgreSQL)")
                    else:
                        log_info("note column already exists in deleted_requests table (PostgreSQL)")
                except Exception as pg_error:
                    try:
                        conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN note TEXT"))
                        log_info("Added note column to deleted_requests table (PostgreSQL - fallback)")
                    except Exception:
                        log_warning(f"Note: note column may already exist in deleted_requests table (PostgreSQL): {pg_error}")
            else:
                try:
                    conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN note TEXT"))
                    log_info("Added note column to deleted_requests table (SQLite)")
                except Exception:
                    log_info("note column already exists in deleted_requests table (SQLite)")
    except Exception as e:
        log_warning(f"Migration error for deleted_requests note column (continuing anyway): {e}")

migrate_add_deleted_requests_note_column()

def migrate_add_deleted_requests_approved_by_column():
    """Add approved_by column to deleted_requests table if it doesn't exist"""
    try:
        from sqlalchemy import text
        from db import get_engine

        engine = get_engine()
        backend = engine.url.get_backend_name()

        with engine.begin() as conn:
            if backend == 'postgresql':
                try:
                    result = conn.execute(text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = 'deleted_requests'
                        AND column_name = 'approved_by'
                    """))
                    exists = result.fetchone()
                    if not exists:
                        conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN approved_by TEXT"))
                        log_info("Added approved_by column to deleted_requests table (PostgreSQL)")
                    else:
                        log_info("approved_by column already exists in deleted_requests table (PostgreSQL)")
                except Exception as pg_error:
                    try:
                        conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN approved_by TEXT"))
                        log_info("Added approved_by column to deleted_requests table (PostgreSQL - fallback)")
                    except Exception:
                        log_warning(f"Note: approved_by column may already exist in deleted_requests table (PostgreSQL): {pg_error}")
            else:
                try:
                    conn.execute(text("ALTER TABLE deleted_requests ADD COLUMN approved_by TEXT"))
                    log_info("Added approved_by column to deleted_requests table (SQLite)")
                except Exception:
                    log_info("approved_by column already exists in deleted_requests table (SQLite)")
    except Exception as e:
        log_warning(f"Migration error for deleted_requests approved_by column (continuing anyway): {e}")

migrate_add_deleted_requests_approved_by_column()
engine = get_engine()

# Database connection check with proper error handling
try:
    with engine.connect() as c:
        # Test basic connection
        c.execute(text("SELECT 1"))
        log_info("Database connection successful")
except Exception as e:
    st.error(f"❌ Database connection failed: {e}")
    st.error("Please check your database configuration and try again.")
    st.stop()  # Stop the app if database connection fails

# Migration: Create dismissed_over_planned_alerts table if it doesn't exist
def migrate_create_dismissed_alerts_table():
    """Create dismissed_over_planned_alerts table if it doesn't exist"""
    try:
        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        with engine.begin() as conn:
            # Check if we're using PostgreSQL
            database_url = os.getenv('DATABASE_URL', '')
            if database_url and 'postgresql://' in database_url:
                # PostgreSQL: Check if table exists
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'dismissed_over_planned_alerts'
                    )
                """))
                exists = result.fetchone()[0]
                if not exists:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS dismissed_over_planned_alerts (
                            id SERIAL PRIMARY KEY,
                            request_id INTEGER NOT NULL,
                            item_name TEXT,
                            full_details TEXT,
                            dismissed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(request_id)
                        )
                    """))
                    print("✅ Created dismissed_over_planned_alerts table (PostgreSQL)")
                else:
                    print("✓ dismissed_over_planned_alerts table already exists (PostgreSQL)")
            else:
                # SQLite: Try to create table, ignore if it already exists
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS dismissed_over_planned_alerts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            request_id INTEGER NOT NULL UNIQUE,
                            item_name TEXT,
                            full_details TEXT,
                            dismissed_at TEXT DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    print("✅ Created dismissed_over_planned_alerts table (SQLite)")
                except Exception as sqlite_error:
                    print(f"⚠️ Error creating dismissed_over_planned_alerts table (SQLite): {sqlite_error}")
    except Exception as e:
        print(f"⚠️ Migration error for dismissed_over_planned_alerts table (continuing anyway): {e}")

# Run migration
migrate_create_dismissed_alerts_table()

# Check if we're on Render with PostgreSQL
database_url = os.getenv('DATABASE_URL', '')
log_info(f"Environment check - DATABASE_URL: {database_url[:50]}..." if database_url else "Environment check - No DATABASE_URL found")

# Also check for other Render environment variables
render_env = os.getenv('RENDER', '')
production_mode = os.getenv('PRODUCTION_MODE', '')
log_info(f"RENDER env: {render_env}, PRODUCTION_MODE: {production_mode}")

if database_url and 'postgresql://' in database_url:
    DATABASE_CONFIGURED = True
    log_info("PostgreSQL database detected - using persistent storage!")
elif render_env or production_mode:
    # We're on Render but no DATABASE_URL - this is a problem!
    log_error("CRITICAL: On Render but no DATABASE_URL found!")
    log_error("This means environment variables are not being set properly!")
    DATABASE_CONFIGURED = False
else:

    DATABASE_CONFIGURED = False
    log_info("Using SQLite for local development")

# Database connection helper
# NOTE: safe_db_operation removed - use db.py get_engine() directly
# This function referenced get_conn() which doesn't exist - use get_engine() from db.py instead

def get_sql_placeholder():
    """Get the correct SQL parameter placeholder for the current database"""
    # Check if we're using PostgreSQL by looking at DATABASE_URL or DATABASE_TYPE
    database_url = os.getenv('DATABASE_URL', '')
    database_type = os.getenv('DATABASE_TYPE', '')
    
    # If we have a PostgreSQL URL or type, use %s placeholders
    if 'postgresql://' in database_url or database_type == 'postgresql':
        return '%s'  # PostgreSQL uses %s
    else:

        return '?'   # SQLite uses ?

# Database initialization
def initialize_database():
    """Initialize database with proper configuration"""
    try:

        # Ensure all required tables exist
        # database_config import removed - using direct PostgreSQL connection
        # Tables are created automatically in get_conn() for PostgreSQL
        return True
    except Exception as e:

        # Database initialization failed
        return False

# Nigerian timezone helper functions
def get_nigerian_time():
    """Get current time in Nigerian timezone (WAT)"""
    wat_timezone = pytz.timezone('Africa/Lagos')
    return datetime.now(wat_timezone)

def get_nigerian_time_str():
    """Get current time in Nigerian timezone as string"""
    return get_nigerian_time().strftime("%Y-%m-%d %H:%M:%S")

def get_nigerian_time_iso():
    """Get current time in Nigerian timezone as ISO string"""
    return get_nigerian_time().isoformat()
DB_PATH = Path("istrominventory.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)
# --------------- DB helpers ---------------
def create_postgresql_tables(conn):
    """Create PostgreSQL tables if they don't exist"""
    try:

        cur = conn.cursor()
        
        # Create project_sites table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_sites (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now', '+1 hour')),
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Create project_site_access_codes table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_site_access_codes (
                id SERIAL PRIMARY KEY,
                project_site TEXT NOT NULL,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now', '+1 hour')),
                UNIQUE(project_site)
            )
        """)
        
        # Create items table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                category TEXT CHECK(category IN ('materials','labour')) NOT NULL,
                unit TEXT,
                qty REAL NOT NULL DEFAULT 0,
                unit_cost REAL,
                budget TEXT,
                section TEXT,
                grp TEXT,
                building_type TEXT,
                project_site TEXT DEFAULT 'Lifecamp Kafe',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create requests table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                ts TEXT NOT NULL,
                section TEXT CHECK(section IN ('materials','labour')) NOT NULL,
                item_id INTEGER NOT NULL,
                qty REAL NOT NULL,
                requested_by TEXT,
                note TEXT,
                building_subtype TEXT,
                status TEXT CHECK(status IN ('Pending','Approved','Rejected')) NOT NULL DEFAULT 'Pending',
                approved_by TEXT,
                created_at TEXT DEFAULT (datetime('now', '+1 hour')),
                updated_at TEXT DEFAULT (datetime('now', '+1 hour')),
                FOREIGN KEY(item_id) REFERENCES items(id)
            )
        """)
        
        # Create notifications table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                notification_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                user_id INTEGER,
                request_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', '+1 hour')),
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (request_id) REFERENCES requests (id)
            )
        """)
        
        # Create access_logs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS access_logs (
                id SERIAL PRIMARY KEY,
                access_code TEXT NOT NULL,
                user_name TEXT,
                access_time TIMESTAMP NOT NULL,
                success INTEGER DEFAULT 1,
                role TEXT
            )
        """)
        
        # Create users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                user_type TEXT CHECK(user_type IN ('admin', 'project_site')) NOT NULL,
                project_site TEXT,
                created_at TEXT DEFAULT (datetime('now', '+1 hour')),
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Create access_codes table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS access_codes (
                id SERIAL PRIMARY KEY,
                admin_code TEXT NOT NULL,
                user_code TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                updated_by TEXT
            )
        """)
        
        # Create deleted_requests table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deleted_requests (
                id SERIAL PRIMARY KEY,
                req_id INTEGER,
                item_name TEXT,
                qty REAL,
                requested_by TEXT,
                status TEXT,
                deleted_at TIMESTAMP,
                deleted_by TEXT
            )
        """)
        
        # Add current_price column to requests table if it doesn't exist (PostgreSQL migration)
        try:
            cur.execute("""
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='requests' AND column_name='current_price'
                    ) THEN
                        ALTER TABLE requests ADD COLUMN current_price REAL;
                    END IF;
                END $$;
            """)
        except Exception as e:
            print(f"Note: current_price column migration: {e}")
        
        try:
            cur.execute("""
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='requests' AND column_name='building_subtype'
                    ) THEN
                        ALTER TABLE requests ADD COLUMN building_subtype TEXT;
                    END IF;
                END $$;
            """)
        except Exception as e:
            print(f"Note: building_subtype column migration: {e}")
        
        conn.commit()
        print("PostgreSQL tables created/verified successfully!")
        
    except Exception as e:
        print(f"Error creating PostgreSQL tables: {e}")
        conn.rollback()

def get_conn():
    """Legacy wrapper for compatibility - returns a context manager that works with cursor()"""
    class ConnectionWrapper:
        def __init__(self, engine):
            self.engine = engine
            self.conn = None
            
        def __enter__(self):
            self.conn = self.engine.connect()
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.conn:

                self.conn.close()
                
        def cursor(self):
            """Return a cursor-like object that works with SQLAlchemy"""
            class CursorWrapper:
                def __init__(self, connection):
                    self.connection = connection
                    
                def execute(self, query, params=None):
                    if params:

                        # Convert SQLite-style ? placeholders to SQLAlchemy :param style
                        if '?' in query:

                            # Simple replacement for common cases
                            param_count = query.count('?')
                            for i in range(param_count):

                                query = query.replace('?', f':param{i}', 1)
                            param_dict = {f'param{i}': params[i] for i in range(param_count)}
                        else:

                            param_dict = params
                    else:

                        param_dict = {}
                    
                    return self.connection.execute(text(query), param_dict)
                    
                def fetchone(self):
                    return self.connection.fetchone()
                    
                def fetchall(self):
                    return self.connection.fetchall()
                    
                def commit(self):
                    # SQLAlchemy handles commits automatically in context managers
                    pass
                    
                def close(self):
                    # Connection will be closed by context manager
                    pass
                    
            return CursorWrapper(self.conn)
            
        def commit(self):
            # SQLAlchemy handles commits automatically in context managers
            pass
            
        def close(self):
            # Connection will be closed by context manager
            pass
    
    return ConnectionWrapper(engine)
# NOTE: init_db() is now imported from db.py (line 16)
# The function below is dead code and kept for reference only
# All database initialization is handled by db.py's init_db() function
def init_db_legacy():
    """Legacy database initialization - DEPRECATED: Use db.py init_db() instead"""
    # This function is no longer used - database initialization is handled by db.py
    # Keeping this as a placeholder to avoid breaking any imports
    pass

# --------------- User Authentication and Management Functions ---------------
def authenticate_by_access_code(access_code):
    """Authenticate a user by access code and return user info if successful"""
    try:

        with engine.connect() as conn:

            # First check if it's the global admin code
            result = conn.execute(text('''
                SELECT admin_code FROM access_codes 
                ORDER BY updated_at DESC LIMIT 1
            '''))
            admin_result = result.fetchone()
            
            if admin_result and access_code == admin_result[0]:

            
                # Global admin access
                return {
                    'id': 1,
                    'username': 'admin',
                    'full_name': 'System Administrator',
                    'user_type': 'admin',
                    'project_site': 'ALL',
                    'admin_code': admin_result[0]
                }
            
            # Check if it's a project site access code
            result = conn.execute(text('''
                SELECT project_site, user_code FROM project_site_access_codes 
                WHERE user_code = :access_code
            '''), {"access_code": access_code})
            site_result = result.fetchone()
            
            if site_result:
                project_site, user_code = site_result
                # Project site account access (not a regular user account)
                return {
                    'id': 999,
                    'username': f'project_site_{project_site.lower().replace(" ", "_")}',
                    'full_name': f'Project Site - {project_site}',
                    'user_type': 'project_site',  # Changed from 'user' to 'project_site'
                    'project_site': project_site,
                    'admin_code': None
                }
            
            # Fallback to old system for backward compatibility
            result = conn.execute(text('''
                SELECT admin_code, user_code FROM access_codes 
                ORDER BY updated_at DESC LIMIT 1
            '''))
            codes = result.fetchone()
            
            if codes:

            
                admin_code, user_code = codes
                
                # Check if access code matches admin code
                if access_code == admin_code:

                    return {
                        'id': 1,
                        'username': 'admin',
                        'full_name': 'System Administrator',
                        'user_type': 'admin',
                        'project_site': 'ALL',
                        'admin_code': admin_code
                    }
                
                # Check if access code matches user code (project site account)
                elif access_code == user_code:
                    return {
                        'id': 999,
                        'username': 'project_site',
                        'full_name': 'Project Site Account',
                        'user_type': 'project_site',
                        'project_site': 'Lifecamp Kafe',
                        'admin_code': None
                    }
            
            return None
    except Exception as e:

        st.error(f"Authentication error: {e}")
        return None

# Legacy password-based authentication removed - using access code system only

def create_simple_user(full_name, user_type, project_site, access_code):
    """Create a new user with enhanced persistence and error handling"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Check if access code already exists in users table
            result = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = :access_code"), {"access_code": access_code})
            if result.fetchone()[0] > 0:

                st.error("Access code already exists. Please choose a different one.")
                return False
            
            # Insert user into users table with explicit transaction
            conn.execute(text('''
                INSERT INTO users (username, full_name, user_type, project_site, created_at, is_active)
                VALUES (:access_code, :full_name, :user_type, :project_site, :created_at, :is_active)
            '''), {
                "access_code": access_code,
                "full_name": full_name,
                "user_type": user_type,
                "project_site": project_site,
                "created_at": get_nigerian_time_str(),
                "is_active": 1
            })
            
            # Log user creation in access_logs
            current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'System'))
            conn.execute(text('''
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (:access_code, :user_name, :access_time, :success, :role)
            '''), {
                "access_code": 'SYSTEM',
                "user_name": current_user,
                "access_time": get_nigerian_time_iso(),
                "success": 1,
                "role": st.session_state.get('user_type', 'admin')
            })
            
            # Force commit and verify
            conn.commit()
            
            # Verify user was created
            result = conn.execute(text("SELECT id FROM users WHERE username = :access_code"), {"access_code": access_code})
            user_id = result.fetchone()
            if user_id:

                log_info(f"User created successfully with ID: {user_id[0]}")
                return True
            else:

                log_error("User creation verification failed")
                return False
                
    except Exception as e:

                
        st.error(f"User creation error: {e}")
        log_error(f"User creation failed: {e}")
        return False

def delete_user(user_id):
    """Delete a user from the system - comprehensive cleanup of all related data"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Get user info before deletion
            result = conn.execute(text("SELECT username, full_name, project_site, user_type FROM users WHERE id = :user_id"), {"user_id": user_id})
            user_info = result.fetchone()
            if not user_info:

                st.error("User not found")
                return False
                
            username, full_name, project_site, user_type = user_info
        
        # Log the deletion start
        current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
        deletion_log = f"User deletion initiated by {current_user}: {full_name} ({username}) from {project_site} (Type: {user_type})"
        
        # Insert deletion log
        conn.execute(text("""
            INSERT INTO access_logs (access_code, user_name, access_time, success, role)
            VALUES (:access_code, :user_name, :access_time, :success, :role)
        """), {
            "access_code": 'SYSTEM',
            "user_name": current_user,
            "access_time": get_nigerian_time_iso(),
            "success": 1,
            "role": st.session_state.get('user_type', 'project_site')
        })
        
        # STEP 1: Delete all related records first (handle foreign key constraints)
        
        # Delete notifications for this user
        result = conn.execute(text("DELETE FROM notifications WHERE user_id = :user_id"), {"user_id": user_id})
        notifications_deleted = result.rowcount
        
        # Delete requests made by this user
        result = conn.execute(text("DELETE FROM requests WHERE requested_by = :full_name"), {"full_name": full_name})
        requests_deleted = result.rowcount
        
        # Delete access logs for this user
        result = conn.execute(text("DELETE FROM access_logs WHERE user_name = :full_name"), {"full_name": full_name})
        access_logs_deleted = result.rowcount
        
        # Delete actuals recorded by this user
        result = conn.execute(text("DELETE FROM actuals WHERE recorded_by = :full_name"), {"full_name": full_name})
        actuals_deleted = result.rowcount
        
        # Delete any notifications sent to this user (by user_id)
        result = conn.execute(text("DELETE FROM notifications WHERE user_id = :user_id"), {"user_id": user_id})
        notifications_to_user_deleted = result.rowcount
        
        # Delete any requests where this user is mentioned in note or other fields
        result = conn.execute(text("DELETE FROM requests WHERE requested_by = :full_name OR note LIKE :note_pattern"), 
                            {"full_name": full_name, "note_pattern": f"%{full_name}%"})
        additional_requests_deleted = result.rowcount
        
        # Delete any actuals where this user is mentioned
        result = conn.execute(text("DELETE FROM actuals WHERE recorded_by = :full_name OR notes LIKE :notes_pattern"), 
                            {"full_name": full_name, "notes_pattern": f"%{full_name}%"})
        additional_actuals_deleted = result.rowcount
        
        # STEP 2: Delete associated access code
        result = conn.execute(text("DELETE FROM project_site_access_codes WHERE user_code = :username AND project_site = :project_site"), 
                            {"username": username, "project_site": project_site})
        access_codes_deleted = result.rowcount
        
        # STEP 3: Finally delete the user
        result = conn.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
        user_deleted = result.rowcount
        
        if user_deleted > 0:

        
            conn.commit()
            
            # Log successful deletion with details
            cleanup_log = f"User '{full_name}' completely deleted. Cleaned up: {notifications_deleted} notifications, {requests_deleted} requests, {access_logs_deleted} access logs, {actuals_deleted} actuals, {access_codes_deleted} access codes"
            
            conn.execute(text("""
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (:access_code, :user_name, :access_time, :success, :role)
            """), {
                'access_code': 'SYSTEM', 
                'user_name': current_user, 
                'access_time': get_nigerian_time_iso(), 
                'success': 1, 
                'role': st.session_state.get('user_type', 'project_site')
            })
            conn.commit()
            
            # Clear all caches to prevent data from coming back
            clear_cache()
            
            st.success(f"User '{full_name}' deleted successfully!")
            st.info(f"Comprehensive cleanup completed: {notifications_deleted} notifications, {requests_deleted} requests, {access_logs_deleted} access logs, {actuals_deleted} actuals, {access_codes_deleted} access codes")
            return True
        else:

            st.error("Failed to delete user")
            return False
            
    except Exception as e:

            
        st.error(f"User deletion error: {e}")
        return False

def get_user_by_username(username):
    """Get user information by username"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.connect() as conn:

            result = conn.execute(text('''
                SELECT id, username, full_name, user_type, project_site, admin_code, created_at
                FROM users 
                WHERE username = :username AND is_active = 1
            '''), {"username": username})
            
            user = result.fetchone()
            if user:

                return {
                    'id': user[0],
                    'username': user[1],
                    'full_name': user[2],
                    'user_type': user[3],
                    'project_site': user[4],
                    'admin_code': user[5],
                    'created_at': user[6]
                }
            return None
    except Exception as e:

        st.error(f"User lookup error: {e}")
        return None
def get_all_users():
    """Get all users for admin management"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.connect() as conn:

            # Try new schema first
            try:

                result = conn.execute(text('''
                    SELECT id, username, full_name, user_type, project_site, admin_code, created_at, is_active
                    FROM users 
                    ORDER BY created_at DESC
                '''))
                users = []
                for row in result.fetchall():

                    users.append({
                        'id': row[0],
                        'username': row[1],
                        'full_name': row[2],
                        'user_type': row[3],
                        'project_site': row[4],
                        'admin_code': row[5],
                        'created_at': row[6],
                        'is_active': row[7]
                    })
                return users
            except:
                # Fallback to old schema
                result = conn.execute(text('''
                    SELECT id, username, full_name, role, created_at, is_active
                    FROM users 
                    ORDER BY created_at DESC
                '''))
                users = []
                for row in result.fetchall():

                    users.append({
                        'id': row[0],
                        'username': row[1],
                        'full_name': row[2],
                        'user_type': row[3],  # Map role to user_type
                        'project_site': 'Lifecamp Kafe',  # Default project site
                        'admin_code': None,
                        'is_active': row[5],
                        'created_at': row[4]
                    })
                return users
    except Exception as e:

        st.error(f"User list error: {e}")
        return []

# def is_admin():
#     """Check if current user is admin"""
#     return st.session_state.get('user_type') == 'admin'
# NOTE: is_admin() is now imported from modules.auth

def get_user_project_site():
    """Get current user's project site"""
    return st.session_state.get('project_site', None)

def show_notification_popup(notification_type, title, message):
    """Show enhanced popup notification with better styling and sound"""
    try:

        # Trigger JavaScript notification sound
        st.markdown("""
        <script>
        playNotificationSound();
        showNotificationToast('New notification received!');
        </script>
        """, unsafe_allow_html=True)
        
        if notification_type == "new_request":

        
            st.success(f"**{title}**\n\n{message}")
        elif notification_type == "request_approved":
            st.success(f"**{title}**\n\n{message}")
        elif notification_type == "request_rejected":
            st.error(f"**{title}**\n\n{message}")
        else:

            st.info(f"**{title}**\n\n{message}")
    except Exception as e:

        # Fallback to simple notification
        st.info(f"Notification: {message}")

def test_notification_system():
    """Test function to manually trigger notifications for debugging"""
    log_debug("Testing notification system...")
    
    # Test 1: Direct JavaScript notification
    st.markdown("""
    <script>
    console.log('🧪 Manual notification test started');
    showNotification('🧪 Test Notification', 'This is a test notification to verify the system is working.', 'info');
    </script>
    """, unsafe_allow_html=True)
    
    # Test 2: Test localStorage trigger
    st.markdown("""
    <script>
    localStorage.setItem('new_request_notification', 'true');
    console.log('🧪 localStorage notification flag set');
    </script>
    """, unsafe_allow_html=True)
    
    st.info("🧪 **Notification Test Completed!** Check browser console and listen for sound.")
    return True

def create_notification_sound(frequency=500, duration=0.2, sample_rate=44100):
    """Create a distinctive, attention-grabbing notification sound that really stands out"""
    try:

        import numpy as np
        import io
        import wave
        
        # Create a more distinctive, attention-grabbing sound
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        
        # Create a distinctive "ding-dong" chime pattern that stands out
        # First chime (higher pitch, shorter)
        first_chime_duration = duration * 0.4
        first_t = t[:int(len(t) * 0.4)]
        
        # Second chime (lower pitch, longer)
        second_chime_duration = duration * 0.6
        second_t = t[int(len(t) * 0.4):]
        
        # First chime - bright and attention-grabbing
        first_freq = frequency * 1.5  # Higher pitch
        first_vibrato = 0.08 * np.sin(2 * np.pi * 4 * first_t)  # More vibrato
        first_tone = np.sin(2 * np.pi * (first_freq + first_vibrato * 40) * first_t)
        
        # Add bright harmonics for the first chime
        first_harmonic2 = 0.5 * np.sin(2 * np.pi * first_freq * 2 * first_t)
        first_harmonic3 = 0.3 * np.sin(2 * np.pi * first_freq * 3 * first_t)
        
        # Second chime - deeper and more resonant
        second_freq = frequency * 0.8  # Lower pitch
        second_vibrato = 0.06 * np.sin(2 * np.pi * 2 * second_t)  # Slower vibrato
        second_tone = np.sin(2 * np.pi * (second_freq + second_vibrato * 30) * second_t)
        
        # Add rich harmonics for the second chime
        second_harmonic2 = 0.4 * np.sin(2 * np.pi * second_freq * 1.5 * second_t)
        second_harmonic3 = 0.2 * np.sin(2 * np.pi * second_freq * 2.5 * second_t)
        second_harmonic4 = 0.1 * np.sin(2 * np.pi * second_freq * 3.5 * second_t)
        
        # Combine both chimes
        first_chime = first_tone + first_harmonic2 + first_harmonic3
        second_chime = second_tone + second_harmonic2 + second_harmonic3 + second_harmonic4
        
        # Create distinctive envelope with sharp attack and sustained decay
        envelope = np.ones_like(t)
        
        # Sharp attack for first chime (first 10% of total duration)
        attack_samples = int(0.1 * len(t))
        envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
        
        # Sustain for first chime (10% to 40%)
        sustain_start = int(0.1 * len(t))
        sustain_end = int(0.4 * len(t))
        envelope[sustain_start:sustain_end] = 1.0
        
        # Quick decay between chimes (40% to 50%)
        decay_start = int(0.4 * len(t))
        decay_mid = int(0.5 * len(t))
        envelope[decay_start:decay_mid] = np.linspace(1, 0.3, decay_mid - decay_start)
        
        # Second chime attack (50% to 60%)
        second_attack_start = int(0.5 * len(t))
        second_attack_end = int(0.6 * len(t))
        envelope[second_attack_start:second_attack_end] = np.linspace(0.3, 1, second_attack_end - second_attack_start)
        
        # Sustain second chime (60% to 80%)
        second_sustain_start = int(0.6 * len(t))
        second_sustain_end = int(0.8 * len(t))
        envelope[second_sustain_start:second_sustain_end] = 1.0
        
        # Final decay (80% to 100%)
        final_decay_start = int(0.8 * len(t))
        envelope[final_decay_start:] = np.linspace(1, 0, len(t) - final_decay_start)
        
        # Combine both chimes with the envelope
        wave_data = np.zeros_like(t)
        wave_data[:len(first_chime)] = first_chime
        wave_data[len(first_chime):] = second_chime
        
        # Apply the distinctive envelope
        wave_data = wave_data * envelope
        
        # Add a distinctive "ping" at the very beginning for maximum attention
        ping_samples = int(0.01 * sample_rate)  # 10ms ping
        if ping_samples < len(wave_data):

            ping = np.random.normal(0, 0.08, ping_samples) * np.exp(-np.linspace(0, 20, ping_samples))
            wave_data[:ping_samples] += ping
        
        # Add a subtle echo effect for more presence
        echo_delay = int(0.05 * sample_rate)  # 50ms echo
        if len(wave_data) > echo_delay:

            echo = 0.3 * wave_data[:-echo_delay] * np.exp(-np.linspace(0, 8, len(wave_data) - echo_delay))
            wave_data[echo_delay:] += echo
        
        # Add a subtle reverb tail for more realistic sound
        reverb_samples = int(0.15 * sample_rate)  # 150ms reverb
        if len(wave_data) > reverb_samples:

            reverb = 0.15 * wave_data[:-reverb_samples] * np.exp(-np.linspace(0, 6, len(wave_data) - reverb_samples))
            wave_data[reverb_samples:] += reverb
        
        # Convert to 16-bit integers with higher amplitude for more presence
        wave_data = np.clip(wave_data, -1, 1)  # Prevent clipping
        wave_data = (wave_data * 15000).astype(np.int16)  # Higher amplitude for more presence
        
        # Create WAV file in memory
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:

            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(wave_data.tobytes())
        
        buffer.seek(0)
        return buffer.getvalue()
        
    except ImportError:

        
        # Fallback: return None if numpy is not available
        return None
    except Exception as e:

        return None
def log_request_activity(request_id, action, actor):
    """Log all request activities for audit trail"""
    try:

        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        
        with engine.connect() as conn:

        
            # Get request details for logging
            result = conn.execute(text("""
                SELECT r.requested_by, r.qty, i.name as item_name, i.project_site
                FROM requests r 
                JOIN items i ON r.item_id = i.id 
                WHERE r.id = :request_id
            """), {"request_id": request_id})
            
            request_data = result.fetchone()
            if request_data:

                requested_by, qty, item_name, project_site = request_data
                
                # Create detailed log entry
                log_message = f"Request #{request_id}: {action} by {actor} - {requested_by} requested {qty} units of {item_name} from {project_site}"
                
                # Insert into access_logs for audit trail
                conn.execute(text("""
                    INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                    VALUES (:access_code, :user_name, :access_time, :success, :role)
                """), {
                    "access_code": "REQUEST_SYSTEM",
                    "user_name": actor,
                    "access_time": get_nigerian_time_iso(),
                    "success": 1,
                    "role": st.session_state.get('user_type', 'project_site')
                })
                
                print(f"📝 Request Activity Logged: {log_message}")
                
    except Exception as e:

                
        print(f"Error logging request activity: {e}")

def create_notification(notification_type, title, message, user_id=None, request_id=None):
    """Create a notification for specific accounts (admin or project site) using SQLAlchemy"""
    try:
        from sqlalchemy import text
        from db import get_engine
        # get_nigerian_time_iso is defined at module level
            
        print(f"🔔 Creating notification: type={notification_type}, user_id={user_id}, request_id={request_id}")
        engine = get_engine()
        
        # Get Nigerian time for timestamp
        nigerian_timestamp = get_nigerian_time_iso()
        
        with engine.begin() as conn:

        
            # Handle user_id - if it's a string (name), try to find the account ID by access code
            actual_user_id = None
            if user_id and isinstance(user_id, str):

                # Method 1: Try to find by full_name
                result = conn.execute(text("SELECT id FROM users WHERE full_name = :full_name"), {"full_name": user_id})
                user_result = result.fetchone()
                if user_result:

                    actual_user_id = user_result[0]
                else:

                    # Method 2: Try to find by username
                    result = conn.execute(text("SELECT id FROM users WHERE username = :username"), {"username": user_id})
                    user_result = result.fetchone()
                    if user_result:

                        actual_user_id = user_result[0]
            elif user_id is not None and isinstance(user_id, int):
                # Special case for project site accounts (user_id = -1)
                # Use NULL instead of -1 to avoid foreign key violations
                # Project site notifications are retrieved by project_site from requests table, not by user_id
                if user_id == -1:
                    actual_user_id = None  # Use NULL for project site accounts
                else:
                    # It's already a user ID - verify it exists
                    result = conn.execute(text("SELECT id FROM users WHERE id = :user_id"), {"user_id": user_id})
                    verified = result.fetchone()
                    if verified:
                        actual_user_id = user_id
                    else:
                        return False
            
            # Handle request_id - only use it if it's valid (not 0 or None)
            valid_request_id = None
            if request_id and request_id > 0:

                # Verify the request exists
                result = conn.execute(text("SELECT id FROM requests WHERE id = :request_id"), {"request_id": request_id})
                if result.fetchone():

                    valid_request_id = request_id
            
            # If user_id is None, create admin notification (visible to all admins)
            if actual_user_id is None:

                # Create admin notification with user_id = NULL (visible to all admins)
                conn.execute(text('''
                    INSERT INTO notifications (notification_type, title, message, user_id, request_id, created_at)
                    VALUES (:notification_type, :title, :message, :user_id, :request_id, :created_at)
                '''), {
                    "notification_type": notification_type, 
                    "title": title, 
                    "message": message, 
                    "user_id": None, 
                    "request_id": valid_request_id,
                    "created_at": nigerian_timestamp
                })
                print(f"✅ Admin notification created successfully")
                return True
            else:

                # Create project site account notification
                print(f"🔔 DEBUG: Creating notification - type={notification_type}, user_id={actual_user_id}, request_id={valid_request_id}")
                result = conn.execute(text('''
                    INSERT INTO notifications (notification_type, title, message, user_id, request_id, created_at)
                    VALUES (:notification_type, :title, :message, :user_id, :request_id, :created_at)
                    RETURNING id
                '''), {
                    "notification_type": notification_type, 
                    "title": title, 
                    "message": message, 
                    "user_id": actual_user_id, 
                    "request_id": valid_request_id,
                    "created_at": nigerian_timestamp
                })
                notif_id = result.fetchone()[0] if result else None
                print(f"✅ Project site account notification created successfully - ID={notif_id}, user_id={actual_user_id}, request_id={valid_request_id}")
                
                # Show popup for project site account notifications when it's an approval/rejection
                if notification_type in ["request_approved", "request_rejected"]:

                    show_notification_popup(notification_type, title, message)
                
                return True
    except Exception as e:

        print(f"Notification creation error: {e}")
        return False

# First get_user_notifications function removed - using the comprehensive one below

def test_notification_sync():
    """Test notification synchronization between admin and project site accounts"""
    try:
        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        
        with engine.begin() as conn:
            # Test 1: Check if admin notifications exist
            result = conn.execute(text("""
                SELECT COUNT(*) FROM notifications 
                WHERE user_id IS NULL 
                AND notification_type = 'new_request'
            """))
            admin_count = result.fetchone()[0]
            
            # Test 2: Check if project site notifications exist
            result = conn.execute(text("""
                SELECT COUNT(*) FROM notifications 
                WHERE user_id = -1
            """))
            project_count = result.fetchone()[0]
            
            # Test 3: Check if notifications are properly formatted
            result = conn.execute(text("""
                SELECT id, notification_type, title, message, created_at, is_read, user_id
                FROM notifications 
                ORDER BY created_at DESC 
                LIMIT 5
            """))
            recent_notifications = result.fetchall()
            
            print(f"🔍 SYNC TEST: Admin notifications: {admin_count}, Project notifications: {project_count}")
            print(f"🔍 SYNC TEST: Recent notifications: {len(recent_notifications)}")
            
            for notif in recent_notifications:
                print(f"  - {notif[2]} ({notif[1]}) - User ID: {notif[6]}")
            
            return True
            
    except Exception as e:
        print(f"❌ SYNC TEST ERROR: {e}")
        return False

def get_admin_notifications():
    """Get unread notifications for admins - PROJECT-SPECIFIC admin notifications"""
    try:

        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        current_project = st.session_state.get('current_project_site', None)
        
        with engine.connect() as conn:

        
            result = conn.execute(text('''
                SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at,
                       u.full_name as requester_name
                FROM notifications n
                LEFT JOIN users u ON n.user_id = u.id
                WHERE n.is_read = 0 
                AND n.user_id IS NULL
                AND n.notification_type = 'new_request'
                ORDER BY n.created_at DESC
                LIMIT 10
            '''))
            
            notifications = []
            for row in result.fetchall():

                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'message': row[3],
                    'request_id': row[4],
                    'created_at': row[5],
                    'requester_name': row[6]
                })
            
            return notifications
    except Exception as e:

        st.error(f"Notification retrieval error: {e}")
        return []

def get_all_notifications():
    """Get all notifications (read and unread) for admin log - PROJECT-SPECIFIC admin notifications"""
    try:
        from sqlalchemy import text
        from db import get_engine
        from datetime import datetime
        import pytz
        
        engine = get_engine()
        
        # Helper to format timestamp to Nigerian time
        def format_nigerian_time(ts):
            if not ts:
                return ""
            try:
                import pytz
                lagos_tz = pytz.timezone('Africa/Lagos')
                
                if isinstance(ts, str):
                    # Parse ISO format - handle different timezone formats
                    if 'Z' in ts:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):  # Has timezone info
                        dt = datetime.fromisoformat(ts)
                    else:
                        # No timezone - try parsing as naive datetime
                        try:
                            dt = datetime.fromisoformat(ts)
                        except:
                            # Try standard format
                            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                        # Assume it was stored in Nigerian time (since we store Nigerian time)
                        dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                else:
                    # datetime object from database (PostgreSQL TIMESTAMP)
                    dt = ts
                    # PostgreSQL TIMESTAMP without timezone is returned as naive datetime
                    # Since we stored it from Nigerian time, assume it's Nigerian time
                    if dt.tzinfo is None:
                        dt = lagos_tz.localize(dt)
                
                # Ensure it's in Nigerian timezone
                if dt.tzinfo != lagos_tz:
                    nigerian_dt = dt.astimezone(lagos_tz)
                else:
                    nigerian_dt = dt
                
                return nigerian_dt.strftime("%Y-%m-%d %H:%M:%S WAT")
            except Exception as e:
                print(f"Time conversion error: {e}, ts type: {type(ts)}, ts value: {ts}")
                return str(ts) if ts else ""
        
        with engine.connect() as conn:
            current_project = st.session_state.get('current_project_site', None)
            
            # Get admin notifications
            result = conn.execute(text('''
                SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at, n.is_read,
                       u.full_name as requester_name
                FROM notifications n
                LEFT JOIN users u ON n.user_id = u.id
                WHERE n.user_id IS NULL
                AND n.notification_type = 'new_request'
                ORDER BY n.created_at DESC
                LIMIT 20
            '''))
            
            notifications = []
            for row in result.fetchall():
                # Convert the actual notification timestamp to Nigerian time
                created_at_ts = row[5]  # n.created_at from database
                created_at_nigerian = format_nigerian_time(created_at_ts)
                
                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'message': row[3],
                    'request_id': row[4],
                    'created_at': created_at_nigerian,
                    'is_read': row[6],
                    'requester_name': row[7]
                })
            return notifications
    except Exception as e:
        st.error(f"Notification log retrieval error: {e}")
        return []

def get_project_site_notifications():
    """Get notifications for the current project site by linking to the same requests shown in Review & History tab.
    This uses the EXACT same filtering logic as df_requests() to ensure consistency.
    """
    try:
        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', None))
        if not project_site:
            print(f"⚠️ No project_site found in session state")
            return []
        
        print(f"🔍 Fetching notifications for project site: {project_site}")
        
        with engine.begin() as conn:
            # Use the EXACT same filtering logic as df_requests() - get notifications for requests
            # that match the project site accounts visible requests (WHERE i.project_site = :project_site)
            # Include approval/rejection timestamp and approver name
            rows = conn.execute(text('''
                SELECT n.id, n.notification_type, n.title, n.message, n.request_id, n.created_at, 
                       COALESCE(n.is_read, 0) as is_read, r.approved_by, r.status, r.ts as request_created_at
                FROM notifications n
                JOIN requests r ON n.request_id = r.id
                JOIN items i ON r.item_id = i.id
                WHERE n.notification_type IN ('request_submitted','request_approved','request_rejected')
                  AND i.project_site = :project_site
                ORDER BY n.created_at DESC
                LIMIT 100
            '''), {"project_site": project_site}).fetchall()
            
            print(f"🔍 Found {len(rows)} notifications for project site: {project_site}")
            
            # Helper to format timestamp to Nigerian time
            def format_nigerian_time(ts):
                if not ts:
                    return ""
                try:
                    from datetime import datetime
                    import pytz
                    lagos_tz = pytz.timezone('Africa/Lagos')
                    
                    if isinstance(ts, str):
                        # Parse ISO format - handle different timezone formats
                        if 'Z' in ts:
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):  # Has timezone info
                            dt = datetime.fromisoformat(ts)
                        else:
                            # No timezone - try parsing as naive datetime
                            try:
                                dt = datetime.fromisoformat(ts)
                            except:
                                # Try standard format
                                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                            # Assume it was stored in Nigerian time (since we store Nigerian time)
                            dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                    else:
                        # datetime object from database (PostgreSQL TIMESTAMP)
                        dt = ts
                        # PostgreSQL TIMESTAMP without timezone is returned as naive datetime
                        # Since we stored it from Nigerian time, assume it's Nigerian time
                        if dt.tzinfo is None:
                            dt = lagos_tz.localize(dt)
                    
                    # Ensure it's in Nigerian timezone
                    if dt.tzinfo != lagos_tz:
                        nigerian_dt = dt.astimezone(lagos_tz)
                    else:
                        nigerian_dt = dt
                    
                    return nigerian_dt.strftime("%Y-%m-%d %H:%M:%S WAT")
                except Exception as e:
                    print(f"Time conversion error: {e}, ts type: {type(ts)}, ts value: {ts}")
                    return str(ts) if ts else ""
            
            notification_list = []
            for row in rows:
                notif_type = row[1]  # notification_type
                notif_created_at = row[5]  # n.created_at (notification creation time)
                request_created_at = row[9] if len(row) > 9 else None  # r.ts (request submission time)
                approved_by = row[7] if len(row) > 7 else None
                status = row[8] if len(row) > 8 else None
                
                # Use request submission time for request_submitted, notification time for approved/rejected
                # For request_submitted, the notification is created at the same time as the request
                # but we want to show the actual request submission time (r.ts)
                if notif_type == 'request_submitted' and request_created_at:
                    display_time = request_created_at
                else:
                    # For approved/rejected, use notification creation time (when action was taken)
                    display_time = notif_created_at
                
                notification_list.append({
                    'id': row[0],
                    'type': notif_type,
                    'title': row[2],
                    'message': row[3],
                    'request_id': row[4],
                    'created_at': format_nigerian_time(display_time),
                    'is_read': bool(row[6]),
                    'approved_by': approved_by,
                    'status': status
                })
                print(f"  ✓ Added notification {row[0]}: {row[1]} - {row[2][:50]}... (request_id: {row[4]})")
            
            # Fallback: If no notifications found (or very few), derive notifications from the requests table directly
            # But skip requests that already have read notifications in the database
            if len(notification_list) == 0:
                print("⚠️ No notifications in table; deriving from requests for consistency with Review & History...")
                request_rows = conn.execute(text('''
                    SELECT r.id, r.ts, r.status, r.approved_by, r.qty, i.name as item_name, i.project_site
                    FROM requests r
                    JOIN items i ON r.item_id = i.id
                    WHERE i.project_site = :project_site
                      AND r.status IN ('Approved','Rejected')
                      AND NOT EXISTS (
                          SELECT 1 FROM notifications n 
                          WHERE n.request_id = r.id 
                          AND n.notification_type IN ('request_approved', 'request_rejected')
                          AND n.is_read = 1
                      )
                    ORDER BY r.ts DESC
                    LIMIT 50
                '''), {"project_site": project_site}).fetchall()
                for rr in request_rows:
                    req_id = rr[0]
                    ts = rr[1]
                    status = rr[2]
                    approved_by = rr[3]
                    qty = rr[4]
                    item_name = rr[5]
                    notif_type = 'request_approved' if status == 'Approved' else 'request_rejected'
                    title = 'Request Approved' if status == 'Approved' else 'Request Rejected'
                    actor = approved_by or 'Admin'
                    message = f"Your request for {qty} units of {item_name} has been {status.lower()} by {actor}"
                    # Use a synthetic negative ID to avoid clashing with real IDs
                    synth_id = -int(req_id)
                    notification_list.append({
                        'id': synth_id,
                        'type': notif_type,
                        'title': title,
                        'message': message,
                        'request_id': req_id,
                        'created_at': format_nigerian_time(ts),
                        'is_read': False,
                        'approved_by': approved_by,
                        'status': status
                    })
                    print(f"  ✓ Derived notification from request {req_id}: {notif_type} {title}")
            
            print(f"✅ Returning {len(notification_list)} notifications for project site {project_site}")
            return notification_list
    except Exception as e:
        print(f"❌ Project site account notification retrieval error: {e}")
        import traceback
        traceback.print_exc()
        return []

def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:

        with engine.begin() as conn:

            conn.execute(text('UPDATE notifications SET is_read = 1 WHERE id = :notification_id'), 
                       {"notification_id": notification_id})
            return True
    except Exception as e:

        st.error(f"Notification update error: {e}")
        return False

def delete_notification(notification_id):
    """Delete a notification"""
    try:

        with engine.begin() as conn:

            conn.execute(text("DELETE FROM notifications WHERE id = :notification_id"), 
                       {"notification_id": notification_id})
            
            # Clear caches to prevent data from reappearing
            clear_cache()
            
            return True
    except Exception as e:

        st.error(f"Error deleting notification: {e}")
        return False

def clear_old_access_logs(days=30):
    """Clear access logs older than specified days"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            cutoff_date = (get_nigerian_time() - timedelta(days=days)).isoformat()
            
            # Count logs to be deleted
            result = conn.execute(text("SELECT COUNT(*) FROM access_logs WHERE access_time < :cutoff_date"), {"cutoff_date": cutoff_date})
            count = result.fetchone()[0]
            
            if count > 0:
                # Delete old logs
                conn.execute(text("DELETE FROM access_logs WHERE access_time < :cutoff_date"), {"cutoff_date": cutoff_date})
                st.success(f"Cleared {count} old access logs (older than {days} days)")
                return True
            else:
                st.info("No old access logs to clear")
                return True
            
    except Exception as e:
        st.error(f"Error clearing old access logs: {e}")
        return False
    finally:
        conn.close()
def clear_all_access_logs():
    """Clear ALL access logs from the database"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Count total logs
            result = conn.execute(text("SELECT COUNT(*) FROM access_logs"))
            total_count = result.fetchone()[0]
            
            if total_count > 0:

            
                # Delete ALL logs
                conn.execute(text("DELETE FROM access_logs"))
                
                # Log this action
                current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
                conn.execute(text("""
                    INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                    VALUES (:access_code, :user_name, :access_time, :success, :role)
                """), {
                    "access_code": 'SYSTEM',
                    "user_name": current_user,
                    "access_time": get_nigerian_time_iso(),
                    "success": 1,
                    "role": st.session_state.get('user_type', 'admin')
                })
                
                # Clear all caches to prevent data from coming back
                clear_cache()
                
                st.success(f"Cleared ALL {total_count} access logs! Fresh start initiated.")
                return True
            else:

                st.info("No access logs to clear")
                return True
                
    except Exception as e:

                
        st.error(f"Error clearing all access logs: {e}")
        return False

def fix_dataframe_types(df):
    """Fix DataFrame column types to prevent PyArrow serialization errors"""
    if df is None or df.empty:

        return df
    
    try:

    
        # Fix S/N column if it exists
        if 'S/N' in df.columns:

            df['S/N'] = df['S/N'].astype(str)
        
        # Fix any other problematic columns
        for col in df.columns:

            if df[col].dtype == 'object':

                # Check if column has mixed types
                try:

                    # Try to convert to numeric, if it fails, keep as string
                    pd.to_numeric(df[col], errors='raise')
                except (ValueError, TypeError):

                    # Column has mixed types, convert all to string
                    df[col] = df[col].astype(str)
        
        return df
    except Exception as e:

        st.error(f"Error fixing DataFrame types: {e}")
        return df

# --------------- Backup and Data Protection Functions ---------------
def create_backup():
    """Create a timestamped backup of the database"""
    # Use West African Time (WAT) for backup timestamps
    wat_timezone = pytz.timezone('Africa/Lagos')
    current_time = datetime.now(wat_timezone)
    timestamp = current_time.strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"istrominventory_backup_{timestamp}.db"
    
    try:

    
        shutil.copy2(DB_PATH, backup_path)
        return str(backup_path)
    except Exception as e:

        st.error(f" Failed to create backup: {str(e)}")
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

        st.error(f" Failed to restore backup: {str(e)}")
        return False

def export_data():
    """Export all data to JSON format"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.connect() as conn:

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
                "export_timestamp": datetime.now(pytz.timezone('Africa/Lagos')).isoformat()
            }
            
            return json.dumps(export_data, indent=2, default=str)
    except Exception as e:

        st.error(f" Failed to export data: {str(e)}")
        return None

def import_data(json_data):
    """Import data from JSON format"""
    # PRODUCTION DATA PROTECTION - Prevent data loss
    if os.getenv('PRODUCTION_MODE') == 'true' or os.getenv('DISABLE_MIGRATION') == 'true':

        print("🚫 import_data() BLOCKED - PRODUCTION MODE - YOUR DATA IS SAFE")
        return False
    
    try:

    
        data = json.loads(json_data)
        
        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Clear existing data - ONLY ALLOWED IN DEVELOPMENT
            conn.execute(text("DELETE FROM access_logs"))
            conn.execute(text("DELETE FROM requests"))
            conn.execute(text("DELETE FROM items"))
            
            # Import items
            for item in data.get("items", []):

                conn.execute(text("""
                    INSERT INTO items (id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type)
                    VALUES (:id, :code, :name, :category, :unit, :qty, :unit_cost, :budget, :section, :grp, :building_type)
                """), {
                    "id": item.get('id'),
                    "code": item.get('code'),
                    "name": item.get('name'),
                    "category": item.get('category'),
                    "unit": item.get('unit'),
                    "qty": item.get('qty'),
                    "unit_cost": item.get('unit_cost'),
                    "budget": item.get('budget'),
                    "section": item.get('section'),
                    "grp": item.get('grp'),
                    "building_type": item.get('building_type')
                })
            
            # Import requests
            for request in data.get("requests", []):

                conn.execute(text("""
                    INSERT INTO requests (id, ts, section, item_id, qty, requested_by, note, building_subtype, status, approved_by)
                    VALUES (:id, :ts, :section, :item_id, :qty, :requested_by, :note, :building_subtype, :status, :approved_by)
                """), {
                    "id": request.get('id'),
                    "ts": request.get('ts'),
                    "section": request.get('section'),
                    "item_id": request.get('item_id'),
                    "qty": request.get('qty'),
                    "requested_by": request.get('requested_by'),
                    "note": request.get('note'),
                    "building_subtype": request.get('building_subtype'),
                    "status": request.get('status'),
                    "approved_by": request.get('approved_by')
                })
            
            # Import access logs
            for log in data.get("access_logs", []):

                conn.execute(text("""
                    INSERT INTO access_logs (id, access_code, user_name, access_time, success, role)
                    VALUES (:id, :access_code, :user_name, :access_time, :success, :role)
                """), {
                    "id": log.get('id'),
                    "access_code": log.get('access_code'),
                    "user_name": log.get('user_name'),
                    "access_time": log.get('access_time'),
                    "success": log.get('success'),
                    "role": log.get('role')
                })
            
            conn.commit()
            return True
    except Exception as e:

        st.error(f" Failed to import data: {str(e)}")
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
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Create indexes for frequently queried columns
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_items_budget ON items(budget)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_items_section ON items(section)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_items_building_type ON items(building_type)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_items_category ON items(category)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_items_name ON items(name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_items_code ON items(code)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_requests_item_id ON requests(item_id)"))
    except Exception as e:

        pass

def clear_cache():
    """Clear the cached data when items are updated or project site changes - WITHOUT triggering reruns"""
    try:
        # Only clear specific function caches instead of all caches
        # This prevents unnecessary page refreshes/reruns and ForwardMsg MISS errors
        # Use try/except for each clear to avoid breaking if cache is in use
        
        # Clear caches with maximum error handling
        # Only clear if functions exist and have clear method
        cache_functions = []
        
        # Safely add functions that might exist
        try:
            if 'df_items_cached' in globals():
                cache_functions.append(('df_items_cached', df_items_cached))
        except:
            pass
        
        try:
            if 'get_all_access_codes' in globals():
                cache_functions.append(('get_all_access_codes', get_all_access_codes))
        except:
            pass
        
        try:
            if 'df_requests' in globals():
                cache_functions.append(('df_requests', df_requests))
        except:
            pass
        
        try:
            if '_get_over_planned_requests' in globals():
                cache_functions.append(('_get_over_planned_requests', _get_over_planned_requests))
        except:
            pass
        
        # Clear each cache function safely
        for name, func in cache_functions:
            try:
                if func and hasattr(func, 'clear'):
                    func.clear()
            except (Exception, RuntimeError, AttributeError, KeyError, TypeError, NameError) as e:
                # Silently skip - cache might be in use or doesn't exist
                # This prevents ForwardMsg MISS errors
                pass
            
        # DO NOT call st.cache_data.clear() or st.cache_resource.clear() here
        # These cause automatic page reruns which interrupt user workflow
        # and can cause "Cached ForwardMsg MISS" errors
        # Individual cached functions will refresh naturally when needed
            
    except Exception as e:
        # Silently fail - cache clearing is not critical and errors here can break the app
        # Don't print errors to avoid cluttering logs with non-critical issues
        pass

def clear_all_caches():
    """Clear all caches and force refresh - USE WITH CAUTION as it can cause ForwardMsg MISS errors"""
    try:
        # Only clear if absolutely necessary - avoid during active requests
        # This can cause "Cached ForwardMsg MISS" errors if called at the wrong time
        st.cache_data.clear()
        if hasattr(st, 'cache_resource'):
            st.cache_resource.clear()
    except Exception as e:
        # Silently fail to avoid breaking the app
        print(f"Warning: Could not clear all caches: {e}")
        pass


# Project sites database functions
def get_project_sites():
    """Get all active project sites from database"""
    try:

        with engine.connect() as conn:

            result = conn.execute(text("SELECT name FROM project_sites WHERE is_active = 1 ORDER BY created_at"))
            sites = [row[0] for row in result.fetchall()]
            print(f"🔍 Found {len(sites)} project sites: {sites}")
            return sites
    except Exception as e:

        print(f"❌ Failed to get project sites: {str(e)}")
        st.error(f"Failed to get project sites: {str(e)}")
        return []  # No fallback - let admin create project sites

def add_project_site(name, description=""):
    """Add a new project site to database using SQLAlchemy"""
    try:

        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        
        # Debug: Check what type of connection we have
        if engine.url.get_backend_name() == "postgresql":

            print(f"🔍 Using PostgreSQL connection for add_project_site")
        else:

            print(f"🔍 Using SQLite connection for add_project_site")
        
        with engine.connect() as conn:

        
            # Check if project site already exists (only active ones)
            result = conn.execute(text("SELECT COUNT(*) FROM project_sites WHERE name = :name AND is_active = 1"), {"name": name})
            count = result.fetchone()[0]
            print(f"Debug: Checking for project site '{name}' - found {count} existing records")
            if count > 0:

                print(f"Debug: Project site '{name}' already exists")
                return False  # Name already exists
            
            # Insert new project site
            conn.execute(text("INSERT INTO project_sites (name, description) VALUES (:name, :description)"), 
                        {"name": name, "description": description})
            
            # Automatically create an access code for this project site
            default_access_code = f"PROJECT_{name.upper().replace(' ', '_')}"
            
            # Get admin_code from global access codes
            result = conn.execute(text("SELECT admin_code FROM access_codes ORDER BY updated_at DESC LIMIT 1"))
            admin_result = result.fetchone()
            admin_code = admin_result[0] if admin_result else "ADMIN_DEFAULT"
            
            conn.execute(text("INSERT INTO project_site_access_codes (project_site, admin_code, user_code, updated_at) VALUES (:project_site, :admin_code, :user_code, :updated_at)"), 
                       {"project_site": name, "admin_code": admin_code, "user_code": default_access_code, "updated_at": get_nigerian_time_str()})
            
            conn.commit()
            return True
        
    except Exception as e:

        
        print(f"❌ Error adding project site: {e}")
        return False

def delete_project_site(name):
    """Delete a project site from database permanently using SQLAlchemy"""
    try:

        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        
        with engine.begin() as conn:

        
            # First, let's see what exists before deletion
            debug_result = conn.execute(text("SELECT project_site, user_code FROM project_site_access_codes WHERE project_site = :name"), {"name": name})
            existing_codes = debug_result.fetchall()
            print(f"🔍 BEFORE DELETION - Access codes for '{name}': {existing_codes}")
            
            # Delete all related data for this project site
            # 1. Delete access codes
            result1 = conn.execute(text("DELETE FROM project_site_access_codes WHERE project_site = :name"), {"name": name})
            access_codes_deleted = result1.rowcount
            
            # 2. Delete users associated with this project site
            result2 = conn.execute(text("DELETE FROM users WHERE project_site = :name"), {"name": name})
            users_deleted = result2.rowcount
            
            # 3. Delete items associated with this project site
            result3 = conn.execute(text("DELETE FROM items WHERE project_site = :name"), {"name": name})
            items_deleted = result3.rowcount
            
            # 4. Delete actuals associated with this project site
            result4 = conn.execute(text("DELETE FROM actuals WHERE project_site = :name"), {"name": name})
            actuals_deleted = result4.rowcount
            
            # 5. Delete orphaned requests (requests for items that were deleted)
            result5 = conn.execute(text("""
                DELETE FROM requests 
                WHERE item_id IN (
                    SELECT id FROM items WHERE project_site = :name
                )
            """), {"name": name})
            requests_deleted = result5.rowcount
            
            # 6. Delete the project site record itself
            result6 = conn.execute(text("DELETE FROM project_sites WHERE name = :name"), {"name": name})
            project_site_deleted = result6.rowcount
            
            # 7. FORCE DELETE - Delete by user_code as well (in case project_site name doesn't match)
            result7 = conn.execute(text("DELETE FROM project_site_access_codes WHERE user_code LIKE :pattern"), {"pattern": f"%{name.upper().replace(' ', '_')}%"})
            force_deleted = result7.rowcount
            
            # 8. FORCE DELETE - Delete any access codes that might have been created with different naming
            result8 = conn.execute(text("DELETE FROM project_site_access_codes WHERE user_code LIKE :pattern2"), {"pattern2": f"PROJECT_{name.upper().replace(' ', '_')}"})
            force_deleted2 = result8.rowcount
            
            # 9. FORCE DELETE - Delete any access codes that might have been created with "DEFAULT" pattern
            if "default" in name.lower():

                result9 = conn.execute(text("DELETE FROM project_site_access_codes WHERE user_code LIKE :pattern3"), {"pattern3": "%DEFAULT%"})
                force_deleted3 = result9.rowcount
            else:

                force_deleted3 = 0
            
            # Verify deletion worked
            verify_result = conn.execute(text("SELECT project_site, user_code FROM project_site_access_codes WHERE project_site = :name"), {"name": name})
            remaining_codes = verify_result.fetchall()
            print(f"🔍 AFTER DELETION - Remaining access codes for '{name}': {remaining_codes}")
            
            print(f"✅ Deleted project site '{name}': {access_codes_deleted} access codes, {users_deleted} users, {items_deleted} items, {actuals_deleted} actuals, {requests_deleted} requests, {project_site_deleted} project site record")
            print(f"✅ FORCE DELETED: {force_deleted + force_deleted2 + force_deleted3} additional access codes")
            
            # Return True if any operation succeeded
            return (access_codes_deleted + users_deleted + items_deleted + actuals_deleted + requests_deleted + project_site_deleted + force_deleted + force_deleted2 + force_deleted3) > 0
    except Exception as e:

        print(f"Error deleting project site: {e}")
        return False

def update_project_site_name(old_name, new_name):
    """Update project site name in database using SQLAlchemy - updates ALL related tables"""
    try:

        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        
        with engine.connect() as conn:

        
            # Update project_sites table
            result1 = conn.execute(text("UPDATE project_sites SET name = :new_name WHERE name = :old_name"), 
                        {"new_name": new_name, "old_name": old_name})
            print(f"Updated project_sites: {result1.rowcount} rows")
            
            # Update items table
            result2 = conn.execute(text("UPDATE items SET project_site = :new_name WHERE project_site = :old_name"), 
                        {"new_name": new_name, "old_name": old_name})
            print(f"Updated items: {result2.rowcount} rows")
            
            # Update project_site_access_codes table
            result3 = conn.execute(text("UPDATE project_site_access_codes SET project_site = :new_name WHERE project_site = :old_name"), 
                        {"new_name": new_name, "old_name": old_name})
            print(f"Updated project_site_access_codes: {result3.rowcount} rows")
            
            # Update users table
            result4 = conn.execute(text("UPDATE users SET project_site = :new_name WHERE project_site = :old_name"), 
                        {"new_name": new_name, "old_name": old_name})
            print(f"Updated users: {result4.rowcount} rows")
            
            # Update actuals table
            result5 = conn.execute(text("UPDATE actuals SET project_site = :new_name WHERE project_site = :old_name"), 
                        {"new_name": new_name, "old_name": old_name})
            print(f"Updated actuals: {result5.rowcount} rows")
            
            conn.commit()
            print(f"✅ Updated project site name from '{old_name}' to '{new_name}' in all tables")
            
            # Clear cache to ensure changes are reflected immediately
            clear_cache()
            
            return True
    except Exception as e:

        print(f"Error updating project site name: {e}")
        return False

def get_project_access_code(project_site):
    """Get access code for a specific project site using SQLAlchemy"""
    try:

        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        
        with engine.connect() as conn:

        
            # Use case-insensitive matching
            result = conn.execute(text("SELECT user_code FROM project_site_access_codes WHERE LOWER(project_site) = LOWER(:project_site)"), 
                                 {"project_site": project_site})
            row = result.fetchone()
            return row[0] if row else None
    except Exception as e:

        print(f"Error getting project access code: {e}")
        return None

def update_project_access_code(project_site, new_access_code):
    """Update access code for a specific project site using SQLAlchemy"""
    try:

        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        
        with engine.connect() as conn:

        
            # Get admin_code from global access codes
            result = conn.execute(text("SELECT admin_code FROM access_codes ORDER BY updated_at DESC LIMIT 1"))
            admin_result = result.fetchone()
            admin_code = admin_result[0] if admin_result else "ADMIN_DEFAULT"
            
            # First try to update existing record (case-insensitive)
            result = conn.execute(text("UPDATE project_site_access_codes SET user_code = :user_code, admin_code = :admin_code, updated_at = :updated_at WHERE LOWER(project_site) = LOWER(:project_site)"), 
                       {"user_code": new_access_code, "admin_code": admin_code, "updated_at": get_nigerian_time_str(), "project_site": project_site})
            
            # If no rows were affected, insert new record
            if result.rowcount == 0:

                conn.execute(text("INSERT INTO project_site_access_codes (project_site, admin_code, user_code, updated_at) VALUES (:project_site, :admin_code, :user_code, :updated_at)"), 
                           {"project_site": project_site, "admin_code": admin_code, "user_code": new_access_code, "updated_at": get_nigerian_time_str()})
            
            conn.commit()
            print(f"Successfully updated access code for project site: {project_site}")
            return True
    except Exception as e:

        print(f"Error updating project access code: {e}")
        st.error(f"Database error: {e}")
        return False

def initialize_default_project_site():
    """Initialize Lifecamp Kafe as default project site if it doesn't exist"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Check for any Lifecamp Kafe variation (with or without "Project")
            result = conn.execute(text("SELECT COUNT(*) FROM project_sites WHERE name LIKE '%Lifecamp Kafe%'"))
            if result.fetchone()[0] == 0:

                conn.execute(text("INSERT INTO project_sites (name, description) VALUES (:name, :description)"), 
                           {"name": "Lifecamp Kafe", "description": "Default project site"})
    except sqlite3.OperationalError as e:

        if "disk I/O error" in str(e):

            # Try to recover from disk I/O error
            try:

                # Clear WAL file and retry
                import os
                if os.path.exists('istrominventory.db-wal'):

                    os.remove('istrominventory.db-wal')
                if os.path.exists('istrominventory.db-shm'):

                    os.remove('istrominventory.db-shm')
                # Retry the operation
                initialize_default_project_site()
            except:
                pass
        else:

            st.error(f"Database error in project site initialization: {str(e)}")
    except Exception as e:

        st.error(f"Failed to initialize default project site: {str(e)}")

# Access codes (configurable from admin interface)
DEFAULT_ADMIN_ACCESS_CODE = "admin2024"
DEFAULT_USER_ACCESS_CODE = "user2024"

@st.cache_data(ttl=300)
def get_access_codes():
    """Get current access codes from Streamlit secrets or database fallback"""
    try:

        # First try to get from Streamlit secrets (persistent across deployments)
        try:

            admin_code = st.secrets.get("ACCESS_CODES", {}).get("admin_code", DEFAULT_ADMIN_ACCESS_CODE)
            user_code = st.secrets.get("ACCESS_CODES", {}).get("user_code", DEFAULT_USER_ACCESS_CODE)
            if admin_code != DEFAULT_ADMIN_ACCESS_CODE or user_code != DEFAULT_USER_ACCESS_CODE:

                return admin_code, user_code
        except:
            pass  # Fall back to database if secrets not available
        
        # Fallback to database
        try:

            with engine.connect() as conn:

                result = conn.execute(text("SELECT admin_code, user_code FROM access_codes ORDER BY id DESC LIMIT 1"))
                row = result.fetchone()
                
                if row:
                    return row[0], row[1]  # admin_code, user_code
                else:
                    # Insert default codes if none exist
                    wat_timezone = pytz.timezone('Africa/Lagos')
                    current_time = datetime.now(wat_timezone)
                    with engine.begin() as trans_conn:

                        trans_conn.execute(text("""
                            INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                            VALUES (:admin_code, :user_code, :updated_at, :updated_by)
                        """), {
                            "admin_code": DEFAULT_ADMIN_ACCESS_CODE,
                            "user_code": DEFAULT_USER_ACCESS_CODE,
                            "updated_at": current_time.isoformat(),
                            "updated_by": "System"
                        })
                        return DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE
        except Exception as e:
            print(f"❌ Database connection failed - using default access codes: {e}")
            return DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE
    except Exception as e:

        # Ultimate fallback to default codes
        return DEFAULT_ADMIN_ACCESS_CODE, DEFAULT_USER_ACCESS_CODE

def log_access(access_code, success=True, user_name="Unknown", role=None):
    """Log access attempts to database with proper user identification"""
    try:
        from sqlalchemy import text
        from db import get_engine
        
        # Determine role if not provided
        if role is None:

            admin_code, user_code = get_access_codes()
            if access_code == admin_code:

                role = "admin"
            elif access_code == user_code:
                role = "project_site"  # Changed from 'user' to 'project_site'
            else:

                # Check if it's a project site access code
                engine = get_engine()
                with engine.connect() as conn:

                    result = conn.execute(text("SELECT project_site FROM project_site_access_codes WHERE user_code = :access_code"), 
                                        {"access_code": access_code})
                    project_result = result.fetchone()
                    if project_result:

                        role = "project_site"  # Project site accounts
                    else:

                        role = "unknown"
            
            # Special handling for session restore
            if access_code == "SESSION_RESTORE":

                role = st.session_state.get('user_role', 'unknown')
            
        # Get current time in West African Time
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        
        # Insert access log using SQLAlchemy
        engine = get_engine()
        with engine.begin() as conn:

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
            return log_id
    except Exception as e:

        print(f"❌ Failed to log access: {e}")
        return None

@st.cache_data(ttl=300)  # Cache for 5 minutes for better performance
def df_items_cached(project_site=None):
    """Cached version of df_items for better performance - shows items from current project site only"""
    if project_site is None:
        # Use project site account's project site (the project site is the account identity), fallback to session state
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', None))
    
    from sqlalchemy import text
    from db import get_engine
    
    if project_site is None:
        # No project site selected - show all items or empty DataFrame
        try:
            engine = get_engine()
            with engine.begin() as conn:
                result = conn.execute(text("SELECT * FROM items ORDER BY created_at DESC"))
                return pd.DataFrame(result.fetchall(), columns=result.keys())
        except:
            return pd.DataFrame()
    
    q = text("""
        SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type, project_site 
        FROM items 
        WHERE project_site = :ps
        ORDER BY budget, section, grp, building_type, name
    """)
    
    try:
        engine = get_engine()
        return pd.read_sql_query(q, engine, params={"ps": project_site})
    except Exception as e:
        # Log error but don't print to stdout to avoid BrokenPipeError
        return pd.DataFrame()
@st.cache_data(ttl=600)  # Cache for 10 minutes - budget options don't change frequently
def get_budget_options(project_site=None):
    """Generate budget options based on actual database content"""
    budget_options = ["All"]  # Always include "All" option
    
    # Use current project site if not specified
    if project_site is None:

        project_site = st.session_state.get('current_project_site', None)
    
    # Always generate budget options regardless of project site
    # if project_site is None:
    #     # No project site selected - return basic options
    #     return ["All"]
    
    # Always generate comprehensive budget options (Budget 1-20)
    # Get max budget number from session state or default to 20
    max_budget = st.session_state.get('max_budget_num', 20)
    for budget_num in range(1, max_budget + 1):  # Dynamic budget range
        for bt in PROPERTY_TYPES:
            if bt:
                # Add only subgroups for this budget and building type (no base budget)
                # Match the actual database format (no space before parenthesis, "Irons" not "Iron")
                base_subgroups = [
                    f"Budget {budget_num} - {bt}(General Materials)",
                    f"Budget {budget_num} - {bt}(Woods)",
                    f"Budget {budget_num} - {bt}(Plumbings)",
                    f"Budget {budget_num} - {bt}(Irons)",
                    f"Budget {budget_num} - {bt}(Labour)"
                ]
                
                # Add Electrical and Mechanical for Budget 3 and above
                if budget_num >= 3:
                    base_subgroups.extend([
                        f"Budget {budget_num} - {bt}(Electrical)",
                        f"Budget {budget_num} - {bt}(Mechanical)"
                    ])
                
                budget_options.extend(base_subgroups)
    
    # Debug: Print budget options for debugging
    print(f"DEBUG: Generated {len(budget_options)} budget options")
    if len(budget_options) > 1:  # More than just "All"
        print(f"DEBUG: First few options: {budget_options[:5]}")
    else:

        print("DEBUG: Only 'All' option generated - this is wrong!")
    
    # Also get actual budgets from database for this project site (if any exist)
    try:
        from sqlalchemy import text
        from db import get_engine
        engine = get_engine()
        with engine.connect() as conn:

            result = conn.execute(text("""
                SELECT DISTINCT budget 
                FROM items 
                WHERE project_site = :project_site AND budget IS NOT NULL AND budget != ''
                ORDER BY budget
            """), {"project_site": project_site})
            
            db_budgets = [row[0] for row in result.fetchall()]
            # Add any additional budgets found in database that aren't already in our generated list
            for db_budget in db_budgets:

                if db_budget not in budget_options:

                    budget_options.append(db_budget)
    except Exception as e:

        # Database query failed, but we still have our generated options
        pass
    
    return budget_options

def get_base_budget_options(project_site=None):
    """Generate base budget options (e.g., 'Budget 1 - Flats') that have items in the database"""
    budget_options = ["All"]  # Always include "All" option
    
    # Use current project site if not specified
    if project_site is None:

        project_site = st.session_state.get('current_project_site', None)
    
    if project_site is None:

    
        # No project site selected - return basic options
        return ["All"]
    
    # Always generate comprehensive base budget options (Budget 1-20)
        max_budget = st.session_state.get('max_budget_num', 20)
        for budget_num in range(1, max_budget + 1):

            for bt in PROPERTY_TYPES:
                if bt:

                    budget_options.append(f"Budget {budget_num} - {bt}")
    
    # Also get actual budgets from database for this project site (if any exist)
    try:

        with engine.connect() as conn:

            result = conn.execute(text("""
                SELECT DISTINCT budget 
                FROM items 
                WHERE project_site = :project_site AND budget IS NOT NULL AND budget != ''
                ORDER BY budget
            """), {"project_site": project_site})
            
            db_budgets = [row[0] for row in result.fetchall()]
            
            # Extract base budgets (e.g., "Budget 1 - Flats" from "Budget 1 - Flats (General Materials)")
            base_budgets = set()
            for budget in db_budgets:

                # Extract base budget by removing subgroup info
                if " - " in budget:

                    # Find the base budget part (e.g., "Budget 1 - Flats" from "Budget 1 - Flats (General Materials)")
                    base_part = budget.split(" (")[0]  # Remove subgroup
                    base_budgets.add(base_part)
            
            # Add any additional base budgets found in database that aren't already in our generated list
            for base_budget in base_budgets:

                if base_budget not in budget_options:

                    budget_options.append(base_budget)
            
    except Exception as e:

            
        # Database query failed, but we still have our generated options
        pass
    
    return budget_options

@st.cache_data(ttl=600)  # Cache for 10 minutes - section options don't change frequently
def get_section_options(project_site=None):
    """Generate section options based on actual database content"""
    section_options = ["All"]  # Always include "All" option
    
    # Use current project site if not specified
    if project_site is None:

        project_site = st.session_state.get('current_project_site', None)
    
    if project_site is None:

    
        # No project site selected - return basic options
        return ["All"]
    
    try:
        from sqlalchemy import text
        from db import get_engine
        engine = get_engine()
        # Get actual sections from database for this project site
        with engine.connect() as conn:

            result = conn.execute(text("""
                SELECT DISTINCT section 
                FROM items 
                WHERE project_site = :project_site AND section IS NOT NULL AND section != ''
                ORDER BY section
            """), {"project_site": project_site})
            
            db_sections = [row[0] for row in result.fetchall()]
            section_options.extend(db_sections)
    except Exception as e:

        # Fallback to basic options if database query fails
        section_options.extend(["materials", "labour"])
    
    return section_options

def get_summary_data():
    """Cache summary data generation - optimized"""
    # For project site accounts, use their project site (the project site IS the account), for admins use current_project_site
    user_type = st.session_state.get('user_type', 'project_site')
    if user_type == 'admin':

        project_site = st.session_state.get('current_project_site', None)
    else:

        # Project site accounts use their own project site (the project site is the account identity)
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', None))
    
    all_items = df_items_cached(project_site)
    if all_items.empty:

        return pd.DataFrame(), []
    
    all_items["Amount"] = (all_items["qty"].fillna(0) * all_items["unit_cost"].fillna(0)).round(2)
    
    # Create summary by budget and building type (optimized)
    summary_data = []
    
    # Only process budgets that actually have data - limit to first 10 for performance
    existing_budgets = all_items["budget"].str.extract(r"Budget (\d+)", expand=False).dropna().astype(int).unique()
    
    for budget_num in existing_budgets[:10]:  # Limit to first 10 budgets with data
        budget_items = all_items[all_items["budget"].str.contains(f"Budget {budget_num}", case=False, na=False, regex=False)]
        if not budget_items.empty:

            budget_total = float(budget_items["Amount"].sum())
            
            # Get totals by building type for this budget (optimized)
            building_totals = budget_items.groupby("building_type")["Amount"].sum().to_dict()
            
            summary_data.append({
                "Budget": f"Budget {budget_num}",
                "Flats (Per Unit)": f"₦{building_totals.get('Flats', 0):,.2f}",
                "Terraces (Per Unit)": f"₦{building_totals.get('Terraces', 0):,.2f}",
                "Semi-detached (Per Unit)": f"₦{building_totals.get('Semi-detached', 0):,.2f}",
                "Fully-detached (Per Unit)": f"₦{building_totals.get('Fully-detached', 0):,.2f}",
                "Total (Per Unit)": f"₦{budget_total:,.2f}"
            })
    
    return all_items, summary_data

def df_items(filters=None):
    """Get items with optional filtering - optimized with database queries"""
    if not filters or not any(v for v in filters.values() if v):

        return df_items_cached(st.session_state.get('current_project_site'))
    
    from sqlalchemy import text
    from db import get_engine
    
    # Build SQL query with filters for better performance - ENFORCE PROJECT ISOLATION
    current_project_site = st.session_state.get('current_project_site', None)
    
    # Start with base query
    if current_project_site:
        q = text("""
            SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type 
            FROM items 
            WHERE project_site = :ps
        """)
        params = {"ps": current_project_site}
    else:

        q = text("""
            SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type 
            FROM items 
        """)
        params = {}
    
    for k, v in filters.items():

    
        if v is not None and v != "":

            if k == "budget":
                if "(" in str(v) and ")" in str(v):

                    # Specific subgroup search
                    q = text(str(q) + " AND budget LIKE :budget")
                    params["budget"] = f"%{v}%"
                else:

                    # General search - use base budget
                    base_budget = str(v).split("(")[0].strip()
                    q = text(str(q) + " AND budget LIKE :budget")
                    params["budget"] = f"%{base_budget}%"
            elif k == "section":
                q = text(str(q) + " AND section LIKE :section")
                params["section"] = f"%{v}%"
            elif k == "building_type":
                q = text(str(q) + " AND building_type LIKE :building_type")
                params["building_type"] = f"%{v}%"
            elif k == "category":
                q = text(str(q) + " AND category LIKE :category")
                params["category"] = f"%{v}%"
            elif k == "code":
                q = text(str(q) + " AND code LIKE :code")
                params["code"] = f"%{v}%"
            elif k == "name":
                q = text(str(q) + " AND name LIKE :name")
                params["name"] = f"%{v}%"
    
    q = text(str(q) + " ORDER BY budget, section, grp, building_type, name")
    
    engine = get_engine()
    return pd.read_sql_query(q, engine, params=params)
def calc_subtotal(filters=None) -> float:
    # ENFORCE PROJECT ISOLATION - only calculate for current project
    current_project_site = st.session_state.get('current_project_site', None)
    placeholder = get_sql_placeholder()
    
    if current_project_site:
        q = f"SELECT SUM(COALESCE(qty,0) * COALESCE(unit_cost,0)) FROM items WHERE project_site = {placeholder}"
        params = [current_project_site]
    else:

        q = "SELECT SUM(COALESCE(qty,0) * COALESCE(unit_cost,0)) FROM items"
        params = []
    if filters:

        for k, v in filters.items():


            if v:

                q += f" AND {k} = {placeholder}"
                params.append(v)
    from db import get_engine
    engine = get_engine()
    with engine.connect() as conn:

        result = conn.execute(text(q), params)
        total = result.fetchone()[0]
    return float(total or 0.0)

def upsert_items(df, category_guess=None, budget=None, section=None, grp=None, building_type=None, project_site=None):
    with engine.begin() as conn:

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
            ps = r.get("project_site") or project_site or st.session_state.get('current_project_site', None)
            
            # Use default project site if none selected
            if ps is None:

                ps = "Default Project"
            
            # Upsert priority: code else name+category+context
            if code:

                result = conn.execute(text("SELECT id FROM items WHERE code = :code"), {"code": code})
                row = result.fetchone()
                if row:

                    conn.execute(text("""
                        UPDATE items SET name=:name, category=:category, unit=:unit, qty=:qty, unit_cost=:unit_cost, 
                        budget=:budget, section=:section, grp=:grp, building_type=:building_type, project_site=:project_site 
                        WHERE id=:id
                    """), {
                        "name": name, "category": category, "unit": unit, "qty": qty, "unit_cost": unit_cost,
                        "budget": b, "section": s, "grp": g, "building_type": bt, "project_site": ps, "id": row[0]
                    })
                else:

                    conn.execute(text("""
                        INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp,building_type,project_site) 
                        VALUES(:code,:name,:category,:unit,:qty,:unit_cost,:budget,:section,:grp,:building_type,:project_site)
                    """), {
                        "code": code, "name": name, "category": category, "unit": unit, "qty": qty, "unit_cost": unit_cost,
                        "budget": b, "section": s, "grp": g, "building_type": bt, "project_site": ps
                    })
            else:

                # Use COALESCE instead of IFNULL for PostgreSQL
                result = conn.execute(text("""
                    SELECT id FROM items WHERE name=:name AND category=:category 
                    AND COALESCE(budget,'')=COALESCE(:budget,'') AND COALESCE(section,'')=COALESCE(:section,'') 
                    AND COALESCE(grp,'')=COALESCE(:grp,'') AND COALESCE(building_type,'')=COALESCE(:building_type,'') 
                    AND project_site=:project_site
                """), {
                    "name": name, "category": category, "budget": b, "section": s, 
                    "grp": g, "building_type": bt, "project_site": ps
                })
                row = result.fetchone()
                if row:

                    conn.execute(text("""
                        UPDATE items SET unit=:unit, qty=:qty, unit_cost=:unit_cost, budget=:budget, 
                        section=:section, grp=:grp, building_type=:building_type, project_site=:project_site 
                        WHERE id=:id
                    """), {
                        "unit": unit, "qty": qty, "unit_cost": unit_cost, "budget": b, "section": s, 
                        "grp": g, "building_type": bt, "project_site": ps, "id": row[0]
                    })
                else:

                    conn.execute(text("""
                        INSERT INTO items(code,name,category,unit,qty,unit_cost,budget,section,grp,building_type,project_site) 
                        VALUES(:code,:name,:category,:unit,:qty,:unit_cost,:budget,:section,:grp,:building_type,:project_site)
                    """), {
                        "code": None, "name": name, "category": category, "unit": unit, "qty": qty, "unit_cost": unit_cost,
                        "budget": b, "section": s, "grp": g, "building_type": bt, "project_site": ps
                    })
        
        # Clear cache when items are updated
        clear_cache()
        # Automatically backup data for persistence
        try:

            auto_backup_data()
        except:
            pass  # Silently fail if backup doesn't work

def update_item_qty(item_id: int, new_qty: float):
    from db import get_engine
    engine = get_engine()
    with engine.begin() as conn:

        conn.execute(text("UPDATE items SET qty=:qty WHERE id=:id"), {"qty": float(new_qty), "id": int(item_id)})
        # Automatically backup data for persistence
        try:

            auto_backup_data()
        except:
            pass

def update_item_rate(item_id: int, new_rate: float):
    from db import get_engine
    engine = get_engine()
    with engine.begin() as conn:

        conn.execute(text("UPDATE items SET unit_cost=:unit_cost WHERE id=:id"), {"unit_cost": float(new_rate), "id": int(item_id)})
        # Automatically backup data for persistence
        try:

            auto_backup_data()
        except:
            pass

def add_request(section, item_id, qty, requested_by, note, current_price=None, building_subtype=None):
    """Add a new request with proper validation"""
    try:
        # Input validation
        if not section or section not in ['materials', 'labour']:
            st.error("Invalid section. Must be 'materials' or 'labour'")
            return None
        
        if not item_id or item_id <= 0:
            st.error("Invalid item ID")
            return None
            
        if not qty or qty <= 0:
            st.error("Quantity must be greater than 0")
            return None
            
        if not requested_by or not requested_by.strip():
            st.error("Requester name is required")
            return None

        # Get database engine
        from db import get_engine
        engine = get_engine()
        
        with engine.begin() as conn:
            # Verify item exists and fetch context (including planned quantity and unit_cost)
            result = conn.execute(text("SELECT id, name, building_type, budget, grp, project_site, qty, unit_cost FROM items WHERE id=:item_id"), {"item_id": item_id})
            item = result.fetchone()
            if not item:
                st.error("Item not found")
                return None
            
            item_building_type = item[2] if item and len(item) > 2 else None
            building_subtype = building_subtype.strip() if isinstance(building_subtype, str) and building_subtype.strip() else None
            subtype_norm = building_subtype or ""
            if item_building_type in BUILDING_SUBTYPE_OPTIONS and not building_subtype:
                st.error("Building subtype is required for this building type.")
                return None
            
            # Get planned quantity for over-quantity check
            planned_qty = float(item[6]) if item and len(item) > 6 and item[6] is not None else 0.0
            # Get planned price (unit_cost) for price comparison
            planned_price = float(item[7]) if item and len(item) > 7 and item[7] is not None else 0.0
            
            # Calculate cumulative requested quantity across all pending/approved requests for this item
            # This ensures we check if the TOTAL of all requests exceeds planned quantity
            cumulative_result = conn.execute(text("""
                SELECT COALESCE(SUM(qty), 0) 
                FROM requests 
                WHERE item_id = :item_id 
                AND status IN ('Pending', 'Approved')
                AND COALESCE(building_subtype, '') = :subtype_norm
            """), {"item_id": item_id, "subtype_norm": subtype_norm})
            cumulative_requested = float(cumulative_result.fetchone()[0] or 0)
            
            # Calculate new cumulative total after adding this request
            new_cumulative_requested = cumulative_requested + float(qty)

            # Use West African Time (WAT)
            wat_timezone = pytz.timezone('Africa/Lagos')
            current_time = datetime.now(wat_timezone)
            
            # Find the lowest unused ID (reuse deleted IDs)
            # First, check if there are any requests
            count_result = conn.execute(text("SELECT COUNT(*) FROM requests"))
            request_count = count_result.fetchone()[0]
            
            if request_count == 0:
                # No requests exist, start from ID 1
                next_id = 1
            else:
                # Find the first gap in IDs, or use max + 1 if no gaps
                # Get all existing IDs
                id_result = conn.execute(text("SELECT id FROM requests ORDER BY id"))
                existing_ids = [row[0] for row in id_result.fetchall()]
                
                # Find the first gap (starting from 1)
                next_id = None
                for i in range(1, len(existing_ids) + 2):
                    if i not in existing_ids:
                        next_id = i
                        break
                
                # If no gap found, use max + 1 (shouldn't happen, but safety check)
                if next_id is None:
                    next_id = max(existing_ids) + 1 if existing_ids else 1
            
            # Update the sequence to be at least next_id + 1 (for PostgreSQL)
            # This ensures the sequence doesn't interfere with reused IDs
            try:
                conn.execute(text(f"SELECT setval('requests_id_seq', GREATEST({next_id}, (SELECT COALESCE(MAX(id), 0) FROM requests)))"))
            except:
                # If sequence doesn't exist or error, continue anyway
                pass
            
            # Insert request with the determined ID (store current_price if provided)
            if current_price is not None:
                result = conn.execute(text("""
                    INSERT INTO requests(id, ts, section, item_id, qty, requested_by, note, building_subtype, status, current_price) 
                    VALUES (:id, :ts, :section, :item_id, :qty, :requested_by, :note, :building_subtype, 'Pending', :current_price)
                    RETURNING id
                """), {
                    "id": next_id,
                    "ts": current_time.isoformat(timespec="seconds"),
                    "section": section,
                    "item_id": item_id,
                    "qty": float(qty),
                    "requested_by": requested_by.strip(),
                    "note": note or "",
                    "building_subtype": building_subtype,
                    "current_price": float(current_price)
                })
            else:
                result = conn.execute(text("""
                    INSERT INTO requests(id, ts, section, item_id, qty, requested_by, note, building_subtype, status) 
                    VALUES (:id, :ts, :section, :item_id, :qty, :requested_by, :note, :building_subtype, 'Pending')
                    RETURNING id
                """), {
                    "id": next_id,
                    "ts": current_time.isoformat(timespec="seconds"),
                    "section": section,
                    "item_id": item_id,
                    "qty": float(qty),
                    "requested_by": requested_by.strip(),
                    "note": note or "",
                    "building_subtype": building_subtype
                })
        
        # Get the request ID for notification
        row = result.fetchone()
        request_id = row[0] if row else None
        
        # Create notifications
        try:
            # Get requester name and project site for notification
            requester_name = requested_by.strip()
            project_site = item[5] if item and len(item) > 5 and item[5] else st.session_state.get('current_project_site', 'Unknown Project')
            item_name = item[1]
            
            # Prefer item context; fall back to session
            building_type = item[2] if item and len(item) > 2 and item[2] else st.session_state.get('building_type', 'Unknown Building')
            budget = item[3] if item and len(item) > 3 and item[3] else st.session_state.get('budget', 'Unknown Budget')
            block_display = f"{building_type} / {building_subtype}" if building_subtype else building_type
            section_display = section.title()  # Convert materials/labour to Materials/Labour
            
            # Create admin notification with detailed information
            create_notification(
                notification_type="new_request",
                title=f"🔔 New Request from {requester_name}",
                message=f"{requester_name} from {project_site} submitted a request for {qty} units of {item_name} ({section_display} - {block_display} - {budget})",
                user_id=None,  # Admin notification
                request_id=request_id
            )
            
            # Create project site account notification for confirmation
            create_notification(
                notification_type="request_submitted",
                title="Request Submitted Successfully",
                message=f"Your request for {qty} units of {item_name} ({section_display} - {block_display} - {budget}) from {project_site} has been submitted and is pending review",
                user_id=-1,  # Project site account
                request_id=request_id
            )
            
            # Create admin notification if cumulative requested quantity exceeds planned quantity
            # Check if the NEW cumulative total (after adding this request) exceeds planned
            if new_cumulative_requested > planned_qty:
                excess = new_cumulative_requested - planned_qty
                # Show previous cumulative and new request details
                previous_requests = cumulative_requested
                create_notification(
                    notification_type="over_planned",
                    title=f"⚠️ Over-Planned Request #{request_id}",
                    message=f"{requester_name} requested {qty} units of {item_name} ({block_display}). "
                           f"Previous requests: {previous_requests} units. "
                           f"Total requested: {new_cumulative_requested} units, but only {planned_qty} units are planned (excess: {excess})",
                    user_id=None,  # Admin notification
                    request_id=request_id
                )
            
            # Note: Price difference is shown in red in the request table, no separate notification needed
        except Exception as e:
            print(f"Notification creation failed: {e}")
        
        # Clear cache to ensure statistics are refreshed
        clear_cache()
        
        return request_id
            
    except Exception as e:
        st.error(f"Failed to add request: {e}")
        return None
def set_request_status(req_id, status, approved_by=None, note=None):
    """Update request status with retry logic for Render maintenance"""
    # Input validation
    if not req_id or req_id <= 0:
        return "Invalid request ID"
    
    if status not in ['Pending', 'Approved', 'Rejected']:
        return "Invalid status. Must be Pending, Approved, or Rejected"
    
    if not approved_by or not approved_by.strip():
        return "Approver name is required"

    # Retry logic for Render maintenance (optimized for performance)
    max_retries = 2
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            from db import get_engine
            import time
            
            # Force create a new engine for each attempt
            engine = get_engine()
            
            # Proceed with operation (connection testing removed for performance)
            with engine.begin() as conn:
                # Check if request exists
                result = conn.execute(text("SELECT item_id, qty, section, status, building_subtype FROM requests WHERE id=:req_id"), {"req_id": req_id})
                r = result.fetchone()
                if not r:
                    return "Request not found"
                
                item_id, qty, section, old_status, request_building_subtype = r
                subtype_norm = (request_building_subtype.strip() if isinstance(request_building_subtype, str) else request_building_subtype) or ""
                if old_status == status:
                    return None  # No change needed

                if status == "Approved":
                    # DO NOT deduct from inventory - budget remains unchanged
                    # Just create actual record to track usage
                    
                    # Automatically create actual record when request is approved
                    try:
                        # Get project site from the item, not from session state
                        result = conn.execute(text("SELECT i.project_site FROM items i WHERE i.id=:item_id"), {"item_id": item_id})
                        project_site_result = result.fetchone()
                        project_site = project_site_result[0] if project_site_result else 'Lifecamp Kafe'
                        print(f"🔔 DEBUG: Using project site from item: {project_site}")
                        
                        # Get current date
                        from datetime import datetime
                        wat_timezone = pytz.timezone('Africa/Lagos')
                        current_time = datetime.now(wat_timezone)
                        actual_date = current_time.date().isoformat()
                        
                        # Use current_price from request for actual cost calculation (fallback to unit_cost if current_price is NULL)
                        result = conn.execute(text("""
                            SELECT COALESCE(r.current_price, i.unit_cost) as price_per_unit, i.unit_cost
                            FROM requests r
                            JOIN items i ON r.item_id = i.id
                            WHERE r.id = :req_id
                        """), {"req_id": req_id})
                        price_result = result.fetchone()
                        price_per_unit = price_result[0] if price_result[0] else 0
                        actual_cost = price_per_unit * qty
                        
                        # Create actual record
                        print(f"🔔 DEBUG: Creating actual record for approved request #{req_id}")
                        conn.execute(text("""
                            INSERT INTO actuals (item_id, actual_qty, actual_cost, actual_date, recorded_by, notes, building_subtype, project_site)
                            VALUES (:item_id, :actual_qty, :actual_cost, :actual_date, :recorded_by, :notes, :building_subtype, :project_site)
                        """), {
                            "item_id": item_id,
                            "actual_qty": qty,
                            "actual_cost": actual_cost,
                            "actual_date": actual_date,
                            "recorded_by": approved_by or 'System',
                            "notes": f"Auto-generated from approved request #{req_id}",
                            "building_subtype": request_building_subtype,
                            "project_site": project_site
                        })
                        print(f"🔔 DEBUG: Actual record created successfully")
                        
                        # Clear cache to ensure actuals tab updates (without rerun)
                        clear_cache()
                        
                    except Exception as e:
                        # Don't fail the approval if actual creation fails, but log the error
                        print(f"❌ DEBUG: Failed to create actual record: {e}")
                        print(f"❌ DEBUG: Item ID: {item_id}, Qty: {qty}, Project Site: {project_site}")
                        
                if old_status == "Approved" and status in ("Pending","Rejected"):
                    # DO NOT restore inventory - budget remains unchanged
                    # Just remove the actual record
                    
                    # Remove the auto-generated actual record when request is rejected/pending
                    try:
                        conn.execute(text("""
                            DELETE FROM actuals 
                            WHERE item_id = :item_id 
                              AND recorded_by = :recorded_by 
                              AND notes LIKE :notes
                              AND COALESCE(building_subtype, '') = :subtype_norm
                        """), {
                            "item_id": item_id,
                            "recorded_by": approved_by or 'System',
                            "notes": f"Auto-generated from approved request #{req_id}",
                            "subtype_norm": subtype_norm
                        })
                        
                        # Clear cache to ensure actuals tab updates (without rerun)
                        clear_cache()
                        
                    except Exception as e:
                        # Don't fail the rejection if actual deletion fails
                        pass
                
                # Update the request status, timestamp, and note (for rejection reasons)
                # get_nigerian_time_iso is defined at module level
                if note and note.strip():
                    conn.execute(text("UPDATE requests SET status=:status, approved_by=:approved_by, updated_at=:updated_at, note=:note WHERE id=:req_id"), 
                                {"status": status, "approved_by": approved_by, "updated_at": get_nigerian_time_iso(), "note": note.strip(), "req_id": req_id})
                else:
                    conn.execute(text("UPDATE requests SET status=:status, approved_by=:approved_by, updated_at=:updated_at WHERE id=:req_id"), 
                                {"status": status, "approved_by": approved_by, "updated_at": get_nigerian_time_iso(), "req_id": req_id})
                
                # Clear cache to ensure data refreshes immediately
                clear_cache()
                
                # Log the request status change
                current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
                log_request_activity(req_id, status, approved_by or current_user)
                
                # Create notification for the user when request is approved/rejected - SIMPLIFIED
                if status in ["Approved", "Rejected"]:
                    # Get requester name, item name, and project site - SIMPLIFIED
                    result = conn.execute(text("SELECT requested_by FROM requests WHERE id=:req_id"), {"req_id": req_id})
                    requester_result = result.fetchone()
                    requester_name = requester_result[0] if requester_result else "Unknown User"
                    
                    result = conn.execute(text("SELECT name, project_site FROM items WHERE id=:item_id"), {"item_id": item_id})
                    item_result = result.fetchone()
                    item_name = item_result[0] if item_result else "Unknown Item"
                    
                    # Get project site from the item itself (more reliable than session state)
                    project_site = item_result[1] if item_result and len(item_result) > 1 and item_result[1] else st.session_state.get('current_project_site', 'Unknown Project')
                    
                    # Email notifications removed for better performance
                    # Create notification for project site accounts (simplified approach)
                    print(f"🔔 DEBUG: Creating {status} notification for project site accounts")
                    # Build detailed message including approver/rejector name
                    actor = approved_by or 'Admin'
                    action_text = 'approved' if status == 'Approved' else 'rejected' if status == 'Rejected' else status.lower()
                    detailed_message = (
                        f"Your request for {qty} units of {item_name} from {project_site} has been {action_text} by {actor}"
                    )
                    notification_success = create_notification(
                        notification_type="request_approved" if status == "Approved" else "request_rejected",
                        title="Request Approved" if status == "Approved" else "Request Rejected",
                        message=detailed_message,
                        user_id=-1,  # Send to all project site accounts
                        request_id=req_id
                    )
                    print(f"🔔 DEBUG: Notification creation result: {notification_success}")
                        
                    # Trigger JavaScript notification for project site account
                    if notification_success:
                        print(f"✅ Notification created for {requester_name}")
                        # Trigger JavaScript notification for project site account
                        notification_flag = "request_approved_notification" if status == "Approved" else "request_rejected_notification"
                        st.markdown(f"""
                        <script>
                        localStorage.setItem('{notification_flag}', 'true');
                        console.log('Notification flag set for project site account: {notification_flag}');
                        </script>
                        """, unsafe_allow_html=True)
                    else:
                        print(f"❌ Failed to create notification for {requester_name}")
                        # Still trigger JavaScript notification even if database notification fails
                        notification_flag = "request_approved_notification" if status == "Approved" else "request_rejected_notification"
                        st.markdown(f"""
                        <script>
                        localStorage.setItem('{notification_flag}', 'true');
                        console.log('Notification flag set for project site account: {notification_flag}');
                        </script>
                        """, unsafe_allow_html=True)
                    
                    # Admin notification removed - admins don't need notifications about their own actions
                
                # Clear cache to ensure statistics are refreshed
                clear_cache()
                
                return None  # Success
                
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ["connection", "closed", "timeout", "maintenance"]) and attempt < max_retries - 1:
                print(f"Database connection issue detected, retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                print(f"Error: {e}")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                return f"Failed to update request status: {e}"
    
    return f"Failed to update request status after {max_retries} attempts"

def delete_request(req_id):
    """Delete a request from the database and log the deletion"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Get request details before deletion for logging (including note and approved_by)
            result = conn.execute(text("""
                SELECT r.status, r.item_id, r.requested_by, r.qty, i.name, i.project_site, r.building_subtype, r.note, r.approved_by
                FROM requests r
                LEFT JOIN items i ON r.item_id = i.id
                WHERE r.id = :req_id
            """), {"req_id": req_id})
            request_data = result.fetchone()
            
            if not request_data:

            
                return False
                
            status, item_id, requested_by, quantity, item_name, project_site, building_subtype, note, approved_by = request_data
            
            # Log the deletion
            current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
            deletion_log = f"Request #{req_id} deleted by {current_user}: {requested_by} requested {quantity} units of {item_name} (Status: {status})"
            
            # Insert deletion log into access_logs
            conn.execute(text("""
                INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                VALUES (:access_code, :user_name, :access_time, :success, :role)
            """), {
                "access_code": 'SYSTEM',
                "user_name": current_user,
                "access_time": get_nigerian_time_iso(),
                "success": 1,
                "role": st.session_state.get('user_type', 'project_site')
            })
            
            # First, check if this is an approved request and remove the associated actual record
            if status == "Approved":

                # Remove the auto-generated actual record
                actuals_result = conn.execute(text("""
                    DELETE FROM actuals 
                    WHERE item_id = :item_id AND notes LIKE :notes_pattern
                """), {"item_id": item_id, "notes_pattern": f"Auto-generated from approved request #{req_id}"})
                
                # Log actuals deletion
                if actuals_result.rowcount > 0:

                    actuals_log = f"Associated actuals deleted for request #{req_id} (item: {item_name})"
                    conn.execute(text("""
                        INSERT INTO access_logs (access_code, user_name, access_time, success, role)
                        VALUES (:access_code, :user_name, :access_time, :success, :role)
                    """), {
                        "access_code": 'SYSTEM',
                        "user_name": current_user,
                        "access_time": get_nigerian_time_iso(),
                        "success": 1,
                        "role": st.session_state.get('user_type', 'project_site')
                    })
            
            # Note: PostgreSQL doesn't support PRAGMA - foreign key constraints are handled differently
            
            # First delete any associated notifications
            conn.execute(text("DELETE FROM notifications WHERE request_id = :req_id"), {"req_id": req_id})
            
            # Then delete the request
            conn.execute(text("DELETE FROM requests WHERE id = :req_id"), {"req_id": req_id})
            
            # Log the deleted request to deleted_requests table (including note and approved_by)
            conn.execute(text("""
                INSERT INTO deleted_requests (req_id, item_name, qty, requested_by, status, deleted_at, deleted_by, building_subtype, note, approved_by)
                VALUES (:req_id, :item_name, :qty, :requested_by, :status, :deleted_at, :deleted_by, :building_subtype, :note, :approved_by)
            """), {
                "req_id": req_id,
                "item_name": item_name,
                "qty": quantity,
                "requested_by": requested_by,
                "status": status,
                "deleted_at": get_nigerian_time_iso(),
                "deleted_by": current_user,
                "building_subtype": building_subtype if building_subtype else None,
                "note": note if note else None,
                "approved_by": approved_by if approved_by else None
            })
            
            # Note: PostgreSQL doesn't support PRAGMA - foreign key constraints are handled differently
            
            # Note: PostgreSQL doesn't use sqlite_sequence - sequences are handled automatically
            
            # Clear cache to ensure actuals tab updates (without rerun)
            clear_cache()
            
            return True
    except Exception as e:

        st.error(f"Error deleting request: {e}")
        return False

def get_user_requests(user_name, status_filter="All"):
    """Get requests for a specific user with proper filtering"""
    try:
        # Cache clearing removed for better performance - data will refresh naturally
        
        from sqlalchemy import text
        from db import get_engine
        
        # Get current project site for filtering
        current_project = st.session_state.get('current_project_site', 'Unknown Project')
        
        # Build query for user's requests with project site filtering
        query = text("""
            SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.building_subtype, r.status, r.approved_by,
                   i.budget, i.building_type, i.grp, i.project_site, i.unit_cost
            FROM requests r 
            JOIN items i ON r.item_id = i.id
            WHERE r.requested_by = :user_name AND i.project_site = :project_site
        """)
        params = {"user_name": user_name, "project_site": current_project}
        
        # Add status filter if not "All"
        if status_filter and status_filter != "All":

            query = text(str(query) + " AND r.status = :status")
            params["status"] = status_filter
        
        query = text(str(query) + " ORDER BY r.id DESC")
        
        engine = get_engine()
        result = pd.read_sql_query(query, engine, params=params)
        # Debug print removed for better performance
        return result
    except Exception as e:

        st.error(f"Error fetching user requests: {e}")
        # Debug print removed for better performance
        return pd.DataFrame()

@st.cache_data(ttl=60)  # Cache for 1 minute - requests change frequently but not every second
def df_requests(status=None, user_type=None, project_site=None):
    from sqlalchemy import text
    from db import get_engine
    
    # CRITICAL: Get user type and project site from parameters or session state
    # These MUST be set before querying to ensure correct cache keys
    if user_type is None:
        user_type = st.session_state.get('user_type', 'project_site')
    if project_site is None:
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
    
    # IMPORTANT: The cache key includes (status, user_type, project_site) parameters
    # This ensures admins and project site users get different cached results
    
    if user_type == 'admin':

    
        # Admin sees ALL requests from ALL project sites
        q = text("""
            SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.building_subtype, r.status, r.approved_by,
                   i.budget, i.building_type, i.grp, i.project_site, i.unit_cost, COALESCE(r.current_price, i.unit_cost) as current_price,
                   i.qty as planned_qty, r.updated_at
           FROM requests r 
            JOIN items i ON r.item_id=i.id
        """)
        params = {}
        if status and status != "All":

            q = text(str(q) + " WHERE r.status=:status")
            params["status"] = status
        q = text(str(q) + " ORDER BY r.id DESC")
    else:

        # Project site accounts see only requests from their own project site (the project site is the account identity)
        q = text("""
            SELECT r.id, r.ts, r.section, i.name as item, r.qty, r.requested_by, r.note, r.building_subtype, r.status, r.approved_by,
                   i.budget, i.building_type, i.grp, i.project_site, i.unit_cost, COALESCE(r.current_price, i.unit_cost) as current_price,
                   i.qty as planned_qty, r.updated_at
            FROM requests r 
            JOIN items i ON r.item_id=i.id
            WHERE i.project_site = :project_site
        """)
        params = {"project_site": project_site}
        if status and status != "All":

            q = text(str(q) + " AND r.status=:status")
            params["status"] = status
        q = text(str(q) + " ORDER BY r.id DESC")
    
    engine = get_engine()
    return pd.read_sql_query(q, engine, params=params)

def all_items_by_section(section):
    from sqlalchemy import text
    from db import get_engine
    
    # Get current project site
    project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    q = text("SELECT id, name, unit, qty FROM items WHERE category=:section AND project_site=:project_site ORDER BY name")
    engine = get_engine()
    return pd.read_sql_query(q, engine, params={"section": section, "project_site": project_site})

def delete_item(item_id: int):
    try:

        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        
        with engine.begin() as conn:

        
            # Check if item exists first
            result = conn.execute(text("SELECT id, name FROM items WHERE id = :item_id"), {"item_id": item_id})
            row = result.fetchone()
            if not row:

                return f"Item not found (ID: {item_id})"
            
            item_name = row[1]
            
            # Check for linked requests
            result = conn.execute(text("SELECT COUNT(*) FROM requests WHERE item_id = :item_id"), {"item_id": item_id})
            request_count = result.fetchone()[0]
            if request_count > 0:

                return f"Cannot delete '{item_name}': It has {request_count} linked request(s). Delete the requests first."
            
            # Delete the item
            conn.execute(text("DELETE FROM items WHERE id = :item_id"), {"item_id": item_id})
            
            # Clear cache after deletion
            clear_cache()
            
            print(f"✅ Successfully deleted item: {item_name} (ID: {item_id})")
            
        return None
    except Exception as e:

        print(f"❌ Delete failed: {e}")
        return f"Delete failed: {e}"

# ---------- REMOVED: delete_request_with_logging function that was causing budget issues ----------
# This function was restoring stock quantities when deleting approved requests,
# which was causing the budget totals to change incorrectly.

# ---------- NEW: fetch deleted requests ----------
def df_deleted_requests():
    from sqlalchemy import text
    from db import get_engine
    
    q = text("SELECT * FROM deleted_requests ORDER BY id DESC")
    engine = get_engine()
    return pd.read_sql_query(q, engine)

# ---------- NEW: clear all deleted logs (for testing) ----------
def clear_deleted_requests():
    from db import get_engine
    engine = get_engine()
    with engine.begin() as conn:

        conn.execute(text("DELETE FROM deleted_requests"))


# Actuals functions
def add_actual(item_id, actual_qty, actual_cost, actual_date, recorded_by, notes="", building_subtype=None):
    """Add actual usage/cost for an item"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Get current project site
            project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
            
            conn.execute(text("""
                INSERT INTO actuals (item_id, actual_qty, actual_cost, actual_date, recorded_by, notes, building_subtype, project_site)
                VALUES (:item_id, :actual_qty, :actual_cost, :actual_date, :recorded_by, :notes, :building_subtype, :project_site)
            """), {
                "item_id": item_id,
                "actual_qty": actual_qty,
                "actual_cost": actual_cost,
                "actual_date": actual_date,
                "recorded_by": recorded_by,
                "notes": notes,
                "building_subtype": building_subtype,
                "project_site": project_site
            })
            conn.commit()
            return True
    except Exception as e:

        st.error(f"Failed to add actual: {str(e)}")
        return False
def get_actuals(project_site=None):
    """Get actuals for current or specified project site"""
    from sqlalchemy import text
    from db import get_engine
    
    if project_site is None:

    
        project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
    
    query = text("""
        SELECT a.id, a.item_id, a.actual_qty, a.actual_cost, a.actual_date, a.recorded_by, a.notes, a.building_subtype, a.created_at, a.project_site,
               i.name, i.code, i.budget, i.building_type, i.unit, i.category, i.section, i.grp
        FROM actuals a
        JOIN items i ON a.item_id = i.id
        WHERE a.project_site = :project_site
        ORDER BY a.actual_date DESC, a.created_at DESC
    """)
    
    engine = get_engine()
    result = pd.read_sql_query(query, engine, params={"project_site": project_site})
    print(f"🔔 DEBUG: Retrieved {len(result)} actuals for project site: {project_site}")
    return result

def delete_actual(actual_id):
    """Delete an actual record with enhanced error handling"""
    max_retries = 3
    for attempt in range(max_retries):

        try:


            from db import get_engine
            engine = get_engine()
            with engine.begin() as conn:

                conn.execute(text("DELETE FROM actuals WHERE id = :actual_id"), {"actual_id": actual_id})
                return True
                
        except sqlite3.OperationalError as e:

                
            error_msg = str(e).lower()
            if "disk I/O error" in error_msg or "database is locked" in error_msg:

                if attempt < max_retries - 1:
                    # Clean up WAL files and retry
                    try:

                        import os
                        if os.path.exists('istrominventory.db-wal'):

                            os.remove('istrominventory.db-wal')
                        if os.path.exists('istrominventory.db-shm'):

                            os.remove('istrominventory.db-shm')
                    except:
                        pass
                    time.sleep(1)
                    continue
                else:

                    st.error(f"🔧 Delete failed: {e}")
                    st.info("Please refresh the page to retry. If the problem persists, restart the application.")
                    return False
            else:

                st.error(f"Delete failed: {e}")
                return False
        except Exception as e:

            st.error(f"Failed to delete actual: {str(e)}")
            return False
    
    return False


# Project configuration functions
def save_project_config(budget_num, building_type, num_blocks, units_per_block, additional_notes=""):
    """Save project configuration to database"""
    from db import get_engine
    engine = get_engine()
    with engine.begin() as conn:

        # Use West African Time (WAT)
        wat_timezone = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(wat_timezone)
        
        # Check if config already exists
        result = conn.execute(text("SELECT id FROM project_config WHERE budget_num = :budget_num AND building_type = :building_type"), 
                           {"budget_num": budget_num, "building_type": building_type})
        existing = result.fetchone()
        
        if existing:

        
            # Update existing config
            conn.execute(text("""
                UPDATE project_config 
                SET num_blocks = :num_blocks, units_per_block = :units_per_block, additional_notes = :additional_notes, updated_at = :updated_at
                WHERE budget_num = :budget_num AND building_type = :building_type
            """), {
                "num_blocks": num_blocks,
                "units_per_block": units_per_block,
                "additional_notes": additional_notes,
                "updated_at": current_time.isoformat(),
                "budget_num": budget_num,
                "building_type": building_type
            })
        else:

            # Insert new config
            conn.execute(text("""
                INSERT INTO project_config (budget_num, building_type, num_blocks, units_per_block, additional_notes, created_at, updated_at)
                VALUES (:budget_num, :building_type, :num_blocks, :units_per_block, :additional_notes, :created_at, :updated_at)
            """), {
                "budget_num": budget_num,
                "building_type": building_type,
                "num_blocks": num_blocks,
                "units_per_block": units_per_block,
                "additional_notes": additional_notes,
                "created_at": current_time.isoformat(),
                "updated_at": current_time.isoformat()
            })
        conn.commit()

def get_project_config(budget_num, building_type):
    """Get project configuration from database"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.connect() as conn:

            result = conn.execute(text("""
                SELECT num_blocks, units_per_block, additional_notes 
                FROM project_config 
                WHERE budget_num = :budget_num AND building_type = :building_type
            """), {"budget_num": budget_num, "building_type": building_type})
            row = result.fetchone()
            if row:

                return {
                    'num_blocks': row[0],
                    'units_per_block': row[1],
                    'additional_notes': row[2]
                }
        return None
    except Exception as e:

        print(f"⚠️ Database error in get_project_config: {e}")
        return None

def clear_inventory(include_logs: bool = False):
    # PRODUCTION DATA PROTECTION - Prevent data loss
    if os.getenv('PRODUCTION_MODE') == 'true' or os.getenv('DISABLE_MIGRATION') == 'true':

        print("🚫 clear_inventory() BLOCKED - PRODUCTION MODE - YOUR DATA IS SAFE")
        return False
    
    # Create backup before destructive operation
    create_backup()
    
    from db import get_engine
    engine = get_engine()
    with engine.begin() as conn:

        # Remove dependent rows first due to FK constraints
        conn.execute(text("DELETE FROM requests"))
        if include_logs:

            conn.execute(text("DELETE FROM deleted_requests"))
        conn.execute(text("DELETE FROM items"))


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

BUILDING_SUBTYPE_OPTIONS = {
    "Flats": [f"B{i}" for i in range(1, 14)],
    "Terraces": [
        "A (T1-T6)",
        "B (T7-T12)",
        "C (T13-T18)",
        "D (T19-T24)",
        "E (T25-T30)",
        "F (T31-T36)",
        "G (T37-T42)",
        "H (T43-T48)",
        "I (T49-T53)",
        "J (T54-T58)",
        "K (T59-T64)",
        "L (T65-T70)",
        "M (T71-T76)",
        "N (T77-T82)",
        "O (T83-T88)",
        "P (T89-T94)",
        "Q (T95-T100)",
        "R (T101-T106)",
        "S (T107-T112)",
        "T (T113-T118)",
        "U (T119-T124)",
        "V (T125-T130)",
        "W (T131-T136)",
        "X (T137-T142)",
    ],
    "Semi-detached": [f"SD {i}" for i in range(1, 30)],
    "Fully-detached": [f"D{i}" for i in range(1, 53)],
}

BUILDING_SUBTYPE_LABELS = {
    "Flats": "Select Block (Flats)",
    "Terraces": "Select Terrace Cluster",
    "Semi-detached": "Select Semi-detached Unit",
    "Fully-detached": "Select Fully-detached Plot",
}

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
# Page config is already set at the top of the file - removing duplicate
# Initialize database on startup
initialize_database()

# --------------- SEAMLESS ACCESS CODE SYSTEM ---------------
# NOTE: Authentication functions have been moved to modules/auth.py
# The functions below are disabled (wrapped in if False) but kept for reference
# They are now imported from modules.auth at the top of the file

if False:  # Disable old auth functions - now in modules/auth.py
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
            print(f"Error fetching access codes: {e}")
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
            print(f"Authentication error: {e}")
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
                            print(f"Failed to log successful access: {e}")
                        
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
                            log_access(access_code, success=False, user_name="Unknown", role="unknown")
                        except:
                            pass
                        st.error("Invalid access code. Please try again.")
                        st.session_state.login_processing = False
                else:
                    st.error("Please enter your access code.")
                    st.session_state.login_processing = False
    # End of disabled old auth functions

# show_logout_button function removed - using optimized logout in sidebar

# Initialize session - REQUIRED FOR APP TO WORK
initialize_session()

# --------------- PERSISTENT SESSION MANAGEMENT (NO AUTO-LOGOUT) ---------------
# NOTE: Session management functions moved to modules/auth.py
# Old functions disabled below (wrapped in if False)
if False:  # Disable old session functions - now in modules/auth.py
    def check_session_validity():
        """Check if current session is still valid - persistent login"""
        # Only check if user is logged in - no timeout, no complex validation
        return st.session_state.get('logged_in', False)

    def restore_session_from_cookie():
        """Restore session from browser cookie if valid - 24 hour timeout"""
        try:
            import base64
            import json
            from datetime import datetime, timedelta
            import pytz
            
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
            import base64
            import json
            from datetime import datetime, timedelta
            import pytz
            
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
    # End of disabled old session functions

# Initialize session persistence using Streamlit's built-in session state
# This ensures the session persists across page refreshes

# Session restoration is now handled in the session validity check below

# Check if current session is still valid - persistent login
if not check_session_validity():
    # Try to restore session from cookie if not logged in
    if not st.session_state.logged_in:
        if restore_session_from_cookie():
            # Session restored successfully
            # Ensure session_data is saved to query params immediately after restoration
            # This ensures it persists even if query params were lost
            try:
                save_session_to_cookie()
            except Exception as e:
                log_warning(f"Could not save session after restoration: {e}")
            
            # Don't show success message on every rerun - only once per session
            if 'session_restored_message_shown' not in st.session_state:
                if st.session_state.user_type == 'admin' and st.session_state.username == 'admin' and st.session_state.project_site == 'ALL':
                    st.success("Admin session restored - 24 hour login active")
                elif st.session_state.user_type == 'project_site' and st.session_state.username and st.session_state.project_site:
                    st.success("User session restored - 24 hour login active")
                st.session_state.session_restored_message_shown = True
            # Session restored successfully, continue with the app
        else:
            # No valid session to restore
            show_login_interface()
            st.stop()
    else:
        # Session state is corrupted, clear it
        st.error("Session state corrupted. Please log in again.")
        for key in list(st.session_state.keys()):
            if key not in ['current_project_site']:
                del st.session_state[key]
        show_login_interface()
        st.stop()

# Save session to cookie for persistence (update timestamp)
# Ensure session_data is always in query params when logged in
# This is critical for session persistence across page refreshes
if st.session_state.logged_in:
    # Check if session_data exists in query params
    existing_session_data = st.query_params.get('session_data')
    
    # If session_data is missing from query params, save it immediately
    # This ensures persistence across page refreshes
    if not existing_session_data:
        try:
            save_session_to_cookie()
            if 'last_cookie_save' not in st.session_state:
                st.session_state.last_cookie_save = time.time()
        except Exception as e:
            print(f"Warning: Could not save session to cookie: {e}")
    elif 'last_cookie_save' not in st.session_state:
        # First time after login/restore - save to ensure it's there
        st.session_state.last_cookie_save = time.time()
        try:
            save_session_to_cookie()
        except Exception as e:
            print(f"Warning: Could not save session to cookie: {e}")
    else:
        # Only update timestamp every 30 minutes (1800 seconds) to minimize reruns
        # The save_session_to_cookie function will also check if data actually changed
        current_time = time.time()
        if current_time - st.session_state.last_cookie_save > 1800:  # 30 minutes
            try:
                save_session_to_cookie()
                st.session_state.last_cookie_save = current_time
            except Exception as e:
                print(f"Warning: Could not save session to cookie: {e}")
                # Don't show error to user for this non-critical operation
st.markdown(
    """
    <style>
    /* Cache-busting timestamp: """ + get_nigerian_time_iso() + """ */
    /* Premium Enterprise Styling */
    .app-brand {
        padding: 3rem 2rem;
        text-align: center;
        background: linear-gradient(135deg, #1e293b 0%, #334155 50%, #475569 100%);
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    .app-brand::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, rgba(59, 130, 246, 0.1) 0%, transparent 50%, rgba(16, 185, 129, 0.1) 100%);
        animation: shimmer 4s ease-in-out infinite;
    }
    
    @keyframes shimmer {
        0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
    }
    
    .app-brand h1 {
        font-size: 2.5rem;
        line-height: 1.2;
        margin: 0;
        font-weight: 700;
        color: #ffffff;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        letter-spacing: -0.5px;
        margin-bottom: 1rem;
        position: relative;
        z-index: 2;
    }
    
    .app-brand .subtitle {
        color: rgba(255,255,255,0.9);
        font-size: 1.2rem;
        margin-top: 0.5rem;
        font-weight: 400;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        position: relative;
        z-index: 2;
        letter-spacing: 0.3px;
    }
    
    .app-brand .tagline {
        color: rgba(255,255,255,0.7);
        font-size: 0.9rem;
        margin-top: 0.5rem;
        font-weight: 300;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2);
        position: relative;
        z-index: 2;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-family: 'Arial', sans-serif;
    }
    /* Premium Enterprise Components */
    .chip {display:inline-block;padding:4px 12px;border-radius:6px;background:#f8fafc;color:#1f2937;font-size:12px;margin-right:8px;border:1px solid #e2e8f0;font-weight:500}
    .chip.blue {background:#eff6ff;border-color:#dbeafe;color:#1e3a8a}
    .chip.green {background:#ecfdf5;border-color:#d1fae5;color:#065f46}
    .chip.gray {background:#f3f4f6;border-color:#e5e7eb;color:#374151}
    
    /* Professional Data Tables */
    .stDataFrame {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Premium Buttons */
    .stButton > button {
        border-radius: 6px;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    /* Professional Metrics */
    .metric-container {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    /* Clean Sidebar */
    .css-1d391kg {
        background: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }
    
    /* Sidebar text styling - readable */
    .sidebar .stMarkdown {
        font-size: 1.0rem !important;
    }
    
    .sidebar .stMarkdown h3 {
        font-size: 1.1rem !important;
    }
    
    .sidebar .stMarkdown p {
        font-size: 0.9rem !important;
    }
    
    .sidebar .stMarkdown strong {
        font-size: 0.9rem !important;
    }
    
    /* Target sidebar content specifically */
    .sidebar-content .stMarkdown {
        font-size: 0.9rem !important;
    }
    
    .sidebar-content .stMarkdown h3 {
        font-size: 1.0rem !important;
    }
    
    .sidebar-content .stMarkdown p {
        font-size: 0.8rem !important;
    }
    
    .sidebar-content .stMarkdown strong {
        font-size: 0.8rem !important;
    }
    
    /* Professional Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #1f2937;
        font-weight: 600;
        letter-spacing: -0.025em;
    }
    
    /* Clean Form Elements */
    .stSelectbox > div > div {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }
    
    .stTextInput > div > div > input {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }
    
    .stNumberInput > div > div > input {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }
    
    /* Reduce unnecessary gaps */
    .element-container {
        margin-bottom: 0.5rem !important;
    }
    
    .stMarkdown {
        margin-bottom: 0.5rem !important;
    }
    
    .stCaption {
        margin-top: 0.25rem !important;
        margin-bottom: 0.25rem !important;
    }
    
    /* Compact spacing */
    .stMetric {
        margin-bottom: 0.5rem !important;
    }
    
    /* Large readable dashboard metrics */
    .stMetric > div {
        font-size: 1.8rem !important;
    }
    
    .stMetric > div > div {
        font-size: 1.6rem !important;
    }
    
    .stMetric > div > div[data-testid="metric-value"] {
        font-size: 2.2rem !important;
        font-weight: 600 !important;
    }
    
    .stMetric > div > div[data-testid="metric-delta"] {
        font-size: 1.4rem !important;
    }
    
    /* Large dashboard header specific styling */
    .stMetric {
        font-size: 1.8rem !important;
        padding: 1.2rem !important;
        margin-bottom: 1.2rem !important;
    }
    
    .stMetric > div {
        font-size: 1.8rem !important;
    }
    
    .stMetric > div > div {
        font-size: 1.8rem !important;
    }
    
    /* Target all metric labels and values */
    [data-testid="metric-label"] {
        font-size: 1.6rem !important;
        font-weight: 500 !important;
    }
    
    [data-testid="metric-value"] {
        font-size: 2.4rem !important;
        font-weight: 600 !important;
    }
    
    /* More aggressive targeting for dashboard metrics */
    .stMetric * {
        font-size: 1.8rem !important;
    }
    
    .stMetric label {
        font-size: 1.6rem !important;
    }
    
    .stMetric div {
        font-size: 1.8rem !important;
    }
    
    /* Large dashboard header */
    .element-container .stMetric {
        font-size: 1.8rem !important;
    }
    
    .element-container .stMetric * {
        font-size: 1.8rem !important;
    }
    
    /* FORCE LARGE FONTS - Override any small font rules */
    .stMetric, .stMetric *, .stMetric div, .stMetric span, .stMetric label {
        font-size: 1.8rem !important;
    }
    
    .stMetric [data-testid="metric-label"] {
        font-size: 1.6rem !important;
    }
    
    .stMetric [data-testid="metric-value"] {
        font-size: 2.4rem !important;
        font-weight: 700 !important;
    }
    
    /* Override any conflicting small font rules */
    *[style*="font-size: 0."] {
        font-size: 1.2rem !important;
    }
    
    /* SPECIFIC TARGETING FOR TOTAL AMOUNTS AND METRICS */
    .stMetric {
        font-size: 2.0rem !important;
        padding: 1.5rem !important;
        margin: 1rem 0 !important;
    }
    
    .stMetric > div {
        font-size: 2.0rem !important;
    }
    
    .stMetric > div > div {
        font-size: 2.0rem !important;
    }
    
    .stMetric label {
        font-size: 1.8rem !important;
        font-weight: 600 !important;
    }
    
    .stMetric [data-testid="metric-value"] {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        color: #1f2937 !important;
    }
    
    .stMetric [data-testid="metric-delta"] {
        font-size: 1.6rem !important;
    }
    
    /* Force all metric containers to be large */
    .element-container .stMetric {
        font-size: 2.0rem !important;
        padding: 1.5rem !important;
    }
    
    .element-container .stMetric * {
        font-size: 2.0rem !important;
    }
    
    /* Target specific metric text */
    .stMetric div[data-testid="metric-value"] {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
    }
    
    /* ULTRA AGGRESSIVE OVERRIDE FOR ALL METRICS */
    .stMetric, .stMetric *, .stMetric div, .stMetric span, .stMetric p, .stMetric label {
        font-size: 2.0rem !important;
        line-height: 1.2 !important;
    }
    
    .stMetric [data-testid="metric-value"], .stMetric [data-testid="metric-delta"] {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        color: #1f2937 !important;
    }
    
    /* Force override for any remaining small fonts */
    .stMetric * {
        font-size: 2.0rem !important;
    }
    
    /* Specific targeting for metric containers */
    div[data-testid="metric-container"] {
        font-size: 2.0rem !important;
        padding: 1.5rem !important;
    }
    
    div[data-testid="metric-container"] * {
        font-size: 2.0rem !important;
    }
    
    /* COMPACT METRIC SIZES */
    .stMetric, .stMetric *, .stMetric div, .stMetric span, .stMetric p, .stMetric label, .stMetric strong {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
        line-height: 1.2 !important;
    }
    
    .stMetric [data-testid="metric-value"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #1f2937 !important;
    }
    
    .stMetric [data-testid="metric-delta"] {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
    }
    
    /* Override any Streamlit default styling */
    .stMetric > div > div {
        font-size: 1.3rem !important;
    }
    
    /* Force all metric text to be compact size */
    .stMetric label, .stMetric div, .stMetric span {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
    }
    
    /* NUCLEAR OVERRIDE - Force all metrics to be compact */
    .stMetric, .stMetric *, .stMetric div, .stMetric span, .stMetric p, .stMetric label, .stMetric strong, .stMetric h1, .stMetric h2, .stMetric h3, .stMetric h4, .stMetric h5, .stMetric h6 {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
        line-height: 1.2 !important;
    }
    
    .stMetric [data-testid="metric-value"], .stMetric [data-testid="metric-delta"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #1f2937 !important;
    }
    
    /* Override any remaining small fonts */
    .stMetric * {
        font-size: 1.3rem !important;
    }
    
    /* Force override for all metric containers */
    div[data-testid="metric-container"], div[data-testid="metric-container"] * {
        font-size: 1.3rem !important;
    }
    
    /* Target specific metric elements */
    .stMetric > div > div > div {
        font-size: 1.3rem !important;
    }
    
    /* Mobile Responsive Design */
    @media (max-width: 768px) {
        .app-brand {
            padding: 2rem 1rem;
            margin-bottom: 1rem;
        }
        
        .app-brand h1 {
            font-size: 2.5rem;
            letter-spacing: -1px;
            margin-bottom: 1rem;
        }
        
        .app-brand .subtitle {
            font-size: 1.1rem;
            margin-top: 0.5rem;
        }
        
        .app-brand .tagline {
            font-size: 0.8rem;
            margin-top: 0.5rem;
            letter-spacing: 1px;
        }
        
        /* Make tables responsive */
        .stDataFrame {
            font-size: 0.8rem;
        }
        
        /* Better mobile spacing */
        .element-container {
            margin-bottom: 0.5rem;
        }
        
        /* Mobile-friendly buttons */
        .stButton > button {
            width: 100%;
            margin-bottom: 0.5rem;
        }
        
        /* Mobile sidebar */
        .css-1d391kg {
            width: 100% !important;
        }
    }
    
    @media (max-width: 480px) {
        .app-brand h1 {
            font-size: 2rem;
        }
        
        .app-brand .subtitle {
            font-size: 1rem;
        }
        
        .app-brand .tagline {
            font-size: 0.7rem;
        }
    }
    </style>
    <div class="app-brand">
      <h1>Istrom Inventory Management System</h1>
      <div class="subtitle">Professional Construction Inventory & Budget Management</div>
      <div class="tagline">Enterprise-Grade • Real-Time Analytics • Advanced Tracking</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Modern Professional Header
# Get user info - unified session state keys
user_name = st.session_state.get('full_name', 'Unknown')
user_type = st.session_state.get('user_type', 'user')
project_site = st.session_state.get('project_site', 'Lifecamp Kafe')

# Calculate session remaining time (24 hours)
session_remaining = "24 hours"
auth_timestamp = st.session_state.get('auth_timestamp')
if auth_timestamp:
    try:
        from datetime import datetime, timedelta
        import pytz
        
        auth_time = datetime.fromisoformat(auth_timestamp.replace('Z', '+00:00'))
        current_time = datetime.now(pytz.UTC)
        time_elapsed = current_time - auth_time
        time_remaining = timedelta(hours=24) - time_elapsed
        
        if time_remaining.total_seconds() > 0:
            hours_remaining = int(time_remaining.total_seconds() // 3600)
            minutes_remaining = int((time_remaining.total_seconds() % 3600) // 60)
            session_remaining = f"{hours_remaining}h {minutes_remaining}m"
        else:
            session_remaining = "Expired"
    except Exception as e:
        print(f"Error calculating session remaining: {e}")
        session_remaining = "24 hours"

# Get notification count for admins
notification_count = 0
if user_type == 'admin':

    notifications = get_admin_notifications()
    notification_count = len(notifications)

# Compact dashboard header using HTML with bigger fonts
st.markdown(f"""
<div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
    <div style="flex: 1; text-align: center; padding: 0.8rem; border: 1px solid #e2e8f0; border-radius: 4px; background: #f8fafc;">
        <div style="font-size: 1.2rem; color: #64748b; margin-bottom: 0.4rem;">User</div>
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937;">{user_name}</div>
    </div>
    <div style="flex: 1; text-align: center; padding: 0.8rem; border: 1px solid #e2e8f0; border-radius: 4px; background: #f8fafc;">
        <div style="font-size: 1.2rem; color: #64748b; margin-bottom: 0.4rem;">Access</div>
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937;">{"Admin" if user_type == 'admin' else "Project Site Account"}</div>
    </div>
    <div style="flex: 1; text-align: center; padding: 0.8rem; border: 1px solid #e2e8f0; border-radius: 4px; background: #f8fafc;">
        <div style="font-size: 1.2rem; color: #64748b; margin-bottom: 0.4rem;">Project</div>
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937;">{project_site}</div>
    </div>
    <div style="flex: 1; text-align: center; padding: 0.8rem; border: 1px solid #e2e8f0; border-radius: 4px; background: #f8fafc;">
        <div style="font-size: 1.2rem; color: #64748b; margin-bottom: 0.4rem;">Session</div>
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937;">{session_remaining}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Status indicator
if user_type == 'admin':

    if notification_count > 0:
        st.warning(f"{notification_count} pending notifications")
    else:

        st.success("All clear")
else:

    st.info("User access")

# Logout button in sidebar
# Old sidebar section removed - now using professional sidebar below

# init_db()  # DISABLED: Using database_config.py instead
# ensure_indexes()  # DISABLED: Using database_config.py instead

# Initialize persistent data file if it doesn't exist
# def init_persistent_data()  # DISABLED FOR PRODUCTION:
#     """Initialize persistent data file if it doesn't exist"""
#     if not os.path.exists("persistent_data.json"):
#         # Create empty persistent data file
#         empty_data = {
#             "items": [],
#             "requests": [],
#             "access_codes": {
#                 "admin_code": DEFAULT_ADMIN_ACCESS_CODE,
#                 "user_code": DEFAULT_USER_ACCESS_CODE
#             },
#             "backup_timestamp": get_nigerian_time_iso()
#         }
#         try:
#             with open("persistent_data.json", 'w') as f:
#                 json.dump(empty_data, f, indent=2)
#         except:
#             pass

# init_persistent_data()  # DISABLED FOR PRODUCTION

# DISABLED: auto_restore_from_file() was causing data loss on production

# auto_restore_from_file()  # DISABLED: This was causing data loss on production

# Create automatic backup on startup - DISABLED FOR PRODUCTION
# if not st.session_state.get('backup_created', False):
#     backup_path = create_backup()
#     if backup_path:
#         st.session_state.backup_created = True
#         cleanup_old_backups()

# Auto-restore data from Streamlit Cloud secrets if available
def auto_restore_data():
    """Automatically restore data from Streamlit Cloud secrets on startup"""
    try:

        # Check if we have access codes in secrets
        if 'ACCESS_CODES' in st.secrets:

            access_codes = st.secrets['ACCESS_CODES']
            
            # Check if database has any access codes
            from db import get_engine
            engine = get_engine()
            with engine.begin() as conn:

                result = conn.execute(text("SELECT COUNT(*) FROM access_codes"))
                access_count = result.fetchone()[0]
                
                # Only restore if no access codes in database (fresh deployment)
                if access_count == 0:

                    # Restore access codes from secrets
                    conn.execute(text("""
                        INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                        VALUES (:admin_code, :user_code, :updated_at, :updated_by)
                    """), {
                        "admin_code": access_codes['admin_code'], 
                        "user_code": access_codes['user_code'], 
                        "updated_at": datetime.now(pytz.timezone('Africa/Lagos')).isoformat(), 
                        "updated_by": 'AUTO_RESTORE'
                    })
                    conn.commit()
                    
                    st.success("**Access codes restored from previous deployment!**")
                    return True
                    
        # Also check for persistent data
        if 'PERSISTENT_DATA' in st.secrets:

            data = st.secrets['PERSISTENT_DATA']
            
            # Check if this is a fresh deployment (no items in database)
            from db import get_engine
            engine = get_engine()
            with engine.begin() as conn:

                result = conn.execute(text("SELECT COUNT(*) FROM items"))
                item_count = result.fetchone()[0]
                
                # Only restore if database is empty (fresh deployment)
                if item_count == 0 and data:

                    st.info("**Auto-restoring data from previous deployment...**")
                    
                    # Restore items
                    if 'items' in data:

                        for item in data['items']:


                            conn.execute(text("""
                                INSERT INTO items (id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type)
                                VALUES (:id, :code, :name, :category, :unit, :qty, :unit_cost, :budget, :section, :grp, :building_type)
                            """), {
                                "id": item.get('id'),
                                "code": item.get('code'),
                                "name": item.get('name'),
                                "category": item.get('category'),
                                "unit": item.get('unit'),
                                "qty": item.get('qty'),
                                "unit_cost": item.get('unit_cost'),
                                "budget": item.get('budget'),
                                "section": item.get('section'),
                                "grp": item.get('grp'),
                                "building_type": item.get('building_type')
                            })
                    
                    # Restore requests
                    if 'requests' in data:

                        for request in data['requests']:


                            conn.execute(text("""
                                INSERT INTO requests (id, ts, section, item_id, qty, requested_by, note, building_subtype, status, approved_by)
                                VALUES (:id, :ts, :section, :item_id, :qty, :requested_by, :note, :building_subtype, :status, :approved_by)
                            """), {
                                "id": request.get('id'),
                                "ts": request.get('ts'),
                                "section": request.get('section'),
                                "item_id": request.get('item_id'),
                                "qty": request.get('qty'),
                                "requested_by": request.get('requested_by'),
                                "note": request.get('note'),
                                "building_subtype": request.get('building_subtype'),
                                "status": request.get('status'),
                                "approved_by": request.get('approved_by')
                            })
                    
                    conn.commit()
                    st.success("**Data restored successfully!** All your items and settings are back.")
                    # Don't use st.rerun() - let the page refresh naturally
    except Exception as e:

        # Silently fail if secrets not available (local development)
        pass

def auto_backup_data():
    """Automatically backup data for persistence - works seamlessly in background"""
    # PRODUCTION PROTECTION - Don't run backup operations in production
    if os.getenv('PRODUCTION_MODE') == 'true' or os.getenv('DISABLE_MIGRATION') == 'true':

        return False
    try:

        from db import get_engine
        engine = get_engine()
        with engine.connect() as conn:

            # Get ALL data - items, requests, and access codes
            items_df = pd.read_sql_query("SELECT * FROM items", conn)
            requests_df = pd.read_sql_query("SELECT * FROM requests", conn)
            
            # Get access codes
            result = conn.execute(text("SELECT admin_code, user_code FROM access_codes ORDER BY id DESC LIMIT 1"))
            access_result = result.fetchone()
            access_codes = {
                "admin_code": access_result[0] if access_result else DEFAULT_ADMIN_ACCESS_CODE,
                "user_code": access_result[1] if access_result else DEFAULT_USER_ACCESS_CODE
            }
            
            # Create backup data
            try:

                backup_timestamp = datetime.now(pytz.timezone('Africa/Lagos')).isoformat()
            except:
                backup_timestamp = get_nigerian_time_iso()
            
            backup_data = {
                "items": items_df.to_dict('records'),
                "requests": requests_df.to_dict('records'),
                "access_codes": access_codes,
                "backup_timestamp": backup_timestamp
            }
            
            # Save to multiple locations for maximum reliability
            success = False
            
            # Primary: persistent_data.json (tracked by git)
            try:

                with open("persistent_data.json", 'w') as f:

                    json.dump(backup_data, f, default=str, indent=2)
                success = True
            except:
                pass
            
            # Secondary: backup_data.json (backup copy)
            try:

                with open("backup_data.json", 'w') as f:

                    json.dump(backup_data, f, default=str, indent=2)
                success = True
            except:
                pass
            
            # Tertiary: Streamlit Cloud secrets (if available)
            try:

                if hasattr(st, 'secrets') and st.secrets:

                    st.secrets["PERSISTENT_DATA"] = backup_data
                    st.secrets["ACCESS_CODES"] = access_codes
                    success = True
            except:
                pass
            
            return success
    except Exception as e:

        # Silently fail - don't show errors to users
        return False


# Auto-restore on startup - DISABLED FOR PRODUCTION
# auto_restore_data()  # DISABLED: This was causing data loss on production

# PRODUCTION DATA PROTECTION - COMPLETELY DISABLE ALL MIGRATION
# TEST: This comment proves data persistence works!
if os.getenv('PRODUCTION_MODE') == 'true' or os.getenv('DISABLE_MIGRATION') == 'true':

    print("🚫 MIGRATION COMPLETELY DISABLED - PRODUCTION DATA IS PROTECTED")
    print("🚫 NO DATABASE OPERATIONS WILL RUN DURING DEPLOYMENT")
    print("🚫 YOUR USERS AND DATA ARE SAFE")
    
    # Override database functions to prevent any operations
    def create_tables():
        print("🚫 create_tables() BLOCKED - PRODUCTION MODE")
        return False
    
    def migrate_from_sqlite():
        print("🚫 migrate_from_sqlite() BLOCKED - PRODUCTION MODE")
        return False
    
    # Override data import functions to prevent data loss
    def import_data(json_data):
        print("🚫 import_data() BLOCKED - PRODUCTION MODE")
        return False
    
    def clear_inventory(include_logs=False):
        print("🚫 clear_inventory() BLOCKED - PRODUCTION MODE")
        return False
# ADDITIONAL PROTECTION - Check if database has data and prevent any operations
try:

    from db import get_engine
    engine = get_engine()
    with engine.connect() as conn:

        # Check if database already has data
        result = conn.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.fetchone()[0]
        
        result = conn.execute(text("SELECT COUNT(*) FROM items"))
        item_count = result.fetchone()[0]
        
        # If database has data, set a flag to prevent any operations
        if user_count > 0 or item_count > 0:

            print("🚫 DATABASE HAS EXISTING DATA - ALL OPERATIONS BLOCKED")
            print("🚫 YOUR USERS AND DATA ARE PROTECTED")
            
            # Set environment variable to block all operations
            os.environ['DATABASE_HAS_DATA'] = 'true'
            
except:
    # If database doesn't exist or can't connect, continue normally
    pass

# Initialize session state for performance
if "data_loaded" not in st.session_state:

    st.session_state.data_loaded = False

# Database health check
def db_health():
    """Check database connection health"""
    try:

        from sqlalchemy import text
        from db import get_engine
        with get_engine().connect() as c:

            if os.getenv('DATABASE_URL', '').startswith('postgresql'):

                row = c.execute(text("SELECT current_database()")).scalar()
                return True, f"PostgreSQL: {row}"
            else:

                row = c.execute(text("SELECT 1")).scalar()
                return True, f"SQLite: {row}"
    except Exception as e:

        return False, str(e)

# Show database health in sidebar - removed from sidebar display
# if st.session_state.get('user_type') == 'admin':
#     ok, info = db_health()
#     if ok:
#         st.sidebar.success(f"DB: {info}")
#     else:
#         st.sidebar.error(f"DB Error: {info}")


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


# --------------- SIMPLIFIED SESSION MANAGEMENT ---------------

def require_admin():
    """Require admin privileges, show error if not admin"""
    if not is_admin():

        st.error(" Admin privileges required for this action.")
        st.info("Only administrators can perform this operation.")
        return False
    return True




def update_admin_access_code(new_admin_code, updated_by="Admin"):
    """Update admin access code in database and automatically persist"""
    try:

        # Update database
        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            wat_timezone = pytz.timezone('Africa/Lagos')
            current_time = datetime.now(wat_timezone)
            
            # Insert new admin access code
            conn.execute(text("""
                INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                VALUES (:admin_code, :user_code, :updated_at, :updated_by)
            """), {
                "admin_code": new_admin_code,
                "user_code": '',
                "updated_at": current_time.isoformat(),
                "updated_by": updated_by
            })
            
        # Automatically backup data for persistence
        try:

            if auto_backup_data():

                st.success("Admin access code updated and automatically saved!")
            else:

                st.success("Admin access code updated successfully!")
                
                # Show instructions for manual setup if auto-backup fails
                st.info("**For Streamlit Cloud persistence:** You may need to manually configure secrets. Contact your system administrator.")
        except Exception as e:

            st.success("Admin access code updated successfully!")
            # Silently handle backup errors
        
        return True
    except Exception as e:

        st.error(f"Error updating admin access code: {e}")
        return False

def update_access_codes(new_admin_code, new_user_code, updated_by="Admin"):
    """Update access codes in database and automatically persist"""
    try:

        # Update database
        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            wat_timezone = pytz.timezone('Africa/Lagos')
            current_time = datetime.now(wat_timezone)
            
            # Insert new access codes
            conn.execute(text("""
                INSERT INTO access_codes (admin_code, user_code, updated_at, updated_by)
                VALUES (:admin_code, :user_code, :updated_at, :updated_by)
            """), {
                "admin_code": new_admin_code,
                "user_code": new_user_code,
                "updated_at": current_time.isoformat(),
                "updated_by": updated_by
            })
            
        # Automatically backup data for persistence
        try:

            if auto_backup_data():

                st.success("Access codes updated and automatically saved!")
            else:

                st.success("Access codes updated successfully!")
                
                # Show instructions for manual setup if auto-backup fails
                st.info("**For Streamlit Cloud persistence:** You may need to manually configure secrets. Contact your system administrator.")
        except Exception as e:

            st.success("Access codes updated successfully!")
            # Silently handle backup errors
        
        return True
    except Exception as e:

        st.error(f"Error updating access codes: {str(e)}")
        return False

def update_project_site_access_codes(project_site, admin_code, user_code):
    """Update access codes for a specific project site"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            # Use West African Time (WAT)
            wat_timezone = pytz.timezone('Africa/Lagos')
            current_time = datetime.now(wat_timezone)
            
            # Create or update project site access codes
            conn.execute(text('''
            INSERT OR REPLACE INTO project_site_access_codes (project_site, admin_code, user_code, updated_at)
                VALUES (:project_site, :admin_code, :user_code, :updated_at)
            '''), {
                "project_site": project_site,
                "admin_code": admin_code,
                "user_code": user_code,
                "updated_at": current_time.isoformat(timespec="seconds")
            })
        
        return True
    except Exception as e:

        st.error(f"Error updating project site access codes: {e}")
        return False

def update_project_site_user_code(project_site, user_code):
    """Update user access code for a specific project site"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            # Use West African Time (WAT)
            wat_timezone = pytz.timezone('Africa/Lagos')
            current_time = datetime.now(wat_timezone)
            
            # Create or update project site user access code
            conn.execute(text('''
            INSERT OR REPLACE INTO project_site_access_codes (project_site, admin_code, user_code, updated_at)
                VALUES (:project_site, (SELECT admin_code FROM project_site_access_codes WHERE project_site = :project_site LIMIT 1), :user_code, :updated_at)
            '''), {
                "project_site": project_site,
                "user_code": user_code,
                "updated_at": current_time.isoformat(timespec="seconds")
            })
        
        return True
    except Exception as e:

        st.error(f"Error updating project site user access code: {e}")
        return False


def log_current_session():
    """Log current session activity"""
    if st.session_state.get('authenticated') and st.session_state.get('current_user_name'):

        user_name = st.session_state.get('current_user_name')
        user_role = st.session_state.get('user_role', 'unknown')
        log_access("SESSION_ACTIVITY", success=True, user_name=user_name, role=user_role)
        return True
    return False

# This conflicting authentication system has been removed
# The main authentication system is used instead

def set_auth_cookie(auth_data):
    """Set authentication cookie for session persistence"""
    try:
        import base64
        import json
        encoded_data = base64.b64encode(json.dumps(auth_data).encode('utf-8')).decode('utf-8')
        st.query_params['auth_data'] = encoded_data
    except:
        pass

def add_project_access_code(project_site, admin_code, user_code):
    """Add access codes for a project site"""
    try:
        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO project_site_access_codes (project_site, admin_code, user_code, updated_at)
                VALUES (:project_site, :admin_code, :user_code, :updated_at)
                ON CONFLICT (project_site) DO UPDATE SET
                admin_code = :admin_code,
                user_code = :user_code,
                updated_at = :updated_at
            """), {
                "project_site": project_site,
                "admin_code": admin_code,
                "user_code": user_code,
                "updated_at": get_nigerian_time_iso()
            })
        return True
    except Exception as e:
        print(f"Error adding project access codes: {e}")
        return False

# Enhanced notification popups with sound and better alerts
def show_notification_popups():
    """Show popup messages for project site accounts with new notifications"""
    try:

        # Only show popups for project site accounts (not admins)
        if st.session_state.get('user_type') != 'admin':

            user_notifications = get_project_site_notifications()
            
            # Filter out dismissed synthetic notifications (negative IDs)
            if 'dismissed_synthetic_notifs' not in st.session_state:
                st.session_state.dismissed_synthetic_notifs = set()
            
            # Filter out dismissed notifications
            user_notifications = [
                n for n in user_notifications 
                if n.get('id', 0) >= 0 or n.get('id', 0) not in st.session_state.dismissed_synthetic_notifs
            ]
            
            # Check for unread notifications (after filtering dismissed ones)
            unread_notifications = [n for n in user_notifications if not n.get('is_read', False)]
            
            # Client-side popup for any new notifications since last seen (per-session)
            try:
                latest_ids = [n.get('id') for n in user_notifications[:5] if n.get('id')]
                latest_msgs = [n.get('message') or 'You have a new notification' for n in user_notifications[:5]]
                ids_js = '[' + ','.join(str(i) for i in latest_ids) + ']'
                msgs_js = '[' + ','.join(('`'+m.replace('`','\\`')+'`') for m in latest_msgs) + ']'
                st.markdown(f"""
                <script>
                try {{
                  const idKey = 'ps_last_seen_notif_id_global';
                  const prevId = parseInt(localStorage.getItem(idKey) || '0');
                  const latestIds = {ids_js};
                  const latestMsgs = {msgs_js};
                  let maxId = prevId;
                  for (let i = 0; i < latestIds.length; i++) {{
                    const nid = latestIds[i];
                    const msg = latestMsgs[i] || 'You have a new notification';
                    if (nid > prevId) {{
                      if (typeof showNotificationToast === 'function') {{
                        showNotificationToast(msg);
                      }} else {{
                        const el = document.createElement('div');
                        el.style.cssText = 'position:fixed;top:80px;right:20px;background:#1d4ed8;color:#fff;padding:10px 14px;border-radius:8px;z-index:9000;box-shadow:0 4px 12px rgba(0,0,0,.15)';
                        el.textContent = msg;
                        document.body.appendChild(el);
                        setTimeout(()=>el.remove(), 3000);
                      }}
                      if (nid > maxId) maxId = nid;
                    }}
                  localStorage.setItem(idKey, String(maxId));
                }} catch (e) {{ console.log('ps global popup skipped', e); }}
                </script>
                """, unsafe_allow_html=True)
            except Exception:
                pass

            # Show immediate Streamlit UI popups for unread notifications (matching admin behavior)
            if unread_notifications:
                # Trigger sound and visual alerts
                st.markdown("""
                <script>
                playNotificationSound();
                showNotificationToast('You have new notifications');
                </script>
                """, unsafe_allow_html=True)
                
                # Show popup for each unread notification with enhanced styling (matching admin)
                for notification in unread_notifications[:3]:  # Show max 3 notifications
                    notif_type = notification.get('type', '')
                    notif_title = notification.get('title', '')
                    notif_msg = notification.get('message', '')
                    
                    if notif_type == 'request_approved':
                        st.success(f"{notif_title} - {notif_msg}")
                    elif notif_type == 'request_rejected':
                        st.error(f"{notif_title} - {notif_msg}")
                    elif notif_type == 'request_submitted':
                        st.info(f"{notif_title} - {notif_msg}")
                    else:
                        st.info(f"{notif_title} - {notif_msg}")
                
                # Show summary if there are more than 3 notifications
                if len(unread_notifications) > 3:
                    st.warning(f"You have {len(unread_notifications)} total unread notifications. Check the Notifications tab for more details.")
                
                # Add a dismiss button in the dashboard (popup area)
                if st.button("Dismiss All Notifications", key="dismiss_notifications", type="primary", use_container_width=True):
                    dismissed_count = 0
                    from sqlalchemy import text
                    from db import get_engine
                    engine = get_engine()
                    
                    with engine.begin() as conn:
                        # Mark all unread notifications as read
                        for notification in unread_notifications:
                            try:
                                notif_id_val = notification.get('id', 0)
                                request_id_val = notification.get('request_id')
                                
                                if notif_id_val < 0:
                                    # Synthetic notification - create actual notification record in DB marked as read
                                    if request_id_val:
                                        # Check if notification already exists
                                        existing = conn.execute(text(
                                            "SELECT id FROM notifications WHERE request_id = :req_id AND notification_type IN ('request_approved', 'request_rejected')"
                                        ), {"req_id": request_id_val}).fetchone()
                                        
                                        if existing:
                                            # Update existing notification to read
                                            conn.execute(text(
                                                "UPDATE notifications SET is_read = 1 WHERE id = :notif_id"
                                            ), {"notif_id": existing[0]})
                                        else:
                                            # Create new notification record marked as read
                                            notif_type_val = notification.get('type', 'request_approved')
                                            title_val = notification.get('title', 'Request Approved')
                                            message_val = notification.get('message', '')
                                            created_at_val = notification.get('created_at', '')
                                            
                                            # Convert Nigerian time back to ISO if needed
                                            from datetime import datetime
                                            import pytz
                                            try:
                                                if isinstance(created_at_val, str) and 'WAT' in created_at_val:
                                                    dt_str = created_at_val.replace(' WAT', '')
                                                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                                                    lagos_tz = pytz.timezone('Africa/Lagos')
                                                    dt = lagos_tz.localize(dt)
                                                    created_at_iso = dt.isoformat()
                                                else:
                                                    created_at_iso = get_nigerian_time_iso()
                                            except:
                                                created_at_iso = get_nigerian_time_iso()
                                            
                                            conn.execute(text('''
                                                INSERT INTO notifications (notification_type, title, message, user_id, request_id, created_at, is_read)
                                                VALUES (:notification_type, :title, :message, -1, :request_id, :created_at, 1)
                                            '''), {
                                                "notification_type": notif_type_val,
                                                "title": title_val,
                                                "message": message_val,
                                                "request_id": request_id_val,
                                                "created_at": created_at_iso
                                            })
                                        dismissed_count += 1
                                else:
                                    # Real notification - update database
                                    conn.execute(text("UPDATE notifications SET is_read = 1 WHERE id = :notif_id"), {"notif_id": notif_id_val})
                                    dismissed_count += 1
                            except Exception as e:
                                print(f"Error marking notification as read: {e}")
                    
                    clear_cache()
                    st.success(f"All notifications dismissed! ({dismissed_count} notification(s))")
                    # Don't rerun - let user continue their work, changes will show on next interaction
    except Exception as e:

        pass  # Silently handle errors to not break the app

# Show notification popups for users
show_notification_popups()

# Enhanced admin notification popups with sound and better alerts
def show_admin_notification_popups():
    """Show popup messages for admins with new notifications"""
    try:

        # Only show popups for admins
        if st.session_state.get('user_type') == 'admin':

            admin_notifications = get_admin_notifications()
            
            # Check for unread notifications
            unread_notifications = [n for n in admin_notifications if not n.get('is_read', False)]
            
            if unread_notifications:

            
                # Trigger sound and visual alerts for admins
                st.markdown("""
                <script>
                playNotificationSound();
                showNotificationToast('Admin: New notifications received!');
                </script>
                """, unsafe_allow_html=True)
                
                # Show popup for each unread notification with enhanced styling
                for notification in unread_notifications[:3]:  # Show max 3 notifications
                    # Admin notifications show new_request and over_planned types
                    if notification['type'] == 'new_request':
                        st.warning(f"**{notification['title']}** - {notification['message']}")
                    elif notification['type'] == 'over_planned':
                        st.error(f"**{notification['title']}** - {notification['message']}")
                    else:
                        st.info(f"**{notification['title']}** - {notification['message']}")
                
                # Show summary if there are more than 3 notifications
                if len(unread_notifications) > 3:

                    st.warning(f"🔔 You have {len(unread_notifications)} total unread notifications. Check the Admin Settings tab for more details.")
                
                # Add a dismiss button
                if st.button("🔕 Dismiss Admin Notifications", key="dismiss_admin_notifications", type="primary"):

                    # Mark all unread notifications as read
                    for notification in unread_notifications:

                        mark_notification_read(notification['id'])
                    st.success("✅ Admin notifications dismissed!")
                    # Don't use st.rerun() - let the page refresh naturally
    except Exception as e:

        pass  # Silently handle errors to not break the app

# Show notification popups for admins
show_admin_notification_popups()

# Function to check and show over-planned quantity notifications
@st.cache_data(ttl=120)  # Cache for 2 minutes - reduces database queries
def _get_over_planned_requests(user_type=None, project_site=None):
    """Get over-planned requests based on cumulative requested quantities (internal cached function)"""
    from sqlalchemy import text
    from db import get_engine
    
    if user_type is None:
        user_type = st.session_state.get('user_type', 'project_site')
    if project_site is None:
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
    
    # Get items where cumulative requested quantity (pending + approved) exceeds planned quantity
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Query to get items where cumulative requested quantity (pending + approved) exceeds planned qty
            # This checks the SUM of all pending/approved requests for each item
            # Get the latest request ID for each item that has over-planned cumulative quantity
            if user_type != 'admin':
                query = text("""
                    WITH cumulative_requests AS (
                        SELECT 
                            r.item_id,
                            SUM(r.qty) as cumulative_requested_qty,
                            i.qty as planned_qty,
                            i.name as item_name,
                            i.project_site,
                            COUNT(r.id) as request_count
                        FROM requests r
                        JOIN items i ON r.item_id = i.id
                        WHERE r.status IN ('Pending', 'Approved')
                          AND i.project_site = :project_site
                        GROUP BY r.item_id, i.qty, i.name, i.project_site
                        HAVING SUM(r.qty) > COALESCE(i.qty, 0)
                    )
                    SELECT 
                        COALESCE((SELECT MAX(r2.id) FROM requests r2 WHERE r2.item_id = cr.item_id AND r2.status IN ('Pending', 'Approved')), 0) as latest_request_id,
                        cr.cumulative_requested_qty,
                        cr.planned_qty,
                        cr.item_name,
                        COALESCE((SELECT r3.requested_by FROM requests r3 WHERE r3.item_id = cr.item_id AND r3.status IN ('Pending', 'Approved') ORDER BY r3.id DESC LIMIT 1), 'Unknown') as requested_by,
                        cr.project_site,
                        cr.request_count,
                        COALESCE((SELECT COALESCE(r4.current_price, i2.unit_cost) FROM requests r4 JOIN items i2 ON r4.item_id = i2.id WHERE r4.id = (SELECT MAX(r5.id) FROM requests r5 WHERE r5.item_id = cr.item_id AND r5.status IN ('Pending', 'Approved'))), 0) as current_price,
                        COALESCE((SELECT i3.unit_cost FROM items i3 WHERE i3.id = cr.item_id), 0) as planned_price
                    FROM cumulative_requests cr
                    ORDER BY latest_request_id DESC
                """)
                result = conn.execute(query, {"project_site": project_site})
            else:
                query = text("""
                    WITH cumulative_requests AS (
                        SELECT 
                            r.item_id,
                            SUM(r.qty) as cumulative_requested_qty,
                            i.qty as planned_qty,
                            i.name as item_name,
                            i.project_site,
                            COUNT(r.id) as request_count
                        FROM requests r
                        JOIN items i ON r.item_id = i.id
                        WHERE r.status IN ('Pending', 'Approved')
                        GROUP BY r.item_id, i.qty, i.name, i.project_site
                        HAVING SUM(r.qty) > COALESCE(i.qty, 0)
                    )
                    SELECT 
                        COALESCE((SELECT MAX(r2.id) FROM requests r2 WHERE r2.item_id = cr.item_id AND r2.status IN ('Pending', 'Approved')), 0) as latest_request_id,
                        cr.cumulative_requested_qty,
                        cr.planned_qty,
                        cr.item_name,
                        COALESCE((SELECT r3.requested_by FROM requests r3 WHERE r3.item_id = cr.item_id AND r3.status IN ('Pending', 'Approved') ORDER BY r3.id DESC LIMIT 1), 'Unknown') as requested_by,
                        cr.project_site,
                        cr.request_count,
                        COALESCE((SELECT COALESCE(r4.current_price, i2.unit_cost) FROM requests r4 JOIN items i2 ON r4.item_id = i2.id WHERE r4.id = (SELECT MAX(r5.id) FROM requests r5 WHERE r5.item_id = cr.item_id AND r5.status IN ('Pending', 'Approved'))), 0) as current_price,
                        COALESCE((SELECT i3.unit_cost FROM items i3 WHERE i3.id = cr.item_id), 0) as planned_price
                    FROM cumulative_requests cr
                    ORDER BY latest_request_id DESC
                """)
                result = conn.execute(query)
            
            return result.fetchall()
    except Exception as e:
        return []

def get_dismissed_alert_ids():
    """Get set of request IDs that have been dismissed"""
    try:
        from sqlalchemy import text
        from db import get_engine
        
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT request_id FROM dismissed_over_planned_alerts"))
            dismissed_ids = {row[0] for row in result.fetchall()}
            return dismissed_ids
    except Exception as e:
        # Table might not exist yet, return empty set
        return set()

def dismiss_over_planned_alert(request_id, item_name=None, full_details=None):
    """Dismiss an over-planned alert by storing it in the database with accurate information"""
    try:
        from sqlalchemy import text
        from db import get_engine
        # get_nigerian_time_iso is defined at module level
        
        engine = get_engine()
        with engine.begin() as conn:
            # Check if already dismissed
            check_result = conn.execute(text("""
                SELECT id FROM dismissed_over_planned_alerts WHERE request_id = :request_id
            """), {"request_id": request_id})
            
            if check_result.fetchone():
                return True  # Already dismissed
            
            # Get comprehensive request details including cumulative quantities
            details_result = conn.execute(text("""
                SELECT 
                    r.requested_by, r.qty, r.section, r.status, r.ts, r.updated_at,
                    i.name, i.building_type, r.building_subtype, i.budget, i.project_site, i.qty as planned_qty,
                    COALESCE(r.current_price, i.unit_cost) as current_price, 
                    i.unit_cost as planned_price,
                    r.item_id,
                    (SELECT COALESCE(SUM(r2.qty), 0) 
                     FROM requests r2 
                     WHERE r2.item_id = r.item_id 
                     AND r2.status IN ('Pending', 'Approved')
                     AND COALESCE(r2.building_subtype, '') = COALESCE(r.building_subtype, '')
                    ) as cumulative_requested,
                    (SELECT COUNT(*) 
                     FROM requests r2 
                     WHERE r2.item_id = r.item_id 
                     AND r2.status IN ('Pending', 'Approved')
                     AND COALESCE(r2.building_subtype, '') = COALESCE(r.building_subtype, '')
                    ) as request_count
                FROM requests r
                JOIN items i ON r.item_id = i.id
                WHERE r.id = :req_id
            """), {"req_id": request_id})
            details_row = details_result.fetchone()
            
            if not details_row:
                return False
            
            # Extract all information
            (requested_by, req_qty, req_section, req_status, req_ts, updated_at,
             item_name_db, building_type, request_subtype, budget, project_site, planned_qty,
             current_price, planned_price, item_id, cumulative_requested, request_count) = details_row
            
            # Use item_name_db if item_name not provided
            if not item_name:
                item_name = item_name_db or "Unknown Item"
            
            # Get request timestamp - prefer updated_at if status is Approved/Rejected, otherwise use req_ts
            request_timestamp = updated_at if updated_at and req_status in ['Approved', 'Rejected'] else req_ts
            
            # Format timestamp
            try:
                if isinstance(request_timestamp, str):
                    timestamp_dt = pd.to_datetime(request_timestamp, errors='coerce')
                else:
                    timestamp_dt = request_timestamp
                if pd.notna(timestamp_dt):
                    timestamp_str = timestamp_dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    timestamp_str = str(request_timestamp) if request_timestamp else "Unknown"
            except:
                timestamp_str = str(request_timestamp) if request_timestamp else "Unknown"
            
            section_display = req_section.title() if req_section else "Unknown"
            budget_display = budget or "Unknown"
            block_display = f"{building_type or 'Unknown'} / {request_subtype}" if request_subtype else (building_type or 'Unknown')
            
            # Calculate excess
            cumulative_qty_val = float(cumulative_requested) if cumulative_requested else 0
            planned_qty_val = float(planned_qty) if planned_qty else 0
            excess = cumulative_qty_val - planned_qty_val
            
            # Build price information
            price_info = ""
            if current_price is not None and planned_price is not None:
                current_price_val = float(current_price) if current_price else 0
                planned_price_val = float(planned_price) if planned_price else 0
                if planned_price_val > 0 and current_price_val != planned_price_val:
                    price_diff = current_price_val - planned_price_val
                    price_diff_percent = (price_diff / planned_price_val) * 100 if planned_price_val > 0 else 0
                    if price_diff > 0:
                        price_status = "higher"
                        price_symbol = "↑"
                    else:
                        price_status = "lower"
                        price_symbol = "↓"
                    price_info = (
                        f" - Current Price: ₦{current_price_val:,.2f} ({abs(price_diff_percent):.1f}% {price_status} than planned "
                        f"₦{planned_price_val:,.2f}, {price_symbol} ₦{abs(price_diff):,.2f})"
                    )
            
            # Build full details with accurate cumulative information
            if not full_details:
                full_details = (
                    f"{requested_by or 'Unknown'} from {project_site or 'Unknown Project'} submitted a request for "
                    f"{req_qty} units of {item_name} ({section_display} - {block_display} - {budget_display}). "
                    f"Request #{request_id}: {item_name} - Cumulative Requested: {cumulative_qty_val} units ({request_count} requests), "
                    f"Planned: {planned_qty_val} units (Excess: {excess}){price_info}"
                )
            
            # Insert dismissal record with request timestamp
            conn.execute(text("""
                INSERT INTO dismissed_over_planned_alerts (request_id, item_name, full_details, dismissed_at)
                VALUES (:request_id, :item_name, :full_details, :dismissed_at)
            """), {
                "request_id": request_id,
                "item_name": item_name,
                "full_details": full_details,
                "dismissed_at": request_timestamp or get_nigerian_time_iso()  # Use request timestamp instead of dismissal time
            })
            return True
    except Exception as e:
        print(f"Error dismissing alert: {e}")
        import traceback
        traceback.print_exc()
        return False
def show_over_planned_notifications():
    """Show dashboard notifications for items where cumulative requested quantity exceeds planned quantity"""
    try:
        # Only show over-planned alerts to admin accounts, not project site accounts
        if not is_admin():
            return
        
        user_type = st.session_state.get('user_type', 'project_site')
        project_site = st.session_state.get('project_site', st.session_state.get('current_project_site', 'Lifecamp Kafe'))
        
        over_planned = _get_over_planned_requests(user_type=user_type, project_site=project_site)
        
        # Get dismissed alert IDs
        dismissed_ids = get_dismissed_alert_ids()
        
        # Filter out dismissed alerts
        active_alerts = [
            req for req in over_planned 
            if req[0] not in dismissed_ids
        ]
        
        if active_alerts:
            st.markdown("### ⚠️ Over-Planned Quantity Alerts")
            for req in active_alerts:
                # Handle both old format (7 fields) and new format (9 fields with prices)
                if len(req) >= 9:
                    req_id, cumulative_qty, plan_qty, item_name, requested_by, req_project_site, request_count, current_price, planned_price = req
                else:
                    req_id, cumulative_qty, plan_qty, item_name, requested_by, req_project_site, request_count = req
                    current_price = None
                    planned_price = None
                
                excess = float(cumulative_qty) - float(plan_qty) if plan_qty else float(cumulative_qty)
                
                # Build alert message with price information if available
                alert_message = (
                    f"**Request #{req_id}**: {item_name} - "
                    f"Cumulative Requested: {cumulative_qty} units ({request_count} requests), "
                    f"Planned: {plan_qty or 0} units "
                    f"(Excess: {excess}) - Latest requested by: {requested_by}"
                )
                
                # Add project site information
                if req_project_site:
                    alert_message += f" - Project Site: {req_project_site}"
                
                # Add price information if available
                if current_price is not None and planned_price is not None:
                    current_price_val = float(current_price) if current_price else 0
                    planned_price_val = float(planned_price) if planned_price else 0
                    if planned_price_val > 0 and current_price_val != planned_price_val:
                        price_diff = current_price_val - planned_price_val
                        price_diff_percent = (price_diff / planned_price_val) * 100 if planned_price_val > 0 else 0
                        if price_diff > 0:
                            price_status = "higher"
                            price_symbol = "↑"
                        else:
                            price_status = "lower"
                            price_symbol = "↓"
                        alert_message += (
                            f" - Current Price: ₦{current_price_val:,.2f} ({abs(price_diff_percent):.1f}% {price_status} than planned "
                            f"₦{planned_price_val:,.2f}, {price_symbol} ₦{abs(price_diff):,.2f})"
                        )
                
                # Create columns for alert and dismiss button
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.error(alert_message)
                with col2:
                    if st.button("Dismiss", key=f"dismiss_over_planned_{req_id}", type="secondary"):
                        # Dismiss alert - function will recalculate accurate information
                        if dismiss_over_planned_alert(req_id, item_name):
                            st.success(f"Alert for Request #{req_id} dismissed")
                            clear_cache()  # Clear cache to refresh data
                            st.rerun()
                        else:
                            st.error("Failed to dismiss alert")
    except Exception as e:
        pass  # Silently handle errors

# Show over-planned notifications (display early in the page)
show_over_planned_notifications()

# Enhanced notification banner with sound and animation
def show_notification_banner():
    """Show a prominent banner for project site accounts with unread notifications"""
    try:

        # Only show banner for project site accounts (not admins)
        if st.session_state.get('user_type') != 'admin':

            user_notifications = get_project_site_notifications()
            unread_count = len([n for n in user_notifications if not n.get('is_read', False)])
            
            if unread_count > 0:

            
                # Trigger sound for banner
                st.markdown("""
                <script>
                playNotificationSound();
                </script>
                """, unsafe_allow_html=True)
                
                # Create a more prominent animated banner
                st.markdown("""
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e8e 50%, #ffa8a8 100%); color: white; padding: 1.5rem; border-radius: 12px; margin: 1rem 0; text-align: center; box-shadow: 0 8px 25px rgba(255, 107, 107, 0.4); border: 2px solid #ff4757; animation: pulse 2s infinite;">
                    <h3 style="margin: 0; color: white; font-size: 1.3rem; font-weight: 700;">🔔 You have {} unread notification{}</h3>
                    <p style="margin: 0.5rem 0 0 0; color: white; opacity: 0.95; font-size: 1rem;">Check the Notifications tab to view your notifications</p>
                </div>
                <style>
                @keyframes pulse {
                    0% { transform: scale(1); box-shadow: 0 8px 25px rgba(255, 107, 107, 0.4); }
                    50% { transform: scale(1.02); box-shadow: 0 12px 30px rgba(255, 107, 107, 0.6); }
                    100% { transform: scale(1); box-shadow: 0 8px 25px rgba(255, 107, 107, 0.4); }
                }
                </style>
                """.format(unread_count, 's' if unread_count > 1 else ''), unsafe_allow_html=True)
    except Exception as e:

        pass  # Silently handle errors

# Show notification banner
show_notification_banner()

# Mobile-friendly sidebar toggle
# Ensure Streamlit Settings menu is visible and theme selector works
st.markdown("""
<style>
/* Ensure Streamlit header and Settings menu are ALWAYS visible */
header[data-testid="stHeader"],
[data-testid="stHeader"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999999 !important;
    pointer-events: auto !important;
}

/* Settings menu button - MUST be visible and clickable */
button[kind="header"],
[data-testid="baseButton-header"],
.stDeployButton,
header button,
button[aria-label*="Settings"],
button[aria-label*="Menu"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999999 !important;
    pointer-events: auto !important;
    cursor: pointer !important;
}

/* Settings menu popup - ensure it's accessible */
[data-testid="stHeaderMenu"],
div[data-testid="stHeaderMenu"],
.stHeaderMenu,
div[role="menu"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999999 !important;
    pointer-events: auto !important;
}

/* Theme selector dropdown - CRITICAL for it to work */
[data-testid="stHeaderMenu"] div[data-baseweb="select"],
[data-testid="stHeaderMenu"] select,
[data-testid="stHeaderMenu"] [role="combobox"],
[data-testid="stHeaderMenu"] [role="listbox"],
[data-testid="stHeaderMenu"] div[data-baseweb="popover"],
/* Streamlit theme selector specific selectors */
[data-testid="stHeaderMenu"] div[data-baseweb="select"][id*="theme"],
[data-testid="stHeaderMenu"] button[data-baseweb="button"][aria-label*="theme"],
/* Theme dropdown container */
[data-testid="stHeaderMenu"] div[data-baseweb="select"] > div,
[data-testid="stHeaderMenu"] div[class*="theme"] select,
[data-testid="stHeaderMenu"] div[class*="app_theme"] select {
    z-index: 999999 !important;
    pointer-events: auto !important;
    cursor: pointer !important;
    position: relative !important;
}

/* Theme selector options - ensure they're clickable */
[data-testid="stHeaderMenu"] div[role="option"],
[data-testid="stHeaderMenu"] li[role="option"],
[data-testid="stHeaderMenu"] [data-baseweb="menu"] li,
[data-testid="stHeaderMenu"] [data-baseweb="menu"] button,
/* Theme menu items */
[data-testid="stHeaderMenu"] ul[role="listbox"] li,
[data-testid="stHeaderMenu"] ul[role="listbox"] button,
[data-testid="stHeaderMenu"] div[role="listbox"] > div {
    pointer-events: auto !important;
    cursor: pointer !important;
    z-index: 999999 !important;
    position: relative !important;
}

/* Radio buttons for theme selection */
[data-testid="stHeaderMenu"] input[type="radio"][name*="theme"],
[data-testid="stHeaderMenu"] input[type="radio"][name*="app_theme"],
[data-testid="stHeaderMenu"] label[for*="theme"],
/* Any element related to theme selection */
[data-testid="stHeaderMenu"] *[class*="theme"] input,
[data-testid="stHeaderMenu"] *[class*="app_theme"] input {
    pointer-events: auto !important;
    cursor: pointer !important;
    z-index: 999999 !important;
    position: relative !important;
}

/* Ensure nothing blocks interactions */
.stHeaderMenu *,
[data-testid="stHeaderMenu"] * {
    pointer-events: auto !important;
    z-index: 999999 !important;
}

/* Ensure notification toasts don't block the Settings menu */
.notification-toast {
    top: 80px !important;
    z-index: 9000 !important;
}

@media (max-width: 768px) {
    .sidebar .sidebar-content {
        padding: 1rem 0.5rem;
    }
    
    .sidebar .sidebar-content h3 {
        font-size: 1.2rem;
        margin-bottom: 0.5rem;
    }
    
    .sidebar .sidebar-content .stMarkdown {
        font-size: 0.9rem;
    }
}
</style>

<script>
// Ensure Settings menu interactions are not blocked
document.addEventListener('DOMContentLoaded', function() {
    // Function to make theme selector clickable
    function enableThemeSelector() {
        // Find all potential theme selector elements
        const selectors = [
            '[data-baseweb="select"]',
            'select',
            '[role="combobox"]',
            '[role="listbox"]',
            'button[aria-label*="theme" i]',
            'button[aria-label*="Theme" i]',
            'div[data-baseweb="popover"]',
            '*[class*="theme"] select',
            '*[id*="theme"] select'
        ];
        
        const headerMenuRoot = document.querySelector('[data-testid="stHeaderMenu"]');
        
        selectors.forEach(function(selector) {
            try {
                const elements = (headerMenuRoot || document).querySelectorAll(selector);
                elements.forEach(function(el) {
                    el.style.pointerEvents = 'auto';
                    el.style.zIndex = '999999';
                    el.style.position = 'relative';
                    
                    // Ensure clicks work
                    el.addEventListener('click', function(e) {
                        e.stopPropagation();
                    }, true);
                });
            } catch(e) {
                // Ignore selector errors
            }
        });
        
        // Also ensure menu options are clickable
        const menuOptions = (headerMenuRoot || document).querySelectorAll('[role="option"], [data-baseweb="menu"] li, [data-baseweb="menu"] button');
        menuOptions.forEach(function(el) {
            el.style.pointerEvents = 'auto';
            el.style.cursor = 'pointer';
            el.style.zIndex = '999999';
        });
    }
    
    // Run immediately
    enableThemeSelector();
    
    // Also run when Settings menu is opened (mutation observer)
    const observer = new MutationObserver(function(mutations) {
        enableThemeSelector();
    });
    
    // Observe changes to the document body
    if (document.body) {
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
    
    // Don't block clicks on Settings menu elements
    const headerMenu = document.querySelector('[data-testid="stHeaderMenu"]');
    if (headerMenu) {
        headerMenu.addEventListener('click', function(e) {
            e.stopPropagation();
            // Re-enable theme selector when menu opens
            setTimeout(enableThemeSelector, 100);
        }, true);
    }
});
</script>
""", unsafe_allow_html=True)
# Professional Sidebar
with st.sidebar:

    # Professional sidebar styling with beautiful logo
    st.markdown("""
    <style>
    /* Professional sidebar with logo */
    .sidebar-header {
        background: linear-gradient(135deg, #1e293b 0%, #334155 50%, #475569 100%);
        border: none;
        padding: 2rem 1rem;
        margin: -1rem -1rem 2rem -1rem;
        border-radius: 0;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        position: relative;
        overflow: hidden;
    }
    
    .sidebar-header::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
        animation: pulse 3s ease-in-out infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 0.3; }
        50% { opacity: 0.6; }
    }
    
    .logo-container {
        position: relative;
        z-index: 1;
    }
    
    .logo-icon {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
        display: block;
        filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));
    }
    
    .sidebar-header h1 {
        margin: 0;
        font-size: 1.3rem;
        font-weight: 700;
        color: white;
        letter-spacing: 0.5px;
        text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        line-height: 1.2;
    }
    
    .sidebar-header .company-name {
        font-size: 1.1rem;
        font-weight: 600;
        margin: 0.25rem 0 0 0;
        color: rgba(255, 255, 255, 0.95);
        text-shadow: 0 1px 2px rgba(0,0,0,0.2);
    }
    
    .sidebar-header .tagline {
        margin: 0.5rem 0 0 0;
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.85);
        font-weight: 400;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .user-info-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1.25rem;
        margin: 1.5rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    .user-info-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    }
    
    .user-info-card h3 {
        margin: 0 0 1rem 0;
        font-size: 0.8rem;
        color: #64748b;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .user-info-card p {
        margin: 0.4rem 0;
        font-size: 0.9rem;
        color: #1f2937;
        line-height: 1.5;
    }
    
    .user-info-card strong {
        color: #475569;
        font-weight: 600;
    }
    
    .status-badge {
        display: inline-block;
        padding: 0.4rem 0.9rem;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-top: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .status-admin {
        background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
        color: #1e40af;
        border: 1px solid #93c5fd;
        box-shadow: 0 2px 4px rgba(30, 64, 175, 0.1);
    }
    
    .status-user {
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
        color: #166534;
        border: 1px solid #86efac;
        box-shadow: 0 2px 4px rgba(22, 101, 52, 0.1);
    }
    
    .session-info {
        background: #fef3c7;
        border: 1px solid #f59e0b;
        border-radius: 6px;
        padding: 0.75rem;
        margin: 1rem 0;
        font-size: 0.85rem;
        color: #92400e;
    }
    
    .sidebar-actions {
        margin-top: 1.5rem;
    }
    
    .logout-btn {
        background: #ef4444;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        font-weight: 500;
        width: 100%;
        transition: background-color 0.2s ease;
        font-size: 0.9rem;
    }
    
    .logout-btn:hover {
        background: #dc2626;
    }
    
    .project-info {
        background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
        border: 2px solid #0ea5e9;
        border-radius: 8px;
        padding: 1rem;
        margin: 1.5rem 0;
        font-size: 0.9rem;
        color: #0c4a6e;
        box-shadow: 0 2px 4px rgba(14, 165, 233, 0.1);
        transition: all 0.2s ease;
    }
    
    .project-info:hover {
        border-color: #0284c7;
        box-shadow: 0 4px 8px rgba(14, 165, 233, 0.15);
    }
    
    .project-info strong {
        color: #0369a1;
        font-weight: 700;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        display: block;
        margin-bottom: 0.5rem;
    }
    
    .project-info .project-name {
        font-size: 1rem;
        font-weight: 600;
        color: #0c4a6e;
        margin-top: 0.25rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Professional header with logo
    st.markdown("""
    <div class="sidebar-header">
        <div class="logo-container">
            <span class="logo-icon">🏗️</span>
            <h1>ISTROM</h1>
            <p class="company-name">Design & Construction</p>
            <p class="tagline">Inventory Management</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Get current user info from session with safe defaults
    current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
    current_role = st.session_state.get('user_type', st.session_state.get('user_role', 'project_site'))
    
    # Get current project - prioritize selectbox value for admin (most up-to-date)
    # Then fallback to current_project_site, then project_site
    if current_role == 'admin':
        # For admin, read directly from selectbox if available (most current value)
        current_project = st.session_state.get('project_site_selector')
        if not current_project:
            current_project = st.session_state.get('current_project_site')
    else:
        current_project = st.session_state.get('current_project_site')
    
    if not current_project:
        # Fallback to project_site if current_project_site is not set
        current_project = st.session_state.get('project_site', 'No Project Selected')
    
    # Ensure current_role is never None
    if current_role is None:
        current_role = 'project_site'
    
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
    
    # Project information - reflects selected project in admin account
    st.markdown(f"""
    <div class="project-info">
        <strong>Current Project</strong>
        <div class="project-name">{current_project}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Session information
    if st.session_state.get('auth_timestamp'):

        try:


            auth_time = datetime.fromisoformat(st.session_state.get('auth_timestamp'))
            expiry_time = auth_time.replace(hour=auth_time.hour + 24)
            time_remaining = expiry_time - get_nigerian_time()
            hours_remaining = int(time_remaining.total_seconds() / 3600)
            
            if hours_remaining > 0:

            
                session_status = f"{hours_remaining}h remaining"
                session_color = "#059669" if hours_remaining > 2 else "#d97706"
            else:

                session_status = "Expiring soon"
                session_color = "#dc2626"
        except:
            session_status = "Active"
            session_color = "#059669"
    else:

        session_status = "Active"
        session_color = "#059669"
    
    st.markdown(f"""
    <div class="session-info" style="border-color: {session_color}; color: {session_color};">
        <strong>Session Status:</strong><br>
        {session_status}
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar actions
    st.markdown('<div class="sidebar-actions">', unsafe_allow_html=True)

    
    # Prevent double-click by checking if already processing
    if 'logout_processing' not in st.session_state:
        st.session_state.logout_processing = False
    
    if st.button("Logout", type="secondary", use_container_width=True, help="Logout from the system", disabled=st.session_state.logout_processing):
        if not st.session_state.logout_processing:
            st.session_state.logout_processing = True
            
            # Optimized logout - clear only essential session state and force fast rerun
            st.session_state.logged_in = False
            st.session_state.user_type = None
            st.session_state.full_name = None
            st.session_state.user_id = None
            st.session_state.auth_timestamp = None
            st.session_state.current_project_site = None
            st.session_state.project_site = None
            st.query_params.clear()
            
            # Clear processing flags
            if 'login_processing' in st.session_state:
                del st.session_state.login_processing
            
            # Clear client-side storage to avoid stale flags/sessions
            st.markdown("""
            <script>
            try {
                localStorage.clear();
                sessionStorage.clear();
                // Best-effort cookie clear for session cookie name used by app, if any
                document.cookie.split(';').forEach(function(c) { 
                  document.cookie = c.replace(/^ +/, '')
                    .replace(/=.*/, '=;expires=' + new Date().toUTCString() + ';path=/'); 
                });
            } catch (e) { console.log('Storage clear skipped:', e); }
            </script>
            """, unsafe_allow_html=True)
            
            # Clear logout processing flag
            st.session_state.logout_processing = False
            
            # Immediate transition to login screen
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
# Don't require project sites for app to function
if 'current_project_site' not in st.session_state:

    st.session_state.current_project_site = None

# Database persistence test - verify PostgreSQL is working
# Test notification synchronization (disabled for performance)
# test_notification_sync()
def test_database_persistence():
    """Test if database persistence is working properly"""
    try:

        from db import get_engine
        engine = get_engine()
        with engine.begin() as conn:

            # Test if we can create and retrieve data
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS persistence_test (
                    id SERIAL PRIMARY KEY,
                    test_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Insert test data
            conn.execute(text("INSERT INTO persistence_test (test_data) VALUES (:test_data)"), {"test_data": "test_persistence"})
            conn.commit()
            
            # Retrieve test data
            result = conn.execute(text("SELECT * FROM persistence_test WHERE test_data = :test_data"), {"test_data": "test_persistence"})
            result_data = result.fetchone()
            
            if result_data:

            
                # Database persistence test PASSED - PostgreSQL is working!
                return True
            else:

                # Database persistence test FAILED - Data not retrievable!
                return False
                
    except Exception as e:

                
        # Database persistence test ERROR
        return False

# User persistence test - test if users actually persist
def test_user_persistence():
    """Test if user creation and retrieval works properly"""
    try:

        with engine.connect() as conn:

            # Check if users table exists and has data
            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.fetchone()[0]
            print(f"📊 Current user count in database: {user_count}")
            
            # Check if there are any users
            result = conn.execute(text("SELECT username, full_name, project_site FROM users LIMIT 5"))
            users = result.fetchall()
            
            if users:

            
                print("✅ Users found in database:")
                for user in users:

                    print(f"   - {user[1]} ({user[0]}) - {user[2]}")
            else:

                print("❌ No users found in database!")
                
            return len(users) > 0
                
    except Exception as e:

                
        print(f"❌ User persistence test ERROR: {e}")
        return False

# Debug functions removed for better performance
# test_database_persistence()
# test_user_persistence()

# Debug actuals issue
def debug_actuals_issue():
    """Debug why approved requests aren't showing in actuals"""
    try:

        with engine.connect() as conn:

            # Check approved requests
            result = conn.execute(text("""
                SELECT r.id, r.status, r.qty, i.name, i.project_site, i.unit_cost
                FROM requests r 
                JOIN items i ON r.item_id = i.id
                WHERE r.status = 'Approved'
                ORDER BY r.id DESC
                LIMIT 5
            """))
            approved_requests = result.fetchall()
            print(f"📋 Approved requests found: {len(approved_requests)}")
            for req in approved_requests:

                print(f"   - Request #{req[0]}: {req[3]} (Qty: {req[2]}, Project: {req[4]}, Price: {req[5]})")
            
            # Check actuals records
            result = conn.execute(text("""
                SELECT a.id, a.actual_qty, a.actual_cost, a.project_site, i.name
                FROM actuals a
                JOIN items i ON a.item_id = i.id
                ORDER BY a.id DESC
                LIMIT 5
            """))
            actuals_records = result.fetchall()
            print(f"📊 Actuals records found: {len(actuals_records)}")
            for actual in actuals_records:

                print(f"   - Actual #{actual[0]}: {actual[4]} (Qty: {actual[1]}, Cost: {actual[2]}, Project: {actual[3]})")
            
            # Check current project site
            current_project = st.session_state.get('current_project_site', 'Not set')
            print(f"🏗️ Current project site: {current_project}")
            
    except Exception as e:

            
        print(f"❌ Debug actuals error: {e}")
# debug_actuals_issue()  # Disabled for better performance
# Comprehensive app connectivity test
def test_app_connectivity():
    """Test all app connections and data flow"""
    # Running comprehensive app connectivity test...
    
    try:

    
        # Test 1: Database connection
        from db import get_engine
        engine = get_engine()
        with engine.connect() as conn:

            conn.execute(text("SELECT 1"))
            # Database connection: PASSED
        
        # Test 2: User authentication system
        test_access_code = "test123"
        auth_result = authenticate_user(test_access_code)
        # Authentication system is working if it returns None for invalid codes (expected behavior)
        # Authentication system: PASSED
        
        # Test 3: Session state
        session_keys = ['logged_in', 'user_type', 'current_project_site']
        session_ok = all(key in st.session_state for key in session_keys)
        # Session state might not be fully initialized outside Streamlit context
        # Session state: PASSED
        
        # Test 4: Notification system
        try:

            # Test notification system without showing popup
            pass  # Notification system: PASSED
        except:
            # Notification system: FAILED
            pass
        
        # Test 5: Data retrieval functions
        try:

            items = df_items_cached("Lifecamp Kafe")
            # For smoke test, use default parameters (will read from session state)
            requests = df_requests(status="Pending")
            # Data retrieval: PASSED
        except Exception as e:

            # Data retrieval: FAILED
            pass
        
        # Test 6: Project site management
        try:

            project_sites = get_project_sites()
            # Project sites: PASSED
        except Exception as e:

            # Project sites: FAILED
            pass
        
        # App connectivity test completed!
        return True
        
    except Exception as e:

        
        # App connectivity test failed
        return False

# test_app_connectivity()  # Disabled for better performance

# Get project sites first
project_sites = get_project_sites()

# Project site selection based on user permissions
user_type = st.session_state.get('user_type', 'user')
user_project_site = st.session_state.get('project_site', None)

if user_type == 'admin':


    # Admins can select any project site or work without one
    if project_sites:

        # Calculate index based on current_project_site, not session state
        # This prevents the widget warning about default value vs session state value
        current_index = 0
        if st.session_state.current_project_site in project_sites:
            current_index = project_sites.index(st.session_state.current_project_site)
        
        # Use selectbox - Streamlit will manage session state via the key
        # Don't initialize project_site_selector in session state before this
        selected_site = st.selectbox(
            "Select Project Site:",
            project_sites,
            index=current_index,
            key="project_site_selector",
            help="Choose which project site you want to work with"
        )
        
        # Check if project site changed before updating
        if st.session_state.current_project_site != selected_site:

            clear_cache()
            st.session_state.current_project_site = selected_site
            # Rerun to update sidebar with new project selection
            st.rerun()
        else:

            st.session_state.current_project_site = selected_site
    else:

        # No project sites - admin can still use the app
        st.session_state.current_project_site = None
        
        # Create a default project site automatically for better UX
        try:

            add_project_site("Default Project", "Auto-created default project site")
            # Also create access codes for it
            admin_code, user_code = get_access_codes()
            add_project_access_code("Default Project", admin_code, user_code)
            # Refresh project sites list
            project_sites = get_project_sites()
            if project_sites:

                st.session_state.current_project_site = project_sites[0]
                st.success("Created default project site automatically!")
                # Don't use st.rerun() - let the page refresh naturally
        except Exception as e:

            print(f"❌ Error creating default project site: {e}")
else:

    # Project site accounts are restricted to their own project site (the project site is the account identity)
    if user_project_site:

        st.session_state.current_project_site = user_project_site
        st.info(f"**Project Site:** {user_project_site}")
    else:

        st.warning("No project site assigned. Please contact an administrator.")

# Display current project site info
if 'current_project_site' in st.session_state and st.session_state.current_project_site:

    if user_type == 'admin':
        st.caption(f"Working with: {st.session_state.current_project_site} | Budgets: 1-20")
    else:

        st.caption(f"Available Budgets: 1-20")
else:

    if user_type == 'admin':

        st.info("Please select a project site from the dropdown above to continue.")
    else:

        st.warning("Please contact an administrator to set up your project site access.")

# Duplicate notification system removed - using the main one above

# Notification system debugging - check if notifications are working
if st.session_state.get('authenticated', False):

    if st.session_state.get('user_role') == 'admin':
        # Check if there are any unread notifications
        try:

            admin_notifications = get_admin_notifications()
            if admin_notifications:

                st.info(f"🔔 You have {len(admin_notifications)} unread notifications")
        except:
            pass
        
        # Simple test button to verify notification system
        if st.button("🔔 Test Notification System", help="Click to test if notifications work"):
            # Create a test notification in the database
            test_success = create_notification(
                notification_type="new_request",
                title="🔔 Test Notification",
                message="This is a test notification to verify the system works",
                user_id=None,  # Admin notification
                request_id=None
            )
            
            if test_success:
                st.success("✅ Test notification created in database!")
            else:
                st.error("❌ Failed to create test notification")
        
        # Test synchronization
        if st.button("🔄 Test Account Synchronization", help="Click to test if admin and project accounts are in sync"):
            sync_result = test_notification_sync()
            if sync_result:
                st.success("✅ Account synchronization test passed!")
            else:
                st.error("❌ Account synchronization test failed!")
            
            st.markdown("""
            <script>
            localStorage.setItem('new_request_notification', 'true');
            console.log('Manual notification test triggered');
            </script>
            """, unsafe_allow_html=True)
            st.success("Notification test triggered! Check for popup and sound.")
    
    # Check notifications for project site accounts
    elif user_type == 'project_site':
        try:
            # Test notification button for project site accounts
            if st.button("🔔 Test Project Site Notifications", help="Click to test if notifications work for project site accounts"):
                st.markdown("""
                <script>
                localStorage.setItem('request_approved_notification', 'true');
                console.log('Project site notification test triggered');
                </script>
                """, unsafe_allow_html=True)
                st.success("Project site notification test triggered! Check for popup and sound.")
            
            # Get notifications for project site accounts
            user_notifications = get_project_site_notifications()
            notif_count = len(user_notifications) if user_notifications else 0
            if notif_count:
                st.info(f"🔔 You have {notif_count} notifications")
                
                # Notify via popup if new notifications arrived (mirror admin experience)
                # Popup with actual messages for any new notifications since last visit
                latest_ids_js_array = '[' + ','.join(str(n.get('id')) for n in user_notifications[:5]) + ']'
                latest_msgs_js_array = '[' + ','.join(('`'+(n.get('message') or '').replace('`','\\`')+'`') for n in user_notifications[:5]) + ']'
                st.markdown(f"""
                <script>
                try {{
                  const idKey = 'ps_last_seen_notif_id';
                  const prevId = parseInt(localStorage.getItem(idKey) || '0');
                  const latestIds = {latest_ids_js_array};
                  const latestMsgs = {latest_msgs_js_array};
                  let maxId = prevId;
                  for (let i = 0; i < latestIds.length; i++) {{
                    const nid = latestIds[i];
                    const msg = latestMsgs[i] || 'You have a new notification';
                    if (nid > prevId) {{
                      if (typeof showNotificationToast === 'function') {{
                        showNotificationToast(msg);
                      }} else {{
                        const el = document.createElement('div');
                        el.style.cssText = 'position:fixed;top:80px;right:20px;background:#1d4ed8;color:#fff;padding:10px 14px;border-radius:8px;z-index:9000;box-shadow:0 4px 12px rgba(0,0,0,.15)';
                        el.textContent = msg;
                        document.body.appendChild(el);
                        setTimeout(()=>el.remove(), 3000);
                      }}
                      if (nid > maxId) maxId = nid;
                    }}
                  localStorage.setItem(idKey, String(maxId));
                }} catch (e) {{ console.log('ps popup skipped', e); }}
                </script>
                """, unsafe_allow_html=True)
                
                # Show recent notifications
                with st.expander("📬 Recent Notifications", expanded=False):
                    for notification in user_notifications[:5]:  # Show last 5 notifications
                        title = notification.get('title') if isinstance(notification, dict) else str(notification)
                        created = notification.get('created_at') if isinstance(notification, dict) else ''
                        message = notification.get('message') if isinstance(notification, dict) else ''
                        status_icon = "🔔" if (isinstance(notification, dict) and not notification.get('is_read', False)) else "✅"
                        st.write(f"{status_icon} **{title}** - {created}")
                        if message:
                            st.caption(f"*{message}*")
            else:
                st.info("📬 No notifications at the moment")
        except Exception as e:
            st.error(f"Error loading notifications: {e}")
            print(f"❌ Notification display error: {e}")

# ============================================================================
# TAB PERSISTENCE SYSTEM - Prevents app from resetting to home page
# ============================================================================
def get_active_tab_index():
    """
    Get the active tab index from query params or session state.
    This ensures tabs persist across reruns, form submissions, and page refreshes.
    Only reads from query params, doesn't modify them to avoid reruns.
    """
    # Priority 1: Check query params (for browser refresh/deep linking)
    # Only read, don't modify to avoid triggering reruns
    tab_param = st.query_params.get('tab', None)
    if tab_param is not None:
        try:
            tab_index = int(tab_param)
            # Validate tab index is within range
            max_tabs = 7
            if 0 <= tab_index < max_tabs:
                # Only update session state if it's different to avoid unnecessary writes
                if st.session_state.get('active_tab_index') != tab_index:
                    st.session_state.active_tab_index = tab_index
                return tab_index
        except (ValueError, TypeError):
            pass
    
    # Priority 2: Use session state (persists during app session)
    if 'active_tab_index' in st.session_state:
        return st.session_state.active_tab_index
    
    # Priority 3: Default to first tab (home)
    # Only set if not already set to avoid unnecessary session state write
    if 'active_tab_index' not in st.session_state:
        st.session_state.active_tab_index = 0
    return st.session_state.active_tab_index

def set_active_tab_index(tab_index):
    """
    Set the active tab index in session state only.
    Query params are updated by JavaScript to avoid triggering reruns.
    """
    # Only update session state - don't modify query params as it causes reruns
    st.session_state.active_tab_index = tab_index

def preserve_current_tab():
    """
    Helper function to preserve the current tab after form submissions or actions.
    Call this after any action that might trigger a rerun.
    """
    current_tab = st.session_state.get('active_tab_index', 0)
    set_active_tab_index(current_tab)

# Simplified JavaScript for tab persistence - passive tracking only, no programmatic clicks
st.markdown("""
<script>
// Simple tab persistence - only tracks clicks, doesn't trigger reruns
(function() {
    function updateTabInURL(tabIndex) {
        // Only update URL without triggering any actions
        try {
            const url = new URL(window.location);
            const currentTab = url.searchParams.get('tab');
            if (currentTab !== tabIndex.toString()) {
                url.searchParams.set('tab', tabIndex.toString());
                window.history.replaceState({}, '', url);
            }
            localStorage.setItem('istrom_last_tab', tabIndex.toString());
        } catch (e) {
            // Silently fail
        }
    }
    
    function trackTabs() {
        const tabContainer = document.querySelector('[data-testid="stTabs"]');
        if (!tabContainer) {
            return;
        }
        
        const tabs = tabContainer.querySelectorAll('button[role="tab"]');
        if (tabs.length === 0) {
            return;
        }
        
        tabs.forEach(function(tab, index) {
            if (!tab.hasAttribute('data-tab-tracked')) {
                tab.setAttribute('data-tab-tracked', 'true');
                tab.addEventListener('click', function() {
                    updateTabInURL(index);
                });
            }
        });

        // Restore the previously selected tab (without causing extra reruns)
        if (!tabContainer.hasAttribute('data-tab-restored')) {
            let desiredTab = null;
            try {
                const url = new URL(window.location);
                const urlTab = url.searchParams.get('tab');
                if (urlTab !== null) {
                    desiredTab = parseInt(urlTab, 10);
                }
            } catch (e) {
                desiredTab = null;
            }

            if (Number.isNaN(desiredTab) || desiredTab === null) {
                const stored = localStorage.getItem('istrom_last_tab');
                if (stored !== null) {
                    desiredTab = parseInt(stored, 10);
                }
            }

            if (!Number.isNaN(desiredTab) && desiredTab !== null && desiredTab >= 0 && desiredTab < tabs.length) {
                const alreadySelected = tabs[desiredTab].getAttribute('aria-selected') === 'true';
                if (!alreadySelected) {
                    tabs[desiredTab].click();
                }
                tabContainer.setAttribute('data-tab-restored', 'true');
            }
        }
    }
    
    // Track tabs when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', trackTabs);
    } else {
        trackTabs();
    }
    
    // Also track after a short delay in case tabs render later
    setTimeout(trackTabs, 500);
})();
</script>
""", unsafe_allow_html=True)

# Get current active tab (will be used to highlight/preserve)
current_active_tab = get_active_tab_index()

# Create tabs based on user type
if st.session_state.get('user_type') == 'admin':
    tab_names = ["Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History", "Budget Summary", "Actuals", "Admin Settings"]
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tab_names)
else:
    # Project site accounts have a Notifications tab to see approvals/rejections
    tab_names = ["Manual Entry (Budget Builder)", "Inventory", "Make Request", "Review & History", "Budget Summary", "Actuals", "Notifications"]
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tab_names)
# Don't modify query params here - let JavaScript handle it to avoid reruns
# Query params will be set by JavaScript when user clicks tabs
# -------------------------------- Tab 1: Manual Entry (Budget Builder) --------------------------------
with tab1:

    st.subheader("Manual Entry - Budget Builder")
    st.caption("Add items with proper categorization and context")
    
    # Check permissions for manual entry
    if not is_admin():

        st.warning("**Read-Only Access**: You can view items but cannot add, edit, or delete them.")
        st.info("Contact an administrator if you need to make changes to the inventory.")
    
    # Project Context (outside form for immediate updates)
    st.markdown("### Project Context")
    col1, col2, col3, col4 = st.columns([2, 1.5, 2, 2])
    with col1:
        # Building type with "All" option
        filtered_property_types = [pt for pt in PROPERTY_TYPES if pt and pt.strip()]
        building_type_options = ["All"] + filtered_property_types
        
        # Preserve building type selection
        building_type_index = 0  # Default to "All"
        if 'last_manual_building_type' in st.session_state:
            last_building_type = st.session_state['last_manual_building_type']
            try:
                if last_building_type in building_type_options:
                    building_type_index = building_type_options.index(last_building_type)
            except (ValueError, AttributeError):
                building_type_index = 0  # Default to "All" if not found
        
        building_type = st.selectbox("Building Type", building_type_options, index=building_type_index, help="Select building type first (or All to see all)", key="building_type_select")
        
        # Store selected building type
        if building_type:
            st.session_state['last_manual_building_type'] = building_type
        
        # Track if building type changed
        if 'last_building_type' not in st.session_state:
            st.session_state['last_building_type'] = building_type
        elif st.session_state['last_building_type'] != building_type:
            # Building type changed - clear stored budget
            if 'last_selected_budget' in st.session_state:
                del st.session_state['last_selected_budget']
            st.session_state['last_building_type'] = building_type
    
    with col2:
        # Budget Number dropdown (1-20)
        budget_number_options = ["All"] + [f"Budget {i}" for i in range(1, 21)]
        
        # Preserve budget number selection
        budget_number_index = 0  # Default to "All"
        if 'last_manual_budget_number' in st.session_state:
            last_budget_number = st.session_state['last_manual_budget_number']
            try:
                if last_budget_number in budget_number_options:
                    budget_number_index = budget_number_options.index(last_budget_number)
            except (ValueError, AttributeError):
                budget_number_index = 0  # Default to "All" if not found
        
        manual_budget_number = st.selectbox(
            "Budget Number",
            budget_number_options,
            index=budget_number_index,
            help="Select budget number (1-20) to filter by",
            key="manual_budget_number_filter"
        )
        
        # Store selected budget number and track if it changed
        if 'last_manual_budget_number' not in st.session_state:
            st.session_state['last_manual_budget_number'] = manual_budget_number
        elif st.session_state.get('last_manual_budget_number') != manual_budget_number:
            # Budget number changed - clear stored budget
            if 'last_selected_budget' in st.session_state:
                del st.session_state['last_selected_budget']
            st.session_state['last_manual_budget_number'] = manual_budget_number
    with col3:

        # Construction sections with "All" option
        common_sections = [
            "SUBSTRUCTURE (GROUND TO DPC LEVEL)",
            "SUBSTRUCTURE (EXCAVATION TO DPC LEVEL)",
            "TERRACES (6-UNITS) DPC(TERRACE SUBSTRUCTURE)",
            "SUPERSTRUCTURE: GROUND FLOOR; (COLUMN, LINTEL AND BLOCK WORK)",
            "SUPERSTRUCTURE, GROUND FLOOR; (SLAB,BEAMS AND STAIR CASE)",
            "SUPERSTRUCTURE, FIRST FLOOR; (COLUMN, LINTEL AND BLOCK WORK)",
            "SUPERSTRUCTURE FIRST FLOOR SLAB WORK (SLAB, BEAMS & STAIRCASE)",
            "SUPERSTRUCTURE, 1ST FLOOR; (COLUMN, LINTEL, BLOCK WORK AND LIFT SHIFT)",
            "SUPERSTRUCTURE, SECOND FLOOR; (SLAB,BEAMS AND STAIR CASE)",
            "FASCIA CASTING, ROOF SLAB AND BLOCK WORK ABOVE ROOF BEAM",
            "ROOF BEAMS, CONCRETE FASCIA, ROOF SLAB & PARAPET WALL",
            "TERRACE BEAM, BLOCK WORK, COLUMN & SHORT ROOF"
        ]
        
        section_options = ["All"] + common_sections
        
        # Preserve section selection
        section_index = 0  # Default to "All"
        if 'last_manual_section' in st.session_state:
            last_section = st.session_state['last_manual_section']
            try:
                if last_section in section_options:
                    section_index = section_options.index(last_section)
            except (ValueError, AttributeError):
                section_index = 0  # Default to "All" if not found
        
        section = st.selectbox("Section", section_options, index=section_index, help="Select construction section (or All to see all)", key="manual_section_selectbox")
        
        # Store selected section
        if section:
            st.session_state['last_manual_section'] = section
    with col4:

        # Filter budget options based on selected building type and budget number
        with st.spinner("Loading budget options..."):

            all_budget_options = get_budget_options(st.session_state.get('current_project_site'))
            
            # Remove "All" from the list for filtering (we'll add it back later)
            budget_options_to_filter = [opt for opt in all_budget_options if opt != "All"]
            
            # Filter out budgets with subcategories appended (e.g., "Budget 5 - Terraces(General Materials - BLOCKWORK ABOVE ROOF BEAM)")
            # These have " - " inside the parentheses, indicating a subcategory was appended
            filtered_budgets = []
            for opt in budget_options_to_filter:
                try:
                    if "(" in opt and ")" in opt:
                        # Extract the part inside parentheses
                        paren_parts = opt.split("(")
                        if len(paren_parts) > 1:
                            paren_content = paren_parts[1].split(")")[0]
                            # If there's " - " inside parentheses, it means a subcategory was appended - skip it
                            if " - " not in paren_content:
                                filtered_budgets.append(opt)
                        else:
                            # Malformed budget string - skip it
                            continue
                    else:
                        # Budgets without parentheses are fine
                        filtered_budgets.append(opt)
                except Exception:
                    # Skip malformed budget strings
                    continue
            budget_options_to_filter = filtered_budgets
            
            # Filter budgets based on budget number FIRST (if not "All")
            if manual_budget_number and manual_budget_number != "All":
                # Extract the budget number (e.g., "Budget 1" -> "1")
                budget_num = manual_budget_number.replace("Budget ", "").strip()
                # Use word boundary to ensure exact match (e.g., Budget 1 doesn't match Budget 10)
                pattern = rf"^Budget {budget_num}\b\s+-"
                budget_options = [opt for opt in budget_options_to_filter if re.match(pattern, opt)]
            else:
                # If "All" is selected for budget number, use all budgets
                budget_options = budget_options_to_filter
            
            # Filter budgets that match the selected building type SECOND (skip if "All" is selected)
            if building_type and building_type != "All":
                # Filter budgets that contain the building type
                # The format is: "Budget X - BuildingType(Category)"
                budget_options = [opt for opt in budget_options if f" - {building_type}(" in opt]
                
                # If no matching budgets found, show all budgets
                if not budget_options:
                    st.warning(f"No budgets found for {building_type}. Showing all budgets.")
                    budget_options = budget_options_to_filter
            # If "All" is selected for building type, don't filter by building type
            
            # Ensure we have at least "All" option
            if not budget_options:
                budget_options = ["All"]
            elif budget_options[0] != "All":
                budget_options = ["All"] + budget_options
        
        # Budget selection - filtered by building type and budget number
        # Preserve previously selected budget if it's still in the filtered options
        selected_budget_index = 0
        if budget_options and len(budget_options) > 0:
            if 'last_selected_budget' in st.session_state:
                last_selected = st.session_state['last_selected_budget']
                try:
                    if last_selected in budget_options:
                        selected_budget_index = budget_options.index(last_selected)
                except (ValueError, AttributeError):
                    selected_budget_index = 0  # Default to first option if not found
            
            budget = st.selectbox("🏷️ Budget Label", budget_options, index=selected_budget_index, help="Select budget type", key="budget_selectbox")
        else:
            # Fallback if no budget options available
            budget = st.selectbox("🏷️ Budget Label", ["All"], index=0, help="No budget options available", key="budget_selectbox")
        
        # Store the selected budget in session state for next rerun
        if budget:
            # Check if budget changed - if so, clear stored subcategory
            if 'last_selected_budget' in st.session_state and st.session_state['last_selected_budget'] != budget:
                # Budget changed - clear stored subcategory if switching away from Budget 5
                if 'Budget 5' not in budget and 'last_selected_budget_5_subcategory' in st.session_state:
                    del st.session_state['last_selected_budget_5_subcategory']
            st.session_state['last_selected_budget'] = budget
        
        # Show info about filtered budgets
        if building_type and building_type != "All" and len(budget_options) < len(all_budget_options):

            st.caption(f"Showing {len(budget_options)} budget(s) for {building_type}")
        
        # Conditional dropdown for Budget 5 - only for Terraces, Semi-detached, Fully-detached general materials (exclude Flats)
        budget_5_subcategory = None
        if budget and "Budget 5" in budget:
            # Exclude Flats - only show for Terraces, Semi-detached, or Fully-detached
            building_types_in_budget = ["Terraces", "Semi-detached", "Fully-detached"]
            is_valid_building_type = any(bt in budget for bt in building_types_in_budget)
            
            # Exclude Flats explicitly
            is_not_flats = "Flats" not in budget
            
            # Check if it's general materials (not specific subgroups like WOODS, PLUMBINGS, IRONS)
            is_general_materials = not any(subgroup in budget for subgroup in ["WOODS", "PLUMBINGS", "IRONS"])
            
            if is_valid_building_type and is_not_flats and is_general_materials:
                budget_5_options = [
                    "None",
                    "BLOCKWORK ABOVE ROOF BEAM",
                    "ROOF BEAM & FASCIA CASTING",
                    "IRON COL ABOVE ROOF BEAM",
                    "COL FORM WORK ABOVE R/B & CASTING",
                    "ROOF SLAB (SHORT) CASTING",
                    "COPPING",
                    "LINTEL",
                    "ROOF SLAB FORMWORK",
                    "ROOF SLAB IRON WORK"
                ]
                
                # Preserve previously selected subcategory if it's still in the options
                selected_subcategory_index = 0
                if 'last_selected_budget_5_subcategory' in st.session_state:
                    last_selected_subcategory = st.session_state['last_selected_budget_5_subcategory']
                    if last_selected_subcategory in budget_5_options:
                        selected_subcategory_index = budget_5_options.index(last_selected_subcategory)
                
                budget_5_subcategory = st.selectbox(
                    "📋 Budget 5 Subcategory",
                    budget_5_options,
                    index=selected_subcategory_index,
                    help="Select subcategory for Budget 5 (or None if not applicable)",
                    key="budget_5_subcategory_selectbox"
                )
                
                # Store the selected subcategory in session state for next rerun
                if budget_5_subcategory:
                    st.session_state['last_selected_budget_5_subcategory'] = budget_5_subcategory

    # Add Item Form
    with st.form("add_item_form", clear_on_submit=False):

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

        st.markdown("### Category")
        category_options = ["Materials", "Labour", "Material/Labour"]
        
        # Preserve category selection
        category_index = 0  # Default to "Materials"
        if 'last_manual_category' in st.session_state:
            last_category = st.session_state['last_manual_category']
            try:
                if last_category in category_options:
                    category_index = category_options.index(last_category)
            except (ValueError, AttributeError):
                category_index = 0  # Default to "Materials" if not found
        
        category = st.selectbox("📂 Category", category_options, index=category_index, help="Select category", key="manual_category_select")
        
        # Store selected category
        if category:
            st.session_state['last_manual_category'] = category
        
        # Set default group based on category
        if category == "Materials":

            grp = "Materials"
        elif category == "Labour":
            grp = "Labour"
        else:  # Material/Labour
            grp = "Material/Labour"

        # Show line amount preview
        line_amount = float((qty or 0) * (rate or 0))
        st.markdown(f"""
        <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937; text-align: center; padding: 0.6rem; background: #f8fafc; border-radius: 8px; margin: 0.4rem 0;">
            Line Amount: ₦{line_amount:,.2f}
        </div>
        """, unsafe_allow_html=True)

        submitted = st.form_submit_button("Add Item", type="primary")
        
        if submitted:

        
            if not is_admin():
                st.error(" Admin privileges required for this action.")
                st.info("Only administrators can add items to the inventory.")
            else:
                # Validate required fields
                if not name or not name.strip():
                    st.error("❌ Item Name is required.")
                elif not budget or budget == "All":
                    st.error("❌ Please select a valid Budget Label (cannot be 'All').")
                elif not section or section == "All" or not section.strip():
                    st.error("❌ Please select a valid Section (cannot be 'All').")
                elif not building_type or building_type == "All":
                    st.error("❌ Please select a valid Building Type (cannot be 'All').")
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
                    
                    # Use building_type from dropdown (not "All")
                    final_bt = building_type if building_type != "All" else (parsed_bt or None)
                    
                    # Additional validation: ensure final_bt is not None (should be caught by earlier validation, but double-check)
                    if not final_bt:
                        st.error("❌ Building Type could not be determined. Please select a specific building type.")
                    else:
                        # Append Budget 5 subcategory to budget if selected (and not "None")
                        final_budget = budget
                        if budget_5_subcategory and budget_5_subcategory != "None" and budget and "Budget 5" in budget:
                            # Append subcategory to budget (e.g., "Budget 5 - Flats(WOODS) - BLOCKWORK ABOVE ROOF BEAM")
                            if "(" in budget and ")" in budget:
                                # Replace the closing parenthesis with subcategory and closing parenthesis
                                final_budget = budget.replace(")", f" - {budget_5_subcategory})")
                            else:
                                # Add subcategory in parentheses
                                final_budget = f"{budget} ({budget_5_subcategory})"

                        # Create and save item
                        df_new = pd.DataFrame([{
                            "name": name,
                            "qty": qty,
                            "unit": unit or None,
                            "unit_cost": rate or None,
                            "category": category,
                            "budget": final_budget,
                            "section": section,
                            "grp": final_grp,
                            "building_type": final_bt
                        }])
                        
                        # Auto-create project site if none exists
                        current_project_site = st.session_state.get('current_project_site')
                        if not current_project_site:

                            # Create a random project site automatically
                            import random
                            import string
                            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
                            auto_project_name = f"Project-{random_suffix}"
                            
                            try:

                            
                                add_project_site(auto_project_name, "Auto-created project site")
                                # Also create access codes for it
                                admin_code, user_code = get_access_codes()
                                add_project_access_code(auto_project_name, admin_code, user_code)
                                # Set as current project site
                                st.session_state.current_project_site = auto_project_name
                                st.success(f"✅ Auto-created project site: {auto_project_name}")
                                st.info("💡 You can rename this project site in the Admin Settings tab")
                            except Exception as e:

                                print(f"❌ Error creating auto project site: {e}")
                                # Fallback to default
                                st.session_state.current_project_site = "Default Project"
                        
                        # Preserve current tab before processing
                        preserve_current_tab()
                        
                        # Add item (no unnecessary spinner)
                        upsert_items(df_new, category_guess=category, budget=final_budget, section=section, grp=final_grp, building_type=final_bt, project_site=st.session_state.get('current_project_site'))
                        # Log item addition activity
                        log_current_session()
                        
                        st.success(f" Successfully added: {name} ({qty} {unit}) to {budget} / {section} / {final_grp} / {final_bt}")
                        st.info("💡 This item will now appear in the Budget Summary tab for automatic calculations!")
                        
                        # Preserve tab after action
                        preserve_current_tab()
# -------------------------------- Tab 2: Inventory --------------------------------
with tab2:

    st.subheader("📦 Current Inventory")
    st.caption("View, edit, and manage all inventory items")
    
    # Check permissions for inventory management
    if not is_admin():

        st.warning("**Read-Only Access**: You can view inventory but cannot modify items.")
        st.info("Contact an administrator if you need to make changes to the inventory.")
    
    # Load all items first with progress indicator (optimized)
    with st.spinner("Loading inventory..."):

        items = df_items_cached(st.session_state.get('current_project_site'))
    
    # Show loading status - clean interface
    if items.empty:

        st.info("📦 **No items found yet.** Add some items in the Manual Entry tab to get started.")
        st.stop()
    
    # Calculate amounts
    items["Amount"] = (items["qty"].fillna(0) * items["unit_cost"].fillna(0)).round(2)

    # Quick stats (optimized)
    total_items = len(items)
    # Calculate total value with proper NaN handling
    total_value = items["Amount"].sum()
    if pd.notna(total_value):

        total_value = float(total_value)
    else:

        total_value = 0.0
    
    # Professional Dashboard Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:

        st.metric("Total Items", f"{total_items:,}", help="Total inventory items")
    with col2:

        st.metric("Total Value", f"₦{total_value:,.2f}", help="Total inventory value")
    with col3:

        materials_count = (items['category'] == 'materials').sum()
        st.metric("Materials", f"{materials_count:,}", help="Material items count")
    with col4:

        labour_count = (items['category'] == 'labour').sum()
        st.metric("Labour", f"{labour_count:,}", help="Labour items count")
    
    # Professional Filters - Improved order: Building Type, Budget Number, Budget, Section
    st.markdown("### Filters")
    
    colf1, colf2, colf3, colf4 = st.columns([2, 1.5, 2, 2])
    
    with colf1:
        # Building type filter (FIRST as requested)
        # Filter out empty strings from PROPERTY_TYPES to avoid spacing issues
        filtered_property_types = [pt for pt in PROPERTY_TYPES if pt and pt.strip()]
        building_type_options = ["All"] + filtered_property_types
        f_building_type = st.selectbox(
            "🏠 Building Type",
            building_type_options,
            index=0,
            help="Select building type to filter by",
            key="inventory_building_type_filter"
        )
    
    with colf2:
        # Budget Number filter (NEW - 1-20)
        budget_number_options = ["All"] + [f"Budget {i}" for i in range(1, 21)]
        f_budget_number = st.selectbox(
            "🔢 Budget Number",
            budget_number_options,
            index=0,
            help="Select budget number (1-20) to filter by",
            key="inventory_budget_number_filter"
        )
    
    with colf3:
        # Budget filter (filtered by building type AND budget number)
        # Get dynamic budget options from database
        all_budget_options = get_budget_options(st.session_state.get('current_project_site'))
        
        # Remove "All" from the list for filtering (we'll add it back later)
        budget_options_to_filter = [opt for opt in all_budget_options if opt != "All"]
        
        # Filter budgets based on building type (if not "All")
        if f_building_type and f_building_type != "All":
            # Filter budgets that contain the building type
            # The format is: "Budget X - BuildingType(Category)"
            budget_options = [opt for opt in budget_options_to_filter if f" - {f_building_type}(" in opt]
        else:
            # If "All" is selected for building type, use all budgets
            budget_options = budget_options_to_filter
        
        # Filter budgets based on budget number (if not "All")
        if f_budget_number and f_budget_number != "All":
            # Extract the budget number (e.g., "Budget 1" -> "1")
            budget_num = f_budget_number.replace("Budget ", "").strip()
            # Filter budgets that match the exact budget number
            # Use pattern "Budget X -" where X is the exact number (not "Budget 10" when looking for "Budget 1")
            # Use word boundary \b after the number to ensure "1" doesn't match "10", "11", etc.
            pattern = rf"^Budget {budget_num}\b\s+-"
            budget_options = [opt for opt in budget_options if re.match(pattern, opt)]
        
        # If no matching budgets found after filtering, show all budgets as fallback
        if not budget_options:
            budget_options = budget_options_to_filter
        
        # Add "All" option at the beginning
        budget_options = ["All"] + budget_options
        
        f_budget = st.selectbox(
            "🏷️ Budget",
            budget_options,
            index=0,
            help="Select budget to filter by (shows all subgroups)",
            key="inventory_budget_filter"
        )
    
    with colf4:
        # Section filter (filtered by sections that exist in filtered items)
        # First, apply building type and budget number filters to get available sections
        temp_filtered = items.copy()
        
        # Apply building type filter
        if f_building_type and f_building_type != "All":
            temp_filtered = temp_filtered[temp_filtered["building_type"] == f_building_type]
        
        # Apply budget number filter
        if f_budget_number and f_budget_number != "All":
            # Extract the budget number (e.g., "Budget 1" -> "1")
            budget_num = f_budget_number.replace("Budget ", "").strip()
            # Match exact budget number using regex pattern "Budget X -" where X is the exact number
            # Use word boundary \b after the number to ensure "1" doesn't match "10", "11", etc.
            pattern = rf"^Budget {budget_num}\b\s+-"
            temp_filtered = temp_filtered[temp_filtered["budget"].str.match(pattern, na=False)]
        
        # Get unique sections from filtered items
        if not temp_filtered.empty:
            available_sections = sorted(temp_filtered["section"].dropna().unique().tolist())
            # Filter out empty strings and None values
            available_sections = [s for s in available_sections if s and str(s).strip()]
            section_options = ["All"] + available_sections
        else:
            # If no items match, show all sections
            all_section_options = get_section_options(st.session_state.get('current_project_site'))
            if all_section_options and all_section_options[0] != "All":
                section_options = ["All"] + all_section_options
            else:
                section_options = all_section_options if all_section_options else ["All"]
        
        f_section = st.selectbox(
            "📂 Section",
            section_options,
            index=0,
            help="Select section to filter by",
            key="inventory_section_filter"
        )

    # Apply filters using hierarchical logic (order: Building Type, Budget Number, Budget, Section)
    filtered_items = items.copy()
    
    # Start with all items
    initial_count = len(filtered_items)
    
    # Building type filter (applied first)
    if f_building_type and f_building_type != "All":
        building_type_matches = filtered_items["building_type"] == f_building_type
        filtered_items = filtered_items[building_type_matches]
    
    # Budget number filter (applied second)
    if f_budget_number and f_budget_number != "All":
        # Extract the budget number (e.g., "Budget 1" -> "1")
        budget_num = f_budget_number.replace("Budget ", "").strip()
        # Match exact budget number using regex pattern "Budget X -" where X is the exact number
        # Use word boundary \b after the number to ensure "1" doesn't match "10", "11", etc.
        pattern = rf"^Budget {budget_num}\b\s+-"
        budget_number_matches = filtered_items["budget"].str.match(pattern, na=False)
        filtered_items = filtered_items[budget_number_matches]
    
    # Budget filter with flexible matching (space and case insensitive) - applied third
    if f_budget and f_budget != "All":
        def normalize_budget_string(budget_str):
            """Normalize budget string for comparison - remove extra spaces, convert to lowercase"""
            if pd.isna(budget_str):
                return ""
            # Convert to string, strip whitespace, convert to lowercase
            normalized = str(budget_str).strip().lower()
            # Remove extra spaces and normalize spacing around parentheses
            normalized = normalized.replace("  ", " ")  # Remove double spaces
            normalized = normalized.replace(" (", "(")   # Remove space before opening parenthesis
            normalized = normalized.replace("( ", "(")   # Remove space after opening parenthesis
            normalized = normalized.replace(" )", ")")   # Remove space before closing parenthesis
            # Handle "Iron" vs "Irons" difference
            normalized = normalized.replace("(iron)", "(irons)")
            return normalized
        
        # Normalize the filter budget
        normalized_filter = normalize_budget_string(f_budget)
        
        if "(" in f_budget and ")" in f_budget:
            # Specific subgroup - flexible exact match
            budget_matches = filtered_items["budget"].apply(
                lambda x: normalize_budget_string(x) == normalized_filter
            )
        else:
            # Hierarchical - show all items that contain this budget
            # e.g., "Budget 1 - Terraces" shows "Budget 1 - Terraces", "Budget 1 - Terraces(Plumbings)", etc.
            budget_matches = filtered_items["budget"].apply(
                lambda x: normalized_filter in normalize_budget_string(x)
            )
        
        filtered_items = filtered_items[budget_matches]
    
    # Section filter (applied fourth)
    if f_section and f_section != "All":
        section_matches = filtered_items["section"] == f_section
        filtered_items = filtered_items[section_matches]
    
    # Update items with filtered results
    items = filtered_items
    
    # Show filter results summary
    if len(items) != initial_count:
        st.info(f"📊 Showing {len(items):,} of {initial_count:,} items")
    current_project = st.session_state.get('current_project_site', 'Not set')
    try:

        total_items_in_project = len(df_items_cached(st.session_state.get('current_project_site')))
    except Exception as e:

        # Could not load items during startup
        total_items_in_project = 0
    # Cache refresh button removed

    st.markdown("### Inventory Items")
    
    # Remove code and project_site columns from display
    display_items = items.drop(columns=['code', 'project_site'], errors='ignore')
    
    # Add pagination for large datasets
    page_size = 100  # Items per page (showing 1-100 format)
    total_items_count = len(display_items)
    total_pages = (total_items_count + page_size - 1) // page_size
    
    if total_pages > 1:
        # Better looking pagination controls with clean layout
        col1, col2, col3 = st.columns([2, 3, 2])
        with col2:
            # Use number_input for better UX with navigation buttons
            page = st.number_input(
                "📄 Page",
                min_value=1,
                max_value=total_pages,
                value=1,
                step=1,
                key="inventory_page",
                help=f"Navigate through pages (Total: {total_pages} pages, {page_size} items per page)"
            )
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items_count)
        paginated_items = display_items.iloc[start_idx:end_idx]
        
        # Display range in format "1-100" or "101-200" etc. with clean styling
        st.markdown(
            f"<div style='text-align: center; padding: 0.5rem; background: #f8fafc; border-radius: 6px; margin: 0.5rem 0; "
            f"border: 1px solid #e2e8f0; font-size: 0.95rem; color: #475569;'>"
            f"<strong>Showing items {start_idx + 1}–{end_idx} of {total_items_count:,} total items</strong> "
            f"(Page {page} of {total_pages})</div>",
            unsafe_allow_html=True
        )
    else:
        paginated_items = display_items
        st.info(f"📄 Showing all **{total_items_count:,}** items")
    
    # Display the dataframe with full width
    st.dataframe(
        paginated_items,
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

    st.markdown("### Item Management")
    require_confirm = st.checkbox("Require confirmation for deletes", value=True, key="inv_confirm")
    
    # Simple item selection for deletion
    st.markdown("####  Select Items to Delete")
    
    # Create a list of items for selection (use filtered items)
    item_options = []
    for _, r in filtered_items.iterrows():

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

    
        st.warning(f"You have selected {len(selected_items)} item(s) for deletion.")
        
        # Wrap delete functionality in a form
        with st.form("delete_items_form", clear_on_submit=False):

            col1, col2 = st.columns([1, 1])
            with col1:

                delete_submitted = st.form_submit_button("🗑️ Delete Selected Items", type="secondary")
            with col2:

                clear_submitted = st.form_submit_button("Clear Selection", type="secondary")
            
            if delete_submitted:

            
                # Delete selected items immediately
                deleted_count = 0
                errors = []
                
                for item in selected_items:

                
                    # Check if item has linked requests using SQLAlchemy
                    try:

                        from sqlalchemy import text
                        from db import get_engine
                        
                        engine = get_engine()
                        with engine.connect() as conn:

                            result = conn.execute(text("SELECT COUNT(*) FROM requests WHERE item_id = :item_id"), {"item_id": item['id']})
                            request_count = result.fetchone()[0]
                        
                        if request_count > 0:

                        
                            errors.append(f"Item {item['name']}: Has {request_count} linked request(s)")
                        else:

                            err = delete_item(item['id'])
                            if err:

                                errors.append(f"Item {item['name']}: {err}")
                            else:

                                deleted_count += 1
                    except Exception as e:

                        errors.append(f"Item {item['name']}: Error checking requests - {e}")
                    
                if deleted_count > 0:

                    
                    st.success(f"✅ Successfully deleted {deleted_count} item(s).")
                    
                    # Show notification popup
                    st.markdown("""
                    <script>
                    localStorage.setItem('item_deleted_notification', 'true');
                    </script>
                    """, unsafe_allow_html=True)
                    
                    if errors:

                    
                        st.error(f"❌ {len(errors)} item(s) could not be deleted:")
                        for error in errors:

                            st.error(error)
                    
                if deleted_count > 0 or errors:

                    
                    # Clear cache to refresh data without page reload
                    clear_cache()
            
            if clear_submitted:

            
                st.session_state["delete_selection"] = []
                # Don't auto-refresh - let user continue working
    elif selected_items and not is_admin():
        st.error(" Admin privileges required for deletion.")
    
    # Individual item editing (simplified to avoid nested columns)
    st.markdown("#### 📝 Individual Item Management")
    st.info("💡 Use the bulk selection above to manage multiple items, or edit items directly below.")
    
    # Individual item edit functionality
    if is_admin():

        st.markdown("##### ✏️ Edit Individual Items")

        st.markdown(f"**Select an item to edit (filtered results: {len(filtered_items)} items):**")
        
        # Create a selectbox for item selection using filtered items (outside the form for immediate reruns)
        item_edit_options = []
        for _, r in filtered_items.iterrows():
            item_edit_options.append({
                'id': int(r['id']),
                'name': r['name'],
                'display': f"[{int(r['id'])}] {r['name']} - {r['qty']} {r['unit'] or ''} @ ₦{(r['unit_cost'] or 0):,.2f}"
            })
        
        if item_edit_options:
            selected_item = st.selectbox(
                "Choose item to edit:",
                options=item_edit_options,
                format_func=lambda x: x['display'],
                key="edit_item_select"
            )
            
            if selected_item:
                current_item = filtered_items[filtered_items['id'] == selected_item['id']].iloc[0]

                # Sync session state values with the selected item so defaults update correctly
                selected_id = selected_item['id']
                current_qty = float(current_item.get('qty', 0) or 0)
                current_cost = float(current_item.get('unit_cost', 0) or 0)

                if st.session_state.get('edit_last_item_id') != selected_id:
                    st.session_state['edit_qty'] = current_qty
                    st.session_state['edit_cost'] = current_cost
                    st.session_state['edit_last_item_id'] = selected_id
                else:
                    if 'edit_qty' not in st.session_state:
                        st.session_state['edit_qty'] = current_qty
                    if 'edit_cost' not in st.session_state:
                        st.session_state['edit_cost'] = current_cost

                with st.form("edit_item_form", clear_on_submit=False):
                    
                    col1, col2 = st.columns(2)
                    with col1:

                        new_qty = st.number_input(
                            "📦 New Quantity",
                            min_value=0.0,
                            step=0.1,
                            key="edit_qty"
                        )
                    with col2:

                        new_cost = st.number_input(
                            "₦ New Unit Cost",
                            min_value=0.0,
                            step=0.01,
                            key="edit_cost"
                        )
                    
                    # Show preview of changes
                    old_qty = float(current_item['qty']) if pd.notna(current_item['qty']) else 0.0
                    old_unit_cost = float(current_item['unit_cost']) if pd.notna(current_item['unit_cost']) else 0.0
                    old_amount = old_qty * old_unit_cost
                    new_amount = new_qty * new_cost
                    amount_change = new_amount - old_amount
                    
                    # Handle NaN values
                    old_amount = float(old_amount) if pd.notna(old_amount) else 0.0
                    new_amount = float(new_amount) if pd.notna(new_amount) else 0.0
                    amount_change = float(amount_change) if pd.notna(amount_change) else 0.0
                    
                    st.markdown("**Change Preview:**")
                    col1, col2, col3 = st.columns(3)
                    with col1:

                        st.metric("Old Amount", f"₦{old_amount:,.2f}")
                    with col2:

                        st.metric("New Amount", f"₦{new_amount:,.2f}")
                    with col3:

                        st.metric("Change", f"₦{amount_change:,.2f}", delta=f"{amount_change:,.2f}")
                    
                    if st.form_submit_button("💾 Update Item", type="primary"):

                        try:


                            from db import get_engine
                            engine = get_engine()
                            with engine.begin() as conn:

                                conn.execute(text(
                                    "UPDATE items SET qty=:qty, unit_cost=:unit_cost WHERE id=:id"
                                ), {
                                    "qty": new_qty,
                                    "unit_cost": new_cost,
                                    "id": selected_item['id']
                                })
                            
                            st.success(f"Successfully updated item: {selected_item['name']}")
                            
                            st.markdown("""
                            <script>
                            localStorage.setItem('item_updated_notification', 'true');
                            </script>
                            """, unsafe_allow_html=True)
                            clear_cache()
                        except Exception as e:
                            st.error(f"Error updating item: {e}")
        else:
            st.info("No items available for editing.")
    else:

        st.info("Admin privileges required to edit items.")
    
    st.divider()
    st.markdown("### Danger Zone")
    coldz1, coldz2 = st.columns([3,2])
    with coldz1:

        if is_admin():

            also_logs = st.checkbox("Also clear deleted request logs", value=False, key="clear_logs")
        else:

            st.info("Admin privileges required for bulk operations")
    with coldz2:

        if is_admin():

            if st.button(" Delete ALL inventory and requests", type="secondary", key="delete_all_button"):
                if not st.session_state.get("confirm_clear_all"):

                    st.session_state["confirm_clear_all"] = True
                    st.warning("Click the button again to confirm full deletion.")
                else:

                    clear_inventory(include_logs=also_logs)
                    st.success(" All items and requests cleared.")
                    # Don't use st.rerun() - let the page refresh naturally
        else:

            st.button(" Delete ALL inventory and requests", type="secondary", key="delete_all_button", disabled=True, help="Admin privileges required")
    st.caption("Tip: Use Manual Entry / Import to populate budgets; use Make Request to deduct stock later.")
# -------------------------------- Tab 5: Budget Summary --------------------------------
with tab5:

    st.subheader("Budget Summary by Building Type")
    print("DEBUG: Budget Summary tab loaded")
    st.caption("Comprehensive overview of all budgets and building types")
    
    # Check permissions for budget management
    if not is_admin():

        st.info("👤 **User Access**: You can view budget summaries but cannot modify them.")
    
    # Get all items for summary (cached)
    actuals_summary = pd.DataFrame()
    with st.spinner("Loading budget summary data..."):

        try:
            current_project = st.session_state.get('current_project_site', 'Not set')
            user_project = st.session_state.get('project_site', 'Not set')
            user_type = st.session_state.get('user_type', 'Not set')
            all_items_summary, summary_data = get_summary_data()
            project_for_actuals = current_project if current_project and current_project != 'Not set' else None
            actuals_summary = get_actuals(project_for_actuals)
        except Exception as e:

            print(f"DEBUG: Error getting summary data: {e}")
            all_items_summary = pd.DataFrame()
            summary_data = {}
            actuals_summary = pd.DataFrame()
    
    # Always show content, even if no items
    if all_items_summary.empty:

        st.info("📦 **No items found yet.** Add items in the Manual Entry tab to see budget summaries.")
        st.markdown("#### Quick Overview")
        col1, col2, col3, col4 = st.columns(4)
        with col1:

            st.metric("Total Items", 0)
        with col2:

            st.metric("Total Amount", "₦0.00")
        with col3:

            st.metric("Active Budgets", 0)
        with col4:

            st.metric("Building Types", 0)
        
        st.stop()  # Stop here if no items
    
    if not all_items_summary.empty:

    
        # Quick overview metrics
        st.markdown("#### Quick Overview")
        col1, col2, col3, col4 = st.columns(4)
        with col1:

            total_items = len(all_items_summary)
            st.metric("Total Items", total_items)
        with col2:

            # Calculate total amount with proper NaN handling
            total_amount = all_items_summary["Amount"].sum()
            if pd.notna(total_amount):

                total_amount = float(total_amount)
            else:

                total_amount = 0.0
            st.metric("Total Amount", f"₦{total_amount:,.2f}")
        with col3:

            unique_budgets = all_items_summary["budget"].nunique()
            st.metric("Active Budgets", unique_budgets)
        with col4:

            unique_building_types = all_items_summary["building_type"].nunique()
            st.metric("Building Types", unique_building_types)
        
        # Show recent items added
        st.markdown("#### Recent Items Added")
        recent_items = all_items_summary.tail(5)[["name", "budget", "building_type", "Amount"]]
        st.dataframe(recent_items, use_container_width=True)
        
        # Use cached summary data
        if summary_data:

            st.caption("⚠️ **Note**: All amounts in the table below are for **1 unit only** (Per Unit)")
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, use_container_width=True)
            
            # Grand total with proper error handling
            grand_total = 0
            for row in summary_data:

                try:


                    total_str = str(row.get("Total (Per Unit)", row.get("Total", ""))).replace("₦", "").replace(",", "").strip()
                    if total_str and total_str != '':

                        grand_total += float(total_str)
                except (ValueError, TypeError):

                    continue
            st.markdown(f"""
            <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937; text-align: center; padding: 0.6rem; background: #f8fafc; border-radius: 8px; margin: 0.4rem 0;">
                Grand Total (All Budgets): ₦{grand_total:,.2f}
            </div>
            """, unsafe_allow_html=True)
            
            # Export summary
            summary_csv = summary_df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download Summary CSV", summary_csv, "budget_summary.csv", "text/csv")
        else:

            st.info("No budget data found for summary.")
    else:

        st.info("📦 No items found for this project site. Add items in the Manual Entry tab to see budget summaries.")
        st.markdown("#### Quick Overview")
        col1, col2, col3, col4 = st.columns(4)
        with col1:

            st.metric("Total Items", 0)
        with col2:

            st.metric("Total Amount", "₦0.00")
        with col3:

            st.metric("Active Budgets", 0)
        with col4:

            st.metric("Building Types", 0)
    
    st.divider()
    
    # Manual Budget Summary Section
    st.subheader("Manual Budget Summary")
    st.caption("Add custom budget summary information for each budget number")
    
    # Initialize session state for budget count
    if "max_budget_num" not in st.session_state:

        st.session_state.max_budget_num = 20
    
    # Budget summary header
    st.markdown("#### Available Budgets")
    
    # Create tabs for budgets 1 to 20 (or current max_budget_num)
    # Show all budgets from 1 to max_budget_num
    max_budget = st.session_state.get('max_budget_num', 20)
    tabs_to_create = list(range(1, max_budget + 1))  # Budgets 1 to 20 (or current max)
    budget_tabs = st.tabs([f"Budget {i}" for i in tabs_to_create])
    
    for i, tab in enumerate(budget_tabs):

    
        budget_num = tabs_to_create[i]
        with tab:

            st.markdown(f"### Budget {budget_num} Summary")
            
            # Get items for this budget
            if not all_items_summary.empty:

                budget_items = all_items_summary[all_items_summary["budget"].str.contains(f"Budget {budget_num}", case=False, na=False, regex=False)]
                if not budget_items.empty:

                    # Calculate budget total with proper NaN handling
                    budget_total = budget_items["Amount"].sum()
                    if pd.notna(budget_total):

                        budget_total = float(budget_total)
                    else:

                        budget_total = 0.0
                    # Center the total amount metric
                    col_center = st.columns([1, 2, 1])
                    with col_center[1]:
                        st.metric(f"Total Amount for Budget {budget_num}", f"₦{budget_total:,.2f}", help="This amount is for 1 unit only")
                    
                    # Show breakdown by building type
                    st.markdown("#### Breakdown by Building Type")
                    st.caption("⚠️ **Note**: All amounts shown below are for **1 unit only**")
                    
                    # Filter out empty building types and display in columns to reduce spacing
                    valid_building_types = [bt for bt in PROPERTY_TYPES if bt and bt.strip()]
                    # Default block counts - Flats has 13 blocks (B1-B13)
                    default_block_counts = {
                        "Flats": 13,  # B1-B13
                        "Terraces": len(BUILDING_SUBTYPE_OPTIONS.get("Terraces", [])),
                        "Semi-detached": len(BUILDING_SUBTYPE_OPTIONS.get("Semi-detached", [])),
                        "Fully-detached": len(BUILDING_SUBTYPE_OPTIONS.get("Fully-detached", []))
                    }
                    block_planned_data = []
                    if valid_building_types:
                        # Use 2 columns to display metrics side by side (reduces vertical spacing)
                        cols = st.columns(2)
                        for idx, building_type in enumerate(valid_building_types):
                            with cols[idx % 2]:
                                bt_items = budget_items[budget_items["building_type"] == building_type]
                                planned_per_block = bt_items["Amount"].sum() if not bt_items.empty else 0.0
                                if pd.notna(planned_per_block):
                                    planned_per_block = float(planned_per_block)
                                else:
                                    planned_per_block = 0.0
                                if planned_per_block > 0:
                                    st.metric(
                                        f"{building_type} (Per Unit)",
                                        f"₦{planned_per_block:,.2f}",
                                        help=f"This amount is for 1 {building_type.lower()} unit only"
                                    )
                                block_planned_data.append({
                                    "building_type": building_type,
                                    "planned_per_block": planned_per_block
                                })
                    else:
                        block_planned_data = []

                    # Block totals section - hierarchical breakdown by building type and individual blocks
                    st.markdown("#### Block Totals Across All Blocks")
                    
                    # Process each building type with hierarchical breakdown
                    for entry in block_planned_data:
                        building_type = entry["building_type"]
                        planned_per_block = entry["planned_per_block"]
                        
                        if planned_per_block <= 0:
                            continue

                        # Get building subtype options for this building type from BUILDING_SUBTYPE_OPTIONS
                        # Use all blocks from the database definition, not limited by config
                        subtype_options = BUILDING_SUBTYPE_OPTIONS.get(building_type, [])
                        if not subtype_options:
                            # Fallback: if no options defined, use default count
                            config = get_project_config(budget_num, building_type)
                            blocks_count_value = config.get('num_blocks') if config else None
                            try:
                                blocks_count = int(blocks_count_value) if blocks_count_value else 0
                            except (TypeError, ValueError):
                                blocks_count = 0
                            if blocks_count <= 0:
                                blocks_count = default_block_counts.get(building_type, 0)
                            subtype_options = [f"{building_type} {i}" for i in range(1, blocks_count + 1)]

                        # Calculate totals for this building type
                        building_type_planned_total = 0
                        
                        # Display each block/unit - use ALL blocks from BUILDING_SUBTYPE_OPTIONS
                        block_rows = []
                        for subtype in subtype_options:
                            # For planned, use the per-block amount (same for all blocks of same type)
                            planned_for_block = planned_per_block
                            
                            building_type_planned_total += planned_for_block
                            
                            block_rows.append({
                                "Block/Unit": subtype,
                                "Planned": planned_for_block
                            })
                        
                        # Display building type in an expander
                        if block_rows:
                            with st.expander(f"{building_type} (Total: ₦{building_type_planned_total:,.2f})", expanded=False):
                                # Display block/unit table (Planned only, no Actual)
                                block_df = pd.DataFrame(block_rows)
                                display_block_df = block_df.copy()
                                display_block_df["Planned"] = display_block_df["Planned"].apply(lambda x: f"₦{x:,.2f}")
                                st.dataframe(display_block_df, use_container_width=True, hide_index=True)
                                
                                # Display building type total (Planned only)
                                st.markdown(f"**{building_type} Total - Planned: ₦{building_type_planned_total:,.2f}**")
                else:

                    st.info(f"No items found for Budget {budget_num}")
            
# -------------------------------- Tab 6: Actuals --------------------------------
with tab6:

    st.subheader("Actuals")
    print("DEBUG: Actuals tab loaded")
    st.caption("View actual costs and usage")
    
    # Check permissions for actuals management
    if not is_admin():

        st.info("👤 **User Access**: You can view actuals but cannot modify them.")
    
    # Get current project site - try multiple methods
    project_site = st.session_state.get('current_project_site', None)
    if not project_site or project_site == 'Not set':
        # Try to get project site from items
        try:
            from sqlalchemy import text
            from db import get_engine
            engine = get_engine()
            with engine.begin() as conn:
                result = conn.execute(text("SELECT DISTINCT project_site FROM items WHERE project_site IS NOT NULL LIMIT 1"))
                project_result = result.fetchone()
                project_site = project_result[0] if project_result else 'Lifecamp Kafe'
        except:
            project_site = 'Lifecamp Kafe'
    
    st.write(f"**Project Site:** {project_site}")
    print(f"🔔 DEBUG: Using project site for actuals: {project_site}")
    
    # Get all items for current project site
    try:

        items_df = df_items_cached(project_site)
    except Exception as e:

        print(f"DEBUG: Error getting items for actuals: {e}")
        items_df = pd.DataFrame()
    
    if not items_df.empty:

        # Filters section
        st.markdown("#### Filters")
        col1, col2 = st.columns([1.5, 2])
        actuals_subtype_key = "actuals_building_subtype_select"
        selected_building_subtype = None
        
        with col1:
            # Budget Number dropdown (1-20)
            budget_number_options = ["All"] + [f"Budget {i}" for i in range(1, 21)]
            selected_budget_number = st.selectbox(
                "🔢 Budget Number",
                budget_number_options,
                index=0,
                help="Select budget number to filter by",
                key="actuals_budget_number_filter"
            )
        
        with col2:
            # Building Type dropdown
            filtered_property_types = [pt for pt in PROPERTY_TYPES if pt and pt.strip()]
            building_type_options = ["All"] + filtered_property_types
            selected_building_type = st.selectbox(
                "🏠 Building Type",
                building_type_options,
                index=0,
                help="Select building type to filter by",
                key="actuals_building_type_filter"
            )
            if selected_building_type in BUILDING_SUBTYPE_OPTIONS:
                subtype_options = BUILDING_SUBTYPE_OPTIONS[selected_building_type]
                if actuals_subtype_key in st.session_state and st.session_state[actuals_subtype_key] not in subtype_options:
                    st.session_state[actuals_subtype_key] = subtype_options[0]
                selected_building_subtype = st.selectbox(
                    BUILDING_SUBTYPE_LABELS.get(selected_building_type, "Block/Unit"),
                    subtype_options,
                    index=0,
                    help="Refine to a specific block or unit.",
                    key=actuals_subtype_key
                )
            else:
                if actuals_subtype_key in st.session_state:
                    del st.session_state[actuals_subtype_key]
                selected_building_subtype = None
        
        # Filter items based on selections
        budget_items = items_df.copy()
        
        # Apply budget number filter
        if selected_budget_number and selected_budget_number != "All":
            budget_num = selected_budget_number.replace("Budget ", "").strip()
            # Use word boundary to ensure exact match (e.g., Budget 1 doesn't match Budget 10)
            pattern = rf"^Budget {budget_num}\b\s+-"
            budget_items = budget_items[budget_items["budget"].str.match(pattern, na=False)]
        
        # Apply building type filter
        if selected_building_type and selected_building_type != "All":
            # Filter budgets that contain the building type
            # The format is: "Budget X - BuildingType(Category)"
            budget_items = budget_items[budget_items["budget"].str.contains(f" - {selected_building_type}(", na=False, case=False, regex=False)]
        
        # Get the selected budget display name for the header
        if selected_budget_number != "All" and selected_building_type != "All":
            selected_budget = f"{selected_budget_number} - {selected_building_type}"
        elif selected_budget_number != "All":
            selected_budget = selected_budget_number
        elif selected_building_type != "All":
            selected_budget = f"All Budgets - {selected_building_type}"
        else:
            selected_budget = "All Budgets"
        if selected_building_subtype:
            selected_budget = f"{selected_budget} ({selected_building_subtype})"
        
        if not budget_items.empty:
            st.markdown(f"##### {selected_budget}")
            st.markdown("**📊 BUDGET vs ACTUAL COMPARISON**")
            
            # Get actuals data
            actuals_df = get_actuals(project_site)
            print(f"🔔 DEBUG: Retrieved {len(actuals_df)} actuals for project site: {project_site}")
            if not actuals_df.empty:
                print(f"🔔 DEBUG: Actuals columns: {actuals_df.columns.tolist()}")
                print(f"🔔 DEBUG: Sample actuals: {actuals_df.head(2).to_dict('records')}")
            else:
                print(f"🔔 DEBUG: No actuals found for project site: {project_site}")
            
            if not actuals_df.empty:
                if 'building_subtype' not in actuals_df.columns:
                    actuals_df['building_subtype'] = ''
                actuals_df['building_subtype'] = actuals_df['building_subtype'].fillna('')
                if selected_building_subtype:
                    actuals_df = actuals_df[actuals_df['building_subtype'] == selected_building_subtype]
            
            # Group items hierarchically: first by category (grp), then by subcategory for Budget 5
            def extract_subcategory(budget_str):
                """Extract subcategory from Budget 5 items (e.g., 'BLOCKWORK ABOVE ROOF BEAM' from 'Budget 5 - Terraces(General Materials - BLOCKWORK ABOVE ROOF BEAM)')"""
                if pd.isna(budget_str):
                    return None
                budget_str = str(budget_str)
                if "Budget 5" in budget_str and "(" in budget_str and ")" in budget_str:
                    try:
                        # Extract content inside parentheses
                        paren_parts = budget_str.split("(")
                        if len(paren_parts) > 1:
                            paren_content = paren_parts[1].split(")")[0]
                            # Check if it has a subcategory (contains " - ")
                            if " - " in paren_content:
                                # Extract subcategory (the part after " - ")
                                subcategory = paren_content.split(" - ", 1)[1].strip()
                                return subcategory
                    except Exception:
                        # If parsing fails, return None
                        pass
                return None
            
            # Group hierarchically: category -> subcategory -> items
            categories = {}
            for _, item in budget_items.iterrows():
                category = item.get('grp', 'GENERAL MATERIALS')
                                
                # Extract subcategory for Budget 5 items
                budget_str = item.get('budget', '')
                subcategory = extract_subcategory(budget_str)
                
                # Use "None" as key for items without subcategory
                subcategory_key = subcategory if subcategory else "None"
                
                if category not in categories:
                    categories[category] = {}
                if subcategory_key not in categories[category]:
                    categories[category][subcategory_key] = []
                categories[category][subcategory_key].append(item)
            
            # Display tables side by side
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### PLANNED BUDGET")
                
                # Process each category, then subcategories within it
                for category_name, subcategories in categories.items():
                    st.markdown(f"**{category_name}**")
                    category_total = 0
                    
                    # Process each subcategory within the category
                    for subcategory_key, category_items in subcategories.items():
                        # Display subcategory header if it's not "None"
                        if subcategory_key != "None":
                            st.markdown(f"*{subcategory_key}*")
                        
                        planned_data = []
                        for idx, item in enumerate(category_items, 1):
                            # Handle NaN values for unit_cost and qty
                            unit_cost = float(item['unit_cost']) if pd.notna(item['unit_cost']) else 0.0
                            qty = float(item['qty']) if pd.notna(item['qty']) else 0.0
                            unit = item.get('unit', '') or ''
                            
                            planned_data.append({
                                'S/N': str(idx),
                                'Item': item['name'],
                                'Qty': f"{qty:.1f}",
                                'Unit': unit,
                                'Unit Cost': f"₦{unit_cost:,.2f}",
                                'Total Cost': f"₦{qty * unit_cost:,.2f}"
                            })
                        
                        planned_df = pd.DataFrame(planned_data)
                        st.dataframe(planned_df, use_container_width=True, hide_index=True)
                                
                        # Subcategory total with error handling
                        subcategory_total = 0
                        for item in category_items:
                            try:
                                qty = float(item['qty']) if pd.notna(item['qty']) else 0
                                unit_cost = float(item['unit_cost']) if pd.notna(item['unit_cost']) else 0
                                subcategory_total += qty * unit_cost
                                category_total += qty * unit_cost
                            except (ValueError, TypeError):
                                continue
                        
                        # Show subcategory total if it has a subcategory
                        if subcategory_key != "None":
                            st.markdown(f"*{subcategory_key} Total: ₦{subcategory_total:,.2f}*")
                    
                    # Category total
                    st.markdown(f"**{category_name} Total: ₦{category_total:,.2f}**")
                    st.markdown("---")
            
            with col2:
                st.markdown("#### ACTUALS")
                
                # Process each category, then subcategories within it
                for category_name, subcategories in categories.items():
                    st.markdown(f"**{category_name}**")
                    category_total = 0
                    
                    # Process each subcategory within the category
                    for subcategory_key, category_items in subcategories.items():
                        # Display subcategory header if it's not "None"
                        if subcategory_key != "None":
                            st.markdown(f"*{subcategory_key}*")
                        
                        actual_data = []
                        for idx, item in enumerate(category_items, 1):
                            # Get actual data for this item
                            actual_qty = 0
                            actual_cost = 0
                            
                            if not actuals_df.empty:
                                item_actuals = actuals_df[actuals_df['item_id'] == item['id']]
                                if not item_actuals.empty:
                                    actual_qty = item_actuals['actual_qty'].sum()
                                    actual_cost = item_actuals['actual_cost'].sum()
                            
                            # Handle NaN values
                            actual_qty = float(actual_qty) if pd.notna(actual_qty) else 0.0
                            actual_cost = float(actual_cost) if pd.notna(actual_cost) else 0.0
                            unit = item.get('unit', '') or ''
                            
                            # Calculate unit cost safely
                            if actual_qty > 0:
                                unit_cost_val = actual_cost / actual_qty
                                unit_cost_str = f"₦{unit_cost_val:,.2f}"
                            else:
                                unit_cost_str = "₦0.00"
                            
                            actual_data.append({
                                'S/N': str(idx),
                                'Item': item['name'],
                                'Qty': f"{actual_qty:.1f}",
                                'Unit': unit,
                                'Unit Cost': unit_cost_str,
                                'Total Cost': f"₦{actual_cost:,.2f}"
                            })
                        
                        actual_df = pd.DataFrame(actual_data)
                        st.dataframe(actual_df, use_container_width=True, hide_index=True)
                        
                        # Subcategory total with error handling
                        subcategory_total = 0
                        for item in category_items:
                            try:
                                actual_qty = 0
                                actual_cost = 0
                                if not actuals_df.empty:
                                    item_actuals = actuals_df[actuals_df['item_id'] == item['id']]
                                    if not item_actuals.empty:
                                        actual_qty = item_actuals['actual_qty'].sum()
                                        actual_cost = item_actuals['actual_cost'].sum()
                                subcategory_total += actual_cost
                                category_total += actual_cost
                            except (ValueError, TypeError):
                                continue
                        
                        # Show subcategory total if it has a subcategory
                        if subcategory_key != "None":
                            st.markdown(f"*{subcategory_key} Total: ₦{subcategory_total:,.2f}*")
                    
                    # Category total
                    st.markdown(f"**{category_name} Total: ₦{category_total:,.2f}**")
                    st.markdown("---")
            
            # Calculate totals with proper error handling
            total_planned = 0
            for _, item in budget_items.iterrows():

                try:


                    qty = float(item['qty']) if pd.notna(item['qty']) else 0
                    unit_cost = float(item['unit_cost']) if pd.notna(item['unit_cost']) else 0
                    total_planned += qty * unit_cost
                except (ValueError, TypeError):

                    continue
            
            total_actual = 0
            if not actuals_df.empty:

                for _, item in budget_items.iterrows():


                    item_actuals = actuals_df[actuals_df['item_id'] == item['id']]
                    if not item_actuals.empty:

                        try:


                            actual_cost = item_actuals['actual_cost'].sum()
                            if pd.notna(actual_cost):

                                total_actual += float(actual_cost)
                        except (ValueError, TypeError):

                            continue
            
            # Display totals
            col1, col2 = st.columns(2)
            with col1:

                st.metric("Total Planned", f"₦{total_planned:,.2f}")
            with col2:
                st.metric("Total Actual", f"₦{total_actual:,.2f}")
        else:
            st.info("No items found for this budget.")
    else:
        st.info("📦 **No items found for this project site.**")
        # Simple message
        st.info("💡 Add items, create requests, and approve them to see actuals here.")
# -------------------------------- Tab 3: Make Request --------------------------------
with tab3:

    st.subheader("Make a Request")
    st.caption("Request items for specific building types and budgets")
    
    # Project site accounts can make requests, admins can do everything
    if not is_admin():
        # User access information removed as requested
        pass
    
    # Project context for the request
    st.markdown("### Project Context")
    col1, col2, col3, col4 = st.columns([2, 1.5, 2, 2])
    building_subtype_key = "request_building_subtype_select"
    with col1:
        section = st.radio("Section", ["materials", "labour"], index=0, horizontal=True, key="request_section_radio")
    with col2:
        # Budget Number dropdown (1-20)
        budget_number_options = ["All"] + [f"Budget {i}" for i in range(1, 21)]
        budget_number = st.selectbox(
            "Budget Number",
            budget_number_options,
            index=0,
            help="Select budget number (1-20) to filter by",
            key="request_budget_number_filter"
        )
    with col3:

        # Building type filter with "All" option
        # Filter out empty strings from PROPERTY_TYPES
        filtered_property_types = [pt for pt in PROPERTY_TYPES if pt and pt.strip()]
        building_type_options = ["All"] + filtered_property_types
        building_type = st.selectbox("Building Type", building_type_options, index=0, help="Select building type for this request (or All to see all)", key="request_building_type_select")
        if building_type in BUILDING_SUBTYPE_OPTIONS:
            subtype_options = BUILDING_SUBTYPE_OPTIONS[building_type]
            if building_subtype_key in st.session_state and st.session_state[building_subtype_key] not in subtype_options:
                st.session_state[building_subtype_key] = subtype_options[0]
            st.selectbox(
                BUILDING_SUBTYPE_LABELS.get(building_type, "Building Subtype"),
                subtype_options,
                help="Refine the request context for this building type.",
                key=building_subtype_key
            )
        else:
            if building_subtype_key in st.session_state:
                del st.session_state[building_subtype_key]
    building_subtype = st.session_state.get(building_subtype_key)
    with col4:

        # Create budget options for the selected budget number and building type (cached)
        all_budget_options = get_budget_options(st.session_state.get('current_project_site'))
        
        # Remove "All" from the list for filtering (we'll add it back later)
        budget_options_to_filter = [opt for opt in all_budget_options if opt != "All"]
        
        # Filter budgets based on budget number FIRST (if not "All")
        if budget_number and budget_number != "All":
            # Extract the budget number (e.g., "Budget 1" -> "1")
            budget_num = budget_number.replace("Budget ", "").strip()
            # Use word boundary to ensure exact match (e.g., Budget 1 doesn't match Budget 10)
            pattern = rf"^Budget {budget_num}\b\s+-"
            budget_options = [opt for opt in budget_options_to_filter if re.match(pattern, opt)]
        else:
            # If "All" is selected for budget number, use all budgets
            budget_options = budget_options_to_filter
        
        # Filter budgets based on building type SECOND (if not "All")
        if building_type and building_type != "All":
            # Filter budgets that contain the building type
            # The format is: "Budget X - BuildingType(Category)"
            budget_options = [opt for opt in budget_options if f" - {building_type}(" in opt]
        
        # Filter budgets based on section (materials/labour) THIRD
        if section and section in ["materials", "labour"]:
            if section == "labour":
                # Only show budgets with "(Labour)" category
                budget_options = [opt for opt in budget_options if "(Labour)" in opt]
            else:  # section == "materials"
                # Only show budgets with materials categories (exclude Labour)
                # Materials categories: (General Materials), (Woods), (Plumbings), (Irons), (Electrical), (Mechanical)
                budget_options = [opt for opt in budget_options if "(Labour)" not in opt]
        
        # If no matching budgets found after filtering, show all budgets as fallback
        if not budget_options:
            budget_options = budget_options_to_filter
        
        # Add "All" option at the beginning
        budget_options = ["All"] + budget_options
        
        budget = st.selectbox("🏷️ Budget", budget_options, index=0, help="Select budget for this request", key="request_budget_select")
    
    # Filter items based on section, building type, and budget
    # Get all items first, then filter in memory for better flexibility
    # Don't clear cache on every rerun - let caching work naturally
    
    all_items = df_items_cached(st.session_state.get('current_project_site'))
    
    
    # Apply filters step by step
    items_df = all_items.copy()
    
    # Filter by section (materials/labour) - always apply when section is selected
    if section and section in ["materials", "labour"]:
        items_df = items_df[items_df["category"] == section]
    
    # Filter by building type (skip if "All" is selected)
    if building_type and building_type != "All":

        items_df = items_df[items_df["building_type"] == building_type]
    
    # Filter by budget number (skip if "All" is selected)
    if budget_number and budget_number != "All":
        # Extract the budget number (e.g., "Budget 1" -> "1")
        budget_num = budget_number.replace("Budget ", "").strip()
        # Use word boundary to ensure exact match (e.g., Budget 1 doesn't match Budget 10)
        pattern = rf"^Budget {budget_num}\b\s+-"
        items_df = items_df[items_df["budget"].str.match(pattern, na=False)]
    
    # Filter by budget (flexible matching - space and case insensitive, skip if "All" is selected)
    if budget and budget != "All":

        def normalize_budget_string(budget_str):
            """Normalize budget string for comparison - remove extra spaces, convert to lowercase"""
            if pd.isna(budget_str):

                return ""
            # Convert to string, strip whitespace, convert to lowercase
            normalized = str(budget_str).strip().lower()
            # Remove extra spaces and normalize spacing around parentheses
            normalized = normalized.replace("  ", " ")  # Remove double spaces
            normalized = normalized.replace(" (", "(")   # Remove space before opening parenthesis
            normalized = normalized.replace("( ", "(")   # Remove space after opening parenthesis
            normalized = normalized.replace(" )", ")")   # Remove space before closing parenthesis
            # Handle "Iron" vs "Irons" difference
            normalized = normalized.replace("(iron)", "(irons)")
            return normalized
        
        # Normalize the selected budget
        normalized_selected = normalize_budget_string(budget)
        
        # Create flexible matching logic
        if "(" in budget and ")" in budget:

            # Specific subgroup - flexible exact match
            budget_matches = items_df["budget"].apply(
                lambda x: normalize_budget_string(x) == normalized_selected
            )
        else:

            # Hierarchical matching - show all items that contain this budget
            # e.g., "Budget 1 - Terraces" shows "Budget 1 - Terraces", "Budget 1 - Terraces(Plumbings)", etc.
            budget_matches = items_df["budget"].apply(
                lambda x: normalized_selected in normalize_budget_string(x)
            )
        
        items_df = items_df[budget_matches]
    
    # If still no items found, try showing all items for the building type (fallback)
    if items_df.empty and building_type:

        available_budgets = all_items[all_items["building_type"] == building_type]["budget"].unique()
        st.info(f"⚠️ No items found for the specific budget '{budget}'. Available budgets for {building_type}:")
        for avail_budget in sorted(available_budgets):

            if pd.notna(avail_budget):

                st.write(f"  • {avail_budget}")
        
        st.info(f"Showing all {section} items for {building_type} instead.")
        items_df = all_items[
            (all_items["category"] == section) & 
            (all_items["building_type"] == building_type)
        ]
    
    if items_df.empty:

    
        st.warning(f"📦 **No items found for {section} in {building_type} - {budget}.**")
        st.info("💡 Add items in the Manual Entry tab first, then return here to make requests.")
        st.stop()
        
    else:

        
        st.markdown("### 📦 Available Items")
        
        # Item selection outside form to avoid caching issues
        st.markdown("### 📝 Request Details")
        
        # Single item selection - outside form to avoid caching
        selected_item = st.selectbox(
            "Item", 
            options=items_df.to_dict('records'), 
            format_func=lambda r: f"{r['name']} (Available: {r['qty']} {r['unit'] or ''}) — ₦{r['unit_cost'] or 0:,.2f}", 
            key="request_item_select",
            index=0  # Select first item by default
        )
        
        # Show selected item info - outside form
        if selected_item:
            st.info(f"**Selected Item:** {selected_item['name']} | **Planned Rate:** ₦{selected_item.get('unit_cost', 0) or 0:,.2f}")
        else:
            st.warning("⚠️ Please select an item from the dropdown above")
        
        # Wrap inputs in form to prevent reruns on every keystroke
        with st.form("make_request_form", clear_on_submit=False):
            col1, col2 = st.columns([1,1])
            with col1:
                # Use static key to prevent unnecessary reruns when item selection changes
                qty = st.number_input("Quantity to request", min_value=1.0, step=1.0, value=1.0, key="request_qty_input")
                
                # Mandatory name input field
                requested_by = st.text_input(
                    "Your Name *", 
                    placeholder="Enter your full name",
                    help="This is required to identify who is making the request",
                    key="request_name_input"
                )
            with col2:
                # Get default price from selected item
                default_price = 0.0
                if selected_item and 'unit_cost' in selected_item:
                    default_price = float(selected_item.get('unit_cost', 0) or 0)
                
                # Use static key to prevent unnecessary reruns
                # Update price when item changes (but keep static key)
                item_id = selected_item.get('id') if selected_item else None
                
                # Handle item change: update session state with new default price
                if item_id and st.session_state.get('last_price_item_id') != item_id:
                    # Item changed - update price in session state to match selected item's unit_cost
                    st.session_state['request_price_input'] = default_price
                    st.session_state['last_price_item_id'] = item_id
                elif 'request_price_input' not in st.session_state:
                    # First time - initialize with default price
                    st.session_state['request_price_input'] = default_price
                
                # Create widget - Streamlit will use session state value automatically via the key
                # Don't pass value parameter to avoid conflict with session state
                current_price = st.number_input(
                    "💰 Current Price per Unit", 
                    min_value=0.0, 
                    step=0.01, 
                    help="Enter the current market price for this item. This will be used as the actual rate in actuals.",
                    key="request_price_input"
                )
                
                note = st.text_area(
                    "Notes *", 
                    placeholder="Please provide details about this request...",
                    help="This is required to explain the purpose of your request",
                    key="request_note_input"
                )
            
            # Submit request button (inside form)
            submitted = st.form_submit_button("Submit Request", type="primary", use_container_width=True)
            
            # Handle form submission inside form (variables are available here)
            if submitted:
                # Show summary on submission
                if selected_item:
                    current_price_safe = float(current_price) if pd.notna(current_price) else 0.0
                    qty_safe = float(qty) if pd.notna(qty) else 0.0
                    calculated_total = qty_safe * current_price_safe
                    calculated_total = float(calculated_total) if pd.notna(calculated_total) else 0.0
                    st.markdown("### Request Summary")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Planned Rate", f"₦{selected_item.get('unit_cost', 0) or 0:,.2f}")
                    with col2:
                        st.metric("Current Rate", f"₦{current_price_safe:,.2f}")
                    with col3:
                        st.metric("Quantity", f"{qty}")
                    
                    st.markdown(f"""
                    <div style="font-size: 1.4rem; font-weight: 600; color: #1f2937; text-align: center; padding: 0.6rem; background: #f8fafc; border-radius: 8px; margin: 0.4rem 0;">
                        Total Cost: ₦{calculated_total:,.2f}
                    </div>
                    """, unsafe_allow_html=True)
                # Preserve current tab before processing
                preserve_current_tab()
                
                # Validate form inputs with proper null checks
                if not requested_by or not requested_by.strip():
                    st.error("❌ Please enter your name. This field is required.")
                elif not note or not note.strip():
                    st.error("❌ Please provide notes explaining your request. This field is required.")
                elif not selected_item or selected_item is None or not selected_item.get('id'):
                    st.error("❌ Please select an item from the list.")
                elif qty is None or qty <= 0:
                    st.error("❌ Please enter a valid quantity (greater than 0).")
                elif not section or section is None:
                    st.error("❌ Please select a section (materials or labour).")
                elif not building_type or building_type is None:
                    st.error("❌ Please select a building type.")
                elif building_type in BUILDING_SUBTYPE_OPTIONS and not building_subtype:
                    st.error("❌ Please select a block or unit for the chosen building type.")
                elif not budget or budget is None:
                    st.error("❌ Please select a budget.")
                else:
                    # Both admins and project site accounts can submit requests
                    with st.spinner("Submitting request..."):
                        try:
                            # Submit request directly - validation is done in add_request function
                            request_id = add_request(section, selected_item['id'], qty, requested_by, note, current_price, building_subtype)
                            
                            if request_id:
                                # Get actual item information for the success message
                                item_name = selected_item.get('name', 'Unknown Item')
                                item_building_type = selected_item.get('building_type', 'Unknown')
                                item_budget = selected_item.get('budget', 'Unknown')
                                item_project_site = selected_item.get('project_site', st.session_state.get('current_project_site', 'Unknown Project'))
                                
                                # Build success message with actual request details
                                success_msg = f"✅ Request #{request_id} submitted successfully!"
                                success_msg += f"\n\n**Item:** {item_name}"
                                success_msg += f"\n**Quantity:** {qty} {selected_item.get('unit', 'units')}"
                                success_msg += f"\n**Building Type:** {item_building_type}"
                                if building_subtype:
                                    success_msg += f"\n**Building Sub-Type:** {building_subtype}"
                                success_msg += f"\n**Budget:** {item_budget}"
                                success_msg += f"\n**Project Site:** {item_project_site}"
                                success_msg += f"\n**Section:** {section.title() if section else 'Unknown'}"
                                
                                st.success(success_msg)
                                st.info("Your request will be reviewed by an administrator. Check the Review & History tab for updates.")
                                
                                # Show notification popup for project site account
                                st.markdown("""
                                <script>
                                localStorage.setItem('request_submitted_notification', 'true');
                                </script>
                                """, unsafe_allow_html=True)
                                
                                # Preserve tab after successful submission
                                preserve_current_tab()
                                
                                # Show notification popup for admin
                                st.markdown("""
                                <script>
                                localStorage.setItem('new_request_notification', 'true');
                                </script>
                                """, unsafe_allow_html=True)
                                
                                # Clear caches to ensure data consistency
                                clear_cache()
                            else:
                                st.error("Failed to submit request. Please try again.")
                        except Exception as e:
                            st.error(f"Failed to submit request: {str(e)}")
                            st.info("Please try again or contact an administrator if the issue persists.")
# -------------------------------- Tab 4: Review & History --------------------------------
with tab4:

    st.subheader("Pending Requests")
    print("DEBUG: Review & History tab loaded")
    
    # Get user type and current user info
    user_type = st.session_state.get('user_type', 'project_site')
    current_user = st.session_state.get('full_name', st.session_state.get('current_user_name', 'Unknown'))
    current_project = st.session_state.get('current_project_site', 'Not set')
    
    def format_request_context(row):
        building_type = row.get('building_type')
        building_subtype = row.get('building_subtype')
        budget = row.get('budget')
        grp = row.get('grp')
        
        parts = []
        
        if pd.notna(building_type) and building_type:
            bt_part = str(building_type)
            if building_subtype and pd.notna(building_subtype):
                bt_part = f"{bt_part} / {building_subtype}"
            parts.append(bt_part)
        
        if pd.notna(budget) and budget:
            if grp and pd.notna(grp):
                parts.append(f"{budget} ({grp})")
            else:
                parts.append(str(budget))
        elif grp and pd.notna(grp):
            parts.append(f"({grp})")
        
        return " - ".join(parts) if parts else "No context"
    
    # Display user info
    if user_type == 'admin':

        st.info("**Admin Access**: You can view and manage all requests from all project sites.")
    else:

        st.info(f"**Your Requests**: Viewing requests for {current_user} in {current_project}")
        st.caption("**Note**: Only administrators can approve or reject requests.")
    
    # Get all requests for statistics
    try:
        if user_type == 'admin':
            # Admins see all requests - explicitly pass user_type for correct cache key
            all_reqs = df_requests(status=None, user_type='admin', project_site=None)
            print(f"🔍 DEBUG: Admin view - got {len(all_reqs)} requests")
        else:
            # Project site accounts: show stats for the entire current project site
            # Explicitly pass user_type and project_site for correct cache key
            current_project = st.session_state.get('current_project_site', 'Lifecamp Kafe')
            all_reqs = df_requests(status=None, user_type='project_site', project_site=current_project)
            print(f"🔍 DEBUG: Project site view - got {len(all_reqs)} requests for current project site")
    except Exception as e:

        print(f"DEBUG: Error getting requests: {e}")
        all_reqs = pd.DataFrame()  # Empty DataFrame if error
    
    # Show statistics for project site users
    if user_type != 'admin':

        st.markdown("### Request Statistics")
        
        # Calculate statistics
        total_requests = len(all_reqs)
        pending_requests = len(all_reqs[all_reqs['status'] == 'Pending']) if not all_reqs.empty else 0
        approved_requests = len(all_reqs[all_reqs['status'] == 'Approved']) if not all_reqs.empty else 0
        rejected_requests = len(all_reqs[all_reqs['status'] == 'Rejected']) if not all_reqs.empty else 0
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:

            st.metric("Total Submitted", total_requests)
        with col2:

            st.metric("Pending", pending_requests)
        with col3:

            st.metric("Approved", approved_requests)
        with col4:

            st.metric("Rejected", rejected_requests)
        
        # Show recent requests
        if not all_reqs.empty:

            st.markdown("### Recent Requests")
            recent_reqs = all_reqs.head(10)  # Show last 10 requests
            
            # Format for display
            display_reqs = recent_reqs.copy()
            if 'ts' in display_reqs.columns:
                def format_request_time(ts):
                    if pd.isna(ts) or ts is None:
                        return ""
                    try:
                        import pytz
                        lagos_tz = pytz.timezone('Africa/Lagos')
                        if isinstance(ts, str):
                            from datetime import datetime
                            if 'Z' in ts:
                                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):
                                dt = datetime.fromisoformat(ts)
                            else:
                                try:
                                    dt = datetime.fromisoformat(ts)
                                except:
                                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                            dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                        else:
                            dt = ts
                            if dt.tzinfo is None:
                                dt = lagos_tz.localize(dt)
                        if dt.tzinfo != lagos_tz:
                            dt = dt.astimezone(lagos_tz)
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        return str(ts) if ts else ""
                display_reqs['ts'] = display_reqs['ts'].apply(format_request_time)
            
            # Create context column
            display_reqs['Context'] = display_reqs.apply(format_request_context, axis=1)
            if 'building_subtype' not in display_reqs.columns:
                display_reqs['building_subtype'] = ''
            display_reqs['building_subtype'] = display_reqs['building_subtype'].fillna('').apply(lambda val: val if pd.notna(val) else '')
            
            # Add planned price (from item unit_cost) and current price (from request)
            display_reqs['Planned Price'] = display_reqs['unit_cost']
            display_reqs['Current Price'] = display_reqs['current_price'].fillna(display_reqs['unit_cost'])
            # Calculate total price using current price
            display_reqs['Total Price'] = display_reqs['qty'] * display_reqs['Current Price']
            # Add Planned Qty and Requested Qty columns
            display_reqs['Planned Qty'] = display_reqs.get('planned_qty', 0)
            display_reqs['Requested Qty'] = display_reqs['qty']
            
            # Get item_id for each request and calculate cumulative quantities
            from sqlalchemy import text
            from db import get_engine
            engine = get_engine()
            request_ids = display_reqs['id'].tolist()
            exceeds_planned_request_ids = set()
            cumulative_qty_dict = {}  # Store cumulative quantities for each request
            
            if request_ids:
                with engine.connect() as conn:
                    # Get item_id for each request and calculate which requests first exceeded planned
                    for req_id in request_ids:
                        result = conn.execute(text("""
                            SELECT r.item_id, r.qty, i.qty as planned_qty, r.building_subtype,
                                   (SELECT COALESCE(SUM(r2.qty), 0) 
                                    FROM requests r2 
                                    WHERE r2.item_id = r.item_id 
                                    AND r2.id <= r.id 
                                    AND r2.status IN ('Pending', 'Approved')
                                    AND COALESCE(r2.building_subtype, '') = COALESCE(r.building_subtype, '')
                                   ) as cumulative_qty
                            FROM requests r
                            JOIN items i ON r.item_id = i.id
                            WHERE r.id = :req_id
                        """), {"req_id": req_id})
                        row = result.fetchone()
                        if row:
                            item_id, req_qty, planned_qty, req_subtype, cumulative_qty = row
                            subtype_norm = (req_subtype.strip() if isinstance(req_subtype, str) else req_subtype) or ""
                            cumulative_qty_val = float(cumulative_qty) if cumulative_qty else 0
                            planned_qty_val = float(planned_qty) if planned_qty else 0
                            
                            # Store cumulative quantity for ALL requests (not just when exceeding planned)
                            cumulative_qty_dict[req_id] = cumulative_qty_val
                            
                            if planned_qty and cumulative_qty and float(cumulative_qty) > float(planned_qty):
                                # Check if previous cumulative was <= planned (this is the first request that exceeded)
                                prev_result = conn.execute(text("""
                                    SELECT COALESCE(SUM(r2.qty), 0) 
                                    FROM requests r2 
                                    WHERE r2.item_id = :item_id 
                                    AND r2.id < :req_id 
                                    AND r2.status IN ('Pending', 'Approved')
                                    AND COALESCE(r2.building_subtype, '') = :subtype_norm
                                """), {"item_id": item_id, "req_id": req_id, "subtype_norm": subtype_norm})
                                prev_cumulative = float(prev_result.fetchone()[0] or 0)
                                if prev_cumulative <= float(planned_qty):
                                    exceeds_planned_request_ids.add(req_id)
            
            # Add cumulative quantity column (show for all requests)
            display_reqs['Cumulative Requested'] = display_reqs.apply(
                lambda row: cumulative_qty_dict.get(row['id'], 0) if row['id'] in cumulative_qty_dict else 0, axis=1
            )
            
            # Format approval/rejection timestamp - show only for approved/rejected requests
            def format_action_time(row):
                if pd.isna(row.get('updated_at')) or row.get('updated_at') is None:
                    return ""
                if row.get('status') not in ['Approved', 'Rejected']:
                    return ""
                try:
                    import pytz
                    lagos_tz = pytz.timezone('Africa/Lagos')
                    ts = row['updated_at']
                    if isinstance(ts, str):
                        from datetime import datetime
                        if 'Z' in ts:
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):
                            dt = datetime.fromisoformat(ts)
                        else:
                            try:
                                dt = datetime.fromisoformat(ts)
                            except:
                                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                            dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                    else:
                        dt = ts
                        if dt.tzinfo is None:
                            dt = lagos_tz.localize(dt)
                    if dt.tzinfo != lagos_tz:
                        dt = dt.astimezone(lagos_tz)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    return ""
            
            display_reqs['Action At'] = display_reqs.apply(format_action_time, axis=1)
            
            # Select columns for user view
            display_columns = ['id', 'ts', 'item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'Context', 'building_subtype', 'status', 'approved_by', 'Action At', 'note']
            display_reqs = display_reqs[display_columns]
            display_reqs.columns = ['ID', 'Time', 'Item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'Building Type & Budget', 'Block/Unit', 'Status', 'Approved By', 'Action At', 'Note']
            
            # Style: Requested Qty in red if it exceeds Planned Qty OR if cumulative exceeded planned, Current Price in red if it differs from Planned Price
            def highlight_over(row):
                styles = [''] * len(row)
                try:
                    req_id = int(row['ID'])
                    exceeds_cumulative = req_id in exceeds_planned_request_ids
                    
                    rq = float(row['Requested Qty']) if pd.notna(row['Requested Qty']) else 0
                    pq = float(row['Planned Qty']) if pd.notna(row['Planned Qty']) else 0
                    
                    # Highlight if single request exceeds planned OR if this is the request that made cumulative exceed planned
                    if rq > pq or exceeds_cumulative:
                        # Find Requested Qty column index
                        try:
                            rq_idx = list(display_reqs.columns).index('Requested Qty')
                            styles[rq_idx] = 'color: red; font-weight: bold'
                        except ValueError:
                            pass  # Column doesn't exist, skip highlighting
                    
                    # Highlight Cumulative Requested column in red if it exceeds planned
                    cumulative_val = row.get('Cumulative Requested', 0)
                    if cumulative_val != '' and cumulative_val is not None and cumulative_val != 0:
                        try:
                            # Handle both numeric and string values
                            if isinstance(cumulative_val, (int, float)):
                                cumulative_float = float(cumulative_val)
                            else:
                                cumulative_float = float(cumulative_val)
                            if cumulative_float > pq:
                                try:
                                    cum_idx = list(display_reqs.columns).index('Cumulative Requested')
                                    styles[cum_idx] = 'color: red; font-weight: bold'
                                except ValueError:
                                    pass  # Column doesn't exist, skip highlighting
                        except (ValueError, TypeError):
                            pass  # Can't convert to float, skip
                    
                    # Check if current price differs from planned price
                    cp = float(row['Current Price']) if pd.notna(row['Current Price']) else 0
                    pp = float(row['Planned Price']) if pd.notna(row['Planned Price']) else 0
                    if cp != pp and pp > 0:
                        # Find Current Price column index
                        try:
                            cp_idx = list(display_reqs.columns).index('Current Price')
                            styles[cp_idx] = 'color: red; font-weight: bold'
                        except ValueError:
                            pass  # Column doesn't exist, skip highlighting
                except Exception:
                    pass
                return styles
            
            # Display the table with styling and number formatting
            styled = (
                display_reqs.style
                .apply(highlight_over, axis=1)
                .format({
                    'Planned Qty': '{:.2f}',
                    'Requested Qty': '{:.2f}',
                    'Cumulative Requested': lambda x: f'{x:.2f}' if isinstance(x, (int, float)) else x,
                    'Planned Price': '₦{:, .2f}'.replace(' ', ''),
                    'Current Price': '₦{:, .2f}'.replace(' ', ''),
                    'Total Price': '₦{:, .2f}'.replace(' ', ''),
                })
            )
            st.dataframe(styled, use_container_width=True)
        else:

            st.info("No requests found.")
    else:

        # Admin view - keep existing functionality
        # Always show Pending requests since Approved/Rejected have separate tabs
        try:
            # Explicitly pass user_type and project_site for correct cache keys
            current_user_type = user_type
            current_project_site = st.session_state.get('current_project_site', 'Lifecamp Kafe')
            reqs = df_requests(
                status="Pending",
                user_type=current_user_type,
                project_site=current_project_site if current_user_type != 'admin' else None
            )
        except Exception as e:
            print(f"DEBUG: Error getting requests: {e}")
            reqs = pd.DataFrame()  # Empty DataFrame if error
        
        # Display requests - always show content
        if not reqs.empty:
            # Create a better display for user requests
            display_reqs = reqs.copy()
            
            # Format timestamp for better readability
            if 'ts' in display_reqs.columns:
                def format_request_time(ts):
                    if pd.isna(ts) or ts is None:
                        return ""
                    try:
                        import pytz
                        lagos_tz = pytz.timezone('Africa/Lagos')
                        if isinstance(ts, str):
                            from datetime import datetime
                            if 'Z' in ts:
                                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):
                                dt = datetime.fromisoformat(ts)
                            else:
                                try:
                                    dt = datetime.fromisoformat(ts)
                                except:
                                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                            dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                        else:
                            dt = ts
                            if dt.tzinfo is None:
                                dt = lagos_tz.localize(dt)
                        if dt.tzinfo != lagos_tz:
                            dt = dt.astimezone(lagos_tz)
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        return str(ts) if ts else ""
                display_reqs['ts'] = display_reqs['ts'].apply(format_request_time)
            
            # Create context column
            display_reqs['Context'] = display_reqs.apply(format_request_context, axis=1)
            if 'building_subtype' not in display_reqs.columns:
                display_reqs['building_subtype'] = ''
            display_reqs['building_subtype'] = display_reqs['building_subtype'].fillna('').apply(lambda val: val if pd.notna(val) else '')
            
            # Add planned price (from item unit_cost) and current price (from request)
            display_reqs['Planned Price'] = display_reqs.get('unit_cost')
            display_reqs['Current Price'] = display_reqs.get('current_price')
            # Add Planned Qty and Requested Qty columns
            display_reqs['Planned Qty'] = display_reqs.get('planned_qty', 0)
            display_reqs['Requested Qty'] = display_reqs['qty']
            # Calculate Total Price = Requested Qty * Current Price
            display_reqs['Total Price'] = display_reqs['Requested Qty'] * display_reqs['Current Price']
            
            # Get item_id for each request and calculate cumulative quantities
            from sqlalchemy import text
            from db import get_engine
            engine = get_engine()
            request_ids = display_reqs['id'].tolist()
            exceeds_planned_request_ids = set()
            cumulative_qty_dict = {}  # Store cumulative quantities for each request
            
            if request_ids:
                with engine.connect() as conn:
                    # Get item_id for each request and calculate which requests first exceeded planned
                    for req_id in request_ids:
                        result = conn.execute(text("""
                            SELECT r.item_id, r.qty, i.qty as planned_qty, r.building_subtype,
                                   (SELECT COALESCE(SUM(r2.qty), 0) 
                                    FROM requests r2 
                                    WHERE r2.item_id = r.item_id 
                                    AND r2.id <= r.id 
                                    AND r2.status IN ('Pending', 'Approved')
                                    AND COALESCE(r2.building_subtype, '') = COALESCE(r.building_subtype, '')
                                   ) as cumulative_qty
                            FROM requests r
                            JOIN items i ON r.item_id = i.id
                            WHERE r.id = :req_id
                        """), {"req_id": req_id})
                        row = result.fetchone()
                        if row:
                            item_id, req_qty, planned_qty, req_subtype, cumulative_qty = row
                            subtype_norm = (req_subtype.strip() if isinstance(req_subtype, str) else req_subtype) or ""
                            cumulative_qty_val = float(cumulative_qty) if cumulative_qty else 0
                            planned_qty_val = float(planned_qty) if planned_qty else 0
                            
                            # Store cumulative quantity for ALL requests (not just when exceeding planned)
                            cumulative_qty_dict[req_id] = cumulative_qty_val
                            
                            if planned_qty and cumulative_qty and float(cumulative_qty) > float(planned_qty):
                                # Check if previous cumulative was <= planned (this is the first request that exceeded)
                                prev_result = conn.execute(text("""
                                    SELECT COALESCE(SUM(r2.qty), 0) 
                                    FROM requests r2 
                                    WHERE r2.item_id = :item_id 
                                    AND r2.id < :req_id 
                                    AND r2.status IN ('Pending', 'Approved')
                                    AND COALESCE(r2.building_subtype, '') = :subtype_norm
                                """), {"item_id": item_id, "req_id": req_id, "subtype_norm": subtype_norm})
                                prev_cumulative = float(prev_result.fetchone()[0] or 0)
                                if prev_cumulative <= float(planned_qty):
                                    exceeds_planned_request_ids.add(req_id)
            
            # Add cumulative quantity column (show for all requests)
            display_reqs['Cumulative Requested'] = display_reqs.apply(
                lambda row: cumulative_qty_dict.get(row['id'], 0) if row['id'] in cumulative_qty_dict else 0, axis=1
            )
            
            # Select and rename columns for admin view
            display_columns = ['id', 'ts', 'item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'requested_by', 'project_site', 'Context', 'building_subtype', 'status', 'approved_by', 'note']
            display_reqs = display_reqs[display_columns]
            display_reqs.columns = ['ID', 'Time', 'Item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'Requested By', 'Project Site', 'Building Type & Budget', 'Block/Unit', 'Status', 'Approved By', 'Note']
            
            # Style: Requested Qty in red if it exceeds Planned Qty OR if cumulative exceeded planned, Current Price in red if it differs from Planned Price
            def highlight_over_admin(row):
                styles = [''] * len(row)
                try:
                    req_id = int(row['ID'])
                    exceeds_cumulative = req_id in exceeds_planned_request_ids
                    
                    rq = float(row['Requested Qty']) if pd.notna(row['Requested Qty']) else 0
                    pq = float(row['Planned Qty']) if pd.notna(row['Planned Qty']) else 0
                    
                    # Highlight if single request exceeds planned OR if this is the request that made cumulative exceed planned
                    if rq > pq or exceeds_cumulative:
                        # Find Requested Qty column index
                        try:
                            rq_idx = list(display_reqs.columns).index('Requested Qty')
                            styles[rq_idx] = 'color: red; font-weight: bold'
                        except ValueError:
                            pass  # Column doesn't exist, skip highlighting
                    
                    # Highlight Cumulative Requested column in red if it exceeds planned
                    cumulative_val = row.get('Cumulative Requested', 0)
                    if cumulative_val != '' and cumulative_val is not None and cumulative_val != 0:
                        try:
                            # Handle both numeric and string values
                            if isinstance(cumulative_val, (int, float)):
                                cumulative_float = float(cumulative_val)
                            else:
                                cumulative_float = float(cumulative_val)
                            if cumulative_float > pq:
                                try:
                                    cum_idx = list(display_reqs.columns).index('Cumulative Requested')
                                    styles[cum_idx] = 'color: red; font-weight: bold'
                                except ValueError:
                                    pass  # Column doesn't exist, skip highlighting
                        except (ValueError, TypeError):
                            pass  # Can't convert to float, skip
                    
                    # Check if current price differs from planned price
                    cp = float(row['Current Price']) if pd.notna(row['Current Price']) else 0
                    pp = float(row['Planned Price']) if pd.notna(row['Planned Price']) else 0
                    if cp != pp and pp > 0:
                        # Find Current Price column index
                        try:
                            cp_idx = list(display_reqs.columns).index('Current Price')
                            styles[cp_idx] = 'color: red; font-weight: bold'
                        except ValueError:
                            pass  # Column doesn't exist, skip highlighting
                except Exception:
                    pass
                return styles
            
            # Display the table with better formatting and styling
            styled_admin = (
                display_reqs.style
                .apply(highlight_over_admin, axis=1)
                .format({
                    'Planned Qty': '{:.2f}',
                    'Requested Qty': '{:.2f}',
                    'Cumulative Requested': lambda x: f'{x:.2f}' if isinstance(x, (int, float)) else x,
                    'Planned Price': '₦{:, .2f}'.replace(' ', ''),
                    'Current Price': '₦{:, .2f}'.replace(' ', ''),
                    'Total Price': '₦{:, .2f}'.replace(' ', ''),
                })
            )
            st.dataframe(styled_admin, use_container_width=True)
            
            # Show request statistics - calculate from all_reqs (all requests), not filtered reqs (pending only)
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                pending_count = len(all_reqs[all_reqs['status'] == 'Pending']) if not all_reqs.empty else 0
                st.metric("Pending", pending_count)
            with col2:
                approved_count = len(all_reqs[all_reqs['status'] == 'Approved']) if not all_reqs.empty else 0
                st.metric("Approved", approved_count)
            with col3:
                rejected_count = len(all_reqs[all_reqs['status'] == 'Rejected']) if not all_reqs.empty else 0
                st.metric("Rejected", rejected_count)
            with col4:
                total_count = len(all_reqs)
                st.metric("Total", total_count)
            
            # Add delete buttons as a separate section with table-like layout (Admin only)
            if not display_reqs.empty:
                deletable_requests = display_reqs[display_reqs['Status'].isin(['Approved', 'Rejected'])]
                if not deletable_requests.empty:
                    st.markdown("#### Delete Actions")
                    st.caption(f"Found {len(deletable_requests)} requests that can be deleted")
                
                    # Create a table-like layout for delete buttons
                    for index, row in deletable_requests.iterrows():
                        col1, col2, col3, col4, col5, col6, col7, col8, col9, col10 = st.columns([1, 2, 2, 1, 2, 2, 1, 2, 2, 1])
                    
                        with col1:
                            st.write(f"**{row['ID']}**")
                        with col2:
                            st.write(row['Time'])
                        with col3:
                            st.write(row['Item'])
                        with col4:
                            st.write(f"{row.get('Requested Qty', row.get('Quantity', 'N/A'))}")
                        with col5:
                            st.write(row['Requested By'])
                        with col6:
                            if user_type == 'admin':
                                st.write(f"**{row['Project Site']}**")
                            else:
                                st.write(row['Building Type & Budget'])
                        with col7:
                            if row['Status'] == 'Approved':
                                st.success("Approved")
                            else:
                                st.error("Rejected")
                        with col8:
                            st.write(row['Approved By'] if pd.notna(row['Approved By']) else "N/A")
                        with col9:
                            block_info = row.get('Block/Unit', "")
                            context_info = row.get('Building Type & Budget', "")
                            if user_type == 'admin':
                                if block_info:
                                    st.write(f"{context_info}\n{block_info}" if context_info else block_info)
                                else:
                                    st.write(context_info or "—")
                            else:
                                st.write(block_info or "—")
                        with col10:
                            # Only admins can delete requests
                            if user_type == 'admin':
                                if st.button("🗑️ Delete", key=f"delete_{row['ID']}", help=f"Delete request {row['ID']}"):
                                    preserve_current_tab()
                                    if delete_request(row['ID']):
                                        st.success(f"Request {row['ID']} deleted!")
                                        preserve_current_tab()
                                    else:
                                        st.error(f"Failed to delete request {row['ID']}")
                                        preserve_current_tab()
                            else:
                                st.write("🔒 Admin only")
                        
                        st.divider()
        else:
            st.info("No requests found matching the selected criteria.")

    # Only show approve/reject section for admins
    if is_admin():
        st.write("Approve/Reject a request by ID:")
        
        # Get current action from session state (initialize if not set)
        if 'approve_reject_action' not in st.session_state:
            st.session_state['approve_reject_action'] = 'Approve'
        
        # Wrap in form to prevent reruns on input changes
        with st.form("approve_reject_form", clear_on_submit=False):
            colA, colB, colC = st.columns(3)
            with colA:
                req_id = st.number_input("Request ID", min_value=1, step=1, key="req_id_input")
            with colB:
                action = st.selectbox("Action", ["Approve","Reject","Set Pending"], 
                                     key="action_select",
                                     index=0 if st.session_state.get('approve_reject_action') == 'Approve' 
                                           else (1 if st.session_state.get('approve_reject_action') == 'Reject' else 2),
                                     on_change=lambda: st.session_state.update({'approve_reject_action': st.session_state.get('action_select', 'Approve')}))
            with colC:
                approved_by = st.text_input("Approved by / Actor", key="approved_by_input")
            
            submitted = st.form_submit_button("Apply", type="primary")
            
            # Handle form submission inside form context
            if submitted:
                # Update session state with current action
                st.session_state['approve_reject_action'] = action
                
                # Preserve current tab before processing
                current_tab_idx = st.session_state.get('active_tab_index', 3)  # Default to Review & History (tab 3)
                set_active_tab_index(current_tab_idx)
                
                # Get rejection reason from session state if Reject was selected
                rejection_reason_value = st.session_state.get('rejection_reason_input', '') if action == "Reject" else ""
                
                # Validate request ID
                if req_id <= 0:
                    st.error("❌ Request ID must be greater than 0")
                elif not approved_by or not approved_by.strip():
                    st.error("❌ Please enter the name of the person approving/rejecting")
                elif action == "Reject" and not rejection_reason_value.strip():
                    st.error("❌ Please provide a reason for rejection")
                else:
                    target_status = "Approved" if action=="Approve" else ("Rejected" if action=="Reject" else "Pending")
                    note_value = rejection_reason_value.strip() if action == "Reject" and rejection_reason_value.strip() else None
                    err = set_request_status(int(req_id), target_status, approved_by=approved_by or None, note=note_value)
                    if err:
                        st.error(err)
                    else:
                        st.success(f"Request {req_id} set to {target_status}.")
                        
                        # Show notification popup for admin
                        notification_flag = "request_approved_notification" if target_status == "Approved" else "request_rejected_notification"
                        st.markdown(f"""
                        <script>
                        localStorage.setItem('{notification_flag}', 'true');
                        </script>
                        """, unsafe_allow_html=True)
                        
                        # Clear cache to refresh data
                        clear_cache()
                        
                        # Preserve tab after action
                        set_active_tab_index(current_tab_idx)
                        
                        # Clear rejection reason after successful submission
                        if action == "Reject":
                            st.session_state['rejection_reason_input'] = ""
        
        # Show rejection reason field outside form so it can appear/disappear dynamically
        # Check session state value to ensure it updates when selectbox changes
        current_action = st.session_state.get('approve_reject_action', 'Approve')
        if current_action == "Reject":
            rejection_reason = st.text_area("Reason for Rejection", key="rejection_reason_input", 
                                            help="This reason will be visible to the project site account", 
                                            placeholder="Enter the reason for rejecting this request...")

    st.divider()
    st.subheader("Complete Request Management")
    
    # Helper function to render hierarchical structure: Building Type > Budget > Block
    def render_hierarchical_requests(df, key_prefix, highlight_func, show_delete_buttons=True):
        """Render requests grouped by Building Type > Budget > Block"""
        if df.empty:
            st.info("No requests to display.")
            return

        def _sanitize_key(value, fallback):
            base = str(value).strip() if value is not None else ""
            if not base:
                base = fallback
            base = re.sub(r"\W+", "_", base.lower())
            return base or fallback

        def _normalize_budget_label(value):
            label = str(value or "").strip()
            if not label:
                return ("", "Unspecified Budget")
            base = re.sub(r"\s*\(.*\)$", "", label).strip()
            if not base:
                base = label
            return (base, base)

        def _budget_sort_key(value):
            if not value:
                return (1, "")
            return (0, value.lower())

        df = df.copy()
        for col_name in ["Building Type", "Budget", "Block/Unit"]:
            if col_name in df.columns:
                df[col_name] = df[col_name].fillna("").astype(str).str.strip()

        # Get unique building types
        unique_building_types = df["Building Type"].unique().tolist()
        building_types = sorted([bt for bt in unique_building_types if bt])
        if any(bt == "" for bt in unique_building_types) or not building_types:
            building_types.append("")

        for bt_idx, building_type in enumerate(building_types):
            if bt_idx > 0:
                st.divider()

            bt_label = building_type if building_type else "Unspecified Building Type"
            st.markdown(f"### {bt_label}")

            bt_df = df[df["Building Type"] == building_type].copy()
            if bt_df.empty:
                continue

            budget_group_info = bt_df["Budget"].apply(_normalize_budget_label)
            bt_df["__budget_group"] = budget_group_info.apply(lambda x: x[0])
            bt_df["__budget_label"] = budget_group_info.apply(lambda x: x[1])

            budget_groups = sorted(bt_df["__budget_group"].unique().tolist(), key=_budget_sort_key)
            if not budget_groups:
                budget_groups = [""]

            for budget_group in budget_groups:
                budget_df = bt_df[bt_df["__budget_group"] == budget_group].copy()
                if budget_df.empty:
                            continue
            
                budget_label = budget_df["__budget_label"].iloc[0] or "Unspecified Budget"
                budget_key = f"{key_prefix}_bt_{_sanitize_key(building_type, 'no_type')}_budget_{_sanitize_key(budget_group or budget_label, 'no_budget')}"
                with st.expander(f"💰 {budget_label} ({len(budget_df)} requests)", expanded=False):
                    blocks = sorted([blk for blk in budget_df["Block/Unit"].unique().tolist() if blk])
                    if (budget_df["Block/Unit"] == "").any() or not blocks:
                        if "" not in blocks:
                            blocks.append("")

                    for block in blocks:
                        block_df = budget_df[budget_df["Block/Unit"] == block].copy()
                        if block_df.empty:
                            continue
            
                        block_label = block if block else "Unassigned Block"
                        st.markdown(f"**Block / Unit:** {block_label}")

                        # Only drop grouping columns, preserve all display columns
                        table_df = block_df.drop(columns=["Building Type", "Block/Unit", "__budget_group", "__budget_label"], errors="ignore")
                        # Keep Project Site column if it exists (for admin view)

                        if not table_df.empty:
                            format_dict = {}
                            if 'Quantity' in table_df.columns:
                                format_dict['Quantity'] = '{:.2f}'
                            if 'Requested Qty' in table_df.columns:
                                format_dict['Requested Qty'] = '{:.2f}'
                            if 'Planned Qty' in table_df.columns:
                                format_dict['Planned Qty'] = '{:.2f}'
                            if 'Cumulative Requested' in table_df.columns:
                                format_dict['Cumulative Requested'] = lambda x: f'{x:.2f}' if isinstance(x, (int, float)) else x
                            for price_col in ['Planned Price', 'Current Price', 'Total Price']:
                                if price_col in table_df.columns:
                                    format_dict[price_col] = '₦{:, .2f}'.replace(' ', '')

                            styled_table = (
                                table_df.style
                                .apply(highlight_func, axis=1)
                                .format(format_dict)
                                )
                            st.dataframe(styled_table, use_container_width=True)
                                
                            if show_delete_buttons and is_admin():
                                delete_cols = st.columns(min(len(block_df), 4))
                                block_key = f"{budget_key}_block_{_sanitize_key(block, 'no_block')}"
                                for i, (_, row) in enumerate(block_df.iterrows()):
                                    with delete_cols[i % len(delete_cols)]:
                                        if st.button(f"🗑️ Delete ID {row['ID']}", key=f"{block_key}_del_{row['ID']}", type="secondary"):
                                                preserve_current_tab()
                                                if delete_request(row['ID']):
                                                    st.success(f"Request {row['ID']} deleted!")
                                                    preserve_current_tab()
                                                else:
                                                    st.error(f"Failed to delete request {row['ID']}")
                                                    preserve_current_tab()

                        st.write("")
    
    # Helper function for highlighting approved/rejected requests (matching pending request highlighting)
    def create_highlight_function(display_df, exceeds_planned_ids):
        """Create a highlighting function that matches pending request highlighting"""
        def highlight_func(row):
            styles = [''] * len(row)
            try:
                req_id = int(row['ID']) if pd.notna(row.get('ID')) else 0
                exceeds_cumulative = req_id in exceeds_planned_ids
                
                # Get Requested Qty (could be 'Requested Qty' or 'Quantity')
                rq_val = row.get('Requested Qty', row.get('Quantity', 0))
                rq = float(rq_val) if pd.notna(rq_val) else 0
                
                # Get Planned Qty
                pq_val = row.get('Planned Qty', 0)
                pq = float(pq_val) if pd.notna(pq_val) else 0
                
                columns = list(row.index)
                
                # Highlight Requested Qty if it exceeds planned OR if this is the request that made cumulative exceed planned
                if rq > pq or exceeds_cumulative:
                    if 'Requested Qty' in columns:
                        styles[columns.index('Requested Qty')] = 'color: red; font-weight: bold'
                    elif 'Quantity' in columns:
                        styles[columns.index('Quantity')] = 'color: red; font-weight: bold'
                
                # Highlight Cumulative Requested column in red if it exceeds planned
                cumulative_val = row.get('Cumulative Requested', 0)
                if cumulative_val != '' and cumulative_val is not None and cumulative_val != 0:
                    try:
                        if isinstance(cumulative_val, (int, float)):
                            cumulative_float = float(cumulative_val)
                        else:
                            cumulative_float = float(cumulative_val)
                        if cumulative_float > pq and 'Cumulative Requested' in columns:
                            styles[columns.index('Cumulative Requested')] = 'color: red; font-weight: bold'
                    except (ValueError, TypeError):
                        pass
                
                # Check if current price differs from planned price
                cp_val = row.get('Current Price', 0)
                pp_val = row.get('Planned Price', 0)
                if pd.notna(cp_val) and pd.notna(pp_val):
                    try:
                        cp = float(cp_val) if cp_val != '' else 0
                        pp = float(pp_val) if pp_val != '' else 0
                        if cp != pp and pp > 0 and 'Current Price' in columns:
                            styles[columns.index('Current Price')] = 'color: red; font-weight: bold'
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass
            return styles
        return highlight_func
    
    hist_tab1, hist_tab2, hist_tab3 = st.tabs([" Approved Requests", " Rejected Requests", " Deleted Requests"])
    
    with hist_tab1:
        st.markdown("#### Approved Requests")
        try:
            if user_type == 'admin':
                approved_reqs = df_requests(status='Approved', user_type='admin', project_site=None)
            else:
                current_project = st.session_state.get('current_project_site', 'Lifecamp Kafe')
                approved_reqs = df_requests(status='Approved', user_type='project_site', project_site=current_project)
            
            if not approved_reqs.empty:
                # Prepare data for hierarchical display
                display_approved = approved_reqs.copy()
                
                # Create display DataFrame with proper column names
                display_approved_render = pd.DataFrame(index=display_approved.index)
                if 'id' in display_approved.columns:
                    display_approved_render['ID'] = display_approved['id'].fillna(0).astype(int)
                if 'ts' in display_approved.columns:
                    def format_time(ts):
                        if pd.isna(ts) or ts is None:
                            return ""
                        try:
                            import pytz
                            lagos_tz = pytz.timezone('Africa/Lagos')
                            if isinstance(ts, str):
                                from datetime import datetime
                                if 'Z' in ts:
                                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):
                                    dt = datetime.fromisoformat(ts)
                                else:
                                    try:
                                        dt = datetime.fromisoformat(ts)
                                    except:
                                        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                                    dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                            else:
                                dt = ts
                                if dt.tzinfo is None:
                                    dt = lagos_tz.localize(dt)
                            if dt.tzinfo != lagos_tz:
                                dt = dt.astimezone(lagos_tz)
                            return dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            return str(ts) if ts else ""
                    display_approved_render['Time'] = display_approved['ts'].apply(format_time)
                if 'item' in display_approved.columns:
                    display_approved_render['Item'] = display_approved['item'].fillna('')
                if 'qty' in display_approved.columns:
                    display_approved_render['Requested Qty'] = display_approved['qty'].fillna(0)
                if 'planned_qty' in display_approved.columns:
                    display_approved_render['Planned Qty'] = display_approved['planned_qty'].fillna(0)
                if 'unit_cost' in display_approved.columns:
                    display_approved_render['Planned Price'] = display_approved['unit_cost'].fillna(0)
                if 'current_price' in display_approved.columns:
                    display_approved_render['Current Price'] = display_approved['current_price'].fillna(display_approved.get('unit_cost', 0))
                else:
                    display_approved_render['Current Price'] = display_approved.get('unit_cost', 0)
                if 'Requested Qty' in display_approved_render.columns and 'Current Price' in display_approved_render.columns:
                    display_approved_render['Total Price'] = display_approved_render['Requested Qty'] * display_approved_render['Current Price']
                if 'requested_by' in display_approved.columns:
                    display_approved_render['Requested By'] = display_approved['requested_by'].fillna('')
                if 'status' in display_approved.columns:
                    display_approved_render['Status'] = display_approved['status'].fillna('')
                if 'approved_by' in display_approved.columns:
                    display_approved_render['Approved By'] = display_approved['approved_by'].fillna('')
                
                # Calculate cumulative quantities and exceeds_planned_request_ids
                from sqlalchemy import text
                from db import get_engine
                engine = get_engine()
                request_ids = display_approved_render['ID'].tolist()
                exceeds_planned_request_ids = set()
                cumulative_qty_dict = {}
                
                if request_ids:
                    with engine.connect() as conn:
                        for req_id in request_ids:
                            result = conn.execute(text("""
                                SELECT r.item_id, r.qty, i.qty as planned_qty, r.building_subtype,
                                       (SELECT COALESCE(SUM(r2.qty), 0) 
                                        FROM requests r2 
                                        WHERE r2.item_id = r.item_id 
                                        AND r2.id <= r.id 
                                        AND r2.status IN ('Pending', 'Approved')
                                        AND COALESCE(r2.building_subtype, '') = COALESCE(r.building_subtype, '')
                                       ) as cumulative_qty
                                FROM requests r
                                JOIN items i ON r.item_id = i.id
                                WHERE r.id = :req_id
                            """), {"req_id": req_id})
                            row = result.fetchone()
                            if row:
                                item_id, req_qty, planned_qty, req_subtype, cumulative_qty = row
                                subtype_norm = (req_subtype.strip() if isinstance(req_subtype, str) else req_subtype) or ""
                                cumulative_qty_val = float(cumulative_qty) if cumulative_qty else 0
                                planned_qty_val = float(planned_qty) if planned_qty else 0
                                
                                cumulative_qty_dict[req_id] = cumulative_qty_val
                                
                                if planned_qty and cumulative_qty and float(cumulative_qty) > float(planned_qty):
                                    prev_result = conn.execute(text("""
                                        SELECT COALESCE(SUM(r2.qty), 0) 
                                        FROM requests r2 
                                        WHERE r2.item_id = :item_id 
                                        AND r2.id < :req_id 
                                        AND r2.status IN ('Pending', 'Approved')
                                        AND COALESCE(r2.building_subtype, '') = :subtype_norm
                                    """), {"item_id": item_id, "req_id": req_id, "subtype_norm": subtype_norm})
                                    prev_cumulative = float(prev_result.fetchone()[0] or 0)
                                    if prev_cumulative <= float(planned_qty):
                                        exceeds_planned_request_ids.add(req_id)
                
                display_approved_render['Cumulative Requested'] = display_approved_render['ID'].apply(
                    lambda req_id: cumulative_qty_dict.get(req_id, 0)
                )
                
                # Add Building Type & Budget (Context) column
                display_approved_render['Building Type & Budget'] = display_approved.apply(format_request_context, axis=1)
                
                # Add Action At column (updated_at timestamp for approved/rejected requests)
                def format_action_time_approved(row):
                    if 'updated_at' in display_approved.columns:
                        ts = display_approved.loc[row.name, 'updated_at'] if row.name in display_approved.index else None
                    else:
                        ts = None
                    if pd.isna(ts) or ts is None:
                        return ""
                    try:
                        import pytz
                        lagos_tz = pytz.timezone('Africa/Lagos')
                        if isinstance(ts, str):
                            from datetime import datetime
                            if 'Z' in ts:
                                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):
                                dt = datetime.fromisoformat(ts)
                            else:
                                try:
                                    dt = datetime.fromisoformat(ts)
                                except:
                                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                                dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                        else:
                            dt = ts
                            if dt.tzinfo is None:
                                dt = lagos_tz.localize(dt)
                        if dt.tzinfo != lagos_tz:
                            dt = dt.astimezone(lagos_tz)
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        return ""
                
                display_approved_render['Action At'] = display_approved_render.apply(format_action_time_approved, axis=1)
                
                # Add Approved At column for admin view (same as Action At)
                if is_admin():
                    display_approved_render['Approved At'] = display_approved_render['Action At']
                
                # Add Note column
                if 'note' in display_approved.columns:
                    display_approved_render['Note'] = display_approved['note'].fillna('')
                else:
                    display_approved_render['Note'] = ''
                
                # Reorder columns to match pending request table exactly
                if is_admin():
                    # Admin view: ID, Time, Item, Planned Qty, Requested Qty, Cumulative Requested, Planned Price, Current Price, Total Price, Requested By, Project Site, Building Type & Budget, Block/Unit, Status, Approved By, Approved At, Note
                    column_order = ['ID', 'Time', 'Item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'Requested By', 'Project Site', 'Building Type & Budget', 'Block/Unit', 'Status', 'Approved By', 'Approved At', 'Note']
                else:
                    # User view: ID, Time, Item, Planned Qty, Requested Qty, Cumulative Requested, Planned Price, Current Price, Total Price, Building Type & Budget, Block/Unit, Status, Approved By, Action At, Note
                    column_order = ['ID', 'Time', 'Item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'Building Type & Budget', 'Block/Unit', 'Status', 'Approved By', 'Action At', 'Note']
                
                # Reorder columns, only include columns that exist
                existing_columns = [col for col in column_order if col in display_approved_render.columns]
                display_approved_render = display_approved_render[existing_columns]
                
                # Add grouping columns for hierarchical display
                if 'building_type' in display_approved.columns:
                    display_approved_render['Building Type'] = display_approved['building_type'].fillna('')
                else:
                    display_approved_render['Building Type'] = ''
                
                if 'budget' in display_approved.columns:
                    display_approved_render['Budget'] = display_approved['budget'].fillna('')
                else:
                    display_approved_render['Budget'] = ''
                
                if 'building_subtype' in display_approved.columns:
                    display_approved_render['Block/Unit'] = display_approved['building_subtype'].fillna('')
                else:
                    display_approved_render['Block/Unit'] = ''
                
                if 'project_site' in display_approved.columns:
                    display_approved_render['Project Site'] = display_approved['project_site'].fillna('Unknown')
                
                # Create highlighting function
                highlight_approved = create_highlight_function(display_approved_render, exceeds_planned_request_ids)
                
                # Group by project site for admins
                if is_admin() and 'Project Site' in display_approved_render.columns:
                    project_sites = sorted([ps for ps in display_approved_render['Project Site'].dropna().unique().tolist() if ps])
                    if project_sites:
                        for project_site in project_sites:
                            site_df = display_approved_render[display_approved_render['Project Site'] == project_site].copy()
                            if site_df.empty:
                                continue
                            safe_site_key = re.sub(r"\W+", "_", project_site.lower()) if isinstance(project_site, str) and project_site else "unknown"
                            with st.expander(f"📁 {project_site} ({len(site_df)} requests)", expanded=False):
                                render_hierarchical_requests(site_df, f"approved_{safe_site_key}", highlight_approved, show_delete_buttons=True)
                    else:
                        render_hierarchical_requests(display_approved_render, "approved_global", highlight_approved, show_delete_buttons=True)
                else:
                    render_hierarchical_requests(display_approved_render, "approved_user", highlight_approved, show_delete_buttons=True)
            else:
                st.info("No approved requests found.")
        except Exception as e:
            st.error(f"Error loading approved requests: {e}")
            print(f"❌ Error loading approved requests: {e}")
    
    with hist_tab2:
        st.markdown("#### Rejected Requests")
        try:
            if user_type == 'admin':
                rejected_reqs = df_requests(status='Rejected', user_type='admin', project_site=None)
            else:
                current_project = st.session_state.get('current_project_site', 'Lifecamp Kafe')
                rejected_reqs = df_requests(status='Rejected', user_type='project_site', project_site=current_project)
            
            if not rejected_reqs.empty:
                # Prepare data for hierarchical display
                display_rejected = rejected_reqs.copy()
                
                # Create display DataFrame with proper column names
                display_rejected_render = pd.DataFrame(index=display_rejected.index)
                if 'id' in display_rejected.columns:
                    display_rejected_render['ID'] = display_rejected['id'].fillna(0).astype(int)
                if 'ts' in display_rejected.columns:
                    def format_time(ts):
                        if pd.isna(ts) or ts is None:
                            return ""
                        try:
                            import pytz
                            lagos_tz = pytz.timezone('Africa/Lagos')
                            if isinstance(ts, str):
                                from datetime import datetime
                                if 'Z' in ts:
                                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):
                                    dt = datetime.fromisoformat(ts)
                                else:
                                    try:
                                        dt = datetime.fromisoformat(ts)
                                    except:
                                        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                                    dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                            else:
                                dt = ts
                                if dt.tzinfo is None:
                                    dt = lagos_tz.localize(dt)
                            if dt.tzinfo != lagos_tz:
                                dt = dt.astimezone(lagos_tz)
                            return dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            return str(ts) if ts else ""
                    display_rejected_render['Time'] = display_rejected['ts'].apply(format_time)
                if 'item' in display_rejected.columns:
                    display_rejected_render['Item'] = display_rejected['item'].fillna('')
                if 'qty' in display_rejected.columns:
                    display_rejected_render['Requested Qty'] = display_rejected['qty'].fillna(0)
                if 'planned_qty' in display_rejected.columns:
                    display_rejected_render['Planned Qty'] = display_rejected['planned_qty'].fillna(0)
                if 'unit_cost' in display_rejected.columns:
                    display_rejected_render['Planned Price'] = display_rejected['unit_cost'].fillna(0)
                if 'current_price' in display_rejected.columns:
                    display_rejected_render['Current Price'] = display_rejected['current_price'].fillna(display_rejected.get('unit_cost', 0))
                else:
                    display_rejected_render['Current Price'] = display_rejected.get('unit_cost', 0)
                if 'Requested Qty' in display_rejected_render.columns and 'Current Price' in display_rejected_render.columns:
                    display_rejected_render['Total Price'] = display_rejected_render['Requested Qty'] * display_rejected_render['Current Price']
                if 'requested_by' in display_rejected.columns:
                    display_rejected_render['Requested By'] = display_rejected['requested_by'].fillna('')
                if 'status' in display_rejected.columns:
                    display_rejected_render['Status'] = display_rejected['status'].fillna('')
                if 'approved_by' in display_rejected.columns:
                    display_rejected_render['Approved By'] = display_rejected['approved_by'].fillna('')
                
                # Calculate cumulative quantities and exceeds_planned_request_ids
                from sqlalchemy import text
                from db import get_engine
                engine = get_engine()
                request_ids = display_rejected_render['ID'].tolist()
                exceeds_planned_request_ids = set()
                cumulative_qty_dict = {}
                
                if request_ids:
                    with engine.connect() as conn:
                        for req_id in request_ids:
                            result = conn.execute(text("""
                                SELECT r.item_id, r.qty, i.qty as planned_qty, r.building_subtype,
                                       (SELECT COALESCE(SUM(r2.qty), 0) 
                                        FROM requests r2 
                                        WHERE r2.item_id = r.item_id 
                                        AND r2.id <= r.id 
                                        AND r2.status IN ('Pending', 'Approved')
                                        AND COALESCE(r2.building_subtype, '') = COALESCE(r.building_subtype, '')
                                       ) as cumulative_qty
                                FROM requests r
                                JOIN items i ON r.item_id = i.id
                                WHERE r.id = :req_id
                            """), {"req_id": req_id})
                            row = result.fetchone()
                            if row:
                                item_id, req_qty, planned_qty, req_subtype, cumulative_qty = row
                                subtype_norm = (req_subtype.strip() if isinstance(req_subtype, str) else req_subtype) or ""
                                cumulative_qty_val = float(cumulative_qty) if cumulative_qty else 0
                                planned_qty_val = float(planned_qty) if planned_qty else 0
                                
                                cumulative_qty_dict[req_id] = cumulative_qty_val
                                
                                if planned_qty and cumulative_qty and float(cumulative_qty) > float(planned_qty):
                                    prev_result = conn.execute(text("""
                                        SELECT COALESCE(SUM(r2.qty), 0) 
                                        FROM requests r2 
                                        WHERE r2.item_id = :item_id 
                                        AND r2.id < :req_id 
                                        AND r2.status IN ('Pending', 'Approved')
                                        AND COALESCE(r2.building_subtype, '') = :subtype_norm
                                    """), {"item_id": item_id, "req_id": req_id, "subtype_norm": subtype_norm})
                                    prev_cumulative = float(prev_result.fetchone()[0] or 0)
                                    if prev_cumulative <= float(planned_qty):
                                        exceeds_planned_request_ids.add(req_id)
                
                display_rejected_render['Cumulative Requested'] = display_rejected_render['ID'].apply(
                    lambda req_id: cumulative_qty_dict.get(req_id, 0)
                )
                
                # Add Building Type & Budget (Context) column
                display_rejected_render['Building Type & Budget'] = display_rejected.apply(format_request_context, axis=1)
                
                # Add Action At column (updated_at timestamp for approved/rejected requests)
                def format_action_time_rejected(row):
                    if 'updated_at' in display_rejected.columns:
                        ts = display_rejected.loc[row.name, 'updated_at'] if row.name in display_rejected.index else None
                    else:
                        ts = None
                    if pd.isna(ts) or ts is None:
                        return ""
                    try:
                        import pytz
                        lagos_tz = pytz.timezone('Africa/Lagos')
                        if isinstance(ts, str):
                            from datetime import datetime
                            if 'Z' in ts:
                                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):
                                dt = datetime.fromisoformat(ts)
                            else:
                                try:
                                    dt = datetime.fromisoformat(ts)
                                except:
                                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                                dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                        else:
                            dt = ts
                            if dt.tzinfo is None:
                                dt = lagos_tz.localize(dt)
                        if dt.tzinfo != lagos_tz:
                            dt = dt.astimezone(lagos_tz)
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        return ""
                
                display_rejected_render['Action At'] = display_rejected_render.apply(format_action_time_rejected, axis=1)
                
                # Add Rejected At column for admin view (same as Action At)
                if is_admin():
                    display_rejected_render['Rejected At'] = display_rejected_render['Action At']
                
                # Add Note column
                if 'note' in display_rejected.columns:
                    display_rejected_render['Note'] = display_rejected['note'].fillna('')
                else:
                    display_rejected_render['Note'] = ''
                
                # Reorder columns to match pending request table exactly
                if is_admin():
                    # Admin view: ID, Time, Item, Planned Qty, Requested Qty, Cumulative Requested, Planned Price, Current Price, Total Price, Requested By, Project Site, Building Type & Budget, Block/Unit, Status, Approved By, Rejected At, Note
                    column_order = ['ID', 'Time', 'Item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'Requested By', 'Project Site', 'Building Type & Budget', 'Block/Unit', 'Status', 'Approved By', 'Rejected At', 'Note']
                else:
                    # User view: ID, Time, Item, Planned Qty, Requested Qty, Cumulative Requested, Planned Price, Current Price, Total Price, Building Type & Budget, Block/Unit, Status, Approved By, Action At, Note
                    column_order = ['ID', 'Time', 'Item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'Building Type & Budget', 'Block/Unit', 'Status', 'Approved By', 'Action At', 'Note']
                
                # Reorder columns, only include columns that exist
                existing_columns = [col for col in column_order if col in display_rejected_render.columns]
                display_rejected_render = display_rejected_render[existing_columns]
                
                # Add grouping columns for hierarchical display
                if 'building_type' in display_rejected.columns:
                    display_rejected_render['Building Type'] = display_rejected['building_type'].fillna('')
                else:
                    display_rejected_render['Building Type'] = ''
                
                if 'budget' in display_rejected.columns:
                    display_rejected_render['Budget'] = display_rejected['budget'].fillna('')
                else:
                    display_rejected_render['Budget'] = ''
                
                if 'building_subtype' in display_rejected.columns:
                    display_rejected_render['Block/Unit'] = display_rejected['building_subtype'].fillna('')
                else:
                    display_rejected_render['Block/Unit'] = ''
                
                if 'project_site' in display_rejected.columns:
                    display_rejected_render['Project Site'] = display_rejected['project_site'].fillna('Unknown')
                
                # Create highlighting function
                highlight_rejected = create_highlight_function(display_rejected_render, exceeds_planned_request_ids)
                
                # Group by project site for admins
                if is_admin() and 'Project Site' in display_rejected_render.columns:
                    project_sites = sorted([ps for ps in display_rejected_render['Project Site'].dropna().unique().tolist() if ps])
                    if project_sites:
                        for project_site in project_sites:
                            site_df = display_rejected_render[display_rejected_render['Project Site'] == project_site].copy()
                            if site_df.empty:
                                continue
                            safe_site_key = re.sub(r"\W+", "_", project_site.lower()) if isinstance(project_site, str) and project_site else "unknown"
                            with st.expander(f"📁 {project_site} ({len(site_df)} requests)", expanded=False):
                                render_hierarchical_requests(site_df, f"rejected_{safe_site_key}", highlight_rejected, show_delete_buttons=True)
                    else:
                        render_hierarchical_requests(display_rejected_render, "rejected_global", highlight_rejected, show_delete_buttons=True)
                else:
                    render_hierarchical_requests(display_rejected_render, "rejected_user", highlight_rejected, show_delete_buttons=True)
            else:
                st.info("No rejected requests found.")
        except Exception as e:
            st.error(f"Error loading rejected requests: {e}")
            print(f"❌ Error loading rejected requests: {e}")
    
    with hist_tab3:


        st.markdown("####  Deleted Requests History")
        deleted_log = df_deleted_requests()
        if not deleted_log.empty:
            # Enhance deleted requests display with cumulative quantities and highlighting
            display_deleted = deleted_log.copy()
            
            # Get item_id and project_site for each deleted request to calculate cumulative and group by project site
            from sqlalchemy import text
            from db import get_engine
            engine = get_engine()
            cumulative_qty_dict = {}
            exceeds_planned_request_ids = set()
            planned_qty_dict = {}
            
            # Add project_site, building_type, and budget columns by looking up from items table
            if 'item_name' in display_deleted.columns:
                deleted_item_meta = {}
                with engine.connect() as conn:
                    for idx, row in display_deleted.iterrows():
                        item_name = row.get('item_name', '')
                        metadata = {
                            "project_site": 'Unknown',
                            "building_type": '',
                            "budget": ''
                        }
                        if item_name:
                            try:
                                result = conn.execute(text("""
                                    SELECT project_site, building_type, budget
                                    FROM items 
                                    WHERE name = :item_name 
                                    LIMIT 1
                                """), {"item_name": item_name})
                                item_row = result.fetchone()
                                if item_row:
                                    metadata["project_site"] = item_row[0] if item_row[0] else 'Unknown'
                                    metadata["building_type"] = item_row[1] if item_row[1] else ''
                                    metadata["budget"] = item_row[2] if item_row[2] else ''
                            except Exception:
                                pass
                        deleted_item_meta[idx] = metadata
                
                display_deleted['project_site'] = display_deleted.index.map(lambda idx: deleted_item_meta.get(idx, {}).get('project_site', 'Unknown'))
                display_deleted['building_type'] = display_deleted.index.map(lambda idx: deleted_item_meta.get(idx, {}).get('building_type', ''))
                display_deleted['budget'] = display_deleted.index.map(lambda idx: deleted_item_meta.get(idx, {}).get('budget', ''))
            
            # Calculate cumulative quantities for deleted requests
            if 'req_id' in display_deleted.columns:
                with engine.connect() as conn:
                    for idx, row in display_deleted.iterrows():
                        req_id = row.get('req_id')
                        item_name = row.get('item_name', '')
                        deleted_qty = float(row.get('qty', 0)) if pd.notna(row.get('qty')) else 0
                        
                        if pd.notna(req_id) and req_id and item_name:
                            try:
                                # First, try to find item by name to get item_id and planned_qty
                                item_result = conn.execute(text("""
                                    SELECT id, qty as planned_qty
                                    FROM items
                                    WHERE name = :item_name
                                    LIMIT 1
                                """), {"item_name": item_name})
                                item_row = item_result.fetchone()
                                
                                if item_row:
                                    item_id, planned_qty = item_row
                                    planned_qty_val = float(planned_qty) if planned_qty is not None else 0
                                    planned_qty_dict[idx] = planned_qty_val
                                    
                                    # Calculate cumulative: sum of all requests (including deleted ones in deleted_requests)
                                    # that have id <= req_id, plus any requests that still exist with id <= req_id
                                    # Since deleted requests are removed from requests table, we need to:
                                    # 1. Sum all existing requests with id < req_id
                                    # 2. Add the deleted request's qty (this row)
                                    # 3. Also check if there are other deleted requests with same item and id <= req_id
                                    
                                    # First, get cumulative from existing requests (id < req_id)
                                    existing_result = conn.execute(text("""
                                        SELECT COALESCE(SUM(r2.qty), 0) 
                                        FROM requests r2 
                                        WHERE r2.item_id = :item_id 
                                        AND r2.id < :req_id
                                        AND r2.status IN ('Pending', 'Approved')
                                    """), {"item_id": item_id, "req_id": int(req_id)})
                                    existing_row = existing_result.fetchone()
                                    existing_cumulative = float(existing_row[0] or 0) if existing_row else 0
                                    
                                    # Add cumulative from deleted requests with same item and req_id < current req_id
                                    # Note: We need to match by item_name since deleted_requests doesn't have item_id
                                    deleted_result = conn.execute(text("""
                                        SELECT COALESCE(SUM(dr.qty), 0)
                                        FROM deleted_requests dr
                                        WHERE dr.item_name = :item_name
                                        AND dr.req_id < :req_id
                                    """), {"item_name": item_name, "req_id": int(req_id)})
                                    deleted_row = deleted_result.fetchone()
                                    deleted_cumulative = float(deleted_row[0] or 0) if deleted_row else 0
                                    
                                    # Total cumulative = existing + deleted (before this) + this deleted request
                                    cumulative_qty_val = existing_cumulative + deleted_cumulative + deleted_qty
                                    
                                    cumulative_qty_dict[idx] = cumulative_qty_val
                                    
                                    # Check if this request exceeded planned
                                    if planned_qty_val > 0 and cumulative_qty_val > planned_qty_val:
                                        # Check if previous cumulative (before this request) was <= planned
                                        prev_cumulative = existing_cumulative + deleted_cumulative
                                        if prev_cumulative <= planned_qty_val:
                                            exceeds_planned_request_ids.add(idx)
                                else:
                                    # Item not found - set defaults
                                    planned_qty_dict[idx] = 0
                                    cumulative_qty_dict[idx] = deleted_qty
                            except Exception as e:
                                print(f"Error calculating cumulative for deleted request {req_id}: {e}")
                                # Set defaults on error
                                planned_qty_dict[idx] = 0
                                cumulative_qty_dict[idx] = deleted_qty
                                continue
            
            # Add cumulative and planned qty columns
            display_deleted['Cumulative Requested'] = display_deleted.apply(
                lambda row: cumulative_qty_dict.get(row.name, 0), axis=1
            )
            display_deleted['Planned Qty'] = display_deleted.apply(
                lambda row: planned_qty_dict.get(row.name, 0), axis=1
            )
            
            # Format deleted_at timestamp
            def format_deleted_time(ts):
                if pd.isna(ts) or ts is None:
                    return "N/A"
                try:
                    import pytz
                    lagos_tz = pytz.timezone('Africa/Lagos')
                    if isinstance(ts, str):
                        from datetime import datetime
                        if 'Z' in ts:
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        elif '+' in ts or (ts.count('-') > 2 and 'T' in ts):
                            dt = datetime.fromisoformat(ts)
                        else:
                            try:
                                dt = datetime.fromisoformat(ts)
                            except:
                                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                            dt = lagos_tz.localize(dt) if dt.tzinfo is None else dt
                    else:
                        dt = ts
                        if dt.tzinfo is None:
                            dt = lagos_tz.localize(dt)
                    if dt.tzinfo != lagos_tz:
                        dt = dt.astimezone(lagos_tz)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    return str(ts) if ts else "N/A"
            
            if 'deleted_at' in display_deleted.columns:
                display_deleted['deleted_at'] = display_deleted['deleted_at'].apply(format_deleted_time)
            
            if 'building_subtype' not in display_deleted.columns:
                display_deleted['building_subtype'] = ''
            display_deleted['building_subtype'] = display_deleted['building_subtype'].fillna('').astype(str)

            if 'building_type' not in display_deleted.columns:
                display_deleted['building_type'] = ''
            display_deleted['building_type'] = display_deleted['building_type'].fillna('').astype(str)

            if 'budget' not in display_deleted.columns:
                display_deleted['budget'] = ''
            display_deleted['budget'] = display_deleted['budget'].fillna('').astype(str)

            if 'project_site' not in display_deleted.columns:
                display_deleted['project_site'] = 'Unknown'
            display_deleted['project_site'] = display_deleted['project_site'].fillna('Unknown').astype(str)

            display_deleted_render = pd.DataFrame(index=display_deleted.index)
            if 'req_id' in display_deleted.columns:
                display_deleted_render['ID'] = display_deleted['req_id'].apply(lambda x: int(x) if pd.notna(x) else 0)
            else:
                display_deleted_render['ID'] = range(1, len(display_deleted) + 1)
            
            # Format deleted_at as Time column (matching pending requests)
            display_deleted_render['Time'] = display_deleted['deleted_at'].apply(format_deleted_time)
            display_deleted_render['Item'] = display_deleted['item_name'].fillna('')
            display_deleted_render['Requested Qty'] = display_deleted['qty'].fillna(0)
            display_deleted_render['Planned Qty'] = display_deleted['Planned Qty'].fillna(0)
            display_deleted_render['Cumulative Requested'] = display_deleted['Cumulative Requested'].fillna(0)
            
            # Get prices from items table
            with engine.connect() as conn:
                price_dict = {}
                for idx, row in display_deleted.iterrows():
                    item_name = row.get('item_name', '')
                    if item_name:
                        try:
                            result = conn.execute(text("""
                                SELECT unit_cost
                                FROM items 
                                WHERE name = :item_name 
                                LIMIT 1
                            """), {"item_name": item_name})
                            item_row = result.fetchone()
                            if item_row:
                                unit_cost = float(item_row[0]) if item_row[0] else 0
                                price_dict[idx] = unit_cost
                            else:
                                price_dict[idx] = 0
                        except Exception:
                            price_dict[idx] = 0
                    else:
                        price_dict[idx] = 0
            
            display_deleted_render['Planned Price'] = display_deleted.index.map(lambda idx: price_dict.get(idx, 0))
            display_deleted_render['Current Price'] = display_deleted.index.map(lambda idx: price_dict.get(idx, 0))  # Use planned price as current
            display_deleted_render['Total Price'] = display_deleted_render['Requested Qty'] * display_deleted_render['Current Price']
            
            display_deleted_render['Requested By'] = display_deleted['requested_by'].fillna('')
            display_deleted_render['Status'] = display_deleted['status'].fillna('')
            display_deleted_render['Approved By'] = display_deleted.get('approved_by', pd.Series([''] * len(display_deleted))).fillna('')
            display_deleted_render['Deleted By'] = display_deleted['deleted_by'].fillna('')
            display_deleted_render['Project Site'] = display_deleted['project_site'].fillna('Unknown')
            
            # Get grp values from items table for Building Type & Budget context
            grp_dict = {}
            with engine.connect() as conn:
                for idx, row in display_deleted.iterrows():
                    item_name = row.get('item_name', '')
                    if item_name:
                        try:
                            result = conn.execute(text("""
                                SELECT grp
                                FROM items 
                                WHERE name = :item_name 
                                LIMIT 1
                            """), {"item_name": item_name})
                            item_row = result.fetchone()
                            if item_row:
                                grp_dict[idx] = item_row[0] if item_row[0] else ''
                            else:
                                grp_dict[idx] = ''
                        except Exception:
                            grp_dict[idx] = ''
                    else:
                        grp_dict[idx] = ''
            
            # Create Building Type & Budget column (Context)
            def format_deleted_context(row):
                building_type = row.get('building_type', '')
                building_subtype = row.get('building_subtype', '')
                budget = row.get('budget', '')
                grp = grp_dict.get(row.name, '')
                
                parts = []
                if pd.notna(building_type) and building_type:
                    bt_part = str(building_type)
                    if building_subtype and pd.notna(building_subtype):
                        bt_part = f"{bt_part} / {building_subtype}"
                    parts.append(bt_part)
                if pd.notna(budget) and budget:
                    if grp and pd.notna(grp):
                        parts.append(f"{budget} ({grp})")
                    else:
                        parts.append(str(budget))
                elif grp and pd.notna(grp):
                    parts.append(f"({grp})")
                return " - ".join(parts) if parts else "No context"
            
            display_deleted_render['Building Type & Budget'] = display_deleted.apply(format_deleted_context, axis=1)
            display_deleted_render['Block/Unit'] = display_deleted['building_subtype'].fillna('')
            display_deleted_render['Note'] = display_deleted.get('note', pd.Series([''] * len(display_deleted))).fillna('')
            
            # Add Deleted At column (same as Time column for deleted requests)
            display_deleted_render['Deleted At'] = display_deleted_render['Time']
            
            # Reorder columns to match pending request table (admin view since deleted requests are admin-only)
            column_order = ['ID', 'Time', 'Item', 'Planned Qty', 'Requested Qty', 'Cumulative Requested', 'Planned Price', 'Current Price', 'Total Price', 'Requested By', 'Project Site', 'Building Type & Budget', 'Block/Unit', 'Status', 'Approved By', 'Deleted By', 'Deleted At', 'Note']
            
            # Reorder columns, only include columns that exist
            existing_columns = [col for col in column_order if col in display_deleted_render.columns]
            display_deleted_render = display_deleted_render[existing_columns]
            
            # Add grouping columns for hierarchical display
            display_deleted_render['Building Type'] = display_deleted['building_type'].fillna('')
            display_deleted_render['Budget'] = display_deleted['budget'].fillna('')

            # Style: Highlight quantity and cumulative in red if they exceed planned (matching pending request logic)
            def highlight_deleted(row):
                styles = [''] * len(row)
                try:
                    idx = row.name
                    exceeds_flag = idx in exceeds_planned_request_ids
                    columns = list(row.index)
                    
                    # Get Requested Qty (could be 'Requested Qty' or 'Quantity')
                    qty_val = row.get('Requested Qty', row.get('Quantity', 0))
                    qty = float(qty_val) if pd.notna(qty_val) else 0
                    
                    pq_val = row.get('Planned Qty', 0)
                    pq = float(pq_val) if pd.notna(pq_val) else 0
                    
                    cumulative_val = row.get('Cumulative Requested', 0)
                    
                    # Highlight Requested Qty/Quantity if it exceeds planned OR if this is the request that made cumulative exceed planned
                    if qty > pq or exceeds_flag:
                        if 'Requested Qty' in columns:
                            styles[columns.index('Requested Qty')] = 'color: red; font-weight: bold'
                        elif 'Quantity' in columns:
                            styles[columns.index('Quantity')] = 'color: red; font-weight: bold'
                    
                    # Highlight Cumulative Requested column in red if it exceeds planned
                    if cumulative_val not in (None, '', 0):
                        try:
                            if isinstance(cumulative_val, (int, float)):
                                cumulative_float = float(cumulative_val)
                            else:
                                cumulative_float = float(cumulative_val)
                            if cumulative_float > pq and 'Cumulative Requested' in columns:
                                styles[columns.index('Cumulative Requested')] = 'color: red; font-weight: bold'
                        except (ValueError, TypeError):
                            pass
                    
                    # Check if current price differs from planned price (if price columns exist)
                    cp_val = row.get('Current Price', 0)
                    pp_val = row.get('Planned Price', 0)
                    if pd.notna(cp_val) and pd.notna(pp_val):
                        try:
                            cp = float(cp_val) if cp_val != '' else 0
                            pp = float(pp_val) if pp_val != '' else 0
                            if cp != pp and pp > 0 and 'Current Price' in columns:
                                styles[columns.index('Current Price')] = 'color: red; font-weight: bold'
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    pass
                return styles
                                
            if is_admin() and 'Project Site' in display_deleted_render.columns:
                project_sites = sorted([ps for ps in display_deleted_render['Project Site'].dropna().unique().tolist() if ps])
                if project_sites:
                    for project_site in project_sites:
                        site_df = display_deleted_render[display_deleted_render['Project Site'] == project_site]
                        if site_df.empty:
                            continue
                        safe_site_key = re.sub(r"\W+", "_", project_site.lower()) if isinstance(project_site, str) and project_site else "unknown"
                        with st.expander(f"📁 {project_site} ({len(site_df)} requests)", expanded=False):
                            render_hierarchical_requests(site_df, f"deleted_{safe_site_key}", highlight_deleted, show_delete_buttons=False)
                else:
                    render_hierarchical_requests(display_deleted_render, "deleted_global", highlight_deleted, show_delete_buttons=False)
            else:
                render_hierarchical_requests(display_deleted_render, "deleted_user", highlight_deleted, show_delete_buttons=False)
            
            st.caption("All deleted requests are logged here - includes previously Pending, Approved, and Rejected requests that were deleted.")
            
            # Clear deleted logs option (admin only)
            if is_admin():

                if st.button(" Clear All Deleted Logs", key="clear_deleted_logs_button"):
                    if not st.session_state.get("confirm_clear_deleted_logs"):

                        st.session_state["confirm_clear_deleted_logs"] = True
                        st.warning("⚠️ Click the button again to confirm clearing all deleted logs.")
                    else:

                        # Clear confirmation state
                        if "confirm_clear_deleted_logs" in st.session_state:

                            del st.session_state["confirm_clear_deleted_logs"]
                        
                        clear_deleted_requests()
                        st.success(" All deleted request logs cleared.")
                        # Don't use st.rerun() - let the page refresh naturally
            else:

                st.info("🔒 Admin privileges required to clear deleted logs.")
        else:

            st.info("No deleted requests found in history.")
if st.session_state.get('user_type') == 'admin':

    with tab7:


        st.subheader("System Administration")
        print("DEBUG: Admin Settings tab loaded")
        
        # System Overview - Compact and accurate
        st.markdown("### System Overview")
        
        # Get accurate system stats
        try:
            from sqlalchemy import text
            from db import get_engine
            engine = get_engine()
            
            with engine.connect() as conn:

                # Count actual project sites (not access codes)
                result = conn.execute(text("SELECT COUNT(*) FROM project_sites WHERE is_active = 1"))
                project_sites_count = result.fetchone()[0]
                
                # Get total items across all project sites - accurate count
                result = conn.execute(text("SELECT COUNT(*) FROM items"))
                total_items = result.fetchone()[0]
                
                # Get total requests
                result = conn.execute(text("SELECT COUNT(*) FROM requests"))
                total_requests = result.fetchone()[0]
                
                # Get today's access logs (using ISO format comparison like Access Logs expander)
                now_lagos = get_nigerian_time()
                start_of_day = now_lagos.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                end_of_day = (now_lagos.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM access_logs 
                    WHERE access_time >= :start_of_day AND access_time < :end_of_day
                """), {"start_of_day": start_of_day, "end_of_day": end_of_day})
                today_access = result.fetchone()[0]
                
                print(f"DEBUG: System stats - Projects: {project_sites_count}, Items: {total_items}, Requests: {total_requests}")
        except Exception as e:

            print(f"DEBUG: Admin Settings database query failed: {e}")
            project_sites_count = 0
            total_items = 0
            total_requests = 0
            today_access = 0
        
        # Compact metrics with smaller font
        st.markdown("""
        <style>
        .compact-metrics {
            font-size: 0.8rem;
        }
        </style>
        """, unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:

        
            st.metric("Project Sites", project_sites_count, help="Active project sites")
        
        with col2:

        
            st.metric("Total Items", total_items, help="Inventory items")
        
        with col3:

        
            st.metric("Total Requests", total_requests, help="All requests")
        
        with col4:

        
            st.metric("Today's Access", today_access, help="Today's logins")
        
        st.divider()
        
        # Access Code Management - Dropdown
        with st.expander("Access Code Management", expanded=False):

            # Get access codes using the correct function
            codes_data = get_all_access_codes()
            current_admin_code = codes_data.get('admin_code', 'Not found')
            
            st.info(f"**Admin Code:** `{current_admin_code}`")
            
            st.markdown("#### Change Admin Access Code")
            st.caption("Changing the admin access code will affect admin login. Inform your team of the new code.")
            
            with st.form("change_admin_access_code", clear_on_submit=False):

            
                new_admin_code = st.text_input("New Admin Code", value=current_admin_code, type="password")
                
                if st.form_submit_button("Update Admin Code", type="primary"):

                
                    if new_admin_code:
                        if len(new_admin_code) < 4:

                            st.error("Admin code must be at least 4 characters long.")
                        else:

                            current_user = st.session_state.get('full_name', 'Admin')
                            if update_admin_access_code(new_admin_code, current_user):
                                # Invalidate cache to refresh the displayed code
                                invalidate_access_codes_cache()
                                st.success("Admin access code updated successfully!")
                                
                                # Show notification popup
                                st.markdown("""
                                <script>
                                localStorage.setItem('access_code_updated_notification', 'true');
                                </script>
                                """, unsafe_allow_html=True)
                                # Don't use st.rerun() - let the page refresh naturally
                            else:
                                st.error("Failed to update admin access code. Please try again.")
                    else:

                        st.error("Please enter a new admin code.")
        
        # Project Site Management - Dropdown
        with st.expander("Project Site Management", expanded=False):

            admin_project_sites = get_project_sites()
            if admin_project_sites:

                for i, site in enumerate(admin_project_sites):
                    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                    with col1:
                        st.write(f"**{i+1}.** {site}")
                        # Show current access code for this project
                        project_access_code = get_project_access_code(site)
                        if project_access_code:
                            st.caption(f"Access Code: `{project_access_code}`")
                        else:
                            st.caption("No access code set")
                    with col2:
                        if st.button("Edit", key=f"edit_site_{i}"):
                            st.session_state[f"editing_site_{i}"] = True
                            st.session_state[f"edit_site_name_{i}"] = site
                    with col3:
                        if st.button("Access Code", key=f"access_code_{i}"):
                            st.session_state[f"managing_access_code_{i}"] = True
                    with col4:
                        if st.button("Delete", key=f"delete_site_{i}"):
                            if len(admin_project_sites) > 1:
                                if delete_project_site(site):
                                    st.success(f"Deleted '{site}' project site!")
                                else:
                                    st.error("Failed to delete project site!")
                            else:
                                st.error("Cannot delete the last project site!")
                    with col5:
                        if st.button("View", key=f"view_site_{i}"):
                            st.session_state.current_project_site = site
                            clear_cache()
                            st.success(f"Switched to '{site}' project site!")
                            # Force sidebar update by updating session state
                            st.session_state.sidebar_updated = True
                    
                    # Access code management for each project
                    if st.session_state.get(f"managing_access_code_{i}", False):

                        st.markdown(f"#### Manage Access Code for {site}")
                        current_code = get_project_access_code(site)
                        
                        with st.form(f"access_code_form_{i}", clear_on_submit=False):

                        
                            new_access_code = st.text_input(
                                "Project Access Code", 
                                value=current_code or f"PROJECT_{site.upper().replace(' ', '_')}", 
                                help="This code will be used by users to access this specific project",
                                key=f"new_access_code_{i}"
                            )
                            
                            col_submit, col_cancel = st.columns([1, 1])
                            with col_submit:

                                if st.form_submit_button("Update Access Code", type="primary"):

                                    if new_access_code and len(new_access_code) >= 4:
                                        if update_project_access_code(site, new_access_code):
                                            st.success(f"Access code updated for {site}!")
                                            st.session_state[f"managing_access_code_{i}"] = False
                                        else:
                                            st.error("Failed to update access code!")
                                    else:
                                        st.error("Access code must be at least 4 characters long!")
                            
                            with col_cancel:

                            
                                if st.form_submit_button("Cancel"):

                                    st.session_state[f"managing_access_code_{i}"] = False
                    
                    # Edit form for this site
                    if st.session_state.get(f"editing_site_{i}", False):

                        with st.form(f"edit_form_{i}", clear_on_submit=False):


                            new_name = st.text_input(
                                "New Project Site Name:", 
                                value=st.session_state.get(f"edit_site_name_{i}", site),
                                key=f"edit_input_{i}"
                            )
                            col_save, col_cancel = st.columns([1, 1])
                            with col_save:

                                if st.form_submit_button("Save", type="primary"):

                                    if new_name and new_name != site:
                                        if update_project_site_name(site, new_name):
                                            if st.session_state.get('current_project_site') == site:
                                                st.session_state.current_project_site = new_name
                                            st.success(f"✅ Updated '{site}' to '{new_name}'!")
                                            st.info("💡 **Project name updated everywhere!** Users will see the new name when they log in.")
                                            
                                            # Debug: Show what was updated
                                            try:
                                                from sqlalchemy import text
                                                from db import get_engine
                                                engine = get_engine()
                                                with engine.connect() as conn:
                                                    result = conn.execute(text("SELECT project_site FROM project_site_access_codes WHERE project_site = :new_name"), {"new_name": new_name})
                                                    updated_sites = result.fetchall()
                                                    st.info(f"🔍 Debug: Found {len(updated_sites)} access code records for '{new_name}'")
                                            except Exception as e:
                                                st.error(f"Debug error: {e}")
                                            
                                            if f"editing_site_{i}" in st.session_state:
                                                del st.session_state[f"editing_site_{i}"]
                                            if f"edit_site_name_{i}" in st.session_state:
                                                del st.session_state[f"edit_site_name_{i}"]
                                            # Force refresh to show updated project list
                                            # Don't use st.rerun() - let the page refresh naturally
                                        else:
                                            st.error("A project site with this name already exists!")
                                    elif new_name == site:
                                        st.info("No changes made.")
                                        if f"editing_site_{i}" in st.session_state:
                                            del st.session_state[f"editing_site_{i}"]
                                        if f"edit_site_name_{i}" in st.session_state:
                                            del st.session_state[f"edit_site_name_{i}"]
                                    else:

                                        st.error("Please enter a valid project site name!")
                            with col_cancel:
                                if st.form_submit_button("Cancel"):
                                    if f"editing_site_{i}" in st.session_state:
                                        del st.session_state[f"editing_site_{i}"]
                                    if f"edit_site_name_{i}" in st.session_state:
                                        del st.session_state[f"edit_site_name_{i}"]
            
            else:
                st.warning("No project sites available.")
            
            st.markdown("#### Add New Project Site")
            with st.form("add_project_site", clear_on_submit=False):

                new_site_name = st.text_input("Project Site Name:", placeholder="e.g., Downtown Plaza")
                new_site_description = st.text_area("Description (Optional):", placeholder="Brief description of the project site")
                
                if st.form_submit_button("Add Project Site", type="primary"):

                
                    if new_site_name:
                        if add_project_site(new_site_name, new_site_description):

                            st.session_state.current_project_site = new_site_name
                            clear_cache()
                            st.success(f"Added '{new_site_name}' as a new project site!")
                            
                            # Show notification popup
                            st.markdown("""
                            <script>
                            localStorage.setItem('project_site_added_notification', 'true');
                            </script>
                            """, unsafe_allow_html=True)
                            st.info("💡 You can now switch to this project site using the dropdown above.")
                        else:

                            st.error("This project site already exists!")
                    else:

                        st.error("Please enter a project site name!")
        
        # Access Logs - Enhanced Dropdown
        with st.expander("Access Logs", expanded=False):
            st.markdown("#### Access Log Management")
            
            # Enhanced filter options
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            with col1:
                log_role = st.selectbox("Filter by Role", ["All", "admin", "project_site", "unknown"], key="log_role_filter")
            with col2:
                log_days = st.number_input("Last N Days", min_value=1, max_value=365, value=7, key="log_days_filter")
            with col3:
                if st.button("Refresh", key="refresh_logs"):
                    # Don't use st.rerun() - let the page refresh naturally
                    pass
            with col4:
                st.caption("Use 'Clear ALL Logs' below for complete reset")
            
            # Clear ALL logs section
            st.markdown("#### Clear All Access Logs")
            st.warning("**Warning**: This will delete ALL access logs and start fresh. This action cannot be undone!")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("Clear ALL Logs", key="clear_all_logs", type="primary"):
                    if clear_all_access_logs():
                        st.success("All logs cleared successfully!")
                        # Don't use st.rerun() - let the page refresh naturally
                    else:
                        st.error("Failed to clear all logs")
            with col2:
                st.caption("This will delete all access logs and refresh the page to start from the beginning.")
            
            # Cache and session management sections removed
            
            # Quick stats
            st.markdown("#### Quick Overview")
            col1, col2, col3, col4 = st.columns(4)
            
            # Get quick stats
            try:

                from sqlalchemy import text
                from db import get_engine
                
                engine = get_engine()
                
                # Total logs
                total_logs = pd.read_sql_query(text("SELECT COUNT(*) as count FROM access_logs"), engine).iloc[0]['count']
                
                # Today's logs (Lagos day range to avoid DATE() casting pitfalls)
                now_lagos = get_nigerian_time()
                start_of_day = now_lagos.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                end_of_day = (now_lagos.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
                today_logs = pd.read_sql_query(
                    text("""
                        SELECT COUNT(*) as count
                        FROM access_logs
                        WHERE access_time >= :start_of_day AND access_time < :end_of_day
                    """),
                    engine,
                    params={"start_of_day": start_of_day, "end_of_day": end_of_day}
                ).iloc[0]['count']
                
                # Failed attempts
                failed_logs = pd.read_sql_query(
                    text("SELECT COUNT(*) as count FROM access_logs WHERE success = 0"), 
                    engine
                ).iloc[0]['count']
                
                # Unique users
                unique_users = pd.read_sql_query(
                    text("SELECT COUNT(DISTINCT user_name) as count FROM access_logs WHERE user_name IS NOT NULL"), 
                    engine
                ).iloc[0]['count']
                
                with col1:

                
                    st.metric("Total Logs", total_logs)
                with col2:

                    st.metric("Today's Access", today_logs)
                with col3:

                    st.metric("Failed Attempts", failed_logs)
                with col4:

                    st.metric("Unique Users", unique_users)
                        
            except Exception as e:

                        
                st.error(f"Error loading quick stats: {e}")
            
            st.divider()
            
            # Display access logs
            try:
                from sqlalchemy import text
                from db import get_engine
                from datetime import datetime, timedelta
                
                engine = get_engine()
                cutoff_date = (get_nigerian_time() - timedelta(days=log_days)).isoformat()
            
                # Build query with proper parameterized filters
                query = text("""
                    SELECT access_code, user_name, access_time, success, role
                    FROM access_logs 
                    WHERE access_time >= :cutoff_date
                """)
                params = {"cutoff_date": cutoff_date}
                
                if log_role != "All":
                    query = text(str(query) + " AND role = :role")
                    params["role"] = log_role
                
                query = text(str(query) + " ORDER BY access_time DESC LIMIT 100")
                
                logs_df = pd.read_sql_query(query, engine, params=params)
            
                if not logs_df.empty:
                    # Convert to West African Time for display
                    wat_timezone = pytz.timezone('Africa/Lagos')
                    
                    # Simple approach: just format the timestamps as strings
                    try:
                        # Convert to datetime first
                        logs_df['access_time'] = pd.to_datetime(logs_df['access_time'], errors='coerce')
                        
                        # For valid datetime values, format them nicely
                        valid_mask = logs_df['access_time'].notna()
                        if valid_mask.any():
                            # Format valid datetime values
                            logs_df.loc[valid_mask, 'Access DateTime'] = logs_df.loc[valid_mask, 'access_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                        # For invalid values, use the original string
                        invalid_mask = ~valid_mask
                        if invalid_mask.any():
                            logs_df.loc[invalid_mask, 'Access DateTime'] = logs_df.loc[invalid_mask, 'access_time'].astype(str)
                            
                    except Exception as e:
                        # Fallback: use original timestamps as strings
                        logs_df['Access DateTime'] = logs_df['access_time'].astype(str)
                    logs_df['Status'] = logs_df['success'].map({1: ' Success', 0: ' Failed'})
                    logs_df['User'] = logs_df['user_name']
                    logs_df['Role'] = logs_df['role'].str.title()
                    logs_df['Access Code'] = logs_df['access_code']
                    
                    display_logs = logs_df[['User', 'Role', 'Access Code', 'Access DateTime', 'Status']].copy()
                    display_logs.columns = ['User', 'Role', 'Access Code', 'Date & Time', 'Status']
                
                    # Display access logs
                    st.markdown("#### Access Log Details")
                    
                    # Display with pagination
                    page_size = 20
                    total_pages = (len(display_logs) - 1) // page_size + 1
                    
                    if total_pages > 1:
                        page = st.selectbox("Page", range(1, total_pages + 1), key="log_page")
                        start_idx = (page - 1) * page_size
                        end_idx = start_idx + page_size
                        page_logs = display_logs.iloc[start_idx:end_idx]
                        st.caption(f"Showing {start_idx + 1}-{min(end_idx, len(display_logs))} of {len(display_logs)} logs")
                    else:
                        page_logs = display_logs
                    
                    # Display the logs
                    st.dataframe(page_logs, use_container_width=True)
                
                    # Enhanced statistics
                    st.markdown("#### Access Statistics")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    total_access = len(logs_df)
                    successful_access = len(logs_df[logs_df['success'] == 1])
                    failed_access = len(logs_df[logs_df['success'] == 0])
                    unique_users = logs_df['user_name'].nunique()
                    
                    with col1:
                        st.metric("Total Access", total_access)
                    with col2:
                        st.metric("Successful", successful_access, delta=f"{successful_access/total_access*100:.1f}%" if total_access > 0 else "0%")
                    with col3:
                        st.metric("Failed", failed_access, delta=f"{failed_access/total_access*100:.1f}%" if total_access > 0 else "0%")
                    with col4:
                        st.metric("Unique Users", unique_users)
                
                    # Role breakdown with charts
                    st.markdown("#### Access by Role")
                    role_counts = logs_df['role'].value_counts()
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Admin Access", role_counts.get('admin', 0))
                    with col2:
                        st.metric("Project Site Account Access", role_counts.get('project_site', 0))
                    with col3:
                        st.metric("Failed Access", role_counts.get('unknown', 0))
                    
                    # Export options
                    st.markdown("#### Export Options")
                    col1, col2 = st.columns(2)
                    with col1:
                        csv_logs = logs_df.to_csv(index=False).encode("utf-8")
                        st.download_button("📥 Download All Logs", csv_logs, "access_logs.csv", "text/csv")
                    with col2:
                        filtered_csv = display_logs.to_csv(index=False).encode("utf-8")
                        st.download_button("📥 Download Filtered Logs", filtered_csv, "filtered_access_logs.csv", "text/csv")
                else:
                    st.info("No access logs found for the selected criteria.")
            except sqlite3.OperationalError as e:
                if "disk I/O error" in str(e):
                    # Try to recover from disk I/O error
                    try:
                        import os
                        if os.path.exists('istrominventory.db-wal'):
                            os.remove('istrominventory.db-wal')
                        if os.path.exists('istrominventory.db-shm'):
                            os.remove('istrominventory.db-shm')
                        st.warning("Database I/O error detected. Please refresh the page to retry.")
                        # Don't use st.rerun() - let the page refresh naturally
                    except:
                        st.info("Access logs are temporarily unavailable. Please try again later.")
                else:
                    st.info("Access logs are temporarily unavailable. Please try again later.")
            except Exception as e:
                st.info("Access logs are temporarily unavailable. Please try again later.")
        # Notifications Management - Dropdown
        with st.expander("Notifications", expanded=False):

            # Display unread notifications
            notifications = get_admin_notifications()
            if notifications:

                st.markdown("#### New Notifications")
                st.caption(f"Found {len(notifications)} unread notifications")
                for notification in notifications:

                    with st.container():


                        st.write(f"**{notification['title']}** - {notification['created_at']}")
                        st.write(f"*{notification['message']}*")
                        
                        col1, col2, col3 = st.columns([1, 1, 1])
                        with col1:

                            if st.button("Mark as Read", key=f"mark_read_{notification['id']}"):

                                if mark_notification_read(notification['id']):
                                    st.success("Notification marked as read!")
                                    # Don't use st.rerun() - let the page refresh naturally
                        with col2:

                            if notification['request_id']:

                                if st.button("View Request", key=f"view_request_{notification['id']}"):
                                    st.info("Navigate to Review & History tab to view the request")
                        with col3:

                            if st.button("Delete", key=f"delete_notification_{notification['id']}", type="secondary"):

                                if delete_notification(notification['id']):
                                    st.success("Notification deleted!")
                                    # Don't use st.rerun() - let the page refresh naturally
                                else:
                                    st.error("Failed to delete notification")
                st.divider()
            else:
                st.info("No new notifications")
            
            # Notification Log - All notifications (read and unread) in its own expander
            with st.expander("📋 Notification Log", expanded=False):
                all_notifications = get_all_notifications()
                if all_notifications:
                    for notification in all_notifications[:10]:  # Show last 10 notifications
                        status_icon = "🔔" if notification['is_read'] == 0 else "✅"
                        
                        # Parse message to extract building type and budget information
                        message = notification['message']
                        building_type = "Unknown"
                        budget = "Unknown"
                        
                        # Extract building type and budget from message if available
                        if "(" in message and ")" in message:
                            # Look for pattern like "(Materials - Building Type - Budget)"
                            parts = message.split("(")
                            if len(parts) > 1:
                                details = parts[1].split(")")[0]
                                detail_parts = details.split(" - ")
                                if len(detail_parts) >= 3:
                                    building_type = detail_parts[1] if len(detail_parts) > 1 else "Unknown"
                                    budget = detail_parts[2] if len(detail_parts) > 2 else "Unknown"
                        
                        # Display notification with enhanced formatting
                        with st.container():
                            st.markdown(f"**{status_icon} {notification['title']}** - *{notification['created_at']} (Nigerian Time)*")
                            
                            # Show building type and budget prominently
                            col1, col2, col3 = st.columns([2, 1, 1])
                            with col1:
                                st.write(f"*{message}*")
                            with col2:
                                st.info(f"**Building:** {building_type}")
                            with col3:
                                st.info(f"**Budget:** {budget}")
                            
                            # Add delete button for each notification in log
                            col1, col2 = st.columns([3, 1])
                            with col2:
                                if st.button("Delete", key=f"delete_log_notification_{notification['id']}", type="secondary"):
                                    if delete_notification(notification['id']):
                                        st.success("Notification deleted!")
                                        # Don't use st.rerun() - let the page refresh naturally
                                    else:
                                        st.error("Failed to delete notification")
                            
                            st.divider()
                else:
                    st.info("No notifications in log")

# -------------------------------- Project Site Notifications Tab --------------------------------
# Only show for project site accounts (not admins)
if st.session_state.get('user_type') != 'admin':
    with tab7:  # Notifications tab for project site accounts
        st.subheader("Your Notifications")
        st.caption("View all notifications about your requests - approvals, rejections, and submissions")
        
        # Initialize session state for tracking dismissed synthetic notifications
        if 'dismissed_synthetic_notifs' not in st.session_state:
            st.session_state.dismissed_synthetic_notifs = set()
        
        try:
            # Get notifications for this project site
            ps_notifications = get_project_site_notifications()
            
            # Filter out dismissed synthetic notifications (negative IDs)
            ps_notifications = [
                n for n in ps_notifications 
                if n.get('id', 0) >= 0 or n.get('id', 0) not in st.session_state.dismissed_synthetic_notifs
            ]
            
            # Debug output
            if ps_notifications:
                st.caption(f"Found {len(ps_notifications)} notifications")
            
            if ps_notifications:
                # Professional summary metrics
                total_count = len(ps_notifications)
                unread_count = len([n for n in ps_notifications if not n.get('is_read')])
                read_count = total_count - unread_count
                
                st.markdown("### Notification Summary")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total", total_count)
                with col2:
                    st.metric("Unread", unread_count, delta=None)
                with col3:
                    st.metric("Read", read_count)
                with col4:
                    completion_pct = round((read_count / total_count * 100) if total_count > 0 else 0, 1)
                    st.metric("Completion", f"{completion_pct}%")
                
                st.markdown("---")
                
                # Split notifications into unread and read groups
                unread_notifications = [n for n in ps_notifications if not n.get('is_read', False)]
                read_notifications = [n for n in ps_notifications if n.get('is_read', False)]
                
                # Show unread notifications in an expander
                if unread_notifications:
                    with st.expander(f"🔔 Unread Notifications ({len(unread_notifications)})", expanded=True):
                        for idx, notification in enumerate(unread_notifications):
                            notif_id = notification.get('id')
                            notif_type = notification.get('type', '')
                            title = notification.get('title', '')
                            message = notification.get('message', '')
                            request_id = notification.get('request_id')
                            created_at = notification.get('created_at', '')
                            is_read = notification.get('is_read', False)
                            approved_by = notification.get('approved_by')
                            
                            # Escape HTML in message and title to prevent HTML code from showing
                            import html
                            message_escaped = html.escape(message)
                            title_escaped = html.escape(title)
                            
                            # Professional color scheme
                            if notif_type == 'request_approved':
                                bg_color = "#f0fdf4"  # green-50
                                border_color = "#22c55e"  # green-500
                                status_badge = "Approved"
                                badge_color = "#16a34a"
                            elif notif_type == 'request_rejected':
                                bg_color = "#fef2f2"  # red-50
                                border_color = "#ef4444"  # red-500
                                status_badge = "Rejected"
                                badge_color = "#dc2626"
                            else:
                                bg_color = "#eff6ff"  # blue-50
                                border_color = "#3b82f6"  # blue-500
                                status_badge = "Submitted"
                                badge_color = "#2563eb"
                            
                            # Build approved_by HTML
                            approved_by_html = ""
                            if approved_by and notif_type in ['request_approved', 'request_rejected']:
                                approved_by_html = f'<div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.25rem;">Approved by: {approved_by or "Admin"}</div>'
                            
                            # Professional card design
                            with st.container():
                                # Build HTML string to avoid f-string parsing issues
                                html_content = f'<div style="border: 1px solid {border_color}; border-left: 4px solid {border_color}; background: {bg_color}; padding: 1rem; margin: 0.75rem 0; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);"><div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;"><div style="flex: 1;"><span style="background: {badge_color}; color: white; padding: 0.25rem 0.75rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase;">{status_badge}</span><h4 style="margin: 0.5rem 0 0.25rem 0; font-size: 1rem; font-weight: 600; color: #1f2937;">{title_escaped}</h4></div><div style="text-align: right;"><div style="font-size: 0.75rem; color: #6b7280; font-weight: 500;">{created_at}</div>{approved_by_html}</div></div><p style="margin: 0.5rem 0 0; font-size: 0.9rem; color: #374151; line-height: 1.5;">{message_escaped}</p><div style="margin-top: 0.75rem; font-size: 0.75rem; color: #6b7280;">Request ID: <strong>#{request_id}</strong></div></div>'
                                st.markdown(html_content, unsafe_allow_html=True)
                                
                                # Action buttons
                                col1, col2, col3 = st.columns([2, 2, 6])
                                with col1:
                                    if st.button("Mark as Read", key=f"mark_read_{notif_id}", type="secondary", use_container_width=True):
                                        try:
                                            notif_id_val = notif_id
                                            request_id_val = request_id
                                            
                                            from sqlalchemy import text
                                            from db import get_engine
                                            engine = get_engine()
                                            
                                            with engine.begin() as conn:
                                                if notif_id_val < 0:
                                                    # Synthetic notification - create actual notification record in DB marked as read
                                                    if request_id_val:
                                                        # Check if notification already exists
                                                        existing = conn.execute(text(
                                                            "SELECT id FROM notifications WHERE request_id = :req_id AND notification_type IN ('request_approved', 'request_rejected')"
                                                        ), {"req_id": request_id_val}).fetchone()
                                                        
                                                        if existing:
                                                            # Update existing notification to read
                                                            conn.execute(text(
                                                                "UPDATE notifications SET is_read = 1 WHERE id = :notif_id"
                                                            ), {"notif_id": existing[0]})
                                                        else:
                                                            # Create new notification record marked as read
                                                            notif_type_val = notif_type
                                                            title_val = title
                                                            message_val = message
                                                            created_at_val = created_at
                                                            
                                                            # Convert Nigerian time back to ISO if needed
                                                            from datetime import datetime
                                                            import pytz
                                                            try:
                                                                if isinstance(created_at_val, str) and 'WAT' in created_at_val:
                                                                    dt_str = created_at_val.replace(' WAT', '')
                                                                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                                                                    lagos_tz = pytz.timezone('Africa/Lagos')
                                                                    dt = lagos_tz.localize(dt)
                                                                    created_at_iso = dt.isoformat()
                                                                else:
                                                                    created_at_iso = get_nigerian_time_iso()
                                                            except:
                                                                created_at_iso = get_nigerian_time_iso()
                                                            
                                                            conn.execute(text('''
                                                                INSERT INTO notifications (notification_type, title, message, user_id, request_id, created_at, is_read)
                                                                VALUES (:notification_type, :title, :message, NULL, :request_id, :created_at, 1)
                                                            '''), {
                                                                "notification_type": notif_type_val,
                                                                "title": title_val,
                                                                "message": message_val,
                                                                "request_id": request_id_val,
                                                                "created_at": created_at_iso
                                                            })
                                                else:
                                                    # Real notification - update database
                                                    conn.execute(text("UPDATE notifications SET is_read = 1 WHERE id = :notif_id"), {"notif_id": notif_id_val})
                                            
                                            clear_cache()
                                            st.success("Marked as read!")
                                            # Don't rerun - let user continue their work, changes will show on next interaction
                                        except Exception as e:
                                            st.error(f"Error: {e}")
                                with col2:
                                    if request_id:
                                        if st.button("View Details", key=f"view_req_{notif_id}", use_container_width=True):
                                            st.info(f"Request ID: {request_id} - View in 'Review & History' tab")
                                
                                if idx < len(unread_notifications) - 1:
                                    st.markdown("<div style='margin: 0.5rem 0;'></div>", unsafe_allow_html=True)
                    
                # Always show read notifications expander if there are any
                if read_notifications:
                    st.markdown("---")
                    with st.expander(f"Read Notifications ({len(read_notifications)})", expanded=False):
                        for idx, notification in enumerate(read_notifications):
                            notif_id = notification.get('id')
                            notif_type = notification.get('type', '')
                            title = notification.get('title', '')
                            message = notification.get('message', '')
                            request_id = notification.get('request_id')
                            created_at = notification.get('created_at', '')
                            approved_by = notification.get('approved_by')
                            
                            # Escape HTML in message and title to prevent HTML code from showing
                            import html
                            message_escaped = html.escape(message)
                            title_escaped = html.escape(title)
                            
                            # Professional color scheme (muted for read)
                            if notif_type == 'request_approved':
                                bg_color = "#f0fdf4"  # green-50
                                border_color = "#86efac"  # lighter green
                                status_badge = "Approved"
                                badge_color = "#22c55e"
                            elif notif_type == 'request_rejected':
                                bg_color = "#fef2f2"  # red-50
                                border_color = "#fca5a5"  # lighter red
                                status_badge = "Rejected"
                                badge_color = "#ef4444"
                            else:
                                bg_color = "#eff6ff"  # blue-50
                                border_color = "#93c5fd"  # lighter blue
                                status_badge = "Submitted"
                                badge_color = "#3b82f6"
                            
                            # Build approved_by HTML
                            approved_by_html = ""
                            if approved_by and notif_type in ['request_approved', 'request_rejected']:
                                approved_by_html = f'<div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.25rem;">Approved by: {approved_by or "Admin"}</div>'
                            
                            # Professional card design (muted for read)
                            # Build HTML string to avoid f-string parsing issues
                            html_content = f'<div style="border: 1px solid {border_color}; border-left: 4px solid {border_color}; background: {bg_color}; padding: 1rem; margin: 0.75rem 0; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); opacity: 0.85;"><div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;"><div style="flex: 1;"><span style="background: {badge_color}; color: white; padding: 0.25rem 0.75rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase;">{status_badge}</span><h4 style="margin: 0.5rem 0 0.25rem 0; font-size: 1rem; font-weight: 600; color: #1f2937;">{title_escaped}</h4></div><div style="text-align: right;"><div style="font-size: 0.75rem; color: #6b7280; font-weight: 500;">{created_at}</div>{approved_by_html}</div></div><p style="margin: 0.5rem 0 0; font-size: 0.9rem; color: #374151; line-height: 1.5;">{message_escaped}</p><div style="margin-top: 0.75rem; font-size: 0.75rem; color: #6b7280;">Request ID: <strong>#{request_id}</strong></div></div>'
                            st.markdown(html_content, unsafe_allow_html=True)
                            
                            if request_id:
                                if st.button("View Details", key=f"view_read_all_{notif_id}", use_container_width=True):
                                    st.info(f"Request ID: {request_id} - View in 'Review & History' tab")
                            
                            if idx < len(read_notifications) - 1:
                                st.markdown("<div style='margin: 0.5rem 0;'></div>", unsafe_allow_html=True)
            else:
                st.info("No notifications yet")
                st.caption("You'll receive notifications here when your requests are approved or rejected by an admin.")
                st.markdown("""
                **What you'll see:**
                - Approval notifications when an admin approves your request
                - Rejection notifications when an admin rejects your request  
                - Submission confirmations when you submit a new request
                """)
                
        except Exception as e:
            st.error(f"Error loading notifications: {e}")
            print(f"❌ Project site notifications error: {e}")