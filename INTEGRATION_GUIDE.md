# Notification System Integration Guide

This guide shows how to integrate the new professional notification system into your existing Streamlit inventory management app.

## Step 1: Run Migration

First, migrate your existing notification data to the new schema:

```bash
python migrate_notifications.py
```

## Step 2: Update Imports

Replace the old notification imports in your main app:

```python
# OLD - Remove these imports
# from istrominventory import create_notification, get_admin_notifications, etc.

# NEW - Add these imports
from notifications import (
    create_notification, get_notifications, get_unread_count,
    mark_notification_as_read, mark_all_as_read, delete_notification,
    delete_all_notifications, show_notification_toast
)
from notification_ui import (
    render_notification_sidebar, render_notification_panel,
    render_notification_header, setup_notification_auto_refresh
)
from notification_integration import (
    integrate_notification_system, notify_new_request,
    notify_request_approved, notify_request_rejected
)
```

## Step 3: Replace Old Notification Functions

### Replace `create_notification` calls:

```python
# OLD
create_notification('new_request', 'Title', 'Message', user_id)

# NEW
create_notification(
    sender_id=None,
    receiver_id=user_id,
    message='Message',
    notification_type='new_request',
    event_key=f'request:{request_id}:submitted'
)
```

### Replace notification retrieval:

```python
# OLD
notifications = get_admin_notifications()

# NEW
notifications = get_notifications(user_id=None, limit=20)  # For admins
# OR
notifications = get_notifications(user_id=current_user_id, limit=20)  # For users
```

## Step 4: Add UI Components

### Add to main app after authentication:

```python
# In your main app file, after st.session_state['logged_in'] = True
if st.session_state.get('logged_in'):
    integrate_notification_system()
```

### Add to sidebar:

```python
# In your sidebar section
if st.session_state.get('user_type') == 'admin':
    render_notification_sidebar(None)  # Admin sees all notifications
else:
    render_notification_sidebar(st.session_state['user_id'])  # User sees their notifications
```

## Step 5: Update Request Submission

Replace your existing request submission notification:

```python
# OLD
def submit_request(request_data):
    # ... existing logic ...
    create_notification('new_request', 'New Request', f"{requester} submitted a request", None)

# NEW
def submit_request(request_data):
    # ... existing logic ...
    notify_new_request(
        request_id=request_data['id'],
        requester_name=request_data['requester'],
        item_name=request_data['item'],
        quantity=request_data['quantity']
    )
```

## Step 6: Update Request Approval/Rejection

Replace your existing approval/rejection notifications:

```python
# OLD
def approve_request(request_id, requester_id):
    # ... existing logic ...
    create_notification('request_approved', 'Request Approved', 'Your request was approved', requester_id)

# NEW
def approve_request(request_id, requester_id):
    # ... existing logic ...
    notify_request_approved(
        request_id=request_id,
        requester_id=requester_id,
        requester_name=get_user_name(requester_id),
        item_name=get_item_name(request_id)
    )
```

## Step 7: Update Admin Panel

Replace your existing admin notification display:

```python
# OLD
with st.expander("Notifications"):
    notifications = get_admin_notifications()
    for notification in notifications:
        st.write(notification['message'])

# NEW
from notification_integration import render_admin_notification_management
render_admin_notification_management()
```

## Step 8: Update User Notification Display

Replace your existing user notification display:

```python
# OLD
def show_user_notifications():
    notifications = get_user_notifications()
    for notification in notifications:
        st.write(notification['message'])

# NEW
def show_user_notifications():
    render_notification_panel(st.session_state['user_id'])
```

## Step 9: Add Auto-refresh

Add auto-refresh for notifications:

```python
# In your main app
setup_notification_auto_refresh(st.session_state['user_id'])
```

## Step 10: Test the Integration

Run the test script to verify everything works:

```bash
python test_notifications.py
```

## Complete Integration Example

Here's a complete example of how to integrate the notification system:

```python
import streamlit as st
from notifications import create_notification, get_notifications
from notification_ui import render_notification_sidebar
from notification_integration import integrate_notification_system

def main():
    st.set_page_config(page_title="Inventory Management", layout="wide")
    
    # Authentication (your existing logic)
    if not st.session_state.get('logged_in'):
        # Your login form
        pass
    else:
        # Add notification system
        integrate_notification_system()
        
        # Your existing app content
        st.title("Inventory Management System")
        
        # Add notification sidebar
        with st.sidebar:
            render_notification_sidebar(st.session_state['user_id'])
        
        # Your existing tabs and content
        # ...

if __name__ == "__main__":
    main()
```

## Migration Checklist

- [ ] Run migration script
- [ ] Update imports
- [ ] Replace old notification functions
- [ ] Add UI components
- [ ] Update request submission
- [ ] Update request approval/rejection
- [ ] Update admin panel
- [ ] Update user notification display
- [ ] Add auto-refresh
- [ ] Test integration

## Troubleshooting

### Common Issues:

1. **"module not found"** - Make sure all new files are in the same directory
2. **"table doesn't exist"** - Run the migration script
3. **"permission denied"** - Check database permissions
4. **"notifications not showing"** - Check user_id in session state

### Debug Steps:

1. Check database connection: `python test_notifications.py`
2. Verify migration: `python migrate_notifications.py`
3. Check logs for errors
4. Verify user authentication
5. Check notification filters

## Performance Tips

1. **Use pagination** - Don't load all notifications at once
2. **Use event keys** - Prevent duplicate notifications
3. **Use indexes** - The migration creates performance indexes
4. **Cache results** - Use Streamlit caching for expensive operations
5. **Limit queries** - Use LIMIT in all queries

## Security Considerations

1. **User isolation** - Users only see their own notifications
2. **Admin access** - Admins can see all notifications
3. **Input validation** - All inputs are sanitized
4. **Cascade deletion** - Deleting a user removes their notifications
5. **Event keys** - Prevent duplicate notifications

## Next Steps

After integration:

1. Test all notification flows
2. Verify user isolation
3. Check admin functionality
4. Test performance
5. Monitor logs
6. Gather user feedback

## Support

If you encounter issues:

1. Check the troubleshooting section
2. Review the API documentation
3. Check database logs
4. Verify user permissions
5. Test with the test script

The new notification system is designed to be a drop-in replacement for your existing system while providing better performance, security, and user experience.
