"""
Istrom Inventory Management System - Main Application
Refactored and organized version with modular structure
"""

import streamlit as st
from db import init_db
from auth import (
    initialize_session, check_session_validity, restore_session_from_cookie,
    show_login_interface, save_session_to_cookie, is_admin, require_admin
)
from database import (
    get_inventory_items, add_inventory_item, update_inventory_item, delete_inventory_item,
    get_requests, add_request, update_request_status, get_notifications, add_notification,
    mark_notification_read, get_project_sites, add_project_site, db_health
)
from ui_components import (
    setup_page_config, setup_custom_css, create_header, create_sidebar,
    create_tabs, create_logout_button, show_success_message, show_error_message
)
# Email functionality removed for better performance

def main():
    """Main application function"""
    # Setup page configuration
    setup_page_config()
    setup_custom_css()
    
    # Initialize database
    init_db()
    
    # Initialize session
    initialize_session()
    
    # Try to restore session from cookie
    if not st.session_state.logged_in:
        if not restore_session_from_cookie():
            show_login_interface()
            st.stop()
    
    # Check session validity
    if not check_session_validity():
        show_login_interface()
        st.stop()
    
    # Save session to cookie for persistence
    save_session_to_cookie()
    
    # Create sidebar
    with st.sidebar:
        create_sidebar()
        create_logout_button()
    
    # Get user info
    user_name = st.session_state.get('full_name', 'Unknown')
    user_type = st.session_state.get('user_type', 'user')
    project_site = st.session_state.get('project_site', 'Lifecamp Kafe')
    session_remaining = "Persistent"
    
    # Create header
    create_header(user_name, user_type, project_site, session_remaining)
    
    # Create main tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = create_tabs()
    
    # Dashboard Tab
    with tab1:
        show_dashboard()
    
    # Inventory Tab
    with tab2:
        show_inventory()
    
    # Make Request Tab
    with tab3:
        show_make_request()
    
    # My Requests Tab
    with tab4:
        show_my_requests()
    
    # Notifications Tab
    with tab5:
        show_notifications()
    
    # Settings Tab
    with tab6:
        show_settings()

def show_dashboard():
    """Show dashboard with metrics and overview"""
    st.markdown("## 📊 Dashboard")
    
    # Get metrics
    try:
        items = get_inventory_items(project_site=st.session_state.get('project_site'))
        requests = get_requests(project_site=st.session_state.get('project_site'))
        notifications = get_notifications(unread_only=True)
        
        # Create metrics columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Items", len(items))
        
        with col2:
            st.metric("Total Requests", len(requests))
        
        with col3:
            st.metric("Unread Notifications", len(notifications))
        
        with col4:
            st.metric("Project Site", st.session_state.get('project_site', 'Unknown'))
        
        # Recent activity
        st.markdown("### Recent Activity")
        if requests:
            st.dataframe(requests[:5], use_container_width=True)
        else:
            st.info("No recent activity")
            
    except Exception as e:
        show_error_message(f"Error loading dashboard: {e}")

def show_inventory():
    """Show inventory management interface"""
    st.markdown("## 📦 Inventory Management")
    
    if not is_admin():
        show_error_message("Admin privileges required for inventory management")
        return
    
    # Inventory operations
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### Inventory Items")
        items = get_inventory_items(project_site=st.session_state.get('project_site'))
        if items:
            st.dataframe(items, use_container_width=True)
        else:
            st.info("No inventory items found")
    
    with col2:
        st.markdown("### Add New Item")
        with st.form("add_item_form"):
            name = st.text_input("Item Name")
            code = st.text_input("Item Code")
            category = st.selectbox("Category", ["materials", "labour"])
            unit = st.text_input("Unit")
            qty = st.number_input("Quantity", min_value=0.0)
            unit_cost = st.number_input("Unit Cost", min_value=0.0)
            budget = st.text_input("Budget")
            section = st.text_input("Section")
            grp = st.text_input("Group")
            building_type = st.text_input("Building Type")
            
            if st.form_submit_button("Add Item"):
                item_data = {
                    'name': name,
                    'code': code,
                    'category': category,
                    'unit': unit,
                    'qty': qty,
                    'unit_cost': unit_cost,
                    'budget': budget,
                    'section': section,
                    'grp': grp,
                    'building_type': building_type,
                    'project_site': st.session_state.get('project_site', 'Lifecamp Kafe')
                }
                
                if add_inventory_item(item_data):
                    show_success_message("Item added successfully!")
                    st.rerun()
                else:
                    show_error_message("Failed to add item")

