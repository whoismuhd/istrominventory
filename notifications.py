"""
Professional Notification System for Streamlit Inventory Management App

This module provides a scalable, thread-safe notification system that works
with both SQLite (local development) and PostgreSQL (production) databases.

Features:
- Idempotent notification creation (prevents duplicates)
- Pagination and performance optimization
- Cascade deletion for user cleanup
- Professional UI components
- Real-time updates with auto-refresh
"""

import logging
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy import text
from database_config import get_engine

logger = logging.getLogger(__name__)

# Notification types with icons and colors
NOTIFICATION_TYPES = {
    'info': {'icon': 'ℹ️', 'color': '#3b82f6'},
    'success': {'icon': '✅', 'color': '#10b981'},
    'warning': {'icon': '⚠️', 'color': '#f59e0b'},
    'error': {'icon': '❌', 'color': '#ef4444'},
    'new_request': {'icon': '📝', 'color': '#8b5cf6'},
    'request_approved': {'icon': '✅', 'color': '#10b981'},
    'request_rejected': {'icon': '❌', 'color': '#ef4444'},
}

def create_notification(
    sender_id: Optional[int],
    receiver_id: Optional[int], 
    message: str,
    notification_type: str = 'info',
    event_key: Optional[str] = None
) -> bool:
    """
    Create a notification with idempotency support.
    
    Args:
        sender_id: ID of user who triggered the notification (None for system)
        receiver_id: ID of user to receive notification (None for all admins)
        message: Notification message text
        notification_type: Type of notification (info, success, warning, error, etc.)
        event_key: Optional unique key to prevent duplicates (e.g., 'request:123:submitted')
    
    Returns:
        bool: True if notification created successfully
    """
    try:
        engine = get_engine()
        
        # Check for idempotency if event_key provided
        if event_key:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT id FROM notifications 
                    WHERE event_key = :event_key
                """), {"event_key": event_key})
                if result.fetchone():
                    logger.info(f"Notification with event_key '{event_key}' already exists, skipping")
                    return True
        
        # Insert notification
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO notifications (sender_id, receiver_id, message, type, event_key, created_at)
                VALUES (:sender_id, :receiver_id, :message, :type, :event_key, :created_at)
            """), {
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "message": message,
                "type": notification_type,
                "event_key": event_key,
                "created_at": datetime.now()
            })
        
        logger.info(f"Notification created: {notification_type} for user {receiver_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
        return False

def get_notifications(
    user_id: int,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0
) -> List[Dict]:
    """
    Get notifications for a user with pagination.
    
    Args:
        user_id: ID of user to get notifications for
        unread_only: If True, only return unread notifications
        limit: Maximum number of notifications to return
        offset: Number of notifications to skip
    
    Returns:
        List of notification dictionaries
    """
    try:
        engine = get_engine()
        
        # Build query with optional filters
        where_clause = "WHERE receiver_id = :user_id"
        params = {"user_id": user_id}
        
        if unread_only:
            where_clause += " AND is_read = FALSE"
        
        query = text(f"""
            SELECT n.id, n.sender_id, n.receiver_id, n.message, n.type, 
                   n.is_read, n.created_at, n.event_key,
                   s.full_name as sender_name
            FROM notifications n
            LEFT JOIN users s ON n.sender_id = s.id
            {where_clause}
            ORDER BY n.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        params.update({"limit": limit, "offset": offset})
        
        with engine.connect() as conn:
            result = conn.execute(query, params)
            notifications = []
            
            for row in result.fetchall():
                notifications.append({
                    'id': row[0],
                    'sender_id': row[1],
                    'receiver_id': row[2],
                    'message': row[3],
                    'type': row[4],
                    'is_read': row[5],
                    'created_at': row[6],
                    'event_key': row[7],
                    'sender_name': row[8] or 'System'
                })
            
            return notifications
            
    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        return []

def get_unread_count(user_id: int) -> int:
    """Get count of unread notifications for a user."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM notifications 
                WHERE receiver_id = :user_id AND is_read = FALSE
            """), {"user_id": user_id})
            return result.scalar() or 0
    except Exception as e:
        logger.error(f"Failed to get unread count: {e}")
        return 0

def mark_notification_as_read(notification_id: int) -> bool:
    """Mark a specific notification as read."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE notifications 
                SET is_read = TRUE 
                WHERE id = :notification_id
            """), {"notification_id": notification_id})
            return result.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to mark notification as read: {e}")
        return False

def mark_all_as_read(user_id: int) -> bool:
    """Mark all notifications as read for a user."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE notifications 
                SET is_read = TRUE 
                WHERE receiver_id = :user_id AND is_read = FALSE
            """), {"user_id": user_id})
            logger.info(f"Marked {result.rowcount} notifications as read for user {user_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to mark all as read: {e}")
        return False

def delete_notification(notification_id: int) -> bool:
    """Delete a specific notification."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
                DELETE FROM notifications 
                WHERE id = :notification_id
            """), {"notification_id": notification_id})
            return result.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to delete notification: {e}")
        return False

def delete_all_notifications(user_id: Optional[int] = None) -> int:
    """
    Delete all notifications for a user (admin only if user_id is None).
    
    Args:
        user_id: User ID to delete notifications for (None for all users, admin only)
    
    Returns:
        Number of notifications deleted
    """
    try:
        engine = get_engine()
        with engine.begin() as conn:
            if user_id is None:
                # Admin delete all
                result = conn.execute(text("DELETE FROM notifications"))
            else:
                # Delete for specific user
                result = conn.execute(text("""
                    DELETE FROM notifications 
                    WHERE receiver_id = :user_id OR sender_id = :user_id
                """), {"user_id": user_id})
            
            deleted_count = result.rowcount
            logger.info(f"Deleted {deleted_count} notifications")
            return deleted_count
            
    except Exception as e:
        logger.error(f"Failed to delete notifications: {e}")
        return 0

def format_relative_time(created_at: datetime) -> str:
    """Format timestamp as relative time (e.g., '5m ago')."""
    now = datetime.now()
    diff = now - created_at
    
    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "Just now"

def render_notification_bell(user_id: int) -> None:
    """
    Render the notification bell icon with unread badge in the sidebar.
    """
    try:
        unread_count = get_unread_count(user_id)
        
        # Bell icon with badge
        if unread_count > 0:
            badge_text = "9+" if unread_count > 9 else str(unread_count)
            st.markdown(f"""
            <div style="position: relative; display: inline-block;">
                <span style="font-size: 24px;">🔔</span>
                <span style="position: absolute; top: -8px; right: -8px; background: #ef4444; color: white; 
                           border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; 
                           justify-content: center; font-size: 12px; font-weight: bold;">{badge_text}</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("🔔")
            
    except Exception as e:
        logger.error(f"Failed to render notification bell: {e}")

def render_notification_dropdown(user_id: int) -> None:
    """
    Render the notification dropdown panel with modern styling.
    """
    try:
        notifications = get_notifications(user_id, limit=10)
        
        if not notifications:
            st.info("No notifications")
            return
        
        # Header with count
        unread_count = len([n for n in notifications if not n['is_read']])
        st.markdown(f"### 🔔 Notifications ({len(notifications)})")
        if unread_count > 0:
            st.caption(f"{unread_count} unread")
        
        # Notification list with modern styling
        for notification in notifications:
            notif_type = notification['type']
            type_info = NOTIFICATION_TYPES.get(notif_type, NOTIFICATION_TYPES['info'])
            
            # Styling based on read status
            bg_color = "#f8fafc" if notification['is_read'] else "#eff6ff"
            border_color = "#e2e8f0" if notification['is_read'] else "#3b82f6"
            
            st.markdown(f"""
            <div style="background: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; 
                       padding: 12px; margin: 8px 0; transition: all 0.2s ease;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 16px;">{type_info['icon']}</span>
                    <div style="flex: 1;">
                        <div style="font-weight: 500; color: #1f2937;">{notification['message']}</div>
                        <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">
                            {format_relative_time(notification['created_at'])} • {notification['sender_name']}
                        </div>
                    </div>
                    {'' if notification['is_read'] else '<div style="width: 8px; height: 8px; background: #3b82f6; border-radius: 50%;"></div>'}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Action buttons
            col1, col2 = st.columns([1, 1])
            with col1:
                if not notification['is_read']:
                    if st.button("Mark Read", key=f"mark_read_{notification['id']}", type="secondary"):
                        if mark_notification_as_read(notification['id']):
                            st.success("Marked as read!")
                            st.rerun()
            with col2:
                if st.button("Delete", key=f"delete_{notification['id']}", type="secondary"):
                    if delete_notification(notification['id']):
                        st.success("Deleted!")
                        st.rerun()
        
        # Footer actions
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Mark All Read", type="primary"):
                if mark_all_as_read(user_id):
                    st.success("All marked as read!")
                    st.rerun()
        with col2:
            if st.button("Delete All", type="secondary"):
                if delete_all_notifications(user_id):
                    st.success("All deleted!")
                    st.rerun()
                    
    except Exception as e:
        logger.error(f"Failed to render notification dropdown: {e}")
        st.error("Failed to load notifications")

def show_notification_toast(notification: Dict) -> None:
    """
    Show a toast notification for immediate feedback.
    """
    try:
        notif_type = notification['type']
        message = notification['message']
        
        if notif_type in ['request_approved', 'success']:
            st.success(f"✅ {message}")
        elif notif_type in ['request_rejected', 'error']:
            st.error(f"❌ {message}")
        elif notif_type == 'warning':
            st.warning(f"⚠️ {message}")
        else:
            st.info(f"ℹ️ {message}")
            
    except Exception as e:
        logger.error(f"Failed to show notification toast: {e}")

# Auto-refresh functionality
def setup_auto_refresh(interval_seconds: int = 15) -> None:
    """
    Set up auto-refresh for notifications using st_autorefresh.
    """
    try:
        from streamlit_autorefresh import st_autorefresh
        
        # Only auto-refresh if there are unread notifications
        if 'user_id' in st.session_state:
            unread_count = get_unread_count(st.session_state['user_id'])
            if unread_count > 0:
                st_autorefresh(interval=interval_seconds * 1000, key="notification_refresh")
    except ImportError:
        # Fallback: manual refresh button
        if st.button("🔄 Refresh Notifications"):
            st.rerun()
    except Exception as e:
        logger.error(f"Failed to setup auto-refresh: {e}")

# Migration helper for existing notifications
def migrate_existing_notifications() -> None:
    """
    Migrate existing notifications to the new schema.
    This should be run once during deployment.
    """
    try:
        engine = get_engine()
        
        # Check if migration is needed
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM notifications 
                WHERE sender_id IS NULL AND receiver_id IS NULL
            """))
            old_count = result.scalar() or 0
            
            if old_count > 0:
                logger.info(f"Found {old_count} old notifications to migrate")
                
                # Update old notifications to have proper sender/receiver
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE notifications 
                        SET sender_id = NULL, receiver_id = NULL 
                        WHERE sender_id IS NULL AND receiver_id IS NULL
                    """))
                    
                logger.info("Migration completed successfully")
                
    except Exception as e:
        logger.error(f"Failed to migrate notifications: {e}")
