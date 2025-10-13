"""
Integration Examples for the New Notification System

This module shows how to integrate the improved notification system
into the existing Streamlit inventory management app.
"""

import streamlit as st
import logging
from typing import Optional
from notifications import (
    create_notification, get_notifications, get_unread_count,
    mark_notification_as_read, mark_all_as_read, delete_notification,
    delete_all_notifications, show_notification_toast
)
from notification_ui import (
    render_notification_header, render_notification_panel,
    render_notification_sidebar, setup_notification_auto_refresh,
    render_notification_css
)

logger = logging.getLogger(__name__)

def integrate_notification_system():
    """
    Main integration function to add notification system to the app.
    Call this in your main app after authentication.
    """
    try:
        # Add custom CSS
        render_notification_css()
        
        # Get current user info
        user_id = st.session_state.get('user_id')
        user_type = st.session_state.get('user_type')
        
        if not user_id:
            return
        
        # Add notification sidebar
        render_notification_sidebar(user_id)
        
        # Add notification header to main area
        with st.container():
            render_notification_header(user_id)
        
        # Setup auto-refresh
        setup_notification_auto_refresh(user_id)
        
        # Show notification panel if requested
        if st.session_state.get('show_notifications', False):
            render_notification_panel(user_id)
            if st.button("Close", key="close_notifications"):
                st.session_state['show_notifications'] = False
                st.rerun()
        
    except Exception as e:
        logger.error(f"Failed to integrate notification system: {e}")

# Example usage functions for different app events

def notify_new_request(request_id: int, requester_name: str, item_name: str, quantity: float) -> None:
    """
    Notify admins when a new request is submitted.
    """
    try:
        # Create notification for all admins (receiver_id = None)
        success = create_notification(
            sender_id=None,  # System notification
            receiver_id=None,  # All admins
            message=f"{requester_name} submitted a request for {quantity} units of {item_name}",
            notification_type='new_request',
            event_key=f'request:{request_id}:submitted'  # Prevent duplicates
        )
        
        if success:
            logger.info(f"Admin notification created for request {request_id}")
        
    except Exception as e:
        logger.error(f"Failed to notify new request: {e}")

def notify_request_approved(request_id: int, requester_id: int, requester_name: str, item_name: str) -> None:
    """
    Notify user when their request is approved.
    """
    try:
        success = create_notification(
            sender_id=None,  # Admin approval
            receiver_id=requester_id,
            message=f"Your request for {item_name} has been approved!",
            notification_type='request_approved',
            event_key=f'request:{request_id}:approved'
        )
        
        if success:
            # Show immediate toast
            show_notification_toast({
                'type': 'request_approved',
                'message': f"Your request for {item_name} has been approved!"
            })
            logger.info(f"User notification created for approved request {request_id}")
        
    except Exception as e:
        logger.error(f"Failed to notify request approval: {e}")

def notify_request_rejected(request_id: int, requester_id: int, requester_name: str, item_name: str, reason: str = "") -> None:
    """
    Notify user when their request is rejected.
    """
    try:
        message = f"Your request for {item_name} has been rejected"
        if reason:
            message += f" - {reason}"
        
        success = create_notification(
            sender_id=None,  # Admin rejection
            receiver_id=requester_id,
            message=message,
            notification_type='request_rejected',
            event_key=f'request:{request_id}:rejected'
        )
        
        if success:
            # Show immediate toast
            show_notification_toast({
                'type': 'request_rejected',
                'message': message
            })
            logger.info(f"User notification created for rejected request {request_id}")
        
    except Exception as e:
        logger.error(f"Failed to notify request rejection: {e}")

def notify_item_added(item_name: str, quantity: float, project_site: str) -> None:
    """
    Notify admins when a new item is added to inventory.
    """
    try:
        success = create_notification(
            sender_id=None,  # System notification
            receiver_id=None,  # All admins
            message=f"New item added: {quantity} units of {item_name} to {project_site}",
            notification_type='info',
            event_key=f'item_added:{item_name}:{project_site}'
        )
        
        if success:
            logger.info(f"Admin notification created for new item {item_name}")
        
    except Exception as e:
        logger.error(f"Failed to notify item addition: {e}")