def show_make_request():
    """Show make request interface"""
    st.markdown("## 📝 Make Request")
    
    # Get available items
    items = get_inventory_items(project_site=st.session_state.get('project_site'))
    
    if not items:
        show_error_message("No items available for request")
        return
    
    # Create request form
    with st.form("make_request_form"):
        st.markdown("### Request Details")
        
        # Item selection
        item_options = {f"{item[1]} ({item[2]})": item[0] for item in items}
        selected_item = st.selectbox("Select Item", list(item_options.keys()))
        item_id = item_options[selected_item]
        
        # Get item details
        selected_item_data = next(item for item in items if item[0] == item_id)
        
        # Request details
        qty = st.number_input("Quantity", min_value=0.1, value=1.0)
        notes = st.text_area("Notes (Optional)")
        
        if st.form_submit_button("Submit Request"):
            request_data = {
                'item_name': selected_item_data[1],
                'qty': qty,
                'requested_by': st.session_state.get('full_name', 'Unknown'),
                'project_site': st.session_state.get('project_site', 'Lifecamp Kafe'),
                'status': 'Pending'
            }
            
            request_id = add_request(request_data)
            if request_id:
                # Add notification
                notification_data = {
                    'user_id': st.session_state.get('user_id'),
                    'title': f"New Request #{request_id}",
                    'message': f"Request for {selected_item_data[1]} submitted",
                    'notification_type': 'request',
                    'project_site': st.session_state.get('project_site', 'Lifecamp Kafe')
                }
                add_notification(notification_data)
                
                # Email notifications removed for better performance
                
                show_success_message(f"Request #{request_id} submitted successfully!")
                st.rerun()
            else:
                show_error_message("Failed to submit request")

def show_my_requests():
    """Show user's requests"""
    st.markdown("## 📋 My Requests")
    
    # Get user's requests
    requests = get_requests(
        project_site=st.session_state.get('project_site'),
        user_name=st.session_state.get('full_name', 'Unknown')
    )
    
    if requests:
        st.dataframe(requests, use_container_width=True)
    else:
        st.info("No requests found")

def show_notifications():
    """Show notifications interface"""
    st.markdown("## 🔔 Notifications")
    
    # Get user's notifications
    notifications = get_notifications(
        user_id=st.session_state.get('user_id'),
        project_site=st.session_state.get('project_site')
    )
    
    if notifications:
        for notification in notifications:
            with st.expander(f"{notification['title']} - {notification['created_at']}"):
                st.write(notification['message'])
                if not notification['is_read']:
                    if st.button(f"Mark as Read", key=f"read_{notification['id']}"):
                        mark_notification_read(notification['id'])
                        st.rerun()
    else:
        st.info("No notifications found")

def show_settings():
    """Show settings interface"""
    st.markdown("## ⚙️ Settings")
    
    if not is_admin():
        show_error_message("Admin privileges required for settings")
        return
    
    # Database health
    st.markdown("### Database Health")
    ok, info = db_health()
    if ok:
        show_success_message(f"Database: {info}")
    else:
        show_error_message(f"Database Error: {info}")
    
    # Project sites
    st.markdown("### Project Sites")
    project_sites = get_project_sites()
    if project_sites:
        st.dataframe(project_sites, use_container_width=True)
    else:
        st.info("No project sites found")

if __name__ == "__main__":
    main()
