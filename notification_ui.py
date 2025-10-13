"""
Modern Notification UI Components for Streamlit

This module provides professional, responsive notification UI components
that integrate seamlessly with the Streamlit inventory management app.
"""

import streamlit as st
import logging
from datetime import datetime
from typing import Dict, List, Optional
from notifications import (
    get_notifications, get_unread_count, mark_notification_as_read,
    mark_all_as_read, delete_notification, delete_all_notifications,
    format_relative_time, NOTIFICATION_TYPES, show_notification_toast
)

logger = logging.getLogger(__name__)

def render_notification_header(user_id: int) -> None:
    """
    Render the notification header with bell icon and unread badge.
    """
    try:
        unread_count = get_unread_count(user_id)
        
        # Create a container for the notification header
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col2:
                if unread_count > 0:
                    badge_text = "9+" if unread_count > 9 else str(unread_count)
                    st.markdown(f"""
                    <div style="text-align: center; position: relative; display: inline-block;">
                        <span style="font-size: 28px; cursor: pointer;" onclick="toggleNotifications()">🔔</span>
                        <span style="position: absolute; top: -5px; right: -5px; background: #ef4444; 
                                   color: white; border-radius: 50%; width: 18px; height: 18px; 
                                   display: flex; align-items: center; justify-content: center; 
                                   font-size: 11px; font-weight: bold;">{badge_text}</span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="text-align: center;">
                        <span style="font-size: 28px; cursor: pointer;" onclick="toggleNotifications()">🔔</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.caption("Click to view notifications")
                
    except Exception as e:
        logger.error(f"Failed to render notification header: {e}")

def render_notification_panel(user_id: int) -> None:
    """
    Render the main notification panel with modern styling.
    """
    try:
        # Get notifications
        notifications = get_notifications(user_id, limit=20)
        
        if not notifications:
            st.info("📭 No notifications yet")
            return
        
        # Calculate stats
        unread_count = len([n for n in notifications if not n['is_read']])
        total_count = len(notifications)
        
        # Header with stats
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   color: white; padding: 16px; border-radius: 12px; margin-bottom: 16px;">
            <h3 style="margin: 0; color: white;">🔔 Notifications</h3>
            <p style="margin: 4px 0 0 0; opacity: 0.9;">
                {total_count} total • {unread_count} unread
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Filter options
        with st.expander("🔍 Filter Options", expanded=False):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                filter_type = st.selectbox(
                    "Type", 
                    ["All", "info", "success", "warning", "error", "new_request", "request_approved", "request_rejected"],
                    key="notification_filter_type"
                )
            
            with col2:
                filter_status = st.selectbox(
                    "Status", 
                    ["All", "Unread", "Read"],
                    key="notification_filter_status"
                )
            
            with col3:
                if st.button("🔄 Refresh", key="refresh_notifications"):
                    st.rerun()
        
        # Filter notifications
        filtered_notifications = notifications
        if filter_type != "All":
            filtered_notifications = [n for n in filtered_notifications if n['type'] == filter_type]
        if filter_status == "Unread":
            filtered_notifications = [n for n in filtered_notifications if not n['is_read']]
        elif filter_status == "Read":
            filtered_notifications = [n for n in filtered_notifications if n['is_read']]
        
        # Display notifications
        if filtered_notifications:
            st.markdown(f"**Showing {len(filtered_notifications)} notification(s)**")
            
            for notification in filtered_notifications:
                render_single_notification(notification)
        else:
            st.info("No notifications match your filters")
        
        # Footer actions
        st.divider()
        render_notification_actions(user_id, unread_count)
        
    except Exception as e:
        logger.error(f"Failed to render notification panel: {e}")
        st.error("Failed to load notifications")

def render_single_notification(notification: Dict) -> None:
    """
    Render a single notification with modern styling.
    """
    try:
        notif_type = notification['type']
        type_info = NOTIFICATION_TYPES.get(notif_type, NOTIFICATION_TYPES['info'])
        
        # Determine styling based on read status
        bg_color = "#f8fafc" if notification['is_read'] else "#eff6ff"
        border_color = "#e2e8f0" if notification['is_read'] else "#3b82f6"
        opacity = "0.7" if notification['is_read'] else "1.0"
        
        # Create notification card
        st.markdown(f"""
        <div style="background: {bg_color}; border: 1px solid {border_color}; 
                   border-radius: 12px; padding: 16px; margin: 12px 0; 
                   transition: all 0.3s ease; opacity: {opacity};
                   box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="display: flex; align-items: flex-start; gap: 12px;">
                <div style="font-size: 20px; margin-top: 2px;">{type_info['icon']}</div>
                <div style="flex: 1;">
                    <div style="font-weight: 500; color: #1f2937; margin-bottom: 4px;">
                        {notification['message']}
                    </div>
                    <div style="font-size: 12px; color: #6b7280; display: flex; align-items: center; gap: 8px;">
                        <span>{format_relative_time(notification['created_at'])}</span>
                        <span>•</span>
                        <span>{notification['sender_name']}</span>
                        {'' if notification['is_read'] else '<span style="color: #3b82f6;">• Unread</span>'}
                    </div>
                </div>
                {'' if notification['is_read'] else '<div style="width: 8px; height: 8px; background: #3b82f6; border-radius: 50%; margin-top: 4px;"></div>'}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Action buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if not notification['is_read']:
                if st.button("✓ Mark Read", key=f"mark_read_{notification['id']}", type="secondary"):
                    if mark_notification_as_read(notification['id']):
                        st.success("Marked as read!")
                        st.rerun()
        
        with col2:
            if st.button("🗑️ Delete", key=f"delete_{notification['id']}", type="secondary"):
                if delete_notification(notification['id']):
                    st.success("Deleted!")
                    st.rerun()
        
        with col3:
            # Show notification type badge
            st.markdown(f"""
            <span style="background: {type_info['color']}; color: white; padding: 2px 8px; 
                        border-radius: 12px; font-size: 10px; font-weight: 500;">
                {notif_type.replace('_', ' ').title()}
            </span>
            """, unsafe_allow_html=True)
            
    except Exception as e:
        logger.error(f"Failed to render single notification: {e}")

def render_notification_actions(user_id: int, unread_count: int) -> None:
    """
    Render notification action buttons.
    """
    try:
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if unread_count > 0:
                if st.button("✓ Mark All Read", type="primary"):
                    if mark_all_as_read(user_id):
                        st.success(f"Marked {unread_count} notifications as read!")
                        st.rerun()
        
        with col2:
            if st.button("🗑️ Delete All", type="secondary"):
                if st.session_state.get('user_type') == 'admin':
                    if delete_all_notifications():
                        st.success("All notifications deleted!")
                        st.rerun()
                else:
                    if delete_all_notifications(user_id):
                        st.success("Your notifications deleted!")
                        st.rerun()
        
        with col3:
            if st.button("🔄 Refresh", key="refresh_all"):
                st.rerun()
                
    except Exception as e:
        logger.error(f"Failed to render notification actions: {e}")

def render_notification_sidebar(user_id: int) -> None:
    """
    Render a compact notification sidebar for quick access.
    """
    try:
        with st.sidebar:
            st.markdown("### 🔔 Notifications")
            
            # Quick stats
            unread_count = get_unread_count(user_id)
            if unread_count > 0:
                st.markdown(f"""
                <div style="background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; 
                           padding: 12px; margin-bottom: 16px;">
                    <div style="font-weight: 500; color: #92400e;">
                        {unread_count} unread notification{'s' if unread_count > 1 else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Recent notifications (max 5)
            recent_notifications = get_notifications(user_id, limit=5)
            
            if recent_notifications:
                for notification in recent_notifications:
                    notif_type = notification['type']
                    type_info = NOTIFICATION_TYPES.get(notif_type, NOTIFICATION_TYPES['info'])
                    
                    # Compact display
                    st.markdown(f"""
                    <div style="background: {'#eff6ff' if not notification['is_read'] else '#f8fafc'}; 
                               border-radius: 8px; padding: 8px; margin: 4px 0; font-size: 12px;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span>{type_info['icon']}</span>
                            <span style="flex: 1; color: #374151;">{notification['message'][:50]}{'...' if len(notification['message']) > 50 else ''}</span>
                            {'' if notification['is_read'] else '<span style="color: #3b82f6; font-size: 10px;">●</span>'}
                        </div>
                        <div style="font-size: 10px; color: #6b7280; margin-top: 2px;">
                            {format_relative_time(notification['created_at'])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No notifications")
            
            # Quick actions
            if st.button("View All Notifications", key="view_all_notifications"):
                st.session_state['show_notifications'] = True
                st.rerun()
                
    except Exception as e:
        logger.error(f"Failed to render notification sidebar: {e}")

def setup_notification_auto_refresh(user_id: int, interval_seconds: int = 20) -> None:
    """
    Set up auto-refresh for notifications.
    """
    try:
        # Check if there are unread notifications
        unread_count = get_unread_count(user_id)
        
        if unread_count > 0:
            # Add a refresh button as fallback
            if st.button("🔄 Refresh Notifications", key="manual_refresh"):
                st.rerun()
                
            # Auto-refresh info
            st.caption(f"Auto-refreshing every {interval_seconds}s (unread: {unread_count})")
            
    except Exception as e:
        logger.error(f"Failed to setup auto-refresh: {e}")

def render_notification_css() -> None:
    """
    Add custom CSS for notification styling.
    """
    st.markdown("""
    <style>
    .notification-card {
        transition: all 0.3s ease;
        cursor: pointer;
    }
    
    .notification-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    .notification-unread {
        border-left: 4px solid #3b82f6;
    }
    
    .notification-badge {
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
    }
    
    .notification-toast {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 1000;
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: slideIn 0.3s ease;
    }
    
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    </style>
    """, unsafe_allow_html=True)
