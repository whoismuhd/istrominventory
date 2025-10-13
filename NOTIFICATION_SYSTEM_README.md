# Professional Notification System

A scalable, thread-safe notification system for the Streamlit inventory management app that works with both SQLite (local) and PostgreSQL (production).

## Features

- ✅ **Idempotent notifications** - Prevents duplicates with event keys
- ✅ **Pagination & performance** - Optimized queries with proper indexes
- ✅ **Cascade deletion** - User deletion removes all related notifications
- ✅ **Professional UI** - Modern bell icon, dropdown, and styling
- ✅ **Real-time updates** - Auto-refresh and toast notifications
- ✅ **Database agnostic** - Works with SQLite and PostgreSQL
- ✅ **Thread-safe** - SQLAlchemy with proper connection management

## Quick Start

### 1. Run Migration

```bash
python migrate_notifications.py
```

### 2. Import and Use

```python
from notifications import create_notification, get_notifications
from notification_ui import render_notification_sidebar
from notification_integration import integrate_notification_system

# In your main app
integrate_notification_system()

# Create notifications
create_notification(
    sender_id=None,
    receiver_id=user_id,
    message="Your request has been approved!",
    notification_type='request_approved',
    event_key='request:123:approved'
)
```

## API Reference

### Core Functions

#### `create_notification(sender_id, receiver_id, message, notification_type='info', event_key=None)`
Create a notification with idempotency support.

**Parameters:**
- `sender_id` (int, optional): ID of user who triggered the notification
- `receiver_id` (int, optional): ID of user to receive notification (None for all admins)
- `message` (str): Notification message text
- `notification_type` (str): Type of notification (info, success, warning, error, etc.)
- `event_key` (str, optional): Unique key to prevent duplicates

**Returns:** `bool` - True if notification created successfully

#### `get_notifications(user_id, unread_only=False, limit=20, offset=0)`
Get notifications for a user with pagination.

**Parameters:**
- `user_id` (int): ID of user to get notifications for
- `unread_only` (bool): If True, only return unread notifications
- `limit` (int): Maximum number of notifications to return
- `offset` (int): Number of notifications to skip

**Returns:** `List[Dict]` - List of notification dictionaries

#### `mark_notification_as_read(notification_id)`
Mark a specific notification as read.

#### `mark_all_as_read(user_id)`
Mark all notifications as read for a user.

#### `delete_notification(notification_id)`
Delete a specific notification.

#### `delete_all_notifications(user_id=None)`
Delete all notifications for a user (admin only if user_id is None).

### UI Components

#### `render_notification_sidebar(user_id)`
Render a compact notification sidebar for quick access.

#### `render_notification_panel(user_id)`
Render the main notification panel with modern styling.

#### `render_notification_header(user_id)`
Render the notification header with bell icon and unread badge.

## Database Schema

The notification system uses the following table structure:

```sql
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    sender_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    receiver_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    type TEXT CHECK(type IN ('info','success','warning','error','new_request','request_approved','request_rejected')) DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    event_key TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX idx_notifications_receiver_read_created ON notifications(receiver_id, is_read, created_at DESC);
CREATE INDEX idx_notifications_sender_created ON notifications(sender_id, created_at DESC);
CREATE INDEX idx_notifications_event_key ON notifications(event_key) WHERE event_key IS NOT NULL;
```

## Integration Examples

### Request Submission Notification

```python
def submit_request(request_data):
    # Your existing submission logic
    request_id = save_request(request_data)
    
    # Notify admins
    create_notification(
        sender_id=None,
        receiver_id=None,  # All admins
        message=f"{request_data['requester']} submitted a request for {request_data['item']}",
        notification_type='new_request',
        event_key=f'request:{request_id}:submitted'
    )
    
    return request_id
```

### Request Approval Notification

```python
def approve_request(request_id, requester_id):
    # Your existing approval logic
    approve_request_in_db(request_id)
    
    # Notify user
    create_notification(
        sender_id=None,  # Admin approval
        receiver_id=requester_id,
        message="Your request has been approved!",
        notification_type='request_approved',
        event_key=f'request:{request_id}:approved'
    )
```

### User Creation Notification

```python
def create_user(user_data):
    # Your existing user creation logic
    user_id = save_user(user_data)
    
    # Notify admins
    create_notification(
        sender_id=None,
        receiver_id=None,  # All admins
        message=f"New user created: {user_data['name']} for {user_data['project']}",
        notification_type='info',
        event_key=f'user_created:{user_data["name"]}:{user_data["project"]}'
    )
    
    return user_id
```

## UI Integration

### Add to Main App

```python
# In your main app file
from notification_integration import integrate_notification_system

# After authentication
if st.session_state.get('logged_in'):
    integrate_notification_system()
```

### Add to Sidebar

```python
# In your sidebar
from notification_ui import render_notification_sidebar

render_notification_sidebar(st.session_state['user_id'])
```

### Add to Admin Panel

```python
# In your admin panel
from notification_integration import render_admin_notification_management

render_admin_notification_management()
```

## Notification Types

The system supports the following notification types with icons and colors:

- `info` - ℹ️ Blue - General information
- `success` - ✅ Green - Success messages
- `warning` - ⚠️ Yellow - Warning messages
- `error` - ❌ Red - Error messages
- `new_request` - 📝 Purple - New request submitted
- `request_approved` - ✅ Green - Request approved
- `request_rejected` - ❌ Red - Request rejected

## Performance Considerations

- **Pagination**: All queries use LIMIT/OFFSET for performance
- **Indexes**: Optimized indexes for common query patterns
- **Caching**: SQLAlchemy connection pooling
- **Idempotency**: Event keys prevent duplicate notifications
- **Cascade deletion**: Automatic cleanup when users are deleted

## Migration Guide

### From Old System

1. **Run migration script**:
   ```bash
   python migrate_notifications.py
   ```

2. **Update imports**:
   ```python
   # Old
   from istrominventory import create_notification
   
   # New
   from notifications import create_notification
   ```

3. **Update function calls**:
   ```python
   # Old
   create_notification('new_request', 'Title', 'Message', user_id)
   
   # New
   create_notification(sender_id=None, receiver_id=user_id, message='Message', notification_type='new_request')
   ```

### Database Migration

The migration script will:
- Add new columns (`sender_id`, `receiver_id`, `type`, `event_key`)
- Migrate existing data
- Add foreign key constraints
- Create performance indexes
- Preserve existing notifications

## Troubleshooting

### Common Issues

1. **"relation notifications does not exist"**
   - Run the migration script: `python migrate_notifications.py`

2. **"duplicate key value violates unique constraint"**
   - Use event keys to prevent duplicates: `event_key='request:123:submitted'`

3. **"current transaction is aborted"**
   - The system uses autocommit transactions to prevent this

4. **Notifications not showing**
   - Check user_id in session state
   - Verify database connection
   - Check notification filters

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Considerations

- **User isolation**: Users only see their own notifications
- **Admin access**: Admins can see all notifications
- **Cascade deletion**: Deleting a user removes all their notifications
- **Event keys**: Prevent duplicate notifications
- **Input validation**: All inputs are sanitized

## Future Enhancements

- [ ] Email notifications
- [ ] Push notifications
- [ ] Notification templates
- [ ] Bulk operations
- [ ] Notification analytics
- [ ] Real-time WebSocket updates

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review the API documentation
3. Check database logs
4. Verify user permissions

## License

This notification system is part of the Streamlit inventory management app and follows the same license terms.