def notify_budget_threshold(budget_name: str, current_amount: float, threshold: float) -> None:
    """
    Notify admins when budget threshold is exceeded.
    """
    try:
        success = create_notification(
            sender_id=None,  # System notification
            receiver_id=None,  # All admins
            message=f"Budget alert: {budget_name} has reached ₦{current_amount:,.2f} (threshold: ₦{threshold:,.2f})",
            notification_type='warning',
            event_key=f'budget_threshold:{budget_name}:{current_amount}'
        )
        
        if success:
            logger.info(f"Budget threshold notification created for {budget_name}")
        
    except Exception as e:
        logger.error(f"Failed to notify budget threshold: {e}")

def notify_user_created(user_name: str, project_site: str) -> None:
    """
    Notify admins when a new user is created.
    """
    try:
        success = create_notification(
            sender_id=None,  # System notification
            receiver_id=None,  # All admins
            message=f"New user created: {user_name} for project {project_site}",
            notification_type='info',
            event_key=f'user_created:{user_name}:{project_site}'
        )
        
        if success:
            logger.info(f"Admin notification created for new user {user_name}")
        
    except Exception as e:
        logger.error(f"Failed to notify user creation: {e}")

# Integration with existing app functions

def enhanced_request_submission(request_data: dict) -> bool:
    """
    Enhanced request submission with notification integration.
    """
    try:
        # Your existing request submission logic here
        # ...
        
        # After successful submission, create notification
        notify_new_request(
            request_id=request_data.get('id'),
            requester_name=request_data.get('requester_name'),
            item_name=request_data.get('item_name'),
            quantity=request_data.get('quantity')
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to submit request with notification: {e}")
        return False

def enhanced_request_approval(request_id: int, requester_id: int, requester_name: str, item_name: str) -> bool:
    """
    Enhanced request approval with notification integration.
    """
    try:
        # Your existing approval logic here
        # ...
        
        # After successful approval, create notification
        notify_request_approved(
            request_id=request_id,
            requester_id=requester_id,
            requester_name=requester_name,
            item_name=item_name
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to approve request with notification: {e}")
        return False

def enhanced_request_rejection(request_id: int, requester_id: int, requester_name: str, item_name: str, reason: str = "") -> bool:
    """
    Enhanced request rejection with notification integration.
    """
    try:
        # Your existing rejection logic here
        # ...
        
        # After successful rejection, create notification
        notify_request_rejected(
            request_id=request_id,
            requester_id=requester_id,
            requester_name=requester_name,
            item_name=item_name,
            reason=reason
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to reject request with notification: {e}")
        return False

# Admin notification management

def render_admin_notification_management():
    """
    Render admin notification management interface.
    """
    try:
        st.markdown("### 🔔 Notification Management")
        
        # Notification stats
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_notifications = len(get_notifications(None, limit=1000))  # Get all
            st.metric("Total Notifications", total_notifications)
        
        with col2:
            unread_count = sum(get_unread_count(user_id) for user_id in [1, 2, 3])  # Example user IDs
            st.metric("Unread Notifications", unread_count)
        
        with col3:
            if st.button("Mark All Read", type="primary"):
                # Mark all notifications as read for all users
                for user_id in [1, 2, 3]:  # Example user IDs
                    mark_all_as_read(user_id)
                st.success("All notifications marked as read!")
                st.rerun()
        
        with col4:
            if st.button("Delete All", type="secondary"):
                if delete_all_notifications():  # Delete all notifications
                    st.success("All notifications deleted!")
                    st.rerun()
        
        # Notification log
        st.markdown("#### Recent Notifications")
        all_notifications = get_notifications(None, limit=50)
        
        if all_notifications:
            for notification in all_notifications:
                st.markdown(f"""
                **{notification['message']}**  
                *{notification['created_at']} • {notification['sender_name']}*
                """)
        else:
            st.info("No notifications found")
            
    except Exception as e:
        logger.error(f"Failed to render admin notification management: {e}")

# Usage example in main app

def example_main_app_integration():
    """
    Example of how to integrate the notification system in your main app.
    """
    # In your main app, after authentication:
    
    # 1. Add notification system integration
    integrate_notification_system()
    
    # 2. In your request submission function:
    # if request_submitted_successfully:
    #     notify_new_request(request_id, requester_name, item_name, quantity)
    
    # 3. In your approval function:
    # if request_approved_successfully:
    #     notify_request_approved(request_id, requester_id, requester_name, item_name)
    
    # 4. In your rejection function:
    # if request_rejected_successfully:
    #     notify_request_rejected(request_id, requester_id, requester_name, item_name, reason)
    
    # 5. In your admin panel:
    # render_admin_notification_management()
    
    pass
